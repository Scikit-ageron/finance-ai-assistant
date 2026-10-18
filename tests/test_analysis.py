"""Tests for the pandas analysis. They run without an API key.

Run:  pytest
"""

import io

import pandas as pd
import pytest

from finance_assistant import analysis
from finance_assistant.assistant import TOOLS, run_tool


@pytest.fixture
def df():
    return pd.DataFrame([
        {"month": "2026-01", "department": "Sales", "account": "Revenue", "type": "income", "budget": 100.0, "actual": 120.0},
        {"month": "2026-01", "department": "IT", "account": "Software", "type": "expense", "budget": 50.0, "actual": 70.0},
        {"month": "2026-02", "department": "Sales", "account": "Revenue", "type": "income", "budget": 100.0, "actual": 90.0},
        {"month": "2026-02", "department": "IT", "account": "Software", "type": "expense", "budget": 50.0, "actual": 40.0},
        # March is open: budget, no actual yet. Variances must ignore it.
        {"month": "2026-03", "department": "Sales", "account": "Revenue", "type": "income", "budget": 100.0, "actual": None},
        {"month": "2026-03", "department": "IT", "account": "Software", "type": "expense", "budget": 50.0, "actual": None},
    ])


def test_variance_sign_rules(df):
    rows = analysis.variance_summary(df, ["month", "department"])
    by_key = {(r["month"], r["department"]): r for r in rows}
    assert by_key[("2026-01", "Sales")]["variance"] == 20.0
    assert by_key[("2026-01", "Sales")]["favourable"]           # more income = good
    assert not by_key[("2026-01", "IT")]["favourable"]          # more expense = bad
    assert not by_key[("2026-02", "Sales")]["favourable"]       # less income = bad
    assert by_key[("2026-02", "IT")]["favourable"]              # less expense = good


def test_filters(df):
    rows = analysis.variance_summary(df, ["department"], month_from="2026-02", department="IT")
    assert len(rows) == 1
    assert rows[0]["actual"] == 40.0


def test_top_deviations_unfavourable(df):
    rows = analysis.top_deviations(df, n=5, only_unfavourable=True)
    assert [(r["month"], r["department"]) for r in rows] == [("2026-01", "IT"), ("2026-02", "Sales")]


def test_pl_summary(df):
    pl = analysis.pl_summary(df)
    assert pl["budget"]["operating_result"] == 100.0   # 200 - 100
    assert pl["actual"]["operating_result"] == 100.0   # 210 - 110
    assert pl["operating_result_variance"] == 0.0


def test_empty_filter_returns_empty_list(df):
    assert analysis.variance_summary(df, ["department"], department="Nobody") == []


def test_every_tool_is_wired(df):
    sample_inputs = {
        "list_dimensions": {},
        "variance_summary": {"group_by": ["department"], "month_from": None, "month_to": None, "department": None, "account": None},
        "top_deviations": {"n": 3, "month_from": None, "month_to": None, "department": None, "only_unfavourable": False},
        "monthly_trend": {"department": None, "account": None},
        "pl_summary": {"month_from": None, "month_to": None},
        "full_year_forecast": {"group_by": ["department"], "method": "run_rate", "as_of": None},
    }
    assert {t["name"] for t in TOOLS} == set(sample_inputs)
    for name, args in sample_inputs.items():
        run_tool(df, name, dict(args))  # must not raise


def test_planted_deviations_in_real_dataset():
    real = analysis.load_data()
    top = analysis.top_deviations(real, n=3, month_from="2026-08", month_to="2026-08")
    assert top[0]["account"] == "Revenue" and not top[0]["favourable"]


# --- Open months -------------------------------------------------------------

def test_open_months_are_listed_and_kept_out_of_variances(df):
    dims = analysis.list_dimensions(df)
    assert dims["last_closed_month"] == "2026-02"
    assert dims["open_months"] == ["2026-03"]
    assert {r["month"] for r in analysis.variance_summary(df, ["month"])} == {"2026-01", "2026-02"}


