"""Budget-vs-actual analysis with pandas.

These functions do all the maths. The AI never calculates numbers itself:
it calls these functions as tools and explains the results. That keeps the
answers exact and easy to check.

Variance convention (common in FP&A):
- variance = actual - budget
- For income, a positive variance is good. For expenses, a positive variance is bad.
  `favourable` says which one it is, so nobody has to remember the sign rule.
"""

from pathlib import Path

import pandas as pd

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "budget_vs_actual.csv"


def load_data(path: Path = DATA_FILE) -> pd.DataFrame:
    return pd.read_csv(path)


def _filter(df: pd.DataFrame, month_from=None, month_to=None, department=None, account=None) -> pd.DataFrame:
    # Months are "YYYY-MM" strings, so text comparison also sorts them by date.
    if month_from:
        df = df[df["month"] >= month_from]
    if month_to:
        df = df[df["month"] <= month_to]
    if department:
        df = df[df["department"] == department]
    if account:
        df = df[df["account"] == account]
    return df


def _add_variance(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["variance"] = (df["actual"] - df["budget"]).round(2)
    df["variance_pct"] = (df["variance"] / df["budget"] * 100).round(1)
    sign = df["type"].map({"income": 1, "expense": -1})
    df["favourable"] = (df["variance"] * sign) >= 0
    return df


def list_dimensions(df: pd.DataFrame) -> dict:
    """Available months, departments and accounts, so the AI uses valid names."""
    return {
        "months": sorted(df["month"].unique().tolist()),
        "departments": sorted(df["department"].unique().tolist()),
        "accounts": sorted(df["account"].unique().tolist()),
    }


def variance_summary(df, group_by, month_from=None, month_to=None, department=None, account=None) -> list[dict]:
    """Budget, actual and variance grouped by the given columns."""
    data = _filter(df, month_from, month_to, department, account)
    if data.empty:
        return []
    keys = list(group_by) + ["type"]  # keep "type" so the sign rule still works
    grouped = data.groupby(keys, as_index=False)[["budget", "actual"]].sum()
    result = _add_variance(grouped)
    return result.sort_values(keys).to_dict(orient="records")


def top_deviations(df, n=5, month_from=None, month_to=None, department=None, only_unfavourable=False) -> list[dict]:
    """The single lines (month x department x account) with the largest variances."""
    data = _add_variance(_filter(df, month_from, month_to, department))
    if only_unfavourable:
        data = data[~data["favourable"]]  # ~ is "not" for a whole column
    data = data.reindex(data["variance"].abs().sort_values(ascending=False).index)
    return data.head(n).to_dict(orient="records")


def monthly_trend(df, department=None, account=None) -> list[dict]:
    """Budget vs. actual month by month for one department and/or account."""
    data = _filter(df, department=department, account=account)
    grouped = data.groupby(["month", "type"], as_index=False)[["budget", "actual"]].sum()
    return _add_variance(grouped).sort_values("month").to_dict(orient="records")


def pl_summary(df, month_from=None, month_to=None) -> dict:
    """Total revenue, total expenses and operating result, budget vs. actual."""
    data = _filter(df, month_from, month_to)
    totals = data.groupby("type")[["budget", "actual"]].sum()
    revenue = totals.loc["income"] if "income" in totals.index else pd.Series({"budget": 0.0, "actual": 0.0})
    expenses = totals.loc["expense"] if "expense" in totals.index else pd.Series({"budget": 0.0, "actual": 0.0})
    result = {}
    for col in ("budget", "actual"):
        result[col] = {
            "revenue": round(float(revenue[col]), 2),
            "expenses": round(float(expenses[col]), 2),
            "operating_result": round(float(revenue[col] - expenses[col]), 2),
        }
    result["operating_result_variance"] = round(
        result["actual"]["operating_result"] - result["budget"]["operating_result"], 2
    )
    return result
