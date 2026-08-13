import io
from html import unescape
import json
import math
import re
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus, urlparse
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="NSE Positional Trader V5.2.19", page_icon="📈", layout="centered")
st.markdown("""
<style>
.block-container{max-width:1100px;padding:.55rem .65rem 2rem}
h1{font-size:1.45rem!important}h2{font-size:1.15rem!important}h3{font-size:1rem!important}
.stButton>button,.stDownloadButton>button{width:100%;min-height:2.7rem}
div[data-testid="stMetric"]{padding:.45rem;border-radius:.6rem;border:1px solid rgba(128,128,128,.2)}
.small-note{font-size:.86rem;opacity:.82}
</style>
""", unsafe_allow_html=True)

APP_VERSION = "V5.2.19"
PRIMARY_UNIVERSE_URL = "https://nsearchives.nseindia.com/content/indices/ind_nifty200list.csv"
SECONDARY_UNIVERSE_URL = "https://www.niftyindices.com/IndexConstituent/ind_nifty200list.csv"
NIFTY_URL = "https://www.niftyindices.com/IndexConstituent/ind_nifty200list.csv"

# V5.2.2 eligibility controls. These are deliberately conservative for positional trading.
MAX_STOCK_PRICE = 15000.0          # Exclude stocks whose latest close is above this level.
MIN_AVG_TRADED_VALUE_CR = 5.0      # 20-day average traded value must be >= ₹5 crore/day.
MIN_MEDIAN_TRADED_VALUE_CR = 2.0   # 20-day median traded value must be >= ₹2 crore/day.
MIN_ACTIVE_VOLUME_DAYS_PCT = 90.0   # At least 90% of the last 20 sessions must have positive volume.
SWING_LOOKBACK = 20
ATR_STOP_MULTIPLIER = 2.0
SWING_BUFFER_ATR = 0.25
MAX_STOP_DISTANCE_PCT = 12.0        # Avoid structurally excessive stops.
MIN_STOP_DISTANCE_PCT = 1.0         # Avoid meaningless/tight stops.
DEFAULT_R_MULTIPLE = 2.0

# Bundled current-ish snapshot used only when the official online constituent download is unavailable.
# It is a fallback snapshot, not a claim of live NSE membership.
BUNDLED_SYMBOLS = """
HDFCBANK
ICICIBANK
RELIANCE
BHARTIARTL
LT
SBIN
INFY
AXISBANK
BAJFINANCE
M&M
360ONE
ABB
APLAPOLLO
AUBANK
ADANIENSOL
ADANIENT
ADANIGREEN
ADANIPORTS
ADANIPOWER
ATGL
ABCAPITAL
ALKEM
AMBUJACEM
APOLLOHOSP
ASHOKLEY
ASIANPAINT
ASTRAL
AUROPHARMA
DMART
BSE
BAJAJ-AUTO
BAJAJFINSV
BAJAJHLDNG
BANKBARODA
BANKINDIA
BDL
BEL
BHARATFORG
BHEL
BPCL
GROWW
BIOCON
BLUESTARCO
BOSCHLTD
BRITANNIA
CGPOWER
CANBK
CHOLAFIN
CIPLA
COALINDIA
COCHINSHIP
COFORGE
COLPAL
CONCOR
COROMANDEL
CUMMINSIND
DLF
DABUR
DIVISLAB
DIXON
DRREDDY
EICHERMOT
ETERNAL
EXIDEIND
NYKAA
FEDERALBNK
FORTIS
GAIL
GVT&D
GMRAIRPORT
GLENMARK
GODFRYPHLP
GODREJCP
GODREJPROP
GRASIM
HCLTECH
HDFCAMC
HDFCLIFE
HAVELLS
HEROMOTOCO
HINDALCO
HAL
HINDPETRO
HINDUNILVR
HINDZINC
POWERINDIA
HUDCO
HYUNDAI
ICICIGI
ICICIAMC
IDFCFIRSTB
ITC
INDIANB
INDHOTEL
IOC
IRCTC
IRFC
IREDA
INDUSTOWER
INDUSINDBK
NAUKRI
INDIGO
JSWENERGY
JSWSTEEL
JINDALSTEL
JIOFIN
JUBLFOOD
KEI
KPITTECH
KALYANKJIL
KOTAKBANK
LTF
LGEINDIA
LICHSGFIN
LTM
LAURUSLABS
LENSKART
LODHA
LUPIN
MRF
M&MFIN
MANKIND
MARICO
MARUTI
MFSL
MAXHEALTH
MAZDOCK
MOTILALOFS
MPHASIS
MCX
MUTHOOTFIN
NHPC
NMDC
NTPC
NATIONALUM
NESTLEIND
OBEROIRLTY
ONGC
OIL
PAYTM
OFSS
POLICYBZR
PIIND
PAGEIND
PATANJALI
PERSISTENT
PHOENIXLTD
PIDILITIND
POLYCAB
PFC
POWERGRID
PREMIERENE
PRESTIGE
PNB
RECLTD
RADICO
RVNL
SBICARD
SBILIFE
SRF
MOTHERSON
SHREECEM
SHRIRAMFIN
ENRIN
SIEMENS
SOLARINDS
SAIL
SUNPHARMA
SUPREMEIND
SUZLON
SWIGGY
TVSMOTOR
TATACAP
TATACOMM
TCS
TATACONSUM
TATAELXSI
TATAINVEST
TMCV
TMPV
TATAPOWER
TATASTEEL
TECHM
TITAN
TORNTPHARM
TRENT
TIINDIA
UPL
ULTRACEMCO
UNIONBANK
UNITDSPR
VBL
VEDL
VMM
IDEA
VOLTAS
WAAREEENER
WIPRO
YESBANK
ZYDUSLIFE
""".splitlines()
BUNDLED_SYMBOLS = sorted(set(s.strip().upper() + ".NS" for s in BUNDLED_SYMBOLS if s.strip()))

# Helpers needed by the filtered-watchlist declaration below.
def symbol_clean(s):
    return str(s).upper().replace(".NS", "").strip()

def nse_symbol(s):
    s = symbol_clean(s)
    return s + ".NS"

# User-provided filtered positional watchlist (32 NSE symbols from the uploaded screenshots).
# This is an additional scan universe only; it does not alter the Nifty 200 universe or scoring formulas.
FILTERED_STOCKS = [
    "LGEINDIA", "COALINDIA", "COROMANDEL", "TATAPOWER", "KPRMILL", "EICHERMOT",
    "TVSMOTOR", "DIXON", "SOLARINDS", "CDSL", "HAL", "CUMMINSIND", "M&M", "VBL",
    "KEI", "PERSISTENT", "OBEROIRLTY", "APLAPOLLO", "MAZDOCK", "POLYMED",
    "SBIN", "BPCL", "UNOMINDA", "LT", "ICICIBANK", "BEL", "BAJAJ-AUTO", "MARUTI",
    "BAJFINANCE", "POLYCAB", "CHOLAFIN", "COFORGE",
]
FILTERED_STOCKS = [nse_symbol(x) for x in FILTERED_STOCKS]

# -----------------------------------------------------------------------------
# 5-minute Heikin-Ashi momentum scanner (isolated feature; no positional logic)
# -----------------------------------------------------------------------------
HA_INTRADAY_PERIOD = "5d"
HA_INTRADAY_INTERVAL = "5m"
HA_TOP_N = 5


def _completed_5m_ohlcv(symbol):
    """Fetch recent 5-minute OHLCV and retain completed candles only.

    This scanner is deliberately isolated from the positional scanner. A stale,
    unavailable, or malformed intraday feed returns an empty frame rather than
    affecting any existing scan or stock-analysis path.
    """
    try:
        raw = yf.download(symbol, period=HA_INTRADAY_PERIOD, interval=HA_INTRADAY_INTERVAL,
                          auto_adjust=False, progress=False, threads=False)
        if raw is None or raw.empty:
            return pd.DataFrame()
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        raw = raw.rename(columns={str(c).title(): str(c).title() for c in raw.columns})
        needed = ["Open", "High", "Low", "Close", "Volume"]
        if any(c not in raw.columns for c in needed):
            return pd.DataFrame()
        df = raw[needed].copy().dropna(subset=["Open", "High", "Low", "Close"])
        if df.empty:
            return df
        idx = pd.DatetimeIndex(df.index)
        if idx.tz is None:
            # Yahoo intraday timestamps are normally tz-aware. If a provider
            # returns naive timestamps, treat them as exchange-local IST.
            idx = idx.tz_localize("Asia/Kolkata")
        df.index = idx
        now = pd.Timestamp.now(tz=idx.tz)
        # A candle ending after 'now' is still forming and must not be used.
        candle_end = df.index + pd.Timedelta(minutes=5)
        df = df[candle_end <= now].copy()
        # Keep regular NSE hours; this also protects against provider artifacts.
        local_idx = df.index.tz_convert("Asia/Kolkata")
        mins = local_idx.hour * 60 + local_idx.minute
        df = df[(mins >= 9 * 60 + 15) & (mins <= 15 * 60 + 25)]
        return df.tail(120)
    except Exception:
        return pd.DataFrame()


def _ha_metrics(df):
    """Return the latest two completed HA candles plus confirmation metrics."""
    if df is None or len(df) < 25:
        return None
    x = df.copy()
    ha_close = (x["Open"] + x["High"] + x["Low"] + x["Close"]) / 4.0
    ha_open = pd.Series(index=x.index, dtype=float)
    ha_open.iloc[0] = (x["Open"].iloc[0] + x["Close"].iloc[0]) / 2.0
    for i in range(1, len(x)):
        ha_open.iloc[i] = (ha_open.iloc[i-1] + ha_close.iloc[i-1]) / 2.0
    ha_high = pd.concat([x["High"], ha_open, ha_close], axis=1).max(axis=1)
    ha_low = pd.concat([x["Low"], ha_open, ha_close], axis=1).min(axis=1)
    ha = pd.DataFrame({"open":ha_open, "high":ha_high, "low":ha_low, "close":ha_close}, index=x.index)
    ha["body"] = (ha["close"] - ha["open"]).abs()
    ha["range"] = (ha["high"] - ha["low"]).replace(0, np.nan)
    ha["body_pct"] = ha["body"] / ha["range"]
    ha["green"] = ha["close"] > ha["open"]
    last2 = ha.iloc[-2:]
    if not bool(last2["green"].all()):
        return None

    close = x["Close"]
    ema9 = close.ewm(span=9, adjust=False).mean()
    vol_avg = x["Volume"].rolling(20).mean()
    latest_vol = float(x["Volume"].iloc[-1])
    vr = latest_vol / float(vol_avg.iloc[-1]) if pd.notna(vol_avg.iloc[-1]) and vol_avg.iloc[-1] > 0 else np.nan
    typical = (x["High"] + x["Low"] + x["Close"]) / 3.0
    vwap = (typical * x["Volume"]).groupby(x.index.tz_convert("Asia/Kolkata").date).cumsum() / x["Volume"].groupby(x.index.tz_convert("Asia/Kolkata").date).cumsum()
    latest_vwap = float(vwap.iloc[-1]) if pd.notna(vwap.iloc[-1]) else np.nan
    mom3 = float((close.iloc[-1] / close.iloc[-4] - 1) * 100) if len(close) >= 4 and close.iloc[-4] else 0.0
    body = float(last2["body_pct"].mean())
    close_near_high = float((x["High"].iloc[-1] - x["Close"].iloc[-1]) / max(x["High"].iloc[-1] - x["Low"].iloc[-1], 1e-9))

    # Confirmation score is separate from every positional score/formula.
    score = 0.0
    score += min(25.0, max(0.0, body * 25.0))
    score += min(20.0, max(0.0, (vr - 0.8) * 20.0 / 1.2)) if pd.notna(vr) else 0.0
    score += 20.0 if close.iloc[-1] > ema9.iloc[-1] else 0.0
    score += 20.0 if pd.notna(latest_vwap) and close.iloc[-1] > latest_vwap else 0.0
    score += min(15.0, max(0.0, mom3 * 3.0))
    score += min(10.0, max(0.0, (1.0 - close_near_high) * 10.0))
    score = round(min(100.0, score), 1)

    setup = "🟢 High" if score >= 75 else ("🟢 Moderate" if score >= 60 else "🟡 Watch")
    return {
        "Last Price": float(close.iloc[-1]),
        "HA Body": body,
        "Volume X": float(vr) if pd.notna(vr) else np.nan,
        "VWAP": latest_vwap,
        "Momentum %": mom3,
        "EMA9": float(ema9.iloc[-1]),
        "HA Time": last2.index[-1].tz_convert("Asia/Kolkata").strftime("%d-%b %H:%M"),
        "HA Score": score,
        "Setup": setup,
    }


def scan_filtered_5m_ha():
    """Scan only the user's 32-stock watchlist and return Top 5 setups."""
    rows, failures = [], []
    for symbol in FILTERED_STOCKS:
        df = _completed_5m_ohlcv(symbol)
        if df.empty:
            failures.append(symbol_clean(symbol))
            continue
        m = _ha_metrics(df)
        if m is None:
            continue
        rows.append({"Symbol": symbol_clean(symbol), **m})
    if not rows:
        return pd.DataFrame(), failures
    out = pd.DataFrame(rows).sort_values(["HA Score", "Volume X", "Momentum %"], ascending=False).head(HA_TOP_N).reset_index(drop=True)
    out.insert(0, "Rank", np.arange(1, len(out) + 1))
    return out, failures

