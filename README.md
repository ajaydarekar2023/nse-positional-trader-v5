# NSE Positional Trader V5.2.3 — Stability Release

Phone-first Streamlit research, screening, paper-trading, risk and journaling tool for NSE equities.

## V5.2.3 fixes
- Fixed Top-20 scan crash caused by the stop engine expecting `SwingLow20` that was not included in the scored-row table.
- Hardened single-stock OHLCV loading against empty/malformed yfinance responses.
- Hardened NIFTY benchmark loading and regime calculation when benchmark data is unavailable.
- Hardened fundamental scoring against scalar, list, ndarray, dict, string and missing provider values.
- Keeps the fundamentals display safe and 2-D.
- Added clearer user-facing data errors instead of raw Streamlit traceback failures.
- Added guards for insufficient history.
- Backtest now uses the same robust OHLCV loader.
- Keeps V5.2.2 rules: Top 20 → Top 6, price <= ₹15,000, liquidity filters, corrected score normalization, sector relative strength, structural ATR/swing stops, 2R target, paper trading only.

## Eligibility
A stock is eligible for the research shortlist only when:
- Latest close <= ₹15,000
- 20-session average traded value >= ₹5 crore/day
- 20-session median traded value >= ₹2 crore/day
- Positive-volume sessions >= 90% of the last 20 sessions
- At least 210 clean daily sessions are available

Missing fundamentals, weekly data or announcements do not automatically remove a stock; they are shown as unavailable/partial.

## Deploy/update
Replace `streamlit_app.py`, `requirements.txt`, and `README.md` in the existing GitHub repository. Keep the bundled `data/nifty500_symbols.csv`.

After deployment, open the app and use **Refresh all cached data**, then run **Scan NSE → Top 20 + Top 6**.

## Important
This is a research/paper-trading tool, not an automated trading system. Verify important corporate announcements with the original NSE/company disclosure. Historical backtests are not guarantees of future performance.
