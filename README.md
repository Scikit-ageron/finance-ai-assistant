# Finance AI Assistant

Ask questions about **budget vs. actual** in plain language and get exact answers.
Load your own planning export, see where the year will land, and get the monthly variance commentary written for you.

> "Why did the operating result miss the budget in August?"
>
> → *Operating result in August was €328k below budget. The main driver is revenue: €416k (-22%) under budget in Sales…*

![Finance AI Assistant answering a question about August](docs/screenshot.jpg)

Built with **Python, pandas and the Claude API**. The company (Northwind Bikes) and all figures are fictitious.

## Why this project

Finance teams spend hours looking for variances in planning reports. I work in Corporate Performance Management (CPM), building planning and budgeting models, and I wanted to see how AI can help with that work **without inventing numbers**.

## How it works

```
Question ──► Claude ──► "I need the P&L for August"  (tool call)
                ▲                     │
                │                     ▼
            answer ◄── result ◄── pandas function runs locally
```

- **pandas does all the maths.** Six analysis functions (P&L summary, variance by any dimension, top deviations, monthly trend, full-year forecast, list of dimensions) are given to Claude as *tools*.
- **Claude decides what to look at and explains it.** It never calculates figures itself, so every number comes from the data and can be checked.
- **Transparent:** the app shows which queries the AI made for each answer, and what each question cost.
- **Private by design:** the full dataset never leaves your computer; the model only sees the small tables the tools return.
- **Good variance logic:** each variance is marked as favourable or unfavourable (more income is good, more expense is bad). Months without actuals are "open", so the budget is never compared with an empty month.

## Features

**1. Your own data (CSV or Excel).** Upload an export from your planning tool in the web app, or use `--data` in the terminal. The file needs one row per month, department and account, with budget and actual. Common column names are recognised (`period`, `cost center`, `plan`, `presupuesto`, `real`…), duplicate rows are added up, and if something is wrong the app says exactly what to fix. Leave `actual` empty for months that are not closed yet. The app has a template to download.

**2. Full-year forecast.** Where will the year land? Actuals to date plus a forecast for the open months, with two methods:

| Method | Open months | Good for |
|---|---|---|
| Remaining budget | hit their budget | a simple "if nothing else changes" view |
| Year-to-date run rate | keep each line's actual/budget ratio | spotting lines that are drifting |

The run rate also repeats one-off deviations, so the assistant is told to point them out.

**3. Monthly variance commentary.** Pick a month and a language and the assistant writes the commentary for the management report: headline, the month, year to date and full-year outlook. You can download it as Markdown. A real example for August (cost: $0.04):

> **Headline** — August missed budget by €328k at operating level, driven almost entirely by a one-month revenue drop in Sales (-22%) …
>
> **Full-year outlook** — Operating result €5,559.6k vs. €6,396.0k budget. Caveat: the run rate repeats August's one-off revenue miss across the remaining months, so it overstates the risk by roughly €0.3–0.4m …

## Project structure

```
data/generate_data.py          creates the fictitious dataset (actuals to September, a few planted deviations)
finance_assistant/analysis.py  loading and checking exports, budget vs. actual, full-year forecast (pandas)
finance_assistant/assistant.py the tool-use loop with the Claude API, chat and monthly commentary
app.py                         web app (Streamlit): dashboard, forecast, chat, commentary
cli.py                         terminal version
tests/                         tests for the analysis and the AI loop (no API key needed)
```

## Run it

```bash
pip install -r requirements.txt
python data/generate_data.py        # creates data/budget_vs_actual.csv
copy .env.example .env              # then add your Anthropic API key in .env
streamlit run app.py                # web app
python cli.py "Which departments are over budget?"   # or the terminal
python cli.py --commentary 2026-08 --language Spanish
python cli.py --data my_export.xlsx "Where will we land at year end?"
pytest                              # tests
```

You need an API key from the [Anthropic Console](https://console.anthropic.com/). The `.env` file is in `.gitignore`, so the key is never uploaded.

## Cost

Each question uses a few tool calls. The app shows the cost of every answer. You can switch to a cheaper model in `.env`:

```
FINANCE_ASSISTANT_MODEL=claude-sonnet-5
```

## Ideas for next steps

- Export the commentary straight to Word or PowerPoint for the management pack.
- Compare two versions of the forecast (e.g. last month's vs. this month's).
- Connect directly to a planning tool's API instead of uploading a file.

---

Made by [Ivan Mur Ordóñez](https://www.linkedin.com/in/ivanmurordonez) · Data & Analytics Consultant
