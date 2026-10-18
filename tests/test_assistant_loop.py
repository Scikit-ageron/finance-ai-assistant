"""Test the tool-use loop with a fake client, so no API key or money is needed."""

from types import SimpleNamespace as NS

from finance_assistant import analysis
from finance_assistant.assistant import FinanceAssistant


class FakeMessages:
    """Returns pre-written responses: first a tool call, then a final answer."""

    def __init__(self):
        self.calls = []
        self.responses = [
            NS(stop_reason="tool_use", usage=NS(input_tokens=1000, output_tokens=100), content=[
                NS(type="tool_use", id="t1", name="pl_summary", input={"month_from": "2026-08", "month_to": "2026-08"}),
            ]),
            NS(stop_reason="end_turn", usage=NS(input_tokens=1200, output_tokens=200), content=[
                NS(type="text", text="August missed the budget."),
            ]),
        ]

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def test_loop_runs_tool_and_returns_answer():
    messages = FakeMessages()
    client = NS(beta=NS(messages=messages))
    assistant = FinanceAssistant(analysis.load_data(), client=client)

    answer = assistant.ask("How did August go?")

    assert answer.text == "August missed the budget."
    assert answer.tool_calls == [{"tool": "pl_summary", "input": {"month_from": "2026-08", "month_to": "2026-08"}}]
    assert (answer.input_tokens, answer.output_tokens) == (2200, 300)
    # History: question, tool call, tool result, final answer. The tool result goes back to the model.
    history = assistant.history
    assert [m["role"] for m in history] == ["user", "assistant", "user", "assistant"]
    tool_result = history[2]["content"][0]
    assert tool_result["type"] == "tool_result" and tool_result["tool_use_id"] == "t1"
    assert "operating_result" in tool_result["content"]


def test_refusal_is_handled():
    messages = FakeMessages()
    messages.responses = [NS(stop_reason="refusal", usage=NS(input_tokens=10, output_tokens=0), content=[])]
    assistant = FinanceAssistant(analysis.load_data(), client=NS(beta=NS(messages=messages)))
    assert "declined" in assistant.ask("anything").text
