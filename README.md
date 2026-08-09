# NSE Positional Trader V5 — Final Research Build

Mobile-first NSE positional-trading research and paper-trading dashboard.

## V5 goal
This is the intended final research version: it adds portfolio-level risk, walk-forward backtesting, realistic costs/slippage, dynamic universe refresh, sector-relative ranking, fundamental scoring, event-risk flags, signal explanations, paper portfolio tracking, and exportable logs.

## Data
Default free mode:
- Prices: Yahoo Finance NSE `.NS` symbols.
- Benchmark: `^NSEI`.
- Fundamentals: Yahoo Finance fields when available.
- Corporate announcements: best-effort public NSE endpoint.
- Nifty 500 constituent list: attempted from the official Nifty Indices download page, with a local fallback list.

Important: this is NOT a licensed NSE real-time feed. NSE documents separate commercial EOD/historical, real-time and corporate-data products. Missing/blocked data is shown as unavailable rather than invented.

## Deployment
Upload:
- `streamlit_app.py`
- `requirements.txt`
- `data/nifty500_symbols.csv`

to GitHub, then deploy `streamlit_app.py` on Streamlit Community Cloud.

## V5 modules
1. Dashboard / market regime
2. Full-universe scanner
3. Stock diagnostics
4. Walk-forward backtest
5. Portfolio simulator
6. Risk engine
7. Persistent-in-session journal + CSV/JSON export
8. AI research prompts
9. Data-health checks

## Trading safety
Research only. No live orders. Backtests are hypothetical and cannot guarantee future returns.
