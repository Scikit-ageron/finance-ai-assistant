"""Terminal version of the assistant.

Run:  python cli.py                                  (interactive)
      python cli.py "Your question"                  (one question)
      python cli.py --commentary 2026-08             (monthly variance commentary)
      python cli.py --data my_export.xlsx "..."      (your own data, CSV or Excel)
"""

import argparse

from finance_assistant.env import load_env

load_env()

from finance_assistant import analysis  # noqa: E402
from finance_assistant.assistant import FinanceAssistant  # noqa: E402


def show(answer) -> None:
    print(f"\n{answer.text}\n")
    tools = ", ".join(call["tool"] for call in answer.tool_calls) or "none"
    print(f"[tools used: {tools} | cost: ${answer.cost_usd:.3f}]\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask questions about budget vs. actual.")
    parser.add_argument("question", nargs="*", help="a question; leave empty for interactive mode")
    parser.add_argument("--data", help="CSV or Excel export to use instead of the demo data")
    parser.add_argument("--commentary", metavar="YYYY-MM", help="write the variance commentary for a month")
    parser.add_argument("--language", default="English", help="language of the commentary")
    args = parser.parse_args()

    try:
        df = analysis.load_data(args.data) if args.data else analysis.load_data()
    except analysis.DataError as exc:
        parser.exit(1, f"Cannot use {args.data}: {exc}\n")
    assistant = FinanceAssistant(df)

    if args.commentary:
        show(assistant.monthly_commentary(args.commentary, args.language))
        return
    if args.question:
        show(assistant.ask(" ".join(args.question)))
        return
    print("Finance AI Assistant - type a question, or 'exit' to quit.")
    while True:
        question = input("> ").strip()
        if question.lower() in {"exit", "quit", "salir"}:
            break
        if question:
            show(assistant.ask(question))


if __name__ == "__main__":
    main()
