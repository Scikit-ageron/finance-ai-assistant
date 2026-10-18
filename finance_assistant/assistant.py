"""The AI part: Claude answers finance questions by calling the analysis functions.

How it works (a "tool use" loop):
1. We send the question plus a list of tools (our pandas functions) to Claude.
2. Claude decides which tool it needs and asks us to run it.
3. We run the function locally and send the result back.
4. Repeat until Claude has enough data and writes the final answer.

The data never leaves your computer in full: Claude only sees the small
tables that the tools return.
"""

import json
import os
from dataclasses import dataclass, field

import anthropic
import pandas as pd

from finance_assistant import analysis

DEFAULT_MODEL = "claude-opus-5"
DEFAULT_EFFORT = "medium"  # low | medium | high
MAX_TOOL_ROUNDS = 8

# USD per million tokens (input, output), to show the cost of each question.
PRICES = {"claude-opus-5": (5.00, 25.00), "claude-sonnet-5": (2.00, 10.00), "claude-haiku-4-5": (1.00, 5.00)}

SYSTEM_PROMPT = """You are a financial planning and analysis (FP&A) assistant. You answer questions \
about the budget vs. actual figures in the loaded dataset (the demo dataset is Northwind Bikes, \
a fictitious company).

Rules:
- Get every number from the tools. Never estimate or invent figures.
- Call list_dimensions first if you are not sure about the exact month, department or account names.
- Months without actuals are open. Variance tools only use closed months; say which months a figure covers.
- Variance = actual - budget. Use the "favourable" field to say if a variance is good or bad.
- For full-year questions use full_year_forecast and say which method you used. "run_rate" also \
extrapolates one-off deviations, so point those out.
- Lead with the answer, then the key figures, then the likely driver if the data shows one.
- Keep it short and clear, for a finance manager. Use euros, with thousands separators.
- Answer in the same language as the question."""

NULLABLE_STR = {"type": ["string", "null"]}
MONTH = {"type": ["string", "null"], "description": "Month as YYYY-MM, or null for no limit."}

