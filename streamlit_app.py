import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import requests, io, re, json, math
import plotly.graph_objects as go
from datetime import datetime, timedelta

st.set_page_config(page_title="NSE Positional Trader V5.1", page_icon="📈", layout="centered")
st.markdown("""<style>
.block-container{max-width:960px;padding:.55rem .65rem 2rem}
h1{font-size:1.45rem!important}h2{font-size:1.15rem!important}
.stButton>button,.stDownloadButton>button{width:100%;min-height:2.7rem}
div[data-testid="stMetric"]{padding:.45rem;border-radius:.6rem;border:1px solid rgba(128,128,128,.2)}
</style>""", unsafe_allow_html=True)

LOCAL = pd.read_csv("data/nifty500_symbols.csv").symbol.dropna().tolist()
NIFTY_URL = "https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv"

# ---------- Core data ----------
def symbol_clean(s): return str(s).upper().replace(".NS", "").strip()

@st.cache_data(ttl=86400, show_spinner=False)
def universe():
    try:
        r=requests.get(NIFTY_URL, headers={"User-Agent":"Mozilla/5.0"}, timeout=12)
        r.raise_for_status(); df=pd.read_csv(io.BytesIO(r.content))
        col=next((c for c in df.columns if str(c).strip().lower()=="symbol"),None)
        if col:
            vals=sorted(set(symbol_clean(x)+".NS" for x in df[col].dropna()))
            if len(vals)>=450: return vals
    except Exception: pass
    return LOCAL

@st.cache_data(ttl=900, show_spinner=False)
def prices(symbol, period="5y", interval="1d"):
    d=yf.download(symbol, period=period, interval=interval, auto_adjust=False, progress=False)
    if isinstance(d.columns,pd.MultiIndex): d.columns=[c[0] for c in d.columns]
    need=["Open","High","Low","Close","Volume"]
    return d[need].dropna()

def ind(d):
    d=d.copy()
    d["SMA20"]=d.Close.rolling(20).mean(); d["SMA50"]=d.Close.rolling(50).mean(); d["SMA200"]=d.Close.rolling(200).mean()
    delta=d.Close.diff(); g=delta.clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean(); l=(-delta.clip(upper=0)).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    d["RSI"]=100-100/(1+g/l.replace(0,np.nan)); prev=d.Close.shift()
    tr=pd.concat([(d.High-d.Low),(d.High-prev).abs(),(d.Low-prev).abs()],axis=1).max(axis=1)
    d["ATR"]=tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean(); d["ATR%"]=100*d.ATR/d.Close
    d["VOL20"]=d.Volume.rolling(20).mean(); d["VOL_RATIO"]=d.Volume/d.VOL20
    d["BREAKOUT20"]=d.High.rolling(20).max().shift(1); d["RET21"]=d.Close.pct_change(21); d["RET63"]=d.Close.pct_change(63)
    return d.dropna()

@st.cache_data(ttl=900, show_spinner=False)
def benchmark(): return ind(prices("^NSEI"))

def regime():
    x=benchmark().iloc[-1]
    if x.Close>x.SMA200 and x.SMA50>x.SMA200 and x.Close>x.SMA50:return "BULLISH","🟢"
    if x.Close>x.SMA200:return "NEUTRAL","🟡"
    return "BEARISH","🔴"

# ---------- Fundamentals / sectors ----------
@st.cache_data(ttl=1800, show_spinner=False)
def fundamentals(symbol):
    try: i=yf.Ticker(symbol).info
    except Exception: i={}
    return {"P/E":i.get("trailingPE"),"Forward P/E":i.get("forwardPE"),"ROE":i.get("returnOnEquity"),"ROA":i.get("returnOnAssets"),"Debt/Equity":i.get("debtToEquity"),"Revenue growth":i.get("revenueGrowth"),"Earnings growth":i.get("earningsGrowth"),"Profit margin":i.get("profitMargins"),"Market cap":i.get("marketCap")}

def fscore(f):
    # Normalized 0-100 fundamental quality score.
    s=0
    if pd.notna(f["ROE"]): s+=20 if f["ROE"]>=.15 else 12 if f["ROE"]>=.10 else 0
    if pd.notna(f["Revenue growth"]) and f["Revenue growth"]>0: s+=15
    if pd.notna(f["Earnings growth"]) and f["Earnings growth"]>0: s+=15
    if pd.notna(f["Profit margin"]) and f["Profit margin"]>.10: s+=15
    if pd.notna(f["Debt/Equity"]): s+=15 if f["Debt/Equity"]<=80 else 8 if f["Debt/Equity"]<=150 else 0
    if pd.notna(f["P/E"]) and 0<f["P/E"]<35: s+=20
    return min(s,100)

