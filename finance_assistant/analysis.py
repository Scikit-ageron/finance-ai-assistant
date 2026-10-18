"""Budget-vs-actual analysis with pandas.

These functions do all the maths. The AI never calculates numbers itself:
it calls these functions as tools and explains the results. That keeps the
answers exact and easy to check.

Variance convention (common in FP&A):
- variance = actual - budget
- For income, a positive variance is good. For expenses, a positive variance is bad.
  `favourable` says which one it is, so nobody has to remember the sign rule.

A month with no actual yet is "open". Variances only use closed months, so the
budget is always compared with a real figure (never with an empty one).
"""

from pathlib import Path

import numpy as np
import pandas as pd

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "budget_vs_actual.csv"

COLUMNS = ["month", "department", "account", "type", "budget", "actual"]
LINE = ["department", "account", "type"]  # one budget line

# Other names planning tools use for the same columns (lower case, spaces instead of "_").
ALIASES = {
    "period": "month", "date": "month", "mes": "month", "periodo": "month", "fecha": "month",
    "cost center": "department", "cost centre": "department", "departamento": "department",
    "centro de coste": "department",
    "gl account": "account", "line item": "account", "cuenta": "account", "partida": "account",
    "account type": "type", "tipo": "type",
    "plan": "budget", "budget amount": "budget", "presupuesto": "budget", "ppto": "budget",
    "actuals": "actual", "real": "actual", "actual amount": "actual", "realizado": "actual",
}
TYPES = {
    "income": "income", "revenue": "income", "sales": "income", "ingreso": "income", "ingresos": "income",
    "expense": "expense", "expenses": "expense", "cost": "expense", "costs": "expense",
    "gasto": "expense", "gastos": "expense", "coste": "expense",
}


class DataError(ValueError):
    """The file cannot be used. The message says what to fix."""


def load_data(source=DATA_FILE) -> pd.DataFrame:
    """Read a CSV or Excel export (a path or an uploaded file) and check it."""
    name = str(getattr(source, "name", source)).lower()  # uploaded files have .name
    if hasattr(source, "seek"):
        source.seek(0)  # an uploaded file may have been read before
    try:
        raw = pd.read_excel(source) if name.endswith((".xlsx", ".xls")) else pd.read_csv(source)
    except Exception as exc:
        raise DataError(f"Could not read the file: {exc}") from exc
    return prepare(raw)


def prepare(raw: pd.DataFrame) -> pd.DataFrame:
    """Rename columns to the standard names, clean the values and sum duplicate lines."""
    df = raw.rename(columns=lambda c: str(c).strip().lower().replace("_", " "))
    df = df.rename(columns=ALIASES)
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise DataError(f"Missing columns: {', '.join(missing)}. Found: {', '.join(map(str, raw.columns))}.")
    df = df[COLUMNS].dropna(how="all")
    if df.empty:
        raise DataError("The file has no rows.")

    months = pd.to_datetime(df["month"].astype(str), format="mixed", errors="coerce")
    if months.isna().any():
        raise DataError(f"Unreadable month: {df.loc[months.isna(), 'month'].iloc[0]!r}. Use YYYY-MM.")
    df["month"] = months.dt.strftime("%Y-%m")

    types = df["type"].astype(str).str.strip().str.lower().map(TYPES)
    if types.isna().any():
        raise DataError(f"Unknown type: {df.loc[types.isna(), 'type'].iloc[0]!r}. Use income or expense.")
    df["type"] = types

    for col in ("department", "account"):
        df[col] = df[col].astype(str).str.strip()
    for col in ("budget", "actual"):
        values = pd.to_numeric(df[col], errors="coerce")
        typed = df[col].notna() & (df[col].astype(str).str.strip() != "")
        if (values.isna() & typed).any():
            raise DataError(f"Not a number in {col}: {df.loc[values.isna() & typed, col].iloc[0]!r}.")
        df[col] = values
    if df["budget"].isna().any():
        raise DataError("Some lines have no budget.")

    # Real exports often have several rows per line (sub-accounts): add them up.
    # min_count=1 keeps an open month empty instead of turning it into 0.
    return df.groupby(["month"] + LINE, as_index=False)[["budget", "actual"]].sum(min_count=1)


def _records(df: pd.DataFrame) -> list[dict]:
    """Rows as dicts, with empty values as None (valid JSON for the AI)."""
    return df.astype(object).where(df.notna(), None).to_dict(orient="records")


def _closed(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["actual"].notna()]


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


def _add_variance(df: pd.DataFrame, actual: str = "actual") -> pd.DataFrame:
    df = df.copy()
    df[["budget", actual]] = df[["budget", actual]].round(2)  # sums of floats leave 0.0000001s
    df["variance"] =(df[actual] - df["budget"]).round(2)
    pct = (df["variance"] / df["budget"] * 100).round(1)
    df["variance_pct"] = pct.replace([np.inf, -np.inf], np.nan)  # a budget of 0 has no %
    sign = df["type"].map({"income": 1, "expense": -1})
    df["favourable"] = (df["variance"] * sign) >= 0
    return df


def last_closed_month(df: pd.DataFrame) -> str | None:
    closed = _closed(df)
    return closed["month"].max() if not closed.empty else None


