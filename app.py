"""Web demo: budget vs. actual dashboard + AI assistant chat.

Run:  streamlit run app.py
"""

import os

import pandas as pd
import streamlit as st

from finance_assistant.env import load_env

load_env()  # read .env before creating the assistant

from finance_assistant import analysis  # noqa: E402
from finance_assistant.assistant import FinanceAssistant  # noqa: E402

EXAMPLES = [
    "Which departments are over budget this year?",
    "Why did the operating result miss the budget in August?",
    "What happened with IT software licenses?",
    "Show me the 5 worst deviations in Q4.",
    "¿Cómo va marketing frente al presupuesto?",
]

st.set_page_config(page_title="Finance AI Assistant", page_icon="📊", layout="wide")
st.title("Finance AI Assistant")
st.caption(
    "Ask questions about budget vs. actual in plain language. "
    "Northwind Bikes is a fictitious company; all figures are invented."
)

df = analysis.load_data()

# --- Dashboard -----------------------------------------------------------
def vs_budget(value: float) -> str:
    # Sign first ("-€5", not "€-5"), so Streamlit picks the right arrow and colour.
    return f"{'-' if value < 0 else '+'}€{abs(value):,.0f} vs budget"


pl = analysis.pl_summary(df)
col1, col2, col3 = st.columns(3)
col1.metric("Revenue (actual)", f"€{pl['actual']['revenue']:,.0f}",
            vs_budget(pl['actual']['revenue'] - pl['budget']['revenue']))
col2.metric("Expenses (actual)", f"€{pl['actual']['expenses']:,.0f}",
            vs_budget(pl['actual']['expenses'] - pl['budget']['expenses']), delta_color="inverse")
col3.metric("Operating result", f"€{pl['actual']['operating_result']:,.0f}",
            vs_budget(pl['operating_result_variance']))

with st.expander("Budget vs. actual by department"):
    table = pd.DataFrame(analysis.variance_summary(df, ["department"]))
    st.dataframe(table, hide_index=True, width="stretch")

trend = pd.DataFrame(analysis.monthly_trend(df))
trend = trend[trend["type"] == "expense"].set_index("month")[["budget", "actual"]]
st.subheader("Monthly expenses: budget vs. actual")
st.line_chart(trend)

# --- Chat ------------------------------------------------------------------
st.subheader("Ask the assistant")

if not os.environ.get("ANTHROPIC_API_KEY"):
    st.warning("Add your ANTHROPIC_API_KEY to a .env file (see README) to use the assistant.")
    st.stop()

# st.session_state keeps values between reruns (Streamlit reruns the script on every click).
if "assistant" not in st.session_state:
    st.session_state.assistant = FinanceAssistant(df)
    st.session_state.messages = []
    st.session_state.total_cost = 0.0

with st.sidebar:
    st.markdown("**Try one of these:**")
    for example in EXAMPLES:
        if st.button(example, width="stretch"):
            st.session_state.pending = example
    st.divider()
    st.markdown(f"Model: `{st.session_state.assistant.model}`")
    cost_box = st.empty()  # filled at the end, after this run's question is answered
    if st.button("New conversation"):
        for key in ("assistant", "messages", "total_cost"):
            st.session_state.pop(key, None)
        st.rerun()

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("tools"):
            with st.expander("Data the assistant used"):
                st.json(message["tools"])

question = st.chat_input("Ask about the budget...") or st.session_state.pop("pending", None)
if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        with st.spinner("Analysing the data..."):
            answer = st.session_state.assistant.ask(question)
        st.markdown(answer.text)
        st.caption(f"{len(answer.tool_calls)} data queries · ${answer.cost_usd:.3f}")
        if answer.tool_calls:
            with st.expander("Data the assistant used"):
                st.json(answer.tool_calls)
    st.session_state.total_cost += answer.cost_usd
    st.session_state.messages.append({"role": "assistant", "content": answer.text, "tools": answer.tool_calls})

cost_box.markdown(f"Cost this session: **${st.session_state.total_cost:.3f}**")