def sector(sym):
    s=symbol_clean(sym)
    groups={"RELIANCE":"Energy","ONGC":"Energy","COALINDIA":"Energy","NTPC":"Utilities","POWERGRID":"Utilities","ADANIGREEN":"Utilities","ADANIPOWER":"Utilities","HDFCBANK":"Financials","ICICIBANK":"Financials","SBIN":"Financials","AXISBANK":"Financials","KOTAKBANK":"Financials","BAJFINANCE":"Financials","BAJAJFINSV":"Financials","INFY":"IT","TCS":"IT","HCLTECH":"IT","WIPRO":"IT","TECHM":"IT","LTIM":"IT","PERSISTENT":"IT","COFORGE":"IT","SUNPHARMA":"Healthcare","DRREDDY":"Healthcare","CIPLA":"Healthcare","APOLLOHOSP":"Healthcare","DIVISLAB":"Healthcare","LUPIN":"Healthcare","TATAMOTORS":"Auto","MARUTI":"Auto","M&M":"Auto","EICHERMOT":"Auto","HEROMOTOCO":"Auto","BAJAJ-AUTO":"Auto","TVSMOTOR":"Auto","TATASTEEL":"Metals","JSWSTEEL":"Metals","HINDALCO":"Metals","JINDALSTEL":"Metals","VEDL":"Metals","ITC":"Consumer","HINDUNILVR":"Consumer","NESTLEIND":"Consumer","BRITANNIA":"Consumer","DABUR":"Consumer","MARICO":"Consumer","TITAN":"Consumer","LT":"Industrials","SIEMENS":"Industrials","ABB":"Industrials","HAL":"Industrials","BEL":"Industrials","CUMMINSIND":"Industrials","CGPOWER":"Industrials"}
    return groups.get(s,"Other")

# ---------- Multi-timeframe ----------
def weekly_snapshot(symbol):
    d=prices(symbol,period="2y",interval="1wk")
    if len(d)<55: return {"weekly_trend":"UNKNOWN","weekly_score":0,"weekly_close":np.nan,"weekly_sma20":np.nan,"weekly_sma40":np.nan}
    x=ind(d).iloc[-1]
    bullish=bool(x.Close>x.SMA20>x.SMA50)
    aligned=bool(x.Close>x.SMA20 and x.SMA20>x.SMA50)
    score=100 if bullish else 70 if aligned else 40 if x.Close>x.SMA20 else 15
    return {"weekly_trend":"BULLISH" if bullish else "POSITIVE" if aligned else "NEUTRAL/WEAK","weekly_score":score,"weekly_close":float(x.Close),"weekly_sma20":float(x.SMA20),"weekly_sma40":float(x.SMA50)}

# ---------- Event / news intelligence ----------
def classify_event_text(text):
    t=str(text).lower()
    negative={"fraud":5,"default":5,"insolvency":5,"resignation":2,"pledge":3,"investigation":4,"penalty":3,"fire":3,"accident":3,"downgrade":4,"litigation":3,"warning":3,"restatement":4,"delay":2}
    positive={"acquisition":1,"merger":1,"order":1,"contract":1,"approval":2,"upgrade":2,"dividend":1,"buyback":1,"capacity":1}
    neg=[k for k in negative if k in t]; pos=[k for k in positive if k in t]
    ns=sum(negative[k] for k in neg); ps=sum(positive[k] for k in pos)
    if ns>=ps+2: return "NEGATIVE",min(ns,15),neg,pos
    if ps>=ns+2: return "POSITIVE",min(ps,8),neg,pos
    return "NEUTRAL",0,neg,pos

@st.cache_data(ttl=900,show_spinner=False)
def event_intelligence(sym):
    rows=[]
    # NSE announcements first.
    s=symbol_clean(sym); url="https://www.nseindia.com/api/corporate-announcements"
    h={"User-Agent":"Mozilla/5.0","Accept":"application/json,text/plain,*/*","Referer":"https://www.nseindia.com/"}
    try:
        q=requests.Session(); q.headers.update(h); q.get("https://www.nseindia.com",timeout=8)
        r=q.get(url,params={"index":"equities","symbol":s},timeout=12); r.raise_for_status()
        data=r.json(); data=data if isinstance(data,list) else data.get("data",[])
        for z in data[:12]:
            text=str(z.get("desc") or z.get("subject") or "")
            bias,impact,neg,pos=classify_event_text(text)
            rows.append({"Source":"NSE","Date":z.get("an_dt") or z.get("date") or "","Headline":text,"Bias":bias,"Impact":impact,"Negative terms":", ".join(neg),"Positive terms":", ".join(pos)})
    except Exception: pass
    # Yahoo news as a secondary source; do not treat it as authoritative.
    try:
        news=yf.Ticker(sym).news or []
        for z in news[:10]:
            content=z.get("content",{}) if isinstance(z,dict) else {}
            title=content.get("title") or z.get("title") or ""
            pub=content.get("pubDate") or z.get("providerPublishTime") or ""
            bias,impact,neg,pos=classify_event_text(title)
            rows.append({"Source":"Yahoo/news","Date":pub,"Headline":title,"Bias":bias,"Impact":impact,"Negative terms":", ".join(neg),"Positive terms":", ".join(pos)})
    except Exception: pass
    df=pd.DataFrame(rows)
    if df.empty: return 0,[],df,"UNKNOWN"
    neg_hits=sorted(set(x for x in df["Negative terms"].astype(str).str.split(", ").explode() if x and x!="nan"))
    penalty=int(min(df.loc[df.Bias=="NEGATIVE","Impact"].sum(),15))
    overall="NEGATIVE" if penalty>=5 else "POSITIVE" if (df.Bias=="POSITIVE").sum()>(df.Bias=="NEGATIVE").sum() else "MIXED/NEUTRAL"
    return penalty,neg_hits,df,overall

