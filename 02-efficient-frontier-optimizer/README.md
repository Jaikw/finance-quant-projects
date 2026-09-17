# Efficient Frontier Portfolio Optimizer

**Difficulty:** Intermediate
**Notebook:** [`Efficient_Frontier_Optimizer.ipynb`](Efficient_Frontier_Optimizer.ipynb) — open directly in [Google Colab](https://colab.research.google.com/) via File → Upload notebook.

## What it does

Given a list of asset tickers, this notebook:

1. Pulls 5 years of live daily prices for a multi-asset-class universe (equities, international, bonds, gold, REITs) from Yahoo Finance.
2. Estimates annualized expected returns and a Ledoit-Wolf shrinkage-adjusted covariance matrix.
3. Solves for the **max-Sharpe** and **minimum-variance** portfolios with PyPortfolioOpt.
4. **Independently cross-checks** both results against a hand-written `cvxpy` convex program.
5. Traces the full efficient frontier across a grid of target returns.
6. Runs an **out-of-sample test** — optimizes on the first 80% of history, holds the weights fixed, and checks how they actually performed on the untouched final 20%, against an equal-weight benchmark.
7. Runs a sensitivity analysis showing how much the "optimal" portfolio changes depending on the lookback window used to estimate returns.

## Why it matters

Mean-variance optimization is the textbook foundation of asset allocation used at private banks, robo-advisors, and multi-asset funds — but the gap between the textbook frontier chart and a usable real-world model is almost entirely about handling estimation error. This notebook doesn't just build the optimizer; it stress-tests it (out-of-sample validation, cross-checked math, sensitivity analysis), which is exactly the discipline expected before trusting an allocation with real capital.

## How to run it

1. Open the notebook in Google Colab.
2. In the **Configuration** cell, edit `TICKERS` to whatever universe you want (default is a diversified 7-ETF set).
3. Runtime → Run all.

## Known limitations

See the "Modeling Caveats & Limitations" section at the end of the notebook — in short, expected returns are simple historical means (the noisiest possible input), and the out-of-sample test uses a single train/test split rather than a full rolling walk-forward.
