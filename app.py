"""Web demo: budget vs. actual dashboard, full-year forecast, AI chat and monthly commentary.

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
    "Where will we land at year end?",
    "Show me the 5 worst deviations in Q3.",
    "¿Cómo va marketing frente al presupuesto?",
]
LANGUAGES = ["English", "Spanish", "French", "German"]

st.set_page_config(page_title="Finance AI Assistant", page_icon="📊", layout="wide")
st.title("Finance AI Assistant")
st.caption("Ask questions about budget vs. actual in plain language, see where the year will land, "
           "and get the monthly variance commentary written for you.")


def money(value: float) -> str:
    return f"€{value:,.0f}"


def vs_budget(value: float) -> str:
    # Sign first ("-€5", not "€-5"), so Streamlit picks the right arrow and colour.
    return f"{'-' if value < 0 else '+'}€{abs(value):,.0f} vs budget"


# --- Data ------------------------------------------------------------------
with st.sidebar:
    st.markdown("**Your data**")
    upload = st.file_uploader("Load a budget vs. actual export", type=["csv", "xlsx", "xls"])
    st.caption("Columns: month, department, account, type (income/expense), budget, actual. "
               "Leave actual empty for months not closed yet. Common names like *period*, "
               "*cost center* or *plan* are recognised.")
    st.download_button("Download a template", analysis.DATA_FILE.read_bytes(),
                       "budget_vs_actual_template.csv", "text/csv", width="stretch")

df, source, data_id = analysis.load_data(), "Demo data · Northwind Bikes (fictitious)", "demo"
if upload is not None:
    try:
        df, source, data_id = analysis.load_data(upload), f"Your file · {upload.name}", upload.file_id
    except analysis.DataError as exc:
        st.sidebar.error(f"{exc} Showing the demo data instead.")

# New data -> new assistant: the old conversation was about other figures.
if st.session_state.get("data_id") != data_id:
    for key in ("assistant", "messages", "total_cost", "commentary"):
        st.session_state.pop(key, None)
    st.session_state.data_id = data_id

last = analysis.last_closed_month(df)
if last is None:
    st.warning("This file has budget but no actuals yet, so there is nothing to compare.")
    st.stop()
year_start = f"{last[:4]}-01"

# --- Dashboard -------------------------------------------------------------
st.caption(f"{source} · actuals through **{last}**")
pl = analysis.pl_summary(df, year_start, last)
forecast = analysis.full_year_forecast(df)
col1, col2, col3, col4 = st.columns(4)
col1.metric("Revenue YTD", money(pl["actual"]["revenue"]),
            vs_budget(pl["actual"]["revenue"] - pl["budget"]["revenue"]))
col2.metric("Expenses YTD", money(pl["actual"]["expenses"]),
            vs_budget(pl["actual"]["expenses"] - pl["budget"]["expenses"]), delta_color="inverse")
col3.metric("Operating result YTD", money(pl["actual"]["operating_result"]),
            vs_budget(pl["operating_result_variance"]))
col4.metric("Full-year landing", money(forecast["operating_result"]["landing"]),
            vs_budget(forecast["operating_result"]["variance"]),
            help="Operating result: actuals to date plus the open months at the year-to-date run rate.")

with st.expander("Year to date by department"):
    st.dataframe(pd.DataFrame(analysis.variance_summary(df, ["department"], year_start, last)),
                 hide_index=True, width="stretch")

with st.expander(f"Full-year forecast ({forecast['months_closed']} months actual + "
                 f"{forecast['months_open']} forecast)"):
    method = st.radio("Method for the open months", ["run_rate", "budget"], horizontal=True,
                      format_func={"run_rate": "Year-to-date run rate", "budget": "Remaining budget"}.get)
    table = pd.DataFrame(analysis.full_year_forecast(df, ["department"], method)["lines"])
    st.dataframe(table[["department", "type", "budget", "actual_ytd", "forecast_rest", "landing",
                        "variance", "variance_pct", "favourable"]], hide_index=True, width="stretch")

trend = pd.DataFrame(analysis.monthly_trend(df))
trend = trend[trend["type"] == "expense"].set_index("month")[["budget", "actual"]]
st.subheader("Monthly expenses: budget vs. actual")
st.line_chart(trend)

# --- Assistant -------------------------------------------------------------
if not os.environ.get("ANTHROPIC_API_KEY"):
    st.warning("Add your ANTHROPIC_API_KEY to a .env file (see README) to use the assistant.")
    st.stop()

# st.session_state keeps values between reruns (Streamlit reruns the script on every click).
if "assistant" not in st.session_state:
    st.session_state.assistant = FinanceAssistant(df)
    st.session_state.messages = []
    st.session_state.total_cost = 0.0
assistant = st.session_state.assistant

with st.sidebar:
    st.divider()
    st.markdown("**Try one of these:**")
    for example in EXAMPLES:
        if st.button(example, width="stretch"):
            st.session_state.pending = example
    st.divider()
    st.markdown(f"Model: `{assistant.model}`")
    cost_box = st.empty()  # filled at the end, after this run's question is answered
    if st.button("New conversation"):
        for key in ("assistant", "messages", "total_cost", "commentary"):
            st.session_state.pop(key, None)
        st.rerun()

chat_tab, commentary_tab = st.tabs(["Ask the assistant", "Monthly commentary"])

with chat_tab:
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
                answer = assistant.ask(question)
            st.markdown(answer.text)
            st.caption(f"{len(answer.tool_calls)} data queries · ${answer.cost_usd:.3f}")
            if answer.tool_calls:
                with st.expander("Data the assistant used"):
                    st.json(answer.tool_calls)
        st.session_state.total_cost += answer.cost_usd
        st.session_state.messages.append({"role": "assistant", "content": answer.text, "tools": answer.tool_calls})

with commentary_tab:
    st.markdown("The variance commentary for the management report: the month, year to date "
                "and full-year outlook, with every figure taken from the data.")
    closed = [m for m in analysis.list_dimensions(df)["months"] if m <= last]
    left, right = st.columns(2)
    month = left.selectbox("Month", closed[::-1])  # latest first
    language = right.selectbox("Language", LANGUAGES)
    if st.button("Write commentary", type="primary"):
        with st.spinner(f"Analysing {month} and writing the commentary..."):
            answer = assistant.monthly_commentary(month, language)
        st.session_state.commentary = {"month": month, "text": answer.text, "tools": answer.tool_calls,
                                       "cost": answer.cost_usd}
        st.session_state.total_cost += answer.cost_usd

    commentary = st.session_state.get("commentary")
    if commentary:
        with st.container(border=True):
            st.markdown(commentary["text"])
        st.caption(f"{len(commentary['tools'])} data queries · ${commentary['cost']:.3f}")
        st.download_button("Download as Markdown", commentary["text"],
                           f"variance-commentary-{commentary['month']}.md", "text/markdown")
        with st.expander("Data the assistant used"):
            st.json(commentary["tools"])

cost_box.markdown(f"Cost this session: **${st.session_state.total_cost:.3f}**")
