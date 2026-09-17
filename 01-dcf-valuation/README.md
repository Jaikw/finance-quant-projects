# Automated DCF Valuation from SEC Filings

**Difficulty:** Intermediate
**Notebook:** [`DCF_Valuation_SEC_EDGAR.ipynb`](DCF_Valuation_SEC_EDGAR.ipynb) — open directly in [Google Colab](https://colab.research.google.com/) via File → Upload notebook.

## What it does

Given a stock ticker, this notebook:

1. Looks up the company's CIK and pulls its full financial history directly from the **SEC EDGAR XBRL API** — no manual copy-pasting from 10-Ks.
2. Cleans and assembles a 6-year historical financial statement (revenue, margins, D&A, capex, effective tax rate).
3. Pulls live market data (price, market cap, beta, debt, cash) from Yahoo Finance and the risk-free rate from FRED.
4. Computes a CAPM-based cost of equity and a full WACC.
5. Projects unlevered free cash flow forward with a fading growth rate.
6. Discounts the projected FCFs and a Gordon-growth terminal value back to the present.
7. Outputs an implied share price, a WACC × terminal-growth sensitivity table, and a comparison to the current market price — plus 4 charts.

## Why it matters

The DCF is the single most widely used intrinsic-valuation framework in equity research, investment banking, and wealth management. Automating the data-ingestion step (rather than retyping numbers out of a 10-K) mirrors what real financial data vendors and internal bank tooling do to speed up analyst workflows.

## How to run it

1. Open the notebook in Google Colab.
2. In the **Configuration** cell, set `TICKER` to any US-listed filer and `SEC_USER_AGENT` to your own name + email (SEC EDGAR requires this — it blocks generic/anonymous requests).
3. Runtime → Run all.

## Known limitations

See the "Modeling Caveats & Limitations" section at the end of the notebook — in short, this is a simplified teaching model (flat margin assumptions, no working-capital schedule), not investment advice, and DCFs are highly sensitive to their WACC/growth assumptions by nature.