# ---------- Scoring engine ----------
SCORING_WEIGHTS={"Trend":25,"Momentum":15,"Relative Strength":20,"Volume/Breakout":15,"Fundamentals":15,"Risk/Event":10}

def score_components(row, fs, event_penalty, weekly):
    trend=100 if row.Close>row.SMA50>row.SMA200 else 55 if row.Close>row.SMA200 else 15
    momentum=100 if 55<=row.RSI<=70 else 75 if 50<=row.RSI<55 or 70<row.RSI<=75 else 40
    rs=100 if row.RS_NIFTY>0 and row.Sector_RS>0 else 75 if row.RS_NIFTY>0 or row.Sector_RS>0 else 35
    vb=100 if row.Close>row.BREAKOUT20 and row.VOL_RATIO>=1.5 else 80 if row.Close>row.BREAKOUT20 or row.VOL_RATIO>=1.5 else 45
    risk=max(0,100-event_penalty*6)
    # Regime-adaptive component weights. The displayed base weights remain stable, but the regime multiplier changes risk appetite.
    rg,_=regime()
    regime_mult={"BULLISH":1.05,"NEUTRAL":0.90,"BEARISH":0.70}[rg]
    weighted=(trend*.25+momentum*.15+rs*.20+vb*.15+fs*.15+risk*.10)*regime_mult
    weighted=max(0,min(100,weighted))
    return {"Trend":round(trend,1),"Momentum":round(momentum,1),"Relative Strength":round(rs,1),"Volume/Breakout":round(vb,1),"Fundamentals":round(fs,1),"Risk/Event":round(risk,1),"Raw Score":round(weighted,1),"Regime multiplier":regime_mult,"Weekly score":weekly.get("weekly_score",0)}

def entry_quality(row,weekly):
    # 0-100: rewards clean trend, breakout proximity, non-extreme RSI and weekly alignment.
    trend=35 if row.Close>row.SMA50>row.SMA200 else 15 if row.Close>row.SMA200 else 0
    breakout=25 if row.Close>=row.BREAKOUT20 else max(0,25*(1-(row.BREAKOUT20-row.Close)/max(row.Close*.08,1)))
    rsi=20 if 55<=row.RSI<=68 else 12 if 50<=row.RSI<55 or 68<row.RSI<=75 else 5
    weekly_part=20*(weekly.get("weekly_score",0)/100)
    return round(max(0,min(100,trend+breakout+rsi+weekly_part)),1)

# ---------- Fast universe scan ----------
@st.cache_data(ttl=900,show_spinner=False)
def batch_scan_universe(symbols,chunk_size=50):
    rows=[]; symbols=list(dict.fromkeys(symbols))
    for start in range(0,len(symbols),chunk_size):
        chunk=symbols[start:start+chunk_size]
        try:
            raw=yf.download(chunk,period="1y",auto_adjust=False,progress=False,group_by="column",threads=True)
            if raw.empty: continue
            for sym in chunk:
                try:
                    if isinstance(raw.columns,pd.MultiIndex):
                        if sym not in raw.columns.get_level_values(-1): continue
                        d=raw.xs(sym,axis=1,level=-1).dropna()
                    else: d=raw.copy()
                    d=d[["Open","High","Low","Close","Volume"]].dropna()
                    if len(d)<210: continue
                    x=ind(d).iloc[-1]
                    rows.append({"Symbol":symbol_clean(sym),"_symbol":sym,"Close":float(x.Close),"SMA50":float(x.SMA50),"SMA200":float(x.SMA200),"RSI":float(x.RSI),"VOL_RATIO":float(x.VOL_RATIO),"ATR%":float(x["ATR%"]),"BREAKOUT20":float(x.BREAKOUT20),"RET63":float(x.RET63)})
                except Exception: continue
        except Exception: continue
    return pd.DataFrame(rows)

