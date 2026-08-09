# NSE Positional Trading System V5.1

Mobile-first Streamlit research/paper-trading dashboard for Indian NSE stocks.

## V5.1 upgrades
- Regime-adaptive scoring engine with transparent component weights
- Multi-timeframe weekly + daily confirmation
- Top 20 research shortlist -> Top 3 trade-ready shortlist
- Entry-quality score
- In-app alerts for Top 3 entry proximity and event risk
- Event/news intelligence with positive/negative/neutral classification
- AI second-opinion prompt designed to challenge the machine signal
- Paper portfolio sector exposure view
- Risk sizing, backtesting and trade journal retained from V5

## Important
This is research/paper-trading software, not a guarantee of profits and not a live execution system. Free data can be delayed, incomplete, rate-limited or unavailable. Verify important announcements with NSE/company filings. Do not put broker credentials or secrets in the repository.

## Streamlit deployment
Main file: `streamlit_app.py`

The app refreshes automatically when the GitHub repository changes. Keep `requirements.txt` and `data/nifty500_symbols.csv` in the repository.