SECTOR_MAP = {
    "RELIANCE":"Energy","ONGC":"Energy","OIL":"Energy","COALINDIA":"Energy","BPCL":"Energy","IOC":"Energy","GAIL":"Energy","PETRONET":"Energy","ATGL":"Energy","MGL":"Energy","IGL":"Energy","MRPL":"Energy","GUJGASLTD":"Energy",
    "NTPC":"Utilities","NTPCGREEN":"Utilities","POWERGRID":"Utilities","NHPC":"Utilities","NLCINDIA":"Utilities","SJVN":"Utilities","TATAPOWER":"Utilities","JSWENERGY":"Utilities","TORNTPOWER":"Utilities","CESC":"Utilities",
    "HDFCBANK":"Financials","ICICIBANK":"Financials","SBIN":"Financials","AXISBANK":"Financials","KOTAKBANK":"Financials","BAJFINANCE":"Financials","BAJAJFINSV":"Financials","HDFCLIFE":"Financials","ICICIPRULI":"Financials","ICICIGI":"Financials","SBILIFE":"Financials","PFC":"Financials","RECLTD":"Financials","JIOFIN":"Financials","PAYTM":"Financials","POLICYBZR":"Financials","MUTHOOTFIN":"Financials","MANAPPURAM":"Financials","SHRIRAMFIN":"Financials","CHOLAFIN":"Financials","FEDERALBNK":"Financials","BANKBARODA":"Financials","BANKINDIA":"Financials","CANBK":"Financials","PNB":"Financials","UNIONBANK":"Financials","INDIANB":"Financials","MAHABANK":"Financials","IDFCFIRSTB":"Financials","INDUSINDBK":"Financials","YESBANK":"Financials","BANDHANBNK":"Financials","MCX":"Financials","BSE":"Financials","CDSL":"Financials","CAMS":"Financials","KFINTECH":"Financials","MOTILALOFS":"Financials","IIFL":"Financials","ANGELONE":"Financials","NUVAMA":"Financials","JIOFIN":"Financials","HUDCO":"Financials","LICI":"Financials","LICHSGFIN":"Financials",
    "INFY":"IT","TCS":"IT","HCLTECH":"IT","WIPRO":"IT","TECHM":"IT","LTIM":"IT","LTTS":"IT","COFORGE":"IT","PERSISTENT":"IT","KPITTECH":"IT","MPHASIS":"IT","OFSS":"IT","CYIENT":"IT","BSOFT":"IT","INTELLECT":"IT","NEWGEN":"IT","LATENTVIEW":"IT","ZENSARTECH":"IT","SONATSOFTW":"IT","HAPPSTMNDS":"IT","TATATECH":"IT","TATAELXSI":"IT","NETWEB":"IT",
    "SUNPHARMA":"Healthcare","DRREDDY":"Healthcare","CIPLA":"Healthcare","APOLLOHOSP":"Healthcare","DIVISLAB":"Healthcare","LUPIN":"Healthcare","AUROPHARMA":"Healthcare","GLENMARK":"Healthcare","TORNTPHARM":"Healthcare","ZYDUSLIFE":"Healthcare","BIOCON":"Healthcare","MAXHEALTH":"Healthcare","FORTIS":"Healthcare","LAURUSLABS":"Healthcare","MANKIND":"Healthcare","JBCHEPHARM":"Healthcare","NATCOPHARM":"Healthcare","POLYMED":"Healthcare","KIMS":"Healthcare","MEDANTA":"Healthcare","LALPATHLAB":"Healthcare","VIJAYA":"Healthcare","GLAND":"Healthcare","IPCALAB":"Healthcare","PFIZER":"Healthcare","SANOFI":"Healthcare",
    "TATAMOTORS":"Auto","MARUTI":"Auto","M&M":"Auto","EICHERMOT":"Auto","HEROMOTOCO":"Auto","BAJAJ-AUTO":"Auto","TVSMOTOR":"Auto","ASHOKLEY":"Auto","BHARATFORG":"Auto","MOTHERSON":"Auto","SONACOMS":"Auto","TIINDIA":"Auto","UNOMINDA":"Auto","APOLLOTYRE":"Auto","BALKRISIND":"Auto","ENDURANCE":"Auto","EXIDEIND":"Auto","BOSCHLTD":"Auto","SCHAEFFLER":"Auto","MRF":"Auto",
    "TATASTEEL":"Metals","JSWSTEEL":"Metals","HINDALCO":"Metals","JINDALSTEL":"Metals","VEDL":"Metals","NMDC":"Metals","NATIONALUM":"Metals","HINDCOPPER":"Metals","SAIL":"Metals","JSL":"Metals","JINDALSAW":"Metals","SHYAMMETL":"Metals",
    "ITC":"Consumer","HINDUNILVR":"Consumer","NESTLEIND":"Consumer","BRITANNIA":"Consumer","DABUR":"Consumer","MARICO":"Consumer","TATACONSUM":"Consumer","VBL":"Consumer","COLPAL":"Consumer","GODREJCP":"Consumer","GODREJAGRO":"Consumer","GODFRYPHLP":"Consumer","UBL":"Consumer","UNITDSPR":"Consumer","RADICO":"Consumer","PAGEIND":"Consumer","TITAN":"Consumer","TRENT":"Consumer","DMART":"Consumer","JUBLFOOD":"Consumer","NYKAA":"Consumer","MANYAVAR":"Consumer","PATANJALI":"Consumer",
    "LT":"Industrials","SIEMENS":"Industrials","ABB":"Industrials","HAL":"Industrials","BEL":"Industrials","CUMMINSIND":"Industrials","CGPOWER":"Industrials","BHEL":"Industrials","THERMAX":"Industrials","POLYCAB":"Industrials","KEI":"Industrials","KEC":"Industrials","RVNL":"Industrials","IRCON":"Industrials","NBCC":"Industrials","NCC":"Industrials","COCHINSHIP":"Industrials","MAZDOCK":"Industrials","GRSE":"Industrials","BEML":"Industrials","SUZLON":"Industrials","SOLARINDS":"Industrials","WAAREEENER":"Industrials",
    "ADANIENT":"Diversified","ADANIGREEN":"Utilities","ADANIPORTS":"Industrials","ADANIPOWER":"Utilities","ABCAPITAL":"Financials","ABFRL":"Consumer","APARINDS":"Industrials","AMBER":"Consumer Durables","DIXON":"Consumer Durables","ASIANPAINT":"Consumer Durables","BERGEPAINT":"Consumer Durables","BLUESTARCO":"Consumer Durables","VOLTAS":"Consumer Durables","HAVELLS":"Consumer Durables","WHIRLPOOL":"Consumer Durables","KALYANKJIL":"Consumer Durables","KAJARIACER":"Consumer Durables","CROMPTON":"Consumer Durables","VGUARD":"Consumer Durables",
}

def sector(sym):
    return SECTOR_MAP.get(symbol_clean(sym), "Other")

@st.cache_data(ttl=86400, show_spinner=False)
def load_universe():
    headers = {"User-Agent":"Mozilla/5.0", "Accept":"text/csv,text/plain,*/*"}
    attempts = [(PRIMARY_UNIVERSE_URL, "NSE official archive"), (SECONDARY_UNIVERSE_URL, "Nifty Indices")]
    errors = []
    for url, label in attempts:
        try:
            r = requests.get(url, headers=headers, timeout=15)
            r.raise_for_status()
            df = pd.read_csv(io.BytesIO(r.content))
            col = next((c for c in df.columns if str(c).strip().lower() == "symbol"), None)
            if col:
                vals = sorted(set(nse_symbol(x) for x in df[col].dropna() if str(x).strip()))
                if len(vals) >= 180:
                    return vals, label, "fresh"
        except Exception as e:
            errors.append(f"{label}: {type(e).__name__}")
    return BUNDLED_SYMBOLS, "bundled snapshot fallback", "fallback"

def universe():
    return load_universe()[0]

@st.cache_data(ttl=900, show_spinner=False)
def download_prices_batch(symbols, period="2y", chunk_size=25):
    symbols = list(dict.fromkeys(symbols))
    rows = []
    failures = []
    for start in range(0, len(symbols), chunk_size):
        chunk = symbols[start:start+chunk_size]
        try:
            raw = yf.download(chunk, period=period, interval="1d", auto_adjust=False, progress=False, group_by="ticker", threads=False)
            if raw is None or raw.empty:
                failures.extend(chunk)
                continue
            for sym in chunk:
                try:
                    d = extract_symbol_frame(raw, sym, len(chunk))
                    if d.empty or len(d) < 210:
                        failures.append(sym)
                        continue
                    d = d[["Open","High","Low","Close","Volume"]].dropna()
                    if len(d) < 210:
                        failures.append(sym)
                        continue
                    x = daily_features(d).iloc[-1]
                    w = weekly_features(d)
                    wx = w.iloc[-1] if not w.empty else None
                    rows.append(feature_row(sym, x, wx, len(d)))
                except Exception:
                    failures.append(sym)
        except Exception:
            failures.extend(chunk)
    return pd.DataFrame(rows), sorted(set(failures))

def extract_symbol_frame(raw, sym, chunk_len):
    if isinstance(raw.columns, pd.MultiIndex):
        levels = [list(raw.columns.get_level_values(i)) for i in range(raw.columns.nlevels)]
        target = sym
        # yfinance can return (Ticker, Field) or (Field, Ticker)
        for level in range(raw.columns.nlevels):
            if target in levels[level]:
                d = raw.xs(target, axis=1, level=level, drop_level=True).copy()
                break
        else:
            return pd.DataFrame()
        if isinstance(d.columns, pd.MultiIndex):
            d.columns = [c[-1] for c in d.columns]
    else:
        d = raw.copy()
    rename = {str(c).title(): str(c).title() for c in d.columns}
    d.columns = [str(c).title() for c in d.columns]
    needed = ["Open","High","Low","Close","Volume"]
    if not all(c in d.columns for c in needed):
        return pd.DataFrame()
    return d[needed].dropna(how="all")

