"""Lightweight V5.2.5 regression smoke test.
Run with: python smoke_test_v525.py
This test avoids network calls by stubbing provider-dependent functions.
"""
import sys, types
import numpy as np, pandas as pd
st = types.SimpleNamespace(cache_data=lambda *a, **k: (lambda f: f), cache_resource=lambda *a, **k: (lambda f: f), set_page_config=lambda *a, **k: None, markdown=lambda *a, **k: None)
sys.modules['streamlit'] = st
sys.modules['yfinance'] = types.SimpleNamespace()
sys.modules['requests'] = types.SimpleNamespace()
src = open('streamlit_app.py', encoding='utf-8').read()
cut = src.index('st.title(f"📈 NSE Positional Trader')
ns = {}
exec(compile(src[:cut], 'streamlit_app.py', 'exec'), ns)
idx = pd.bdate_range('2025-01-01', periods=280)
close = np.linspace(100, 150, len(idx)) + np.sin(np.arange(len(idx))) * 2
d = pd.DataFrame({'Open': close + .2, 'High': close + 2, 'Low': close - 2, 'Close': close, 'Volume': 1_000_000.0}, index=idx)
ns['benchmark_data'] = lambda: ns['daily_features'](d.copy())
ns['fundamentals'] = lambda sym: {'P/E':20,'Forward P/E':18,'ROE':.2,'ROA':.1,'Debt/Equity':50,'Revenue growth':.1,'Earnings growth':.1,'Profit margin':.12,'Market cap':1e10}
ns['event_risk'] = lambda sym: (0, [], pd.DataFrame(), 'TEST')
ns['market_regime'] = lambda: ('BULL','🟢',ns['daily_features'](d.copy()).iloc[-1])
ns['load_single_price_history'] = lambda sym, period='2y': d.copy()
f = ns['daily_features'](d.copy()); assert not f.empty
x = f.iloc[-1]; w = ns['weekly_features'](d.copy()); wx = w.iloc[-1]
r = ns['feature_row']('TEST.NS', x, wx, len(d))
stp = ns['derive_stop_target'](d.copy(), entry=float(x['Close']))
assert stp['Stop'] < stp['Target']
r2, *_ = ns['signal']('TEST.NS')
assert r2['Stop'] < r2['Entry'] < r2['Target']
for fn in ['score_trend','score_momentum','score_volume','entry_quality','weekly_status','daily_status']:
    ns[fn](dict(r))
print('V5.2.5 regression smoke test passed')