@st.cache_data(ttl=900,show_spinner=False)
def auto_top20(limit=20):
    syms=universe(); base=batch_scan_universe(syms)
    if base.empty:return pd.DataFrame()
    bench=benchmark().iloc[-1]; base["RS_NIFTY"]=base["RET63"]-float(bench.RET63); base["Sector"]=[sector(x) for x in base["Symbol"]]
    base["Sector_RS"]=base["RET63"]-base.groupby("Sector")["RET63"].transform("median")
    base["T0"]=((base.Close>base.SMA50)&(base.SMA50>base.SMA200)).astype(int)*20
    base["T0"]+=(base.Close>base.BREAKOUT20).astype(int)*15
    base["T0"]+=(base.VOL_RATIO>=1.5).astype(int)*10
    base["T0"]+=np.where(base.RSI.between(55,75),10,np.where(base.RSI.between(50,55),5,0))
    base["T0"]+=(base.RS_NIFTY>0).astype(int)*10;base["T0"]+=(base.Sector_RS>0).astype(int)*10;base["T0"]+=np.where(base["ATR%"]<5,10,5)
    base=base.sort_values("T0",ascending=False).head(max(30,limit*3)).copy()
    enriched=[]
    for _,row in base.iterrows():
        sym=row["_symbol"]
        try:
            f=fundamentals(sym); fs=fscore(f); ep,eh,edf,eoverall=event_intelligence(sym); weekly=weekly_snapshot(sym)
            comp=score_components(row,fs,ep,weekly); eq=entry_quality(row,weekly); rg,_=regime()
            # Trade-readiness favors a good entry without overriding quality score.
            trade_score=round(comp["Raw Score"]*.75+eq*.25,1)
            entry=float(row.Close); stop=entry-2*(float(row["ATR%"])/100)*entry; target=entry+2*(entry-stop)
            reasons=[]
            if row.Close>row.SMA50>row.SMA200: reasons.append("uptrend")
            if row.Close>row.BREAKOUT20: reasons.append("20D breakout")
            if row.VOL_RATIO>=1.5: reasons.append("volume expansion")
            if row.RS_NIFTY>0: reasons.append("beats NIFTY")
            if row.Sector_RS>0: reasons.append("beats sector")
            if weekly["weekly_score"]>=70: reasons.append("weekly confirmation")
            if ep: reasons.append("event risk")
            signal="TRADE-READY" if trade_score>=78 and eq>=65 and rg!="BEARISH" and ep<5 else "WATCH"
            enriched.append({"Symbol":row.Symbol,"Sector":row.Sector,"Score":comp["Raw Score"],"Entry quality":eq,"Trade score":trade_score,"Technical":round((comp["Trend"]*.5+comp["Momentum"]*.3+comp["Volume/Breakout"]*.2),1),"Fundamental":fs,"RS vs NIFTY %":round(row.RS_NIFTY*100,2),"Sector RS %":round(row.Sector_RS*100,2),"RSI":round(row.RSI,1),"Vol X":round(row.VOL_RATIO,2),"ATR %":round(row["ATR%"],2),"Weekly trend":weekly["weekly_trend"],"Weekly score":weekly["weekly_score"],"Entry":round(entry,2),"Stop":round(stop,2),"Target":round(target,2),"Event penalty":ep,"Event bias":eoverall,"Signal":signal,"Why":", ".join(reasons)})
        except Exception: continue
    if not enriched:return pd.DataFrame()
    out=pd.DataFrame(enriched).sort_values(["Trade score","Score"],ascending=False).head(limit).reset_index(drop=True);out.insert(0,"Rank",np.arange(1,len(out)+1));return out

def top3_from_top10(top):
    if top is None or top.empty:return pd.DataFrame()
    return top.sort_values(["Trade score","Entry quality","Score"],ascending=False).head(3).reset_index(drop=True).assign(Rank=lambda x:np.arange(1,len(x)+1))