def daily_features(d):
    d = _clean_ohlcv_frame(d) if not (isinstance(d, pd.DataFrame) and all(c in d.columns for c in ["Open","High","Low","Close","Volume"])) else d.copy()
    d = d.sort_index()
    if d.empty:
        return pd.DataFrame()
    d["SMA20"] = d["Close"].rolling(20).mean()
    d["SMA50"] = d["Close"].rolling(50).mean()
    d["SMA200"] = d["Close"].rolling(200).mean()
    delta = d["Close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    d["RSI"] = 100 - 100/(1 + gain/loss.replace(0, np.nan))
    prev = d["Close"].shift()
    tr = pd.concat([(d["High"]-d["Low"]), (d["High"]-prev).abs(), (d["Low"]-prev).abs()], axis=1).max(axis=1)
    d["ATR"] = tr.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    d["ATR%"] = 100*d["ATR"]/d["Close"]
    d["VOL20"] = d["Volume"].rolling(20).mean()
    d["VOL_RATIO"] = d["Volume"]/d["VOL20"]
    d["TRADED_VALUE"] = d["Close"] * d["Volume"]
    d["AVG_TRADED_VALUE20"] = d["TRADED_VALUE"].rolling(20).mean()
    d["MEDIAN_TRADED_VALUE20"] = d["TRADED_VALUE"].rolling(20).median()
    d["ACTIVE_VOLUME_DAYS20"] = d["Volume"].gt(0).rolling(20).mean() * 100
    d["BREAKOUT20"] = d["High"].rolling(20).max().shift(1)
    d["SWING_LOW20"] = d["Low"].rolling(SWING_LOOKBACK).min().shift(1)
    d["RET21"] = d["Close"].pct_change(21)
    d["RET63"] = d["Close"].pct_change(63)
    return d.dropna(subset=["SMA20","SMA50","SMA200","RSI","ATR","ATR%","VOL20","VOL_RATIO","BREAKOUT20","SWING_LOW20","RET21","RET63","AVG_TRADED_VALUE20","MEDIAN_TRADED_VALUE20","ACTIVE_VOLUME_DAYS20"])

def weekly_features(d):
    w = d.resample("W-FRI").agg({"Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum"}).dropna()
    if len(w) < 40:
        return pd.DataFrame()
    w["SMA20W"] = w["Close"].rolling(20).mean()
    w["SMA40W"] = w["Close"].rolling(40).mean()
    w["RET12W"] = w["Close"].pct_change(12)
    return w.dropna(subset=["SMA20W","SMA40W","RET12W"])

def feature_row(sym, x, wx, history_len):
    return {
        "Symbol": symbol_clean(sym), "_symbol": sym, "Sector": sector(sym),
        "Close": float(x["Close"]), "SMA20": float(x["SMA20"]), "SMA50": float(x["SMA50"]), "SMA200": float(x["SMA200"]),
        "RSI": float(x["RSI"]), "ATR": float(x["ATR"]), "ATR%": float(x["ATR%"]), "VOL_RATIO": float(x["VOL_RATIO"]),
        "BREAKOUT20": float(x["BREAKOUT20"]), "SwingLow20": float(x["SWING_LOW20"]), "RET21": float(x["RET21"]), "RET63": float(x["RET63"]),
        "AvgTradedValue20Cr": float(x["AVG_TRADED_VALUE20"])/1e7,
        "MedianTradedValue20Cr": float(x["MEDIAN_TRADED_VALUE20"])/1e7,
        "ActiveVolumeDays20Pct": float(x["ACTIVE_VOLUME_DAYS20"]),
        "WeeklyClose": float(wx["Close"]) if wx is not None else np.nan,
        "WeeklySMA20": float(wx["SMA20W"]) if wx is not None else np.nan,
        "WeeklySMA40": float(wx["SMA40W"]) if wx is not None else np.nan,
        "WeeklyRet12": float(wx["RET12W"]) if wx is not None else np.nan,
        "HistoryDays": int(history_len),
    }

@st.cache_data(ttl=900, show_spinner=False)
def benchmark_data():
    """Load NIFTY benchmark through the same defensive OHLCV normalizer."""
    for loader in ("history", "download"):
        try:
            if loader == "history":
                d = yf.Ticker("^NSEI").history(period="2y", interval="1d", auto_adjust=False)
            else:
                d = yf.download("^NSEI", period="2y", interval="1d", auto_adjust=False, progress=False, threads=False)
            d = _clean_ohlcv_frame(d, "^NSEI")
            if len(d) >= 210:
                out = daily_features(d)
                return out if len(out) >= 10 else pd.DataFrame()
        except Exception:
            continue
    return pd.DataFrame()

def market_regime():
    try:
        d = benchmark_data()
        x = d.iloc[-1]
        if x["Close"] > x["SMA200"] and x["SMA50"] > x["SMA200"] and x["Close"] > x["SMA50"]:
            return "BULL", "🟢", x
        if x["Close"] > x["SMA200"]:
            return "NEUTRAL", "🟡", x
        return "BEAR", "🔴", x
    except Exception:
        return "UNKNOWN", "⚪", None

def liquidity_status(r):
    """Return (eligible, reason) for positional-trading liquidity/price controls."""
    price = float(r["Close"])
    avg_cr = float(r.get("AvgTradedValue20Cr", np.nan))
    med_cr = float(r.get("MedianTradedValue20Cr", np.nan))
    active_pct = float(r.get("ActiveVolumeDays20Pct", np.nan))
    reasons = []
    if not np.isfinite(price) or price > MAX_STOCK_PRICE:
        reasons.append(f"price > ₹{MAX_STOCK_PRICE:,.0f}")
    if not np.isfinite(avg_cr) or avg_cr < MIN_AVG_TRADED_VALUE_CR:
        reasons.append(f"20D avg traded value < ₹{MIN_AVG_TRADED_VALUE_CR:g}Cr")
    if not np.isfinite(med_cr) or med_cr < MIN_MEDIAN_TRADED_VALUE_CR:
        reasons.append(f"20D median traded value < ₹{MIN_MEDIAN_TRADED_VALUE_CR:g}Cr")
    if not np.isfinite(active_pct) or active_pct < MIN_ACTIVE_VOLUME_DAYS_PCT:
        reasons.append(f"active-volume days < {MIN_ACTIVE_VOLUME_DAYS_PCT:g}%")
    return len(reasons) == 0, "; ".join(reasons)

def derive_stop_target(d, entry=None, r_multiple=DEFAULT_R_MULTIPLE):
    """Derive a structurally sensible long stop and target.

    Compares a 2x ATR stop with a recent swing-low stop, rejects absurdly
    tight/wide distances, and uses the tighter valid structural stop.
    The position-size calculator remains the final risk constraint.
    """
    if d is None or d.empty:
        raise ValueError("Price history is empty")
    f = d if "ATR" in d.columns else daily_features(d)
    x = f.iloc[-1]
    entry = float(x["Close"] if entry is None else entry)
    atr = float(x["ATR"])
    if not np.isfinite(entry) or not np.isfinite(atr) or atr <= 0:
        raise ValueError("Invalid entry/ATR for stop calculation")
    atr_stop = entry - ATR_STOP_MULTIPLIER * atr
    recent = f.tail(SWING_LOOKBACK)
    swing_low = float(recent["Low"].min())
    swing_stop = swing_low - SWING_BUFFER_ATR * atr
    candidates = [("ATR 2x", atr_stop), ("Swing low", swing_stop)]
    valid = []
    for method, stop in candidates:
        dist_pct = (entry - stop) / entry * 100
        if MIN_STOP_DISTANCE_PCT <= dist_pct <= MAX_STOP_DISTANCE_PCT and stop < entry:
            valid.append((method, stop, dist_pct))
    if valid:
        # Prefer the tighter valid stop to avoid unnecessary risk, but keep it
        # below a real technical structure when possible.
        method, stop, dist_pct = min(valid, key=lambda z: z[2])
    else:
        # Fall back to ATR stop if structurally reasonable; otherwise cap the
        # distance so a bad swing low cannot create an outsized position risk.
        method, stop = "ATR 2x fallback", atr_stop
        dist_pct = (entry - stop) / entry * 100
        if dist_pct > MAX_STOP_DISTANCE_PCT:
            stop = entry * (1 - MAX_STOP_DISTANCE_PCT / 100)
            method = "Capped ATR fallback"
        elif dist_pct < MIN_STOP_DISTANCE_PCT:
            stop = entry * (1 - MIN_STOP_DISTANCE_PCT / 100)
            method = "Minimum-distance fallback"
        dist_pct = (entry - stop) / entry * 100
    risk_per_share = entry - stop
    target = entry + r_multiple * risk_per_share
    return {
        "Stop": round(float(stop), 2),
        "Target": round(float(target), 2),
        "RiskPerShare": round(float(risk_per_share), 2),
        "StopDistancePct": round(float(dist_pct), 2),
        "StopMethod": method,
        "RMultiple": float(r_multiple),
        "ATR": round(atr, 2),
        "SwingLow20": round(swing_low, 2),
    }

def derive_stop_from_values(entry, atr, swing_low, r_multiple=DEFAULT_R_MULTIPLE):
    """Fast stop/target helper for already-computed scan rows."""
    entry=float(entry); atr=float(atr); swing_low=float(swing_low)
    atr_stop=entry-ATR_STOP_MULTIPLIER*atr
    swing_stop=swing_low-SWING_BUFFER_ATR*atr
    valid=[]
    for method,stop in (("ATR 2x",atr_stop),("Swing low",swing_stop)):
        dist=(entry-stop)/entry*100
        if MIN_STOP_DISTANCE_PCT <= dist <= MAX_STOP_DISTANCE_PCT and stop < entry:
            valid.append((method,stop,dist))
    if valid:
        method,stop,dist=min(valid,key=lambda z:z[2])
    else:
        method,stop,dist="ATR 2x fallback",atr_stop,(entry-atr_stop)/entry*100
        if dist>MAX_STOP_DISTANCE_PCT:
            stop=entry*(1-MAX_STOP_DISTANCE_PCT/100); method="Capped ATR fallback"
        elif dist<MIN_STOP_DISTANCE_PCT:
            stop=entry*(1-MIN_STOP_DISTANCE_PCT/100); method="Minimum-distance fallback"
        dist=(entry-stop)/entry*100
    risk=entry-stop
    return {"Stop":round(stop,2),"Target":round(entry+r_multiple*risk,2),"RiskPerShare":round(risk,2),"StopDistancePct":round(dist,2),"StopMethod":method,"RMultiple":float(r_multiple),"ATR":round(atr,2),"SwingLow20":round(swing_low,2)}

def score_trend(r):
    pts = 0
    pts += 8 if r["Close"] > r["SMA50"] else 0
    pts += 8 if r["SMA50"] > r["SMA200"] else 0
    slope = (r["SMA50"] / r["SMA200"] - 1) if r["SMA200"] else 0
    pts += 5 if slope > 0.02 else 3 if slope > 0 else 0
    if pd.notna(r["WeeklyClose"]):
        pts += 4 if r["WeeklyClose"] > r["WeeklySMA20"] > r["WeeklySMA40"] else 2 if r["WeeklyClose"] > r["WeeklySMA40"] else 0
    else:
        pts += 2  # neutral treatment for missing weekly data; status remains UNKNOWN
    return min(25, pts)

def score_momentum(r):
    rsi = r["RSI"]
    pts = 0
    pts += 5 if 55 <= rsi <= 68 else 3 if 50 <= rsi < 55 or 68 < rsi <= 75 else 0
    pts += 5 if r["RET21"] > 0.03 else 3 if r["RET21"] > 0 else 0
    pts += 5 if r["RET63"] > 0.08 else 3 if r["RET63"] > 0 else 0
    return min(15, pts)

def score_relative(r, benchmark_return, sector_median_return=None):
    """Score relative strength against NIFTY and the stock's sector.

    Sector relative strength is calculated from the median 63-day return of
    eligible stocks in the same mapped sector. If fewer than two sector peers
    are available, the sector component is explicitly marked unavailable and
    receives a neutral 5/10 rather than comparing the stock with itself.
    """
    rs = float(r["RET63"]) - float(benchmark_return)
    if sector_median_return is None or not np.isfinite(sector_median_return):
        sector_rs = np.nan
        sector_points = 5
    else:
        sector_rs = float(r["RET63"]) - float(sector_median_return)
        sector_points = 10 if sector_rs > 0.08 else 7 if sector_rs > 0 else 3 if sector_rs > -0.05 else 0
    nifty_points = 10 if rs > 0.08 else 7 if rs > 0 else 3 if rs > -0.05 else 0
    return nifty_points, sector_points, rs, sector_rs

def score_volume(r):
    breakout = r["Close"] > r["BREAKOUT20"]
    pts = 0
    pts += 5 if r["VOL_RATIO"] >= 1.5 else 3 if r["VOL_RATIO"] >= 1.0 else 0
    pts += 5 if breakout else 2 if r["Close"] >= 0.98*r["BREAKOUT20"] else 0
    pts += 5 if breakout and r["VOL_RATIO"] >= 1.5 else 3 if r["VOL_RATIO"] >= 1.2 else 0
    return min(15, pts), breakout

BROKERAGE_FIRM_MAP = {
    "morgan stanley": "Morgan Stanley",
    "jefferies": "Jefferies",
    "clsa": "CLSA",
    "jp morgan": "JP Morgan",
    "jpmorgan": "JP Morgan",
    "hsbc": "HSBC",
    "goldman sachs": "Goldman Sachs",
    "nomura": "Nomura",
    "ubs": "UBS",
    "citi": "Citi",
    "macquarie": "Macquarie",
    "bernstein": "Bernstein",
    "emkay": "Emkay",
    "motilal oswal": "Motilal Oswal",
    "prabhudas lilladher": "Prabhudas Lilladher",
    "kotak institutional equities": "Kotak Institutional Equities",
    "axis securities": "Axis Securities",
    "icici securities": "ICICI Securities",
    "hdfc securities": "HDFC Securities",
    "edelweiss": "Edelweiss",
    "ambit": "Ambit",
    "incred": "InCred",
    "yes securities": "YES Securities",
    "sharekhan": "Sharekhan",
    "motilal oswal": "Motilal Oswal",
}

def _brokerage_firm_from_text(text):
    low = str(text).lower()
    return next((name for key, name in BROKERAGE_FIRM_MAP.items() if key in low), "")

def _brokerage_action_from_text(text):
    low = str(text).lower()
    if re.search(r"\bdowngrad(?:e|ed|es|ing)\b", low):
        return "Downgrade"
    if re.search(r"\bupgrad(?:e|ed|es|ing)\b", low):
        return "Upgrade"
    if re.search(r"\biniti(?:ate|ated|ates|ating)\b", low):
        return "Initiated"
    if any(x in low for x in ("maintain", "reiterate", "retains", "retained", "continues to rate")):
        return "Maintained"
    if any(x in low for x in ("buy", "sell", "hold", "neutral", "overweight", "underweight", "outperform", "underperform")):
        return "Rating"
    if re.search(r"\btarget(?:\s+price)?\b|\btp\b", low):
        return "Target"
    return ""


def _extract_brokerage_target(text):
    """Extract a numeric brokerage target from headline/summary/article text.

    This is information-only. It never feeds the trading score, entry, stop,
    target, eligibility or ranking calculations.
    """
    text = unescape(re.sub(r"<[^>]+>", " ", str(text or "")))
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""

    # Prefer the *new/current* target when wording contains a revision such as
    # "raised target to Rs 12,096" or "target revised to 11,700".
    patterns = [
        r"(?:target(?:\s+price)?|price\s+target)\s*(?:was\s+)?(?:raised|hiked|increased|revised|cut|lowered|reduced)?\s*(?:to|at|of|is|:)?\s*(?:₹|rs\.?|inr)\s*([0-9][0-9,]*(?:\.[0-9]+)?)",
        r"(?:raised|hiked|increased|revised|cut|lowered|reduced)\s+(?:the\s+)?target(?:\s+price)?\s*(?:to|at|of|:)?\s*(?:₹|rs\.?|inr)\s*([0-9][0-9,]*(?:\.[0-9]+)?)",
        r"(?:target(?:\s+price)?|price\s+target)\s*(?:was\s+)?(?:raised|hiked|increased|revised|cut|lowered|reduced)?\s*(?:to|at|of|is|:)?\s*([0-9][0-9,]*(?:\.[0-9]+)?)",
        r"(?:target(?:\s+price)?|price\s+target)\s*[-–—:]?\s*(?:₹|rs\.?|inr)\s*([0-9][0-9,]*(?:\.[0-9]+)?)",
        r"(?:₹|rs\.?|inr)\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:target(?:\s+price)?|price\s+target)",
        r"\b(?:tp|PT)\s*(?:to|at|of|:)?\s*(?:₹|rs\.?|inr)?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\b",
    ]
    for pat in patterns:
        matches = list(re.finditer(pat, text, re.I))
        if matches:
            # For revision language, the first match is normally the current
            # target. Avoid accidentally selecting an old target from the same
            # sentence when a later current target is explicitly stated.
            m = matches[0]
            raw = m.group(1).replace(",", "")
            try:
                value = float(raw)
                if 1 <= value <= 1000000:
                    return f"₹{value:,.2f}".rstrip("0").rstrip(".")
            except Exception:
                pass
    return ""

def _fetch_article_target(url, headers):
    """Best-effort target extraction from the linked publisher article.

    Used only when RSS title/summary does not contain a target. Failures are
    swallowed so a source outage cannot break the brokerage section.
    """
    url = str(url or "").strip()
    if not url or not url.startswith(("http://", "https://")):
        return ""
    try:
        resp = requests.get(url, headers=headers, timeout=5, allow_redirects=True)
        if not getattr(resp, "ok", False):
            return ""
        html = str(resp.text or "")[:500000]
        snippets = []
        for pat in [
            r'<title[^>]*>(.*?)</title>',
            r'<meta[^>]+(?:name|property)=["\'](?:description|og:description)["\'][^>]+content=["\'](.*?)["\']',
            r'<meta[^>]+content=["\'](.*?)["\'][^>]+(?:name|property)=["\'](?:description|og:description)["\']',
        ]:
            snippets.extend(re.findall(pat, html, re.I | re.S))
        # Also inspect visible text as a fallback; cap it to avoid excessive
        # processing on large publisher pages.
        visible = re.sub(r'<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>', ' ', html, flags=re.I | re.S)
        visible = re.sub(r'<[^>]+>', ' ', visible)
        snippets.append(visible[:250000])
        for snippet in snippets:
            target = _extract_brokerage_target(unescape(str(snippet)))
            if target:
                return target
    except Exception:
        return ""
    return ""

def _resolve_original_source_url(link, headers):
    """Resolve a Google News feed redirect to the publisher article when possible.

    If resolution is blocked/unavailable, retain the feed URL rather than failing the
    brokerage section. The source link is informational only and never affects trading
    calculations.
    """
    link = str(link or "").strip()
    if not link:
        return ""
    try:
        host = (urlparse(link).netloc or "").lower()
        if "news.google.com" not in host:
            return link
        resp = requests.get(link, headers=headers, timeout=4, allow_redirects=True)
        final_url = str(getattr(resp, "url", "") or "").strip()
        if final_url.startswith(("http://", "https://")) and "news.google.com" not in (urlparse(final_url).netloc or "").lower():
            return final_url
    except Exception:
        pass
    return link

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_brokerage_updates(symbol, limit=10):
    """Information-only brokerage/news layer.

    Source priority:
      1) Zee Business
      2) CNBC-TV18
      3) Other reputable financial sources
    Recent 0-30 day items are preferred, with 31-90 day items as fallback.
    The function never changes score, ranking, eligibility, entry, stop or target.
    """
    clean = symbol_clean(symbol)
    queries = [
        f'"{clean}" brokerage upgrade downgrade target price',
        f'"{clean}" analyst rating target price',
    ]
    source_groups = [
        ("Zee Business", "zeebiz.com", 1),
        ("CNBC-TV18", "cnbctv18.com", 2),
        ("Secondary financial sources", "moneycontrol.com;economictimes.indiatimes.com;business-standard.com;financialexpress.com;reuters.com", 3),
    ]
    cols = ["Date", "Type", "Brokerage", "Action", "Target", "Headline", "Description", "Source", "Priority", "AgeDays", "Link"]
    rows, seen = [], set()
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}

    def classify(title):
        low = title.lower()
        if "upgrade" in low:
            return "Upgrade"
        if "downgrade" in low:
            return "Downgrade"
        if any(k in low for k in ("target price", "target raised", "target cut", "target of", "target at", "tp ")):
            return "Target price"
        if any(k in low for k in ("buy", "sell", "neutral", "overweight", "underweight", "rating")):
            return "Rating"
        return "Brokerage"

    def add_feed(url, fallback_source, priority):
        try:
            resp = requests.get(url, headers=headers, timeout=12)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
        except Exception:
            return 0
        added = 0
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub = (item.findtext("pubDate") or "").strip()
            desc = (item.findtext("description") or "").strip()
            source_el = item.find("source")
            source = (source_el.text or "").strip() if source_el is not None else fallback_source
            if priority == 1:
                source = "Zee Business"
            elif priority == 2:
                source = "CNBC-TV18"
            combined = f"{title} {desc}"
            # A row is considered verified for display only when the article
            # identifies a known brokerage, has an article URL, and contains a
            # recognizable brokerage action/rating/target signal. This prevents
            # generic market-news stories from appearing as brokerage calls.
            brokerage_firm = _brokerage_firm_from_text(combined)
            action = _brokerage_action_from_text(combined)
            if not brokerage_firm or not link or not action:
                continue
            key = link or title
            if key in seen:
                continue
            seen.add(key)
            dt = pd.to_datetime(pub, errors="coerce", utc=True)
            age = None
            if pd.notna(dt):
                try:
                    age = max(0, int((pd.Timestamp.now(tz="UTC") - dt).total_seconds() // 86400))
                except Exception:
                    age = None
            # Date is required for the 30-day priority/fallback rule.
            if age is None:
                continue
            rows.append({
                "Date": pub,
                "Type": classify(combined),
                "Brokerage": brokerage_firm,
                "Action": action,
                "Target": _extract_brokerage_target(combined),
                "Headline": title,
                "Description": desc,
                "Source": source,
                "Priority": priority,
                "AgeDays": age,
                "Link": link,
            })
            added += 1
        return added

    errors = []
    for label, domains, priority in source_groups:
        for query in queries:
            q = f"{query} site:{domains.split(';')[0]}" if ";" not in domains else f"{query} ({' OR '.join('site:'+d for d in domains.split(';'))})"
            try:
                url = f"https://news.google.com/rss/search?q={quote_plus(q)}&hl=en-IN&gl=IN&ceid=IN:en"
                add_feed(url, label, priority)
            except Exception as e:
                errors.append(f"{label}: {type(e).__name__}")

    out = pd.DataFrame(rows, columns=cols)
    if out.empty:
        msg = "No recent brokerage/upgrade/downgrade coverage found."
        if errors:
            msg += " Sources may be temporarily unavailable."
        return out, msg

    try:
        out["_dt"] = pd.to_datetime(out["Date"], errors="coerce", utc=True)
        now = pd.Timestamp.now(tz="UTC")
        cutoff = now - pd.Timedelta(days=90)
        out = out[out["_dt"].notna() & (out["_dt"] >= cutoff)].copy()
        out["_fresh"] = out["_dt"] >= now - pd.Timedelta(days=30)
        out = out.sort_values(["_fresh", "_dt", "Priority"], ascending=[False, False, True], na_position="last")
        out = out.drop(columns=["_dt", "_fresh"]).head(limit)
        # Preserve the actual publisher article URL whenever the feed supplies a
        # Google News redirect. If redirect resolution fails, keep the feed URL so
        # the user still has a working source link instead of a blank cell.
        if not out.empty:
            out["Link"] = out["Link"].map(lambda u: _resolve_original_source_url(u, headers))
            # Fill missing targets from the original publisher article only.
            # RSS summaries frequently omit the numeric target even though the
            # linked brokerage story contains it (for example, "target Rs 12,096").
            for idx, row in out.iterrows():
                if not str(row.get("Target", "") or "").strip():
                    target = _fetch_article_target(row.get("Link", ""), headers)
                    if target:
                        out.at[idx, "Target"] = target
    except Exception:
        out = out.head(limit)
    return out.reset_index(drop=True), "OK"

def fundamentals(symbol):
    try:
        info = yf.Ticker(symbol).info or {}
    except Exception:
        info = {}
    return {
        "P/E": info.get("trailingPE"), "Forward P/E": info.get("forwardPE"), "ROE": info.get("returnOnEquity"),
        "ROA": info.get("returnOnAssets"), "Debt/Equity": info.get("debtToEquity"),
        "Revenue growth": info.get("revenueGrowth"), "Earnings growth": info.get("earningsGrowth"),
        "Profit margin": info.get("profitMargins"), "Market cap": info.get("marketCap"),
    }

def safe_fundamental_rows(f):
    """Convert yfinance fundamental values into a guaranteed 2-D display table.
    Some providers can return numpy/list-like values for an otherwise scalar field;
    Streamlit/pandas may reject those as non-2-D input.
    """
    rows = []
    for key, value in (f or {}).items():
        try:
            if isinstance(value, np.ndarray):
                if value.size == 1:
                    value = value.reshape(-1)[0].item()
                else:
                    value = ", ".join(map(str, value.reshape(-1).tolist()))
            elif isinstance(value, (list, tuple, set)):
                if len(value) == 1:
                    value = next(iter(value))
                else:
                    value = ", ".join(map(str, value))
            elif isinstance(value, dict):
                value = json.dumps(value, default=str)
        except Exception:
            value = str(value)
        if value is None or (isinstance(value, float) and np.isnan(value)):
            value = "N/A"
        rows.append({"Metric": str(key), "Value": value})
    return pd.DataFrame(rows, columns=["Metric", "Value"])

def _safe_number(value):
    """Return a finite scalar float or NaN. Prevent provider values from breaking scoring."""
    try:
        if isinstance(value, np.ndarray):
            if value.size != 1:
                return np.nan
            value = value.reshape(-1)[0]
        if isinstance(value, (list, tuple, set, dict)):
            return np.nan
        out = float(value)
        return out if np.isfinite(out) else np.nan
    except Exception:
        return np.nan

def _normalize_fundamentals(f):
    """Coerce provider fundamentals to stable scalar numeric values."""
    defaults = {
        "P/E": np.nan, "Forward P/E": np.nan, "ROE": np.nan, "ROA": np.nan,
        "Debt/Equity": np.nan, "Revenue growth": np.nan, "Earnings growth": np.nan,
        "Profit margin": np.nan, "Market cap": np.nan,
    }
    for k in defaults:
        defaults[k] = _safe_number((f or {}).get(k))
    return defaults

def fundamental_score(f):
    # 0-15. Missing data is neutral, not a rejection. Status is shown separately.
    f = _normalize_fundamentals(f)
    checks = []
    if np.isfinite(f["ROE"]): checks.append(3 if f["ROE"] >= .15 else 2 if f["ROE"] >= .10 else 0)
    if np.isfinite(f["Revenue growth"]): checks.append(2 if f["Revenue growth"] > .05 else 1 if f["Revenue growth"] > 0 else 0)
    if np.isfinite(f["Earnings growth"]): checks.append(2 if f["Earnings growth"] > .05 else 1 if f["Earnings growth"] > 0 else 0)
    if np.isfinite(f["Profit margin"]): checks.append(2 if f["Profit margin"] > .10 else 1 if f["Profit margin"] > 0 else 0)
    if np.isfinite(f["Debt/Equity"]): checks.append(2 if f["Debt/Equity"] <= 100 else 1 if f["Debt/Equity"] <= 200 else 0)
    if np.isfinite(f["P/E"]): checks.append(4 if 0 < f["P/E"] < 30 else 2 if 0 < f["P/E"] < 50 else 0)
    if not checks:
        return 7.5, "MISSING"
    raw = sum(checks)
    coverage = min(1.0, len(checks)/6)
    score = raw + (15-raw)*(1-coverage)*0.5
    return round(float(score), 1), "PARTIAL" if coverage < 1 else "FULL"

@st.cache_data(ttl=1800, show_spinner=False)
def event_risk(symbol):
    s = symbol_clean(symbol)
    url = "https://www.nseindia.com/api/corporate-announcements"
    headers = {"User-Agent":"Mozilla/5.0", "Accept":"application/json,text/plain,*/*", "Referer":"https://www.nseindia.com/"}
    try:
        sess = requests.Session(); sess.headers.update(headers)
        sess.get("https://www.nseindia.com", timeout=8)
        r = sess.get(url, params={"index":"equities","symbol":s}, timeout=10)
        r.raise_for_status()
        data = r.json(); rows = data if isinstance(data, list) else data.get("data", [])
        texts = [str(x.get("desc") or x.get("subject") or "") for x in rows[:20]]
        terms = {"fraud":5,"default":5,"insolvency":5,"resignation":2,"pledge":3,"investigation":4,"penalty":3,"fire":3,"accident":3,"downgrade":4,"litigation":3,"debt":2}
        hits=[]; pen=0
        for text in texts:
            low=text.lower()
            for k,v in terms.items():
                if k in low: hits.append(k); pen += v
        return min(pen,10), sorted(set(hits)), pd.DataFrame([{"Subject":t} for t in texts[:10]]), "FRESH"
    except Exception:
        return 0, [], pd.DataFrame(), "UNAVAILABLE"

def entry_quality(r):
    score = 0
    score += 25 if r["Close"] > r["SMA50"] > r["SMA200"] else 12 if r["Close"] > r["SMA200"] else 0
    distance = (r["Close"]/r["BREAKOUT20"] - 1) if r["BREAKOUT20"] else 0
    score += 25 if -0.01 <= distance <= 0.03 else 18 if -0.03 <= distance <= 0.06 else 8 if distance > 0.06 else 12
    score += 20 if r["Close"] > r["BREAKOUT20"] and r["VOL_RATIO"] >= 1.5 else 12 if r["Close"] > 0.98*r["BREAKOUT20"] else 6
    score += 15 if 55 <= r["RSI"] <= 68 else 10 if 50 <= r["RSI"] <= 75 else 4
    score += 15 if r["VOL_RATIO"] >= 1.5 else 10 if r["VOL_RATIO"] >= 1.2 else 5
    return round(min(100, score), 1)

def weekly_status(r):
    if pd.isna(r["WeeklyClose"]): return "UNKNOWN", "⚪"
    if r["WeeklyClose"] > r["WeeklySMA20"] > r["WeeklySMA40"]: return "BULLISH", "🟢"
    if r["WeeklyClose"] > r["WeeklySMA40"]: return "NEUTRAL", "🟡"
    return "BEARISH", "🔴"

def daily_status(r):
    if r["Close"] > r["SMA50"] > r["SMA200"]: return "BULLISH", "🟢"
    if r["Close"] > r["SMA200"]: return "NEUTRAL", "🟡"
    return "BEARISH", "🔴"

def build_ranked_candidates(base, limit=20, enrich_n=40):
    if base.empty:
        return pd.DataFrame(), {}, {}
    regime, _, bench = market_regime()
    bench_ret = float(bench["RET63"]) if bench is not None else 0.0
    base = base.copy()
    base["Sector"] = base["_symbol"].map(sector)
    # Robust sector benchmark: median 63D return of peers, excluding the stock itself
    # when the sector has multiple members.
    sector_counts = base.groupby("Sector")["_symbol"].transform("count")
    sector_sum = base.groupby("Sector")["RET63"].transform("sum")
    base["SectorMedianRET63"] = base.groupby("Sector")["RET63"].transform("median")
    base["SectorPeerCount"] = sector_counts
    eligible = []
    excluded = []
    for _, r in base.iterrows():
        ok, reason = liquidity_status(r)
        if ok:
            eligible.append(r)
        else:
            excluded.append((r["_symbol"], reason))
    if not eligible:
        return pd.DataFrame(), {"Universe": len(base), "Price data available": len(base), "Rankable candidates": 0, "Top 20 returned": 0, "Excluded by price/liquidity": len(excluded)}, {}
    base = pd.DataFrame(eligible).reset_index(drop=True)
    # Recalculate sector medians after price/liquidity eligibility.
    base["SectorMedianRET63"] = base.groupby("Sector")["RET63"].transform("median")
    base["SectorPeerCount"] = base.groupby("Sector")["RET63"].transform("count")
    rows=[]
    for _, r in base.iterrows():
        trend = score_trend(r)
        mom = score_momentum(r)
        sector_median = float(r["SectorMedianRET63"]) if r["SectorPeerCount"] >= 2 else None
        rs_n, rs_s, rsn_raw, rss_raw = score_relative(r, bench_ret, sector_median)
        vol, breakout = score_volume(r)
        entry = entry_quality(r)
        ws, wi = weekly_status(r); ds, di = daily_status(r)
        rows.append({
            "Symbol": r["Symbol"], "_symbol": r["_symbol"], "Sector": r["Sector"], "Trend": trend, "Momentum": mom,
            "RS vs NIFTY": rs_n, "Sector RS": rs_s, "RSNIFTY%": rsn_raw*100,
            "SectorRS%": (rss_raw*100 if np.isfinite(rss_raw) else np.nan),
            "SectorPeerCount": int(r["SectorPeerCount"]), "Volume/Breakout": vol,
            "Close": r["Close"], "SMA50": r["SMA50"], "SMA200": r["SMA200"], "RSI": r["RSI"], "Vol X": r["VOL_RATIO"], "ATR": r["ATR"], "ATR%": r["ATR%"],
            "BREAKOUT20": r["BREAKOUT20"], "SwingLow20": r.SwingLow20, "RET21": r["RET21"], "RET63": r["RET63"], "Weekly": ws, "WeeklyIcon": wi, "Daily": ds,
            "Entry Quality": entry, "Breakout": breakout, "HistoryDays": r.HistoryDays,
            "AvgTradedValue20Cr": r.AvgTradedValue20Cr, "MedianTradedValue20Cr": r.MedianTradedValue20Cr,
            "ActiveVolumeDays20Pct": r.ActiveVolumeDays20Pct,
        })
    scored = pd.DataFrame(rows)
    scored["TechnicalCore"] = scored["Trend"] + scored["Momentum"] + scored["RS vs NIFTY"] + scored["Sector RS"] + scored["Volume/Breakout"]
    scored["RegimeAdj"] = 5 if regime == "BULL" else 2.5 if regime == "NEUTRAL" else 0
    scored["Fundamental"] = 7.5; scored["FundStatus"] = "NOT ENRICHED"
    scored["EventPenalty"] = 0; scored["EventStatus"] = "NOT ENRICHED"; scored["DataQuality"] = 100.0
    scored = scored.sort_values(["TechnicalCore","Entry Quality"], ascending=False).reset_index(drop=True)
    enriched = min(enrich_n, len(scored))
    for idx in range(enriched):
        sym = scored.at[idx, "_symbol"]
        f = fundamentals(sym); fs, fstatus = fundamental_score(f)
        scored.at[idx, "Fundamental"] = fs; scored.at[idx, "FundStatus"] = fstatus
        scored.at[idx, "DataQuality"] = 100.0 if fstatus == "FULL" else 90.0 if fstatus == "PARTIAL" else 80.0
        if idx < min(25, enriched):
            pen, hits, _, estate = event_risk(sym)
            scored.at[idx, "EventPenalty"] = pen; scored.at[idx, "EventStatus"] = estate
            scored.at[idx, "EventHits"] = ", ".join(hits) if hits else ""
        else:
            scored.at[idx, "EventHits"] = ""
    # Exact component maximum: Trend 25 + Momentum 15 + RS 20 + Volume 15 + Fundamentals 15 = 90.
    # Regime is a separate 0-5 modifier and event risk is a 0-10 penalty.
    # Normalize against the maximum achievable score in the current regime.
    max_regime = 5.0 if regime == "BULL" else 2.5 if regime == "NEUTRAL" else 0.0
    max_score = 90.0 + max_regime
    scored["RawScore"] = scored["Trend"] + scored["Momentum"] + scored["RS vs NIFTY"] + scored["Sector RS"] + scored["Volume/Breakout"] + scored["Fundamental"] + scored["RegimeAdj"] - scored["EventPenalty"]
    scored["Score"] = (scored["RawScore"] / max_score * 100).clip(0,100)
    scored["PriorityFit"] = np.select([
        (scored["Weekly"]=="BULLISH") & (scored["Daily"]=="BULLISH") & (regime=="BULL"),
        (scored["Daily"]=="BULLISH") & (scored["Weekly"]!="BEARISH"),
        (scored["Daily"]!="BEARISH")
    ], [100,85,65], default=40)
    scored["PriorityScore"] = (0.60*scored["Score"] + 0.25*scored["Entry Quality"] + 0.15*scored["PriorityFit"]).round(1)
    scored = scored.sort_values(["Score","Entry Quality"], ascending=False).reset_index(drop=True)
    top20 = scored.head(limit).copy(); top20.insert(0, "Rank", np.arange(1,len(top20)+1))
    stop_rows=[]
    for _, row in top20.iterrows():
        stp=derive_stop_from_values(float(row["Close"]), float(row["ATR"]), float(row["SwingLow20"]))
        stop_rows.append(stp)
    stop_df=pd.DataFrame(stop_rows, index=top20.index)
    for col in stop_df.columns: top20[col]=stop_df[col]
    top20["Entry"] = top20["Close"].round(2)
    top20["Signal"] = np.where((top20["Score"]>=75) & (regime!="BEAR"), "PRIORITY CANDIDATE", "WATCH")
    top20["Why"] = top20.apply(lambda x: "; ".join([
        "uptrend" if x["Daily"]=="BULLISH" else "daily trend not bullish",
        "weekly confirmation" if x["Weekly"]=="BULLISH" else f"weekly {x['Weekly'].lower()}",
        "relative strength" if x["RS vs NIFTY"]>=7 else "mixed relative strength",
        "liquid" if x["AvgTradedValue20Cr"]>=MIN_AVG_TRADED_VALUE_CR else "liquidity caution",
        "volume expansion" if x["Vol X"]>=1.5 else "normal volume",
        "breakout" if x["Breakout"] else "near/under breakout",
    ]), axis=1)
    health = {
        "Universe": len(base) + len(excluded), "Price data available": len(base) + len(excluded),
        "Price/liquidity eligible": len(base), "Excluded by price/liquidity": len(excluded),
        "Technical candidates": len(base), "Rankable candidates": len(scored),
        "Enriched candidates": enriched, "Event-enriched": min(25, enriched),
        "Top 20 returned": len(top20), "Data source": load_universe()[1], "Data mode": load_universe()[2],
        "Eligibility": f"Close ≤ ₹{MAX_STOCK_PRICE:,.0f}; 20D avg traded value ≥ ₹{MIN_AVG_TRADED_VALUE_CR:g}Cr; median ≥ ₹{MIN_MEDIAN_TRADED_VALUE_CR:g}Cr; active volume days ≥ {MIN_ACTIVE_VOLUME_DAYS_PCT:g}%",
    }
    return top20, health, scored

def select_top6(top20):
    if top20.empty: return top20.copy()
    chosen=[]; sector_counts={}
    # Greedy diversification: prefer priority score while limiting a sector to 2 names.
    candidates=top20.sort_values("PriorityScore", ascending=False).copy()
    for _, row in candidates.iterrows():
        sec=row["Sector"]; count=sector_counts.get(sec,0)
        if count >= 2 and len(chosen) < 6: continue
        chosen.append(row)
        sector_counts[sec]=count+1
        if len(chosen)==6: break
    if len(chosen)<min(6,len(candidates)):
        used={x["Symbol"] for x in chosen}
        for _, row in candidates.iterrows():
            if row["Symbol"] not in used:
                chosen.append(row)
                if len(chosen)==6: break
    out=pd.DataFrame(chosen).copy()
    if out.empty: return out
    out=out.sort_values("PriorityScore", ascending=False).reset_index(drop=True)
    out["Priority Rank"]=np.arange(1,len(out)+1)
    return out

@st.cache_data(ttl=900, show_spinner=False)
def scan_nse(limit=20):
    """Run the full scan without allowing a provider/data anomaly to crash the app."""
    syms=universe()
    try:
        base, failures=download_prices_batch(syms)
        top20, health, ranked=build_ranked_candidates(base, limit=limit, enrich_n=40)
        health = health or {}
        health["Download failures"] = len(failures)
        health["Failed symbols sample"] = ", ".join(symbol_clean(x) for x in failures[:12])
        health["Status"] = "OK" if not top20.empty else "NO_RANKABLE_CANDIDATES"
        return top20, select_top6(top20), health, ranked
    except Exception as e:
        health={
            "Universe": len(syms), "Price data available": 0, "Price/liquidity eligible": 0,
            "Excluded by price/liquidity": 0, "Technical candidates": 0, "Rankable candidates": 0,
            "Enriched candidates": 0, "Event-enriched": 0, "Top 20 returned": 0,
            "Download failures": 0, "Failed symbols sample": "",
            "Data source": load_universe()[1], "Data mode": load_universe()[2],
            "Status": "SCAN_ERROR", "Error": f"{type(e).__name__}: {e}"
        }
        return pd.DataFrame(), pd.DataFrame(), health, pd.DataFrame()

def _clean_ohlcv_frame(d, symbol=""):
    """Normalize any yfinance single-symbol response into a plain OHLCV DataFrame.

    yfinance can return MultiIndex columns and, depending on version/provider
    behavior, some responses may be wrapped or otherwise non-standard. This
    function is deliberately defensive so a single-stock analysis never tries
    to access ["Close"] on a dict/list-like object.
    """
    if d is None:
        return pd.DataFrame()
    if isinstance(d, dict):
        # Handle common wrapper shapes without assuming a specific provider version.
        for key in (symbol, symbol_clean(symbol), nse_symbol(symbol), "data", "history", "prices"):
            if key in d:
                candidate = d[key]
                if isinstance(candidate, pd.DataFrame):
                    d = candidate
                    break
        else:
            # A dict of column -> values can still be converted safely.
            try:
                d = pd.DataFrame(d)
            except Exception:
                return pd.DataFrame()
    if isinstance(d, pd.Series):
        try:
            d = d.to_frame().T
        except Exception:
            return pd.DataFrame()
    if not isinstance(d, pd.DataFrame) or d.empty:
        return pd.DataFrame()

    d = d.copy()
    if isinstance(d.columns, pd.MultiIndex):
        # Prefer the ticker level when present; otherwise flatten field names.
        levels = [list(map(str, d.columns.get_level_values(i))) for i in range(d.columns.nlevels)]
        target = nse_symbol(symbol)
        selected = None
        for level in range(d.columns.nlevels):
            if target in levels[level]:
                try:
                    selected = d.xs(target, axis=1, level=level, drop_level=True).copy()
                    break
                except Exception:
                    pass
        if selected is not None:
            d = selected
        else:
            # If only one ticker exists, flatten the remaining field level.
            d.columns = [str(c[-1] if isinstance(c, tuple) else c) for c in d.columns]

    # Normalize common casing/naming variants.
    rename = {}
    for c in d.columns:
        raw = str(c).strip().lower().replace(" ", "")
        mapping = {"open":"Open", "high":"High", "low":"Low", "close":"Close",
                   "adjclose":"Adj Close", "volume":"Volume"}
        if raw in mapping:
            rename[c] = mapping[raw]
    d = d.rename(columns=rename)
    needed = ["Open", "High", "Low", "Close", "Volume"]
    if not all(c in d.columns for c in needed):
        return pd.DataFrame()
    d = d[needed].apply(pd.to_numeric, errors="coerce")
    d = d.replace([np.inf, -np.inf], np.nan).dropna(subset=["Open","High","Low","Close"])
    # Volume can occasionally be missing; use zero rather than destroying the
    # price history. Liquidity rules will then correctly reject the stock.
    d["Volume"] = d["Volume"].fillna(0)
    try:
        d.index = pd.to_datetime(d.index)
        if getattr(d.index, "tz", None) is not None:
            d.index = d.index.tz_localize(None)
    except Exception:
        pass
    return d.sort_index()

def load_single_price_history(symbol, period="2y"):
    """Safely load one NSE equity history using Ticker.history first.

    Ticker.history is used for single-stock analysis because it avoids several
    MultiIndex/wrapper edge cases seen with yf.download across yfinance versions.
    A download fallback is retained for resilience.
    """
    sym = nse_symbol(symbol)
    errors = []
    try:
        d = yf.Ticker(sym).history(period=period, interval="1d", auto_adjust=False)
        d = _clean_ohlcv_frame(d, sym)
        if not d.empty:
            if len(d) < 210:
                errors.append(f"only {len(d)} sessions from Ticker.history")
            else:
                return d
    except Exception as e:
        errors.append(f"Ticker.history: {type(e).__name__}")
    try:
        d = yf.download(sym, period=period, interval="1d", auto_adjust=False, progress=False, threads=False)
        d = _clean_ohlcv_frame(d, sym)
        if not d.empty and len(d) >= 210:
            return d
        errors.append(f"download returned {len(d)} clean sessions")
    except Exception as e:
        errors.append(f"download: {type(e).__name__}")
    detail = "; ".join(errors[-3:])
    raise ValueError(f"No usable market data for {symbol_clean(sym)}. {detail}")

def signal(symbol):
    sym=nse_symbol(symbol)
    d=load_single_price_history(sym, period="2y")
    f=daily_features(d)
    if f.empty:
        raise ValueError(f"Not enough clean technical data for {symbol_clean(sym)}.")
    x=f.iloc[-1]
    w=weekly_features(d); wx=w.iloc[-1] if not w.empty else None
    r=feature_row(sym,x,wx,len(d))
    ok, reason = liquidity_status(r)
    if not ok:
        raise ValueError(f"{symbol_clean(sym)} is excluded by V5.2.6 eligibility rules: {reason}")
    try:
        bench_df=benchmark_data()
        bench=bench_df.iloc[-1] if not bench_df.empty else None
        bench_ret=float(bench["RET63"]) if bench is not None and np.isfinite(bench["RET63"]) else 0.0
    except Exception:
        bench_ret=0.0
    # Use the already-scanned universe when available for a robust sector benchmark.
    sector_median=None; peer_count=0
    try:
        if "scan" in st.session_state:
            ranked=st.session_state["scan"][3]
            sec=sector(sym); peers=ranked[ranked["Sector"]==sec]
            if len(peers)>=2:
                sector_median=float(peers["RET63"].median()); peer_count=len(peers)
    except Exception:
        pass
    trend=score_trend(pd.Series(r)); mom=score_momentum(pd.Series(r))
    rsn,rss,rsnr,rsstr=score_relative(pd.Series(r),bench_ret,sector_median if peer_count>=2 else None)
    vol,br=score_volume(pd.Series(r))
    fq,fstatus=fundamental_score(fundamentals(sym)); regime,_,_=market_regime(); pen,hits,ann,estate=event_risk(sym)
    max_regime=5.0 if regime=="BULL" else 2.5 if regime=="NEUTRAL" else 0.0
    max_score=90.0+max_regime
    score=float(np.clip((trend+mom+rsn+rss+vol+fq+max_regime-pen)/max_score*100,0,100))
    stp=derive_stop_target(d,entry=float(x["Close"]))
    ws,wi=weekly_status(pd.Series(r)); ds,di=daily_status(pd.Series(r))
    eq=entry_quality(pd.Series(r))
    signal_name="PRIORITY CANDIDATE" if score>=75 and regime!="BEAR" else "WATCH"
    result={"Symbol":symbol_clean(sym),"Sector":sector(sym),"Score":round(score,1),"Trend":trend,"Momentum":mom,"RS vs NIFTY":rsn,"Sector RS":rss,"Volume/Breakout":vol,"Fundamental":fq,"Fundamental status":fstatus,"Event penalty":pen,"Event status":estate,"RS vs NIFTY %":round(rsnr*100,2),"Sector RS %":round(rsstr*100,2) if np.isfinite(rsstr) else None,"Sector peer count":peer_count,"RSI":round(float(x["RSI"]),1),"Vol X":round(float(x["VOL_RATIO"]),2),"ATR %":round(float(x["ATR%"]),2),"20D avg traded value ₹Cr":round(float(x["AVG_TRADED_VALUE20"]/1e7),2),"20D median traded value ₹Cr":round(float(x["MEDIAN_TRADED_VALUE20"]/1e7),2),"Active volume days %":round(float(x["ACTIVE_VOLUME_DAYS20"]),1),"Weekly":ws,"Daily":ds,"Entry Quality":eq,"Entry":round(float(x["Close"]),2),"Signal":signal_name,"DataQuality":100.0 if fstatus=="FULL" else 90.0 if fstatus=="PARTIAL" else 80.0,**stp,"Event hits":hits}
    return result, d, fundamentals(sym), ann

def risk_size(cap,riskpct,entry,stop,maxpos):
    rps=abs(entry-stop); budget=cap*riskpct/100; shares=int(budget/rps) if rps else 0
    shares=min(shares,int(cap*maxpos/100/entry)) if entry else 0
    return shares,shares*entry,shares*rps

def costs(value, bps): return value*bps/10000

def backtest(sym,initial,riskpct,maxpos,fee_bps,slip_bps):
    d=load_single_price_history(sym, period="5y")
    d=daily_features(d)
    if d.empty or len(d) < 210:
        raise ValueError("Insufficient history for backtest.")
    cash=initial;pos=None;trades=[];equity=[]
    for i in range(200,len(d)-1):
        r=d.iloc[i]
        if pos:
            exit_px=None;reason=None
            if r["Low"]<=pos["stop"]: exit_px=pos["stop"];reason="STOP"
            elif r["High"]>=pos["target"]: exit_px=pos["target"];reason="TARGET"
            elif r["Close"]<r["SMA50"]: exit_px=float(r["Close"]);reason="TREND EXIT"
            if exit_px is not None:
                gross=(exit_px-pos["entry"])*pos["shares"];turn=exit_px*pos["shares"]+pos["entry"]*pos["shares"];all_cost=costs(turn,fee_bps+slip_bps);cash+=exit_px*pos["shares"]-all_cost
                trades.append([pos["date"],d.index[i],pos["entry"],exit_px,pos["shares"],gross-all_cost,reason]);pos=None
        if pos is None and r["Close"]>r["BREAKOUT20"] and r["Close"]>r["SMA50"]>r["SMA200"] and r["VOL_RATIO"]>=1.5:
            en=float(d.iloc[i+1]["Open"])
            try:
                stp=derive_stop_target(d.iloc[:i+1], entry=en); stop=stp["Stop"]; target=stp["Target"]
            except Exception:
                stop=en-2*float(r["ATR"]); target=en+DEFAULT_R_MULTIPLE*(en-stop)
            sh=int((cash*riskpct/100)/(en-stop));sh=min(sh,int(cash*maxpos/100/en)) if en else 0
            if sh:
                cost=en*sh;cash-=cost+costs(cost,fee_bps+slip_bps);pos={"date":d.index[i+1],"entry":en,"stop":stop,"target":target,"shares":sh}
        equity.append([d.index[i],cash+(pos["shares"]*r["Close"] if pos else 0)])
    eq=pd.DataFrame(equity,columns=["Date","Equity"]).set_index("Date")
    tr=pd.DataFrame(trades,columns=["Entry","Exit","EntryPrice","ExitPrice","Shares","PnL","Reason"])
    return eq,tr

def build_alerts(top20):
    if top20 is None or top20.empty:
        return []
    alerts=[]
    for _, r in top20.iterrows():
        if r["Close"] <= r["BREAKOUT20"] and r["BREAKOUT20"] > 0:
            gap=(r["BREAKOUT20"]-r["Close"])/r["Close"]*100
            if 0 <= gap <= 2:
                alerts.append({"Type":"ENTRY ZONE","Symbol":r["Symbol"],"Message":f"{r['Symbol']} is within {gap:.1f}% of its 20D breakout level."})
        if r.get("EventPenalty",0) > 0:
            alerts.append({"Type":"EVENT RISK","Symbol":r["Symbol"],"Message":f"{r['Symbol']} has an event-risk penalty of {int(r['EventPenalty'])}/10; verify the underlying filing."})
        if r["Weekly"] == "UNKNOWN":
            alerts.append({"Type":"DATA","Symbol":r["Symbol"],"Message":f"{r['Symbol']} weekly confirmation is UNKNOWN."})
    return alerts[:30]

def make_ai_prompt(snapshot):
    return f"""You are a skeptical NSE positional-trading research assistant.\n\nHolding period: 2–12 weeks.\n\nMachine snapshot:\n{json.dumps(snapshot,indent=2,default=str)}\n\nUse current, verifiable information and official company disclosures where possible. Separate FACTS from INTERPRETATION. Do not invent missing figures. Do not give guaranteed returns or a future price prediction.\n\nChallenge this setup rather than simply agreeing with it. Review: market regime, weekly/daily trend alignment, relative strength vs NIFTY and sector, breakout quality, volume, RSI, valuation, earnings/revenue growth, ROE/ROCE, leverage/cash flow, promoter/institutional information when verified, recent corporate announcements, event risks, liquidity, and portfolio concentration.\n\nReturn:\n1) Evidence table\n2) Bull case\n3) Bear case\n4) Strongest reasons NOT to take the trade\n5) What would invalidate the setup\n6) Missing/uncertain information\n7) WATCH / PRIORITY-CANDIDATE / AVOID\n8) Confidence level and why\n"""

st.title(f"📈 NSE Positional Trader {APP_VERSION}")
st.caption("Stability release • Top 20 → Top 6 • robust data handling • no live orders")

if st.button("🔄 Refresh all cached data"):
    st.cache_data.clear(); st.session_state.pop("scan",None); st.rerun()

# Optional deep-link into individual stock analysis from shortlist tables.
_stock_q = st.query_params.get("stock", "")
_stock_q = symbol_clean(_stock_q) if _stock_q else ""
_section_q = str(st.query_params.get("section", "")).lower()
_stock_deeplink = bool(_stock_q and _stock_q in {symbol_clean(x) for x in universe()})

# Navigation hand-off used by shortlist Analyze buttons.  We set the widget state
# on the run BEFORE the segmented_control is created; this avoids Streamlit's
# widget-state assignment restriction and makes the action reliable on mobile.
if st.session_state.pop("_pending_stock_nav", False):
    st.session_state["section_nav"] = "🔍 Stock"

_default_section = "🔍 Stock" if (_stock_deeplink or _section_q == "stock") else "🏠 Dashboard"
if "section_nav" not in st.session_state:
    st.session_state["section_nav"] = _default_section
tab=st.segmented_control("Section",["🏠 Dashboard","🏆 Top 20/Top 6","🔎 Scanner","🚀 5-Min HA","🔍 Stock","📊 Backtest","💼 Portfolio","📝 Journal","🤖 AI"],key="section_nav")

def _open_stock_analysis(symbol, key_prefix):
    s = symbol_clean(symbol)
    if st.button("🔍 Analyze", key=f"{key_prefix}_{s}", use_container_width=True):
        st.session_state["_pending_stock"] = s
        st.session_state["_pending_stock_nav"] = True
        st.query_params["stock"] = s
        st.query_params["section"] = "stock"
        st.session_state.pop("stock_analysis", None)
        st.rerun()

def _render_analysis_table(df, key_prefix):
    """Render shortlist data as a real responsive table plus a safe in-app Analyze control.

    The previous implementation used Streamlit columns for every cell and then placed a
    full-width button outside those columns. On narrow/mobile screens Streamlit stacks
    the columns vertically, making the table look like a long list and separating the
    Analyze button from its row. Keep the data itself in st.dataframe so it remains a
    proper table, and use one explicit stock selector + Analyze button below it.
    """
    if df is None or df.empty:
        st.info("No candidates returned.")
        return

    table = df.reset_index(drop=True).copy()
    preferred = ["Rank","Symbol","Score","Entry Quality","Entry","Stop","Target","R:R","Signal"]
    visible = [c for c in preferred if c in table.columns]
    if not visible:
        visible = list(table.columns)
    table = table[visible]

    st.dataframe(table, use_container_width=True, hide_index=True)

    symbols = [symbol_clean(x) for x in df["Symbol"].dropna().astype(str).tolist()] if "Symbol" in df.columns else []
    symbols = list(dict.fromkeys(x for x in symbols if x))
    if not symbols:
        return

    c1, c2 = st.columns([2.2, 1.0])
    with c1:
        selected = st.selectbox("Stock to analyze", symbols, key=f"{key_prefix}_select")
    with c2:
        st.write("")
        st.write("")
        analyze = st.button("🔍 Analyze", key=f"{key_prefix}_analyze", use_container_width=True)
    if analyze:
        # Store the selection before rerun. On the next run the navigation widget
        # is initialized to Stock first, then the existing stock-analysis path
        # automatically runs for this symbol.
        st.session_state["_pending_stock"] = selected
        st.session_state["_pending_stock_nav"] = True
        st.query_params["stock"] = selected
        st.query_params["section"] = "stock"
        st.session_state.pop("stock_analysis", None)
        st.rerun()

if tab=="🏠 Dashboard":
    rg,ico,bx=market_regime()
    c1,c2,c3=st.columns(3)
    if bx is not None:
        c1.metric("NIFTY 50",f"{bx["Close"]:,.0f}"); c3.metric("Benchmark data",str(benchmark_data().index[-1].date()))
    else:
        c1.metric("NIFTY 50","Unavailable"); c3.metric("Benchmark data","Unavailable")
    c2.metric("Regime",f"{ico} {rg}")
    st.info("V5.2.10 uses free public/provider data by default. It is research/paper-trading software, not a licensed real-time NSE feed and not a live broker execution system.")
    st.subheader("🚀 One-tap NSE scan")
    st.write("Scan the full available Nifty 200 universe, rank the best 20 candidates, then select a diversified Top 6 priority list.")
    if st.button("🚀 Scan NSE → Top 20 + Top 6",key="dashscan"):
        with st.spinner("Scanning NSE universe. This can take a few minutes on free cloud data providers…"):
            result=scan_nse(20)
        st.session_state["scan"]=result
    if "scan" in st.session_state:
        top20,top6,health,ranked=st.session_state["scan"]
        st.subheader("📊 Scan health")
        cols=st.columns(4)
        cols[0].metric("Universe",health["Universe"]); cols[1].metric("Price data",health["Price data available"]); cols[2].metric("Rankable",health["Rankable candidates"]); cols[3].metric("Top 20",health["Top 20 returned"])
        st.caption(f"Source: {health['Data source']} • Mode: {health['Data mode']} • Download failures: {health['Download failures']}")
        if health["Download failures"]:
            st.warning(f"Some symbols could not be downloaded. Sample: {health['Failed symbols sample'] or 'not available'}")
        if health["Top 20 returned"]<20:
            st.warning("Fewer than 20 candidates were rankable. This is a data-availability limitation, not a reason to invent rows.")
        st.subheader("🏆 Top 20 research shortlist")
        display=["Rank","Symbol","Sector","Score","Entry Quality","Weekly","Daily","Trend","Momentum","RS vs NIFTY","Sector RS","Vol X","Fundamental","FundStatus","EventPenalty","DataQuality","Entry","Stop","Target","Signal"]
        if top20.empty:
            st.warning(f"No candidates could be ranked. Status: {health.get('Status','UNKNOWN')}. {health.get('Error','Check Scan Health and data availability.')}")
        else:
            _show = top20[[c for c in display if c in top20.columns]].copy()
            _render_analysis_table(_show, "dashboard_top20")
            st.download_button("⬇️ Export Top 20",top20.to_csv(index=False),"v5_2_top20.csv","text/csv",key="top20csv")
        st.subheader("🎯 Top 6 priority setups")
        st.caption("Priority = 60% V5 score + 25% entry quality + 15% regime/portfolio fit, with a soft sector concentration cap of two names per sector.")
        display6=["Priority Rank","Symbol","Sector","PriorityScore","Score","Entry Quality","PriorityFit","Weekly","Daily","RS vs NIFTY","Vol X","Fundamental","EventPenalty","Entry","Stop","Target","Signal"]
        if top6.empty:
            st.info("Top 6 is unavailable until at least one candidate is rankable.")
        else:
            _show = top6[[c for c in display6 if c in top6.columns]].copy()
            _render_analysis_table(_show, "top20_tab")
            st.download_button("⬇️ Export Top 6",top6.to_csv(index=False),"v5_2_top6.csv","text/csv",key="top6csv")
        st.subheader("🔔 Alerts")
        alerts=build_alerts(top20)
        if alerts:
            st.dataframe(pd.DataFrame(alerts),use_container_width=True,hide_index=True)
        else:
            st.success("No current in-app alerts from the Top 20 snapshot.")

elif tab=="🏆 Top 20/Top 6":
    st.subheader("🏆 Top 20 → 🎯 Top 6")
    if st.button("🚀 Run fresh scan",key="topfresh"):
        with st.spinner("Scanning…"):
            st.session_state["scan"]=scan_nse(20)
    if "scan" not in st.session_state:
        st.info("Run the fresh scan to populate the shortlist.")
    else:
        top20,top6,health,ranked=st.session_state["scan"]
        st.write("### Top 20 research list")
        if top20.empty:
            st.warning(f"No candidates could be ranked. {health.get('Error','Review Scan Health.')}")
        else:
            cols20=["Rank","Symbol","Sector","Score","Entry Quality","Weekly","Daily","RS vs NIFTY","Sector RS","Vol X","Fundamental","FundStatus","EventPenalty","DataQuality"]
            _show = top20[[c for c in cols20 if c in top20.columns]].copy()
            _render_analysis_table(_show, "top6_tab")
        st.write("### Top 6 priority list")
        if top6.empty:
            st.info("No Top 6 candidates available.")
        else:
            cols6=["Priority Rank","Symbol","Sector","PriorityScore","Score","Entry Quality","PriorityFit","Weekly","Daily","RS vs NIFTY","Sector RS","Vol X","Fundamental","EventPenalty"]
            _show = top6[[c for c in cols6 if c in top6.columns]].copy()
            _render_analysis_table(_show, "scanner_top20")
            st.write("### Why the candidates ranked")
            for _,r in top6.iterrows():
                st.write(f"**{int(r['Priority Rank'])}. {r['Symbol']}** — {r['Why']}")
        st.write("### 🔔 Alerts")
        alerts=build_alerts(top20)
        if alerts: st.dataframe(pd.DataFrame(alerts),use_container_width=True,hide_index=True)
        else: st.success("No current in-app alerts from the Top 20 snapshot.")

elif tab=="🔎 Scanner":
    u=universe(); source=load_universe()[1]
    st.caption(f"Universe: {len(u)} symbols • source: {source}. Critical price-data failure can exclude a symbol; missing fundamentals/news/weekly data do not automatically exclude it.")
    mode=st.radio("Mode",["🏆 Automatic Top 20 + Top 6","🎯 My 32 → Top 10","🎯 Custom selection"],horizontal=True)
    if mode.startswith("🏆"):
        if st.button("🚀 Run corrected NSE scan",key="scannerfresh"):
            with st.spinner("Downloading and ranking the NSE universe…"):
                st.session_state["scan"]=scan_nse(20)
        if "scan" in st.session_state:
            top20,top6,health,ranked=st.session_state["scan"]
            st.json(health)
            if top20.empty:
                st.warning(f"No candidates could be ranked. {health.get('Error','Review Scan Health.')}")
            else:
                cols20=["Rank","Symbol","Sector","Score","Entry Quality","Weekly","Daily","Trend","Momentum","RS vs NIFTY","Sector RS","Vol X","Fundamental","FundStatus","EventPenalty","DataQuality","Entry","Stop","Target"]
                _show = top20[[c for c in cols20 if c in top20.columns]].copy()
                _render_analysis_table(_show, "scanner_top20")
    elif mode.startswith("🎯 My 32"):
        st.caption(f"Your filtered watchlist: {len(FILTERED_STOCKS)} stocks • same V5.2.6 scoring/eligibility logic • no formula changes.")
        if st.button("🚀 Scan my 32 → Top 10",key="filtered32scan"):
            with st.spinner("Downloading and ranking your 32 filtered stocks…"):
                try:
                    base, failures = download_prices_batch(FILTERED_STOCKS)
                    top10, health, ranked = build_ranked_candidates(base, limit=10, enrich_n=32)
                    health = dict(health or {})
                    health.update({"Filtered watchlist": len(FILTERED_STOCKS), "Download failures": len(failures), "Failed symbols sample": ", ".join(symbol_clean(x) for x in failures[:12]), "Status": "OK" if not top10.empty else "NO_RANKABLE_CANDIDATES"})
                    st.session_state["filtered_scan"] = (top10, health, ranked)
                except Exception as e:
                    st.session_state["filtered_scan"] = (pd.DataFrame(), {"Filtered watchlist": len(FILTERED_STOCKS), "Status": "SCAN_ERROR", "Error": f"{type(e).__name__}: {e}"}, pd.DataFrame())
        if "filtered_scan" in st.session_state:
            top10, health, ranked = st.session_state["filtered_scan"]
            st.write("### 🎯 My 32 → Top 10")
            st.json(health)
            if top10.empty:
                st.warning(f"No candidates could be ranked. {health.get('Error','Review Scan Health.')}")
            else:
                cols=["Rank","Symbol","Sector","Score","Entry Quality","Weekly","Daily","Trend","Momentum","RS vs NIFTY","Sector RS","Vol X","Fundamental","FundStatus","EventPenalty","DataQuality","Entry","Stop","Target","StopMethod"]
                _show = top10[[c for c in cols if c in top10.columns]].copy()
                # Use the same in-app Analyze action as Top 20/Top 6.
                # Do not construct a URL or depend on an undefined link helper.
                _render_analysis_table(_show, "my32_top10")
                st.download_button("⬇️ Export My Top 10",top10.to_csv(index=False),"my32_top10.csv","text/csv",key="my32top10csv")
    else:
        sel=st.multiselect("Select stocks",u,default=u[:10])
        if st.button("🚀 Run custom scanner",key="custom"):
            rows=[]
            with st.spinner("Analyzing selected stocks…"):
                for s in sel:
                    try:
                        r,_,_,_=signal(s); rows.append(r)
                    except Exception as e:
                        st.warning(f"{symbol_clean(s)}: {e}")
            if rows: st.dataframe(pd.DataFrame(rows).sort_values("Score",ascending=False),use_container_width=True,hide_index=True)

elif tab=="🚀 5-Min HA":
    st.write("### 🚀 5-Min Heikin-Ashi Momentum")
    st.caption("Scans only your 32 filtered stocks. Requires the latest two COMPLETED 5-minute candles to be green; confirmation factors rank the strongest setups.")
    st.warning("This is a short-term setup scanner, not a guaranteed prediction. Intraday data may be delayed or unavailable; no signal is generated from stale daily data.")
    if st.button("🔄 Scan my 32 now", key="ha32scan", use_container_width=True):
        with st.spinner("Fetching completed 5-minute candles for your 32 stocks…"):
            try:
                ha_top5, ha_failures = scan_filtered_5m_ha()
                st.session_state["ha5_scan"] = (ha_top5, ha_failures, datetime.now(timezone.utc))
            except Exception as e:
                st.session_state["ha5_scan"] = (pd.DataFrame(), FILTERED_STOCKS, datetime.now(timezone.utc))
                st.error(f"5-minute scanner unavailable: {type(e).__name__}: {e}")
    if "ha5_scan" in st.session_state:
        ha_top5, ha_failures, ha_ts = st.session_state["ha5_scan"]
        if ha_top5.empty:
            st.info("No stocks currently meet the mandatory 2-consecutive-green completed Heikin-Ashi condition.")
        else:
            display = ha_top5[["Rank","Symbol","Last Price","HA Time","HA Body","Volume X","VWAP","Momentum %","HA Score","Setup"]].copy()
            display["Last Price"] = display["Last Price"].map(lambda x: f"₹{x:,.2f}")
            display["HA Body"] = display["HA Body"].map(lambda x: f"{x:.0%}")
            display["Volume X"] = display["Volume X"].map(lambda x: f"{x:.1f}×" if pd.notna(x) else "—")
            display["VWAP"] = display["VWAP"].map(lambda x: f"₹{x:,.2f}" if pd.notna(x) else "—")
            display["Momentum %"] = display["Momentum %"].map(lambda x: f"{x:+.2f}%")
            display["HA Score"] = display["HA Score"].map(lambda x: f"{x:.1f}")
            st.dataframe(display, use_container_width=True, hide_index=True)
            st.caption(f"Scanned: {len(FILTERED_STOCKS)} stocks • qualifying Top {len(ha_top5)} • last scan: {ha_ts.astimezone().strftime('%d-%b-%Y %H:%M:%S')}")
            if ha_failures:
                st.caption("Data unavailable/stale for: " + ", ".join(ha_failures[:12]) + (" …" if len(ha_failures) > 12 else ""))

elif tab=="🔍 Stock":
    _u = universe()
    # A shortlist Analyze click supplies _pending_stock before rerun. Seed the
    # selectbox widget state BEFORE it is created so Streamlit cannot retain the
    # previously selected stock on mobile. The same mechanism also handles a
    # direct stock query parameter.
    _pending = symbol_clean(st.session_state.pop("_pending_stock", ""))
    _requested = _pending or _stock_q
    # Match by cleaned symbol because the universe normally contains Yahoo-style
    # tickers (e.g. HAL.NS) while shortlist rows use NSE symbols (HAL).
    _requested_raw = next((x for x in _u if symbol_clean(x) == _requested), None) if _requested else None
    if _requested_raw is not None:
        st.session_state["stock_selector"] = _requested_raw
    sym=st.selectbox("NSE stock",_u,key="stock_selector")
    st.caption(f"Eligibility: close ≤ ₹{MAX_STOCK_PRICE:,.0f} and liquid (20D avg traded value ≥ ₹{MIN_AVG_TRADED_VALUE_CR:g}Cr, median ≥ ₹{MIN_MEDIAN_TRADED_VALUE_CR:g}Cr, active volume days ≥ {MIN_ACTIVE_VOLUME_DAYS_PCT:g}%).")
    _auto_key = f"deep_analyzed_{symbol_clean(sym)}"
    _should_auto = bool(_requested and symbol_clean(sym) == _requested and not st.session_state.get(_auto_key, False))
    if st.button("Analyze stock",key="anstock") or _should_auto:
        with st.spinner("Loading stock data…"):
            try:
                st.session_state["stock_analysis"]=signal(sym)
                st.session_state[_auto_key] = True
                # The query parameter has done its job; keeping the selected widget
                # state is sufficient and prevents accidental re-analysis loops.
                if _stock_q:
                    try:
                        st.query_params.clear()
                    except Exception:
                        pass
            except Exception as e: st.error(str(e))
    if "stock_analysis" in st.session_state:
        r,d,f,ann=st.session_state["stock_analysis"]
        a,b,c,d1=st.columns(4); a.metric("Score",r["Score"]); b.metric("Entry quality",r["Entry Quality"]); c.metric("RSI",r["RSI"]); d1.metric("Signal",r["Signal"] if "Signal" in r else ("PRIORITY" if r["Score"]>=75 else "WATCH"))
        fig=go.Figure(); fig.add_trace(go.Candlestick(x=d.index,open=d["Open"],high=d["High"],low=d["Low"],close=d["Close"],name="Price"));
        dd=daily_features(d); fig.add_trace(go.Scatter(x=dd.index,y=dd["SMA50"],name="SMA50")); fig.add_trace(go.Scatter(x=dd.index,y=dd["SMA200"],name="SMA200")); fig.update_layout(height=420,xaxis_rangeslider_visible=False,margin=dict(l=5,r=5,t=5,b=5)); st.plotly_chart(fig,use_container_width=True)
        st.subheader("Decision sheet"); st.json(r)
        st.subheader("Fundamentals")
        try:
            ftable = safe_fundamental_rows(f)
            st.dataframe(ftable, use_container_width=True, hide_index=True)
        except Exception as e:
            st.warning(f"Fundamental data could not be displayed safely: {e}")
            st.json({str(k): str(v) for k, v in (f or {}).items()})
        st.subheader("Recent announcement sample")
        st.dataframe(ann, use_container_width=True, hide_index=True)
        st.caption("Verify material announcements against the original NSE/company disclosure before acting.")

        st.subheader("🏦 Brokerage Updates")
        st.caption("Simple information-only table • Last 30 days prioritized • Zee Business → CNBC-TV18 → secondary financial sources. Brokerage calls never modify scoring, entry, stop, target, eligibility or ranking.")

        # Brokerage reports are deliberately independent of the trading formulas.
        # They can also be fetched without first running the technical/fundamental analysis.
        _broker_key = f"brokerage_updates_{symbol_clean(sym)}"
        _fetch_broker_now = st.button("📰 Fetch latest brokerage updates", key=f"{_broker_key}_button", use_container_width=True)
        if _fetch_broker_now or st.session_state.get("brokerage_updates_symbol") == symbol_clean(sym) or "stock_analysis" in st.session_state:
            if _fetch_broker_now or st.session_state.get("brokerage_updates_symbol") != symbol_clean(sym):
                with st.spinner("Fetching recent brokerage reports…"):
                    _broker_df, _broker_status = fetch_brokerage_updates(sym, limit=10)
                st.session_state["brokerage_updates_symbol"] = symbol_clean(sym)
                st.session_state["brokerage_updates_df"] = _broker_df
                st.session_state["brokerage_updates_status"] = _broker_status
            else:
                _broker_df = st.session_state.get("brokerage_updates_df", pd.DataFrame())
                _broker_status = st.session_state.get("brokerage_updates_status", "")

            if _broker_status != "OK":
                st.info(_broker_status or "No recent brokerage/upgrade/downgrade coverage found.")
            elif _broker_df is None or _broker_df.empty:
                st.info("No recent brokerage/upgrade/downgrade coverage found for this stock in the available public sources.")
            else:
                _b = _broker_df.copy()
                _b["_text"] = (_b.get("Headline", "").fillna("").astype(str) + " " + _b.get("Description", "").fillna("").astype(str))

                # Verified brokerage/action fields are produced by the fetch layer.
                # Keep a defensive fallback for older cached rows.
                def _broker_firm(h):
                    firm = _brokerage_firm_from_text(h)
                    return firm or "Other / not stated"

                def _action(h):
                    return _brokerage_action_from_text(h) or "Target / Rating"

                def _target(h):
                    target = _extract_brokerage_target(h)
                    return target or "—"

                if "Brokerage" not in _b.columns:
                    _b["Brokerage"] = _b["_text"].map(_broker_firm)
                else:
                    _b["Brokerage"] = _b["Brokerage"].fillna("").astype(str)
                    _b.loc[_b["Brokerage"].eq(""), "Brokerage"] = _b.loc[_b["Brokerage"].eq(""), "_text"].map(_broker_firm)
                if "Action" not in _b.columns:
                    _b["Action"] = _b["_text"].map(_action)
                else:
                    _b["Action"] = _b["Action"].fillna("").astype(str)
                    _b.loc[_b["Action"].eq(""), "Action"] = _b.loc[_b["Action"].eq(""), "_text"].map(_action)
                if "Target" not in _b.columns:
                    _b["Target"] = ""
                _b["Target"] = _b["Target"].fillna("").astype(str)
                _missing_target = _b["Target"].str.strip().eq("") | _b["Target"].eq("—")
                _b.loc[_missing_target, "Target"] = _b.loc[_missing_target, "_text"].map(_target)
                _b["Target"] = _b["Target"].replace("", "—")
                _b["Window"] = _b["AgeDays"].apply(lambda x: "Last 30 days" if pd.notna(x) and x <= 30 else "31–90 days")
                _b["Date"] = pd.to_datetime(_b["Date"], errors="coerce", utc=True).dt.strftime("%d-%b-%Y")
                # Keep the simple grid. IMPORTANT: do not retain both the publisher
                # "Source" field and the article "Link" under the same column name.
                # That creates duplicate pandas column labels and makes
                # _display["Source"].str fail with: AttributeError: DataFrame has no
                # attribute "str". The clickable Source column below is the original
                # article URL captured from the feed item.
                _display = _b[["Date", "Brokerage", "Action", "Target", "Link", "Window", "Headline"]].copy()
                _display = _display.rename(columns={"Headline": "Report / headline", "Link": "Source"})
                _display = _display.loc[:, ~_display.columns.duplicated()].copy()
                _display["Source"] = _display["Source"].fillna("").astype(str)
                _display.loc[~_display["Source"].str.match(r"^https?://", na=False), "Source"] = ""
                try:
                    cfg = {"Source": st.column_config.LinkColumn("Source", display_text="Open report", validate=r"^https?://")}
                    st.dataframe(_display, use_container_width=True, hide_index=True, column_config=cfg)
                except Exception:
                    # Older Streamlit fallback: retain the source URL as visible text.
                    st.dataframe(_display, use_container_width=True, hide_index=True)
                st.caption("Fresh 0–30 day reports are shown first; 31–90 day items are fallback context. Target values are extracted from the report headline/summary when stated; verify the original report before relying on a target or rating.")

elif tab=="📊 Backtest":
    sym=st.selectbox("Stock",universe()); initial=st.number_input("Initial capital ₹",100000.,100000000.,1000000.,100000.); rp=st.number_input("Risk/trade %",.1,3.,.75,.05); mp=st.number_input("Max position %",5.,50.,20.,1.); fee=st.number_input("Fees/taxes bps",0.,100.,10.,1.); slip=st.number_input("Slippage bps",0.,100.,5.,1.)
    if st.button("▶️ Run backtest"):
        try:
            eq,tr=backtest(sym,initial,rp,mp,fee,slip); dd=eq.Equity/eq.Equity.cummax()-1
            a,b,c,d=st.columns(4); a.metric("Final",f"₹{eq.Equity.iloc[-1]:,.0f}"); b.metric("Return",f"{(eq.Equity.iloc[-1]/initial-1)*100:.1f}%"); c.metric("Max DD",f"{dd.min()*100:.1f}%"); d.metric("Trades",len(tr))
            if len(tr): st.metric("Win rate",f"{(tr.PnL>0).mean()*100:.1f}%")
            st.plotly_chart(go.Figure(go.Scatter(x=eq.index,y=eq.Equity,mode="lines")),use_container_width=True); st.dataframe(tr,use_container_width=True,hide_index=True)
            st.caption("Historical simulation only. It does not remove survivorship bias from a current constituent universe and is not a prediction.")
        except Exception as e: st.error(str(e))

elif tab=="💼 Portfolio":
    st.subheader("Paper portfolio risk")
    cap=st.number_input("Portfolio equity ₹",100000.,100000000.,1000000.,100000.); rp=st.number_input("Risk/trade %",.1,3.,.75,.05); mp=st.number_input("Max position %",5.,50.,20.,1.)
    if "portfolio" not in st.session_state: st.session_state.portfolio=[]
    sym=st.selectbox("Candidate",universe());
    try: r,_,_,_=signal(sym); sh,val,loss=risk_size(cap,rp,r["Entry"],r["Stop"],mp)
    except Exception as e: r=None; st.warning(str(e)); sh=val=loss=0
    a,b,c=st.columns(3); a.metric("Shares",sh); b.metric("Position",f"₹{val:,.0f}"); c.metric("Risk",f"₹{loss:,.0f}")
    if st.button("➕ Add paper position") and r:
        st.session_state.portfolio.append({"Date":datetime.now().date(),"Symbol":r["Symbol"],"Sector":r["Sector"],"Entry":r["Entry"],"Stop":r["Stop"],"Target":r["Target"],"Shares":sh,"Risk₹":loss,"Score":r["Score"],"Entry Quality":r["Entry Quality"],"Regime":market_regime()[0]})
    if st.session_state.portfolio:
        pf=pd.DataFrame(st.session_state.portfolio); st.dataframe(pf,use_container_width=True,hide_index=True); st.metric("Total planned risk",f"₹{pf['Risk₹'].sum():,.0f}"); st.download_button("⬇️ Export portfolio",pf.to_csv(index=False),"paper_portfolio.csv","text/csv")

elif tab=="📝 Journal":
    st.subheader("Trade journal")
    cols=["Date","Symbol","Setup","Entry","Stop","Target","Shares","Risk₹","Result","R","Notes"]
    if "journal" not in st.session_state: st.session_state.journal=pd.DataFrame(columns=cols)
    with st.form("trade_journal_form_v525"):
        sym=st.text_input("Symbol"); setup=st.selectbox("Setup",["Breakout","Retest","Trend continuation","Pullback","Other"]); a,b=st.columns(2); en=a.number_input("Entry ₹",0.); sp=b.number_input("Stop ₹",0.); a,b=st.columns(2); tg=a.number_input("Target ₹",0.); sh=b.number_input("Shares",0,1000000,0); res=st.selectbox("Result",["OPEN","WIN","LOSS","BREAKEVEN"]); notes=st.text_area("Notes"); ok=st.form_submit_button("Add")
    if ok and sym:
        risk=abs(en-sp)*sh; pnl=(tg-en)*sh if res=="WIN" else -risk if res=="LOSS" else 0
        row={"Date":datetime.now().date(),"Symbol":symbol_clean(sym),"Setup":setup,"Entry":en,"Stop":sp,"Target":tg,"Shares":sh,"Risk₹":risk,"Result":res,"R":pnl/risk if risk else 0,"Notes":notes}
        st.session_state.journal=pd.concat([st.session_state.journal,pd.DataFrame([row])],ignore_index=True)
    st.dataframe(st.session_state.journal,use_container_width=True,hide_index=True); st.download_button("⬇️ Export journal",st.session_state.journal.to_csv(index=False),"trade_journal.csv","text/csv")

else:
    st.subheader("🤖 AI second opinion")
    st.caption("The AI prompt is deliberately adversarial: it is asked to search for reasons not to take the setup.")
    sym=st.text_input("Stock", "RELIANCE.NS")
    if st.button("Generate AI research packet"):
        try:
            r,_,_,_=signal(sym); prompt=make_ai_prompt(r); st.session_state["ai_prompt"]=prompt
        except Exception as e: st.error(str(e))
    if "ai_prompt" in st.session_state:
        st.code(st.session_state["ai_prompt"]); st.download_button("⬇️ Save AI prompt",st.session_state["ai_prompt"],"v5_2_ai_second_opinion.txt","text/plain")

st.divider(); st.caption("V5.2 is research/paper-trading software. Data can be delayed, incomplete, stale, rate-limited or unavailable. No live broker orders are placed. Never treat a ranking as a guaranteed profit signal.")
