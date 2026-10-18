"""Terminal version of the assistant.

Run:  python cli.py                      (interactive)
      python cli.py "Your question"      (one question)
"""

import sys

from finance_assistant.env import load_env

load_env()

from finance_assistant.assistant import FinanceAssistant  # noqa: E402


def show(answer) -> None:
    print(f"\n{answer.text}\n")
    tools = ", ".join(call["tool"] for call in answer.tool_calls) or "none"
    print(f"[tools used: {tools} | cost: ${answer.cost_usd:.3f}]\n")


def main() -> None:
    assistant = FinanceAssistant()
    if len(sys.argv) > 1:
        show(assistant.ask(" ".join(sys.argv[1:])))
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