# ---------- Detailed signal ----------
def signal(sym):
    d=ind(prices(sym)); x=d.iloc[-1]; m=benchmark().iloc[-1]; rg,_=regime(); f=fundamentals(sym); fs=fscore(f); sec=sector(sym)
    sector_ret=[]
    for p in universe()[:]:
        if sector(p)==sec and len(sector_ret)<10:
            try: sector_ret.append(ind(prices(p,period="1y")).iloc[-1].RET63)
            except: pass
    sr=x.RET63-np.mean(sector_ret) if sector_ret else np.nan; rs=x.RET63-m.RET63
    row=pd.Series({"Close":x.Close,"SMA50":x.SMA50,"SMA200":x.SMA200,"RSI":x.RSI,"VOL_RATIO":x.VOL_RATIO,"BREAKOUT20":x.BREAKOUT20,"RET63":x.RET63,"RS_NIFTY":rs,"Sector_RS":sr})
    ep,hits,news,bias=event_intelligence(sym); weekly=weekly_snapshot(sym); comp=score_components(row,fs,ep,weekly); eq=entry_quality(row,weekly)
    score=comp["Raw Score"]; trade_score=round(score*.75+eq*.25,1)
    entry=float(x.Close);stop=entry-2*float(x.ATR);target=entry+2*(entry-stop)
    reasons=[]
    if x.Close>x.SMA50>x.SMA200:reasons.append("uptrend")
    if x.Close>x.BREAKOUT20:reasons.append("20D breakout")
    if x.VOL_RATIO>=1.5:reasons.append("volume expansion")
    if rs>0:reasons.append("beats NIFTY")
    if pd.notna(sr) and sr>0:reasons.append("beats sector")
    if weekly["weekly_score"]>=70:reasons.append("weekly confirmation")
    if ep:reasons.append("event risk")
    return {"Symbol":symbol_clean(sym),"Sector":sec,"Score":round(score,1),"Trade score":trade_score,"Entry quality":eq,"Components":comp,"Fundamental":fs,"RS vs NIFTY %":round(rs*100,2),"Sector RS %":round(sr*100,2) if pd.notna(sr) else np.nan,"RSI":round(x.RSI,1),"Vol X":round(x.VOL_RATIO,2),"ATR %":round(x["ATR%"],2),"Weekly trend":weekly["weekly_trend"],"Weekly score":weekly["weekly_score"],"Entry":round(entry,2),"Stop":round(stop,2),"Target":round(target,2),"Event penalty":ep,"Event bias":bias,"Event keywords":hits,"Signal":"TRADE-READY" if trade_score>=78 and eq>=65 and rg!="BEARISH" and ep<5 else "WATCH","Why":", ".join(reasons)}

# ---------- Risk ----------
def risk_size(cap,riskpct,entry,stop,maxpos):
    rps=abs(entry-stop); budget=cap*riskpct/100; sh=int(budget/rps) if rps else 0; sh=min(sh,int(cap*maxpos/100/entry)) if entry else 0
    return sh,sh*entry,sh*rps

def portfolio_exposure(pf):
    if pf.empty:return pd.DataFrame()
    return pf.groupby("Sector",dropna=False).agg(PositionValue=("Position ₹","sum"),Risk=("Risk₹","sum"),Positions=("Symbol","count")).reset_index().sort_values("PositionValue",ascending=False)

# ---------- Backtest ----------
def costs(value,turnover_bps,slippage_bps):return value*(turnover_bps+slippage_bps)/10000

def backtest(sym,initial,riskpct,maxpos,fee_bps,slip_bps):
    d=ind(prices(sym));cash=initial;pos=None;trades=[];equity=[]
    for i in range(200,len(d)-1):
        r=d.iloc[i]
        if pos:
            exit_px=None;reason=None
            if r.Low<=pos["stop"]:exit_px=pos["stop"];reason="STOP"
            elif r.High>=pos["target"]:exit_px=pos["target"];reason="TARGET"
            elif r.Close<r.SMA50:exit_px=float(r.Close);reason="TREND EXIT"
            if exit_px is not None:
                gross=(exit_px-pos["entry"])*pos["shares"];turn=exit_px*pos["shares"]+pos["entry"]*pos["shares"];fee=costs(turn,fee_bps,slip_bps);cash+=exit_px*pos["shares"]-fee
                trades.append([pos["date"],d.index[i],pos["entry"],exit_px,pos["shares"],gross-fee,reason]);pos=None
        if pos is None and r.Close>r.BREAKOUT20 and r.Close>r.SMA50>r.SMA200 and r.VOL_RATIO>=1.5:
            en=float(d.iloc[i+1].Open);stop=en-2*float(r.ATR);target=en+2*(en-stop);sh=int((cash*riskpct/100)/(en-stop));sh=min(sh,int(cash*maxpos/100/en)) if en else 0
            if sh:cost=en*sh;cash-=cost+costs(cost,fee_bps,slip_bps);pos={"date":d.index[i+1],"entry":en,"stop":stop,"target":target,"shares":sh}
        equity.append([d.index[i],cash+(pos["shares"]*r.Close if pos else 0)])
    eq=pd.DataFrame(equity,columns=["Date","Equity"]).set_index("Date");tr=pd.DataFrame(trades,columns=["Entry","Exit","EntryPrice","ExitPrice","Shares","PnL","Reason"]);return eq,tr

# ---------- UI ----------
st.title("📈 NSE Positional Trader V5.1")
st.caption("Regime-adaptive scoring • multi-timeframe • Top 20 → Top 3 • entry quality • event/news intelligence • AI second opinion • alerts")
if st.button("🔄 Refresh all cached data"): st.cache_data.clear(); st.rerun()
tab=st.segmented_control("Section",["🏠 Dashboard","🔎 Scanner","🔍 Stock","📊 Backtest","💼 Portfolio","📝 Journal","🤖 AI"],default="🏠 Dashboard")

