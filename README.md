# NSE Positional Trading System V5 — Top 10 Edition

Mobile-first Streamlit research/paper-trading dashboard for Indian equities.

## New Top 10 workflow

The Dashboard and Scanner now have **Scan NSE → Top 10**. Instead of manually selecting stocks, V5:

1. Attempts to refresh the Nifty 500 universe from the official Nifty Indices constituent CSV.
2. Performs a fast batched first-pass scan across the available universe.
3. Scores trend, breakout, volume, RSI, NIFTY relative strength, sector relative strength and volatility.
4. Enriches only the strongest shortlist with fundamentals and corporate-event risk.
5. Applies the V5 composite score and returns the **Top 10 candidates** in descending score order.
6. Exports the shortlist to CSV.

The Top 10 are **research candidates, not guaranteed buys**. Free data can be delayed, incomplete, rate-limited or unavailable. Verify important prices and company/NSE disclosures before trading.

## Deployment

Upload `streamlit_app.py`, `requirements.txt`, `README.md`, and `data/nifty500_symbols.csv` to GitHub, then deploy `streamlit_app.py` on Streamlit Community Cloud.

## Safety

No live broker orders are placed. Do not store broker credentials or secrets in the repository.