def test_trend_shows_open_month_without_actual(df):
    march = [r for r in analysis.monthly_trend(df) if r["month"] == "2026-03"]
    assert {r["budget"] for r in march} == {100.0, 50.0}
    assert all(r["actual"] is None and r["favourable"] is None for r in march)


# --- Full-year forecast --------------------------------------------------------

def test_forecast_run_rate(df):
    # Sales: YTD 210 vs 200 -> ratio 1.05 -> March 105 -> landing 315 vs 300
    # IT:    YTD 110 vs 100 -> ratio 1.10 -> March 55  -> landing 165 vs 150
    fc = analysis.full_year_forecast(df, ["department"], method="run_rate")
    lines = {r["department"]: r for r in fc["lines"]}
    assert (fc["as_of"], fc["months_closed"], fc["months_open"]) == ("2026-02", 2, 1)
    assert lines["Sales"]["landing"] == 315.0 and lines["Sales"]["favourable"]
    assert lines["IT"]["landing"] == 165.0 and not lines["IT"]["favourable"]
    assert fc["operating_result"] == {"budget": 150.0, "landing": 150.0, "variance": 0.0}


def test_forecast_budget_method(df):
    fc = analysis.full_year_forecast(df, method="budget")
    landing = {r["type"]: r["landing"] for r in fc["lines"]}
    assert landing == {"income": 310.0, "expense": 160.0}  # actual to date + March budget


def test_forecast_as_of_earlier_month(df):
    fc = analysis.full_year_forecast(df, ["department"], method="budget", as_of="2026-01")
    assert {r["department"]: r["landing"] for r in fc["lines"]} == {"Sales": 320.0, "IT": 170.0}


def test_forecast_rejects_open_month(df):
    with pytest.raises(ValueError, match="no actuals"):
        analysis.full_year_forecast(df, as_of="2026-03")


# --- Loading real exports ------------------------------------------------------

def test_prepare_accepts_other_column_names_and_dates():
    raw = pd.DataFrame({
        "Period": [pd.Timestamp("2026-01-31"), "2026-02"],
        "Cost Center": [" Sales ", "Sales"],
        "GL_Account": ["Revenue", "Revenue"],
        "Tipo": ["Ingresos", "revenue"],
        "Plan": ["100", 100],
        "Real": [120, ""],
    })
    df = analysis.prepare(raw)
    assert df["month"].tolist() == ["2026-01", "2026-02"]
    assert df["department"].tolist() == ["Sales", "Sales"]
    assert df["type"].tolist() == ["income", "income"]
    assert df["actual"].iloc[0] == 120 and pd.isna(df["actual"].iloc[1])  # empty = open month


def test_prepare_sums_duplicate_lines(df):
    doubled = analysis.prepare(pd.concat([df, df]))
    assert len(doubled) == len(df)
    assert doubled["budget"].sum() == 2 * df["budget"].sum()
    assert doubled["actual"].isna().sum() == 2  # open months stay open


@pytest.mark.parametrize("change, message", [
    (lambda d: d.drop(columns="budget"), "Missing columns: budget"),
    (lambda d: d.assign(type="other"), "Unknown type"),
    (lambda d: d.assign(month="someday"), "Unreadable month"),
    (lambda d: d.assign(actual="1.234,5"), "Not a number in actual"),
])
def test_prepare_explains_bad_files(df, change, message):
    with pytest.raises(analysis.DataError, match=message):
        analysis.prepare(change(df))


def test_load_excel_upload(df):
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False)
    buffer.name = "export.xlsx"  # like a file uploaded in the web app
    buffer.seek(len(buffer.getvalue()))  # already read once: load_data must rewind
    loaded = analysis.load_data(buffer)
    assert len(loaded) == len(df)
    assert analysis.pl_summary(loaded) == analysis.pl_summary(df)