if tab=="🏠 Dashboard":
    rg,ico=regime(); x=benchmark().iloc[-1]
    a,b,c=st.columns(3);a.metric("NIFTY 50",f"{x.Close:,.0f}");b.metric("Regime",f"{ico} {rg}");c.metric("Data",str(benchmark().index[-1].date()))
    st.info("Research/paper-trading only. Free data can be delayed, incomplete or rate-limited. No live broker orders are placed.")
    st.subheader("🏆 V5.1 Top 20 → Top 3")
    if st.button("🚀 Scan NSE → Top 20 + Top 3",key="dashboard_top20"):
        with st.spinner("Scanning NSE universe, scoring, checking weekly trend and events…"):
            top=auto_top20(20); top3=top3_from_top10(top)
        if top.empty: st.error("No candidates returned. Refresh data and try again later.")
        else:
            st.session_state["top10"]=top; st.session_state["top3"]=top3
    if "top10" in st.session_state and not st.session_state.top10.empty:
        top=st.session_state.top10; top3=st.session_state.top3
        st.markdown("### 🏆 Top 20 research shortlist")
        st.dataframe(top[["Rank","Symbol","Score","Entry quality","Trade score","Weekly trend","RSI","Vol X","Entry","Stop","Target","Event bias","Signal"]],use_container_width=True,hide_index=True)
        st.download_button("⬇️ Export Top 20",top.to_csv(index=False),"v5_top20.csv","text/csv",key="top20_export")
        st.markdown("### 🎯 Top 3 trade-ready shortlist")
        st.caption("Top 3 is a prioritization layer, not an automatic buy list. It favors quality + entry quality + regime/event filters.")
        st.dataframe(top3[["Rank","Symbol","Score","Entry quality","Trade score","Weekly trend","RS vs NIFTY %","Sector RS %","Entry","Stop","Target","Signal","Why"]],use_container_width=True,hide_index=True)
        st.download_button("⬇️ Export Top 3",top3.to_csv(index=False),"v5_top3.csv","text/csv",key="top3_export")
        st.subheader("🔔 Alerts")
        alert_thr=st.number_input("Alert when price is within % of entry",0.5,10.0,2.0,0.5)
        alerts=[]
        for _,rr in top3.iterrows():
            try:
                last=float(ind(prices(rr.Symbol,period="6mo")).iloc[-1].Close); dist=abs(last-rr.Entry)/rr.Entry*100
                if dist<=alert_thr: alerts.append(f"🔔 {rr.Symbol}: price ₹{last:,.2f} is {dist:.1f}% from V5 entry zone.")
                if rr["Event bias"]=="NEGATIVE": alerts.append(f"⚠️ {rr.Symbol}: negative event/news bias detected; verify filings before any trade.")
            except Exception: pass
        if alerts:
            for atext in alerts: st.warning(atext)
        else: st.success("No configured price/event alerts for the current Top 3.")
        st.caption("Alerts are in-app checks while the dashboard is open; they are not push notifications.")

elif tab=="🔎 Scanner":
    u=universe();st.caption(f"Universe available: {len(u)} symbols. Automatic mode is recommended.")
    mode=st.radio("Scan mode",["🏆 Automatic Top 20 + Top 3","🎯 Custom selection"],horizontal=True)
    if mode=="🏆 Automatic Top 20 + Top 3":
        if st.button("🚀 Run NSE scan → Top 20",key="scanner_top20"):
            with st.spinner("Scanning NSE universe…"): out=auto_top20(20)
            if out.empty: st.error("No candidates returned.")
            else:
                st.session_state["top10"]=out;st.session_state["top3"]=top3_from_top10(out)
        if "top10" in st.session_state and not st.session_state.top10.empty:
            out=st.session_state.top10
            st.dataframe(out,use_container_width=True,hide_index=True)
            st.download_button("⬇️ Export Top 20",out.to_csv(index=False),"v5_top20.csv","text/csv",key="scanner_top20_export")
            st.markdown("### 🎯 Top 3")
            st.dataframe(st.session_state.top3,use_container_width=True,hide_index=True)
    else:
        sel=st.multiselect("Scan universe",u,default=u[:12])
        if st.button("🚀 Run custom scanner",key="custom_scan"):
            rows=[]
            with st.spinner("Scanning selected symbols…"):
                for s in sel:
                    try: rows.append(signal(s))
                    except Exception as e: st.warning(f"{s}: {e}")
            if rows:
                out=pd.DataFrame(rows).sort_values("Trade score",ascending=False);st.dataframe(out,use_container_width=True,hide_index=True);st.download_button("⬇️ Export signals",out.to_csv(index=False),"v5_signals.csv","text/csv",key="custom_export")

