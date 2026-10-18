"""Generate a fictitious budget-vs-actual dataset for the demo.

The company ("Northwind Bikes") and every number are invented. A few
deviations are planted on purpose so the assistant has something real to find.

Run:  python data/generate_data.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42  # fixed seed -> the same CSV every time (like srand(42) in C)
YEAR = 2026
CLOSED_THROUGH = 9  # actuals up to September; October-December are still open (budget only)
OUTPUT = Path(__file__).with_name("budget_vs_actual.csv")

# Monthly budget per (department, account), in euros.
# A dict maps a key to a value; here the key is a tuple.
BUDGET = {
    ("Sales", "Revenue"): 2_100_000,
    ("Sales", "Personnel"): 180_000,
    ("Sales", "Travel"): 25_000,
    ("Marketing", "Campaigns"): 90_000,
    ("Marketing", "Personnel"): 70_000,
    ("Operations", "Cost of goods"): 640_000,
    ("Operations", "Logistics"): 85_000,
    ("Operations", "Personnel"): 210_000,
    ("IT", "Software licenses"): 40_000,
    ("IT", "Personnel"): 95_000,
    ("HR", "Personnel"): 45_000,
    ("HR", "Training"): 12_000,
    ("Finance", "Personnel"): 60_000,
    ("Finance", "Consulting"): 15_000,
}

# Seasonality for revenue and cost of goods (index 0 = January).
SEASONALITY = [0.80, 0.85, 1.00, 1.10, 1.20, 1.25, 1.15, 0.90, 1.00, 1.00, 0.90, 0.85]

# Planted deviations: (month, department, account) -> actual / budget ratio.
PLANTED = {
    (3, "Marketing", "Campaigns"): 1.45,       # spring campaign overspend
    (7, "IT", "Software licenses"): 1.60,      # annual renewals paid early
    (8, "IT", "Software licenses"): 1.55,
    (9, "IT", "Software licenses"): 1.50,
    (8, "Sales", "Revenue"): 0.78,             # weak August: a big client delayed orders
    (8, "Operations", "Cost of goods"): 0.82,  # less revenue -> less cost of goods
    (9, "Operations", "Logistics"): 1.35,      # fuel price increase
}

SEASONAL_ACCOUNTS = {"Revenue", "Cost of goods"}


def build_dataset() -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    rows = []  # a list of dicts; pandas turns it into a table at the end
    for month in range(1, 13):
        for (department, account), base in BUDGET.items():
            budget = base * (SEASONALITY[month - 1] if account in SEASONAL_ACCOUNTS else 1.0)
            # The random draw happens for every line, so the closed months stay the same numbers.
            ratio = PLANTED.get((month, department, account), rng.normal(1.0, 0.03))
            actual = round(budget * ratio, 2) if month <= CLOSED_THROUGH else None
            rows.append(
                {
                    "month": f"{YEAR}-{month:02d}",
                    "department": department,
                    "account": account,
                    "type": "income" if account == "Revenue" else "expense",
                    "budget": round(budget, 2),
                    "actual": actual,
                }
            )
    return pd.DataFrame(rows)


if __name__ == "__main__":  # only runs when the file is executed, not when imported
    df = build_dataset()
    df.to_csv(OUTPUT, index=False)
    print(f"Wrote {len(df)} rows to {OUTPUT}")
