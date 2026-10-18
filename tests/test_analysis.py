"""Tests for the pandas analysis. They run without an API key.

Run:  pytest
"""

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
    }
    assert {t["name"] for t in TOOLS} == set(sample_inputs)
    for name, args in sample_inputs.items():
        run_tool(df, name, dict(args))  # must not raise


def test_planted_deviations_in_real_dataset():
    real = analysis.load_data()
    top = analysis.top_deviations(real, n=3, month_from="2026-08", month_to="2026-08")
    assert top[0]["account"] == "Revenue" and not top[0]["favourable"]