elif tab=="🔍 Stock":
    sym=st.selectbox("NSE stock",universe()); d=ind(prices(sym)); x=d.iloc[-1]; r=signal(sym); f=fundamentals(sym)
    a,b,c,d1=st.columns(4);a.metric("V5 Score",r["Score"]);b.metric("Trade score",r["Trade score"]);c.metric("Entry quality",r["Entry quality"]);d1.metric("Signal",r["Signal"])
    st.caption(f"Weekly: {r['Weekly trend']} • Event bias: {r['Event bias']} • Regime-adjusted scoring")
    fig=go.Figure();fig.add_trace(go.Candlestick(x=d.index,open=d.Open,high=d.High,low=d.Low,close=d.Close,name="Price"));fig.add_trace(go.Scatter(x=d.index,y=d.SMA50,name="SMA50"));fig.add_trace(go.Scatter(x=d.index,y=d.SMA200,name="SMA200"));fig.update_layout(height=420,xaxis_rangeslider_visible=False,margin=dict(l=5,r=5,t=5,b=5));st.plotly_chart(fig,use_container_width=True)
    st.subheader("🧠 Scoring breakdown")
    comp=pd.DataFrame([r["Components"]]).T.rename(columns={0:"Score"});st.dataframe(comp,use_container_width=True)
    st.caption("Base weights: Trend 25%, Momentum 15%, Relative Strength 20%, Volume/Breakout 15%, Fundamentals 15%, Risk/Event 10%. Market regime applies an adaptive multiplier.")
    st.subheader("🎯 Entry quality")
    st.progress(int(r["Entry quality"]));st.write("Entry quality combines trend alignment, breakout proximity, RSI location and weekly confirmation.")
    st.subheader("📅 Multi-timeframe confirmation")
    st.json({"Weekly trend":r["Weekly trend"],"Weekly score":r["Weekly score"]})
    st.subheader("📰 Event/news intelligence")
    ep,hits,news,bias=event_intelligence(sym);st.write(f"Overall bias: **{bias}** • Risk penalty: **{ep}**");
    if hits: st.warning("Negative keywords: "+", ".join(hits))
    st.dataframe(news,use_container_width=True,hide_index=True)
    st.subheader("Fundamentals");st.dataframe(pd.DataFrame([f]).T.rename(columns={0:"Value"}),use_container_width=True)
    st.caption("News classification is a screening aid. Verify important disclosures on NSE/company filings.")

elif tab=="📊 Backtest":
    sym=st.selectbox("Stock",universe());initial=st.number_input("Initial capital ₹",100000.,100000000.,1000000.,100000.);rp=st.number_input("Risk/trade %",.1,3.,.75,.05);mp=st.number_input("Max position %",5.,50.,20.,1.);fee=st.number_input("Fees + taxes (bps/turnover)",0.,100.,10.,1.);slip=st.number_input("Slippage (bps/turnover)",0.,100.,5.,1.)
    if st.button("▶️ Run cost-aware backtest"):
        eq,tr=backtest(sym,initial,rp,mp,fee,slip);dd=eq.Equity/eq.Equity.cummax()-1
        a,b,c,d=st.columns(4);a.metric("Final",f"₹{eq.Equity.iloc[-1]:,.0f}");b.metric("Return",f"{(eq.Equity.iloc[-1]/initial-1)*100:.1f}%");c.metric("Max DD",f"{dd.min()*100:.1f}%");d.metric("Trades",len(tr))
        if len(tr):st.metric("Win rate",f"{(tr.PnL>0).mean()*100:.1f}%")
        st.plotly_chart(go.Figure(go.Scatter(x=eq.index,y=eq.Equity,mode="lines")),use_container_width=True);st.dataframe(tr,use_container_width=True,hide_index=True)

elif tab=="💼 Portfolio":
    st.subheader("Paper portfolio risk + sector exposure")
    cap=st.number_input("Portfolio equity ₹",100000.,100000000.,1000000.,100000.);rp=st.number_input("Risk/trade %",.1,3.,.75,.05);mp=st.number_input("Max position %",5.,50.,20.,1.)
    if "portfolio" not in st.session_state:st.session_state.portfolio=[]
    sym=st.selectbox("Add candidate",universe());r=signal(sym);sh,val,loss=risk_size(cap,rp,r["Entry"],r["Stop"],mp);sec=r["Sector"]
    a,b,c=st.columns(3);a.metric("Suggested shares",sh);b.metric("Position",f"₹{val:,.0f}");c.metric("Risk",f"₹{loss:,.0f}")
    if st.button("➕ Add paper position"):
        st.session_state.portfolio.append({"Symbol":r["Symbol"],"Sector":sec,"Entry":r["Entry"],"Stop":r["Stop"],"Target":r["Target"],"Shares":sh,"Position ₹":val,"Risk₹":loss,"Score":r["Score"],"Trade score":r["Trade score"]})
    if st.session_state.portfolio:
        pf=pd.DataFrame(st.session_state.portfolio);st.dataframe(pf,use_container_width=True,hide_index=True);st.metric("Total planned risk",f"₹{pf['Risk₹'].sum():,.0f}")
        exp=portfolio_exposure(pf);st.subheader("Sector exposure");st.dataframe(exp,use_container_width=True,hide_index=True)
        if len(exp) and exp.PositionValue.sum()>0:
            exp["Exposure %"]=exp.PositionValue/exp.PositionValue.sum()*100;st.dataframe(exp[["Sector","Exposure %","Positions","Risk"]],use_container_width=True,hide_index=True)
        st.download_button("⬇️ Export portfolio",pf.to_csv(index=False),"paper_portfolio.csv","text/csv")

