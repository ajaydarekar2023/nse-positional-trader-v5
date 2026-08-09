# NSE Positional Trader V5.2.0 — Corrected Build

Phone-first NSE positional-trading research and paper-trading dashboard.

## What was corrected
- Top 20 is a ranking layer, not a filter requiring every optional data field.
- Top 6 is selected from Top 20 using priority score plus a soft sector-concentration cap.
- Missing fundamentals/news/weekly data do **not** silently remove a stock.
- `UNKNOWN`, `MISSING`, `PARTIAL`, `UNAVAILABLE` statuses are shown explicitly.
- Scan-health counters show where candidates were lost.
- Robust handling for yfinance multi-index batch responses.
- Official NSE Nifty 500 CSV is attempted first; a second Nifty Indices URL is attempted next; a bundled 500+ symbol snapshot is the final fallback.
- Weekly confirmation is derived from daily history; it is never assumed bullish when unavailable.
- Event/news enrichment is limited to a shortlist to reduce rate-limit pressure.
- No live broker orders.

## Daily workflow
1. Open Dashboard.
2. Tap `Scan NSE → Top 20 + Top 6`.
3. Check `Scan health` first.
4. Review Top 20 research candidates.
5. Review Top 6 priority candidates.
6. Open a candidate in Stock for the detailed decision sheet.
7. Use the risk calculator before creating a paper position.
8. Use the AI second-opinion prompt as a devil's advocate.
9. Record the trade in the journal.

## Scoring
Displayed V5 score is normalized to a 0–100 scale and is based on:
- Trend: 25
- Momentum: 15
- Relative strength vs NIFTY: 10
- Sector relative strength: 10
- Volume/breakout: 15
- Fundamentals: 15
- Regime adjustment: up to 5
- Event risk: up to -10

The maximum component total before event penalty is 95; the displayed score is normalized to 100. Missing fundamentals are neutral-filled for ranking and clearly flagged; they are not treated as a failed stock.

## Top 6 priority
`Priority Score = 60% V5 Score + 25% Entry Quality + 15% Priority Fit`.
A soft sector cap of two names is used when constructing the Top 6 so the shortlist is less likely to be dominated by one sector.

## Data
Default free mode uses Yahoo Finance for price/fundamental fields and best-effort public NSE endpoints for corporate announcements. This is not a licensed NSE real-time feed. Always verify important corporate events using original NSE/company disclosures.

The official NSE page documents a downloadable Nifty 500 constituent CSV. The application attempts the official NSE archive first. The bundled fallback is a snapshot and may become stale; the app labels whether the online or fallback universe was used.

## Deployment
Upload these files to the existing GitHub repository:
- `streamlit_app.py`
- `requirements.txt`
- `data/nifty500_symbols.csv` (optional; V5.2 has a larger embedded fallback)

Then redeploy/restart the existing Streamlit app. Do not create a second Streamlit app.

## Safety
This is research/paper-trading software. Scores, backtests and AI outputs are not guarantees of future returns. Do not use the shortlist as an automatic buy list. No live broker orders are placed.
