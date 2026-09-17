# Finance & Quant Colab Projects

A portfolio of applied finance/quant projects built as Google Colab notebooks — real market and filings data, working Python, and models used in actual equity research, wealth management, and quant workflows.

Built by Jaik Wolfe (Finance major) as hands-on practice ahead of finance internship recruiting (wealth management, asset management, and quant-adjacent roles).

## Projects

| # | Project | Difficulty | What it does |
|---|---------|-----------|--------------|
| 01 | [DCF Valuation from SEC Filings](01-dcf-valuation/) | Intermediate | Pulls a company's real financials from the SEC EDGAR XBRL API and builds a full WACC-based DCF valuation with a sensitivity table, compared against the live market price. |
| 02 | [Efficient Frontier Portfolio Optimizer](02-efficient-frontier-optimizer/) | Intermediate | Builds a mean-variance optimizer (max-Sharpe, min-variance) with Ledoit-Wolf shrinkage, cross-checks it against a hand-written cvxpy solve, and stress-tests it with an out-of-sample backtest and a lookback-window sensitivity analysis. |

More projects will be added here as they're built (risk models, systematic trading strategies, and further institutional-level work).

## Stack

Python, pandas, numpy, requests, yfinance, scipy, PyPortfolioOpt, cvxpy, matplotlib, plotly — run entirely in Google Colab, no local setup required.
