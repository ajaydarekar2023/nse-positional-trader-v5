# NSE Positional Trader V5.2.6 — Stability + Regression Fix

Phone-first Streamlit research, screening, paper-trading, risk and journaling tool for NSE equities.

## V5.2.6 changes
- Retained all V5.2.6 single-stock/AI/custom-scanner `'dict' object has no attribute 'Close'` regression by removing pandas attribute-style OHLC/indicator access from the analysis pipeline and using explicit column keys.
- Retained defensive column access to benchmark, scoring, stop/target, chart and backtest paths.
- Retained the Trade Journal fix `StreamlitValueAssignmentNotAllowedError` caused by using the same key for `st.form()` and `st.session_state['journal']`. The form now has a unique widget key.
- Retained robust OHLCV normalization for yfinance DataFrame/MultiIndex/Series/dict-like responses.
- Retained safe fundamentals normalization and 2-D fundamentals display.
- Retained Top 20 → Top 6 ranking, price/liquidity filters, corrected scoring, sector RS, structural stops and 2R target.
- Changed the research universe from Nifty 500 to Nifty 200 only.
- Primary and secondary online constituent endpoints now request Nifty 200.
- Bundled fallback is a 200-symbol Nifty 200 snapshot (2026-08-09 reference), used only if both online constituent downloads fail.
- Kept NIFTY 50 as the market-regime/relative-strength benchmark; this release does not change benchmark logic.

## Universe + eligibility
The scan universe is Nifty 200. NSE Indices describes Nifty 200 as including all companies in Nifty 100 and Nifty Midcap 100. The app still applies the existing price/liquidity eligibility filters after loading the universe.

## Eligibility
A stock is eligible for the research shortlist only when:
- Latest close <= ₹15,000
- 20-session average traded value >= ₹5 crore/day
- 20-session median traded value >= ₹2 crore/day
- Positive-volume sessions >= 90% of the last 20 sessions
- At least 210 clean daily sessions are available

Missing fundamentals, weekly data or announcements do not automatically remove a stock; they are shown as unavailable/partial.

## Regression checks performed
- Python compilation of `streamlit_app.py`
- Synthetic OHLCV pipeline test
- Single-stock `signal()` test with mocked external data
- Stop/target calculation test
- Score functions tested with dictionary-style rows to catch the exact `.Close` failure class

## Deploy/update
Replace `streamlit_app.py`, `requirements.txt`, `README.md`, and `VERSION.txt` in the existing GitHub repository. Keep the bundled `data/nifty200_symbols.csv`.

After deployment, open the app and use **Refresh all cached data**, then test:
1. **Top 20/Top 6 → Run corrected NSE scan**
2. **Stock → Analyze stock**
3. **Journal → Add**
4. **AI → Generate AI research packet**
5. **Scanner → Custom selection → Run custom scanner**

## Important
This is a research/paper-trading tool, not an automated trading system. Verify important corporate announcements with the original NSE/company disclosure. Historical backtests are not guarantees of future performance.