# Tool definitions: name, description and a JSON schema for the inputs.
# strict=True makes Claude's tool inputs always match the schema.
TOOLS = [
    {
        "name": "list_dimensions",
        "description": "List the available months, departments and accounts in the dataset.",
        "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        "strict": True,
    },
    {
        "name": "variance_summary",
        "description": "Budget, actual and variance grouped by month, department and/or account, with optional filters.",
        "input_schema": {
            "type": "object",
            "properties": {
                "group_by": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["month", "department", "account"]},
                    "description": "Columns to group by, e.g. [\"department\"] or [\"month\", \"account\"].",
                },
                "month_from": MONTH,
                "month_to": MONTH,
                "department": NULLABLE_STR,
                "account": NULLABLE_STR,
            },
            "required": ["group_by", "month_from", "month_to", "department", "account"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "top_deviations",
        "description": "The individual lines (month x department x account) with the largest variances in euros.",
        "input_schema": {
            "type": "object",
            "properties": {
                "n": {"type": "integer", "description": "How many lines to return (1-20)."},
                "month_from": MONTH,
                "month_to": MONTH,
                "department": NULLABLE_STR,
                "only_unfavourable": {"type": "boolean", "description": "True to return only bad variances."},
            },
            "required": ["n", "month_from", "month_to", "department", "only_unfavourable"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "monthly_trend",
        "description": "Budget vs. actual month by month, optionally for one department and/or account.",
        "input_schema": {
            "type": "object",
            "properties": {"department": NULLABLE_STR, "account": NULLABLE_STR},
            "required": ["department", "account"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "full_year_forecast",
        "description": (
            "Full-year landing: actual to date plus a forecast for the open months, vs. the full-year budget. "
            "method 'budget' assumes open months hit budget; 'run_rate' keeps each line's year-to-date "
            "actual/budget ratio."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "group_by": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["department", "account"]},
                    "description": "Columns to group by, or [] for totals by income/expense.",
                },
                "method": {"type": "string", "enum": ["run_rate", "budget"]},
                "as_of": {
                    "type": ["string", "null"],
                    "description": "Last closed month as YYYY-MM, or null for the latest month with actuals.",
                },
            },
            "required": ["group_by", "method", "as_of"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "pl_summary",
        "description": "Total revenue, expenses and operating result (budget vs. actual) for a period.",
        "input_schema": {
            "type": "object",
            "properties": {"month_from": MONTH, "month_to": MONTH},
            "required": ["month_from", "month_to"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


COMMENTARY_PROMPT = """Write the monthly variance commentary for {month} for the management report.
Get the figures with the tools: the month, the year to date up to {month}, the biggest deviations \
and the full-year landing (run_rate method, as of {month}).

Format it in Markdown, under 300 words, with these sections:
### Headline
One sentence: how the month went and what matters most.
### {month}
Operating result vs. budget and the three main drivers, with figures.
### Year to date
Where we stand, and whether the month's issues are one-offs or a trend.
### Full-year outlook
Expected landing vs. budget, the main risks, and one-off effects the run rate may overstate.

Write it in {language}, for a finance director. Do not ask questions; write the commentary."""


@dataclass
class Answer:
    text: str
    model: str = DEFAULT_MODEL
    tool_calls: list = field(default_factory=list)  # what the AI looked at, for transparency
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def cost_usd(self) -> float:
        price_in, price_out = PRICES.get(self.model, PRICES[DEFAULT_MODEL])
        return (self.input_tokens * price_in + self.output_tokens * price_out) / 1_000_000


def run_tool(df: pd.DataFrame, name: str, args: dict):
    """Map a tool name to the matching pandas function (like a switch in C)."""
    if name == "list_dimensions":
        return analysis.list_dimensions(df)
    if name == "variance_summary":
        return analysis.variance_summary(df, **args)  # ** unpacks the dict into named arguments
    if name == "top_deviations":
        args["n"] = max(1, min(int(args["n"]), 20))
        return analysis.top_deviations(df, **args)
    if name == "monthly_trend":
        return analysis.monthly_trend(df, **args)
    if name == "pl_summary":
        return analysis.pl_summary(df, **args)
    if name == "full_year_forecast":
        return analysis.full_year_forecast(df, **args)
    raise ValueError(f"Unknown tool: {name}")


class FinanceAssistant:
    def __init__(self, df: pd.DataFrame | None = None, client: anthropic.Anthropic | None = None):
        self.df = df if df is not None else analysis.load_data()
        self.client = client or anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
        self.history: list[dict] = []  # the conversation, so follow-up questions work
        # Settings come from the environment (or .env), so you can switch model without editing code.
        self.model = os.environ.get("FINANCE_ASSISTANT_MODEL", DEFAULT_MODEL)
        self.effort = os.environ.get("FINANCE_ASSISTANT_EFFORT", DEFAULT_EFFORT)

    def ask(self, question: str) -> Answer:
        """Chat: the question joins the conversation, so follow-ups work."""
        self.history.append({"role": "user", "content": question})
        return self._run(self.history)

    def monthly_commentary(self, month: str, language: str = "English") -> Answer:
        """A one-off report in its own conversation, so it does not mix with the chat."""
        prompt = COMMENTARY_PROMPT.format(month=month, language=language)
        return self._run([{"role": "user", "content": prompt}])

    def _run(self, history: list[dict]) -> Answer:
        """The tool-use loop. Appends every turn to `history`."""
        answer = Answer(text="", model=self.model)

        for _ in range(MAX_TOOL_ROUNDS):
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=history,
                thinking={"type": "adaptive"},
                output_config={"effort": self.effort},
                cache_control={"type": "ephemeral"},  # reuse the prompt between rounds -> cheaper
                # If the model declines a request, the API retries it on a fallback model.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
            answer.input_tokens += response.usage.input_tokens
            answer.output_tokens += response.usage.output_tokens
            # Keep the full content (thinking + tool calls), not only the text.
            history.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "refusal":
                answer.text = "The model declined to answer this question."
                return answer
            if response.stop_reason == "max_tokens":
                answer.text = "The answer was too long and got cut. Try a more specific question."
                return answer
            if response.stop_reason != "tool_use":
                answer.text = "\n".join(b.text for b in response.content if b.type == "text").strip()
                return answer

            # Claude asked for one or more tools: run them all, send all results in ONE message.
            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                args = dict(block.input)
                answer.tool_calls.append({"tool": block.name, "input": dict(args)})
                try:
                    output = run_tool(self.df, block.name, args)
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(output, default=str),
                    })
                except Exception as exc:  # report the error to Claude instead of crashing
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": f"Error: {exc}",
                        "is_error": True,
                    })
            history.append({"role": "user", "content": results})

        answer.text = "I could not finish the analysis in a reasonable number of steps. Try a narrower question."
        return answer