elif tab=="📝 Journal":
    st.subheader("Trade journal")
    if "journal" not in st.session_state:st.session_state.journal=pd.DataFrame(columns=["Date","Symbol","Setup","Entry","Stop","Target","Shares","Result","R","Notes"])
    with st.form("journal"):
        sym=st.text_input("Symbol");setup=st.selectbox("Setup",["Breakout","Retest","Trend continuation","Pullback","Other"]);a,b=st.columns(2);en=a.number_input("Entry ₹",0.);sp=b.number_input("Stop ₹",0.);a,b=st.columns(2);tg=a.number_input("Target ₹",0.);sh=b.number_input("Shares",0,1000000,0);res=st.selectbox("Result",["OPEN","WIN","LOSS","BREAKEVEN"]);notes=st.text_area("Notes");ok=st.form_submit_button("Add")
    if ok and sym:
        risk=abs(en-sp)*sh;pnl=(tg-en)*sh if res=="WIN" else -risk if res=="LOSS" else 0;new=pd.DataFrame([{"Date":datetime.now().date(),"Symbol":symbol_clean(sym),"Setup":setup,"Entry":en,"Stop":sp,"Target":tg,"Shares":sh,"Result":res,"R":pnl/risk if risk else 0,"Notes":notes}]);st.session_state.journal=pd.concat([st.session_state.journal,new],ignore_index=True)
    st.dataframe(st.session_state.journal,use_container_width=True,hide_index=True)
    if not st.session_state.journal.empty:
        j=st.session_state.journal;closed=j[j.Result!="OPEN"];st.subheader("Performance snapshot");a,b,c,d=st.columns(4);a.metric("Trades",len(closed));b.metric("Win rate",f"{(closed.R>0).mean()*100:.1f}%" if len(closed) else "—");c.metric("Avg R",f"{closed.R.mean():.2f}" if len(closed) else "—");d.metric("Net R",f"{closed.R.sum():.2f}" if len(closed) else "—")
    st.download_button("⬇️ Export journal",st.session_state.journal.to_csv(index=False),"trade_journal.csv","text/csv")

else:
    st.subheader("🤖 AI second opinion")
    sym=st.text_input("Stock","RELIANCE.NS");
    try:r=signal(sym) if symbol_clean(sym)+".NS" in universe() else None
    except:r=None
    machine=json.dumps(r,indent=2,default=str) if r else "No machine snapshot available."
    prompt=f"""You are an NSE positional-trading research assistant providing a SECOND OPINION, not a trade command.

Stock: {symbol_clean(sym)}.NS
Holding period: 2–12 weeks.

V5.1 machine snapshot:
{machine}

Instructions:
- Use current, verifiable information and prefer official company/NSE disclosures for material claims.
- Separate FACTS from INTERPRETATION.
- Do not invent missing figures.
- Challenge the machine signal: actively search for reasons the setup may fail.
- Assess quarterly financial trend, valuation vs peers/history, ROE/ROCE, margins, debt/cash flow, promoter/shareholding and institutional flows where verified, sector strength, weekly/daily technical trend, entry quality, liquidity, recent corporate/news events, and event risks.
- Explain whether the current entry is attractive, early, extended, or invalidated.
- Do not predict a future price.

Return exactly:
1. FACTS table with source/date where possible
2. Bull case
3. Bear case / strongest counterarguments
4. Entry-quality assessment
5. Event/news risk assessment
6. What would invalidate the setup
7. Missing information / data-quality concerns
8. SECOND OPINION: SUPPORT / WATCH / REJECT
9. Confidence level and why

This output is research assistance, not guaranteed investment advice."""
    st.code(prompt);st.download_button("⬇️ Save AI second-opinion prompt",prompt,"v5_ai_second_opinion.txt","text/plain")
    st.info("Paste the prompt into an AI tool that can browse current sources. The AI should challenge the V5 signal rather than simply echo it.")

st.divider();st.caption("V5.1 is research/paper-trading software. No live broker orders are placed. Alerts are in-app checks, not guaranteed push notifications. Event/news classification is probabilistic and must be verified against primary disclosures.")