def list_dimensions(df: pd.DataFrame) -> dict:
    """Available months, departments and accounts, so the AI uses valid names."""
    months = sorted(df["month"].unique().tolist())
    last = last_closed_month(df)
    return {
        "months": months,
        "last_closed_month": last,
        "open_months": [m for m in months if last is None or m > last],
        "departments": sorted(df["department"].unique().tolist()),
        "accounts": sorted(df["account"].unique().tolist()),
    }


def variance_summary(df, group_by, month_from=None, month_to=None, department=None, account=None) -> list[dict]:
    """Budget, actual and variance grouped by the given columns (closed months only)."""
    data = _closed(_filter(df, month_from, month_to, department, account))
    if data.empty:
        return []
    keys = list(group_by) + ["type"]  # keep "type" so the sign rule still works
    grouped = data.groupby(keys, as_index=False)[["budget", "actual"]].sum()
    return _records(_add_variance(grouped).sort_values(keys))


def top_deviations(df, n=5, month_from=None, month_to=None, department=None, only_unfavourable=False) -> list[dict]:
    """The single lines (month x department x account) with the largest variances."""
    data = _add_variance(_closed(_filter(df, month_from, month_to, department)))
    if only_unfavourable:
        data = data[~data["favourable"]]  # ~ is "not" for a whole column
    data = data.reindex(data["variance"].abs().sort_values(ascending=False).index)
    return _records(data.head(n))


def monthly_trend(df, department=None, account=None) -> list[dict]:
    """Budget vs. actual month by month. Open months have budget but no actual."""
    data = _filter(df, department=department, account=account)
    grouped = data.groupby(["month", "type"], as_index=False)[["budget", "actual"]].sum(min_count=1)
    result = _add_variance(grouped)
    result["favourable"] = result["favourable"].where(result["actual"].notna())  # unknown yet
    return _records(result.sort_values("month"))


def pl_summary(df, month_from=None, month_to=None) -> dict:
    """Total revenue, total expenses and operating result, budget vs. actual (closed months)."""
    data = _closed(_filter(df, month_from, month_to))
    totals = data.groupby("type")[["budget", "actual"]].sum()
    revenue = totals.loc["income"] if "income" in totals.index else pd.Series({"budget": 0.0, "actual": 0.0})
    expenses = totals.loc["expense"] if "expense" in totals.index else pd.Series({"budget": 0.0, "actual": 0.0})
    result = {"months": sorted(data["month"].unique().tolist())}
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


def full_year_forecast(df, group_by=(), method="run_rate", as_of=None) -> dict:
    """Full-year landing = actual to date + a forecast for the months still open.

    method "budget":   open months are expected to hit their budget.
    method "run_rate": each line keeps its year-to-date actual/budget ratio,
                       so the budget's seasonality is kept.
    """
    last = last_closed_month(df)
    as_of = as_of or last
    if as_of is None:
        raise ValueError("There are no actuals yet, so there is nothing to forecast from.")
    if last is not None and as_of > last:
        raise ValueError(f"{as_of} has no actuals yet. The last closed month is {last}.")
    if method not in ("budget", "run_rate"):
        raise ValueError("method must be 'budget' or 'run_rate'")

    data = df[df["month"].str[:4] == as_of[:4]]  # the year of as_of
    done = data[data["month"] <= as_of].groupby(LINE)[["budget", "actual"]].sum()
    rest = data[data["month"] > as_of].groupby(LINE)["budget"].sum()
    table = pd.DataFrame({
        "budget": data.groupby(LINE)["budget"].sum(),
        "budget_ytd": done["budget"],
        "actual_ytd": done["actual"],
        "budget_rest": rest,
    }).fillna(0.0)

    if method == "run_rate":
        ratio = (table["actual_ytd"] / table["budget_ytd"]).replace([np.inf, -np.inf], np.nan).fillna(1.0)
        table["forecast_rest"] = table["budget_rest"] * ratio
    else:
        table["forecast_rest"] = table["budget_rest"]
    table["landing"] = table["actual_ytd"] + table["forecast_rest"]

    keys = list(group_by) + ["type"]
    cols = ["budget", "actual_ytd", "forecast_rest", "landing"]
    grouped = table.reset_index().groupby(keys, as_index=False)[cols].sum()
    grouped[cols] = grouped[cols].round(2)
    lines = _add_variance(grouped, actual="landing").sort_values(keys)

    by_type = grouped.groupby("type")[["budget", "landing"]].sum()
    income = by_type.loc["income"] if "income" in by_type.index else pd.Series({"budget": 0.0, "landing": 0.0})
    expense = by_type.loc["expense"] if "expense" in by_type.index else pd.Series({"budget": 0.0, "landing": 0.0})
    budget_result = round(float(income["budget"] - expense["budget"]), 2)
    landing_result = round(float(income["landing"] - expense["landing"]), 2)
    months = sorted(data["month"].unique().tolist())
    return {
        "as_of": as_of,
        "method": method,
        "months_closed": sum(m <= as_of for m in months),
        "months_open": sum(m > as_of for m in months),
        "lines": _records(lines),
        "operating_result": {
            "budget": budget_result,
            "landing": landing_result,
            "variance": round(landing_result - budget_result, 2),
        },
    }
