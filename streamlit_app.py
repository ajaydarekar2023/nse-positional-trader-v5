
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import requests, io, re, json
import plotly.graph_objects as go
from datetime import datetime, timedelta

st.set_page_config(page_title="NSE Positional Trader V5",page_icon="📈",layout="centered")
st.markdown("""<style>
.block-container{max-width:960px;padding:.55rem .65rem 2rem}
h1{font-size:1.45rem!important}h2{font-size:1.15rem!important}
.stButton>button,.stDownloadButton>button{width:100%;min-height:2.7rem}
div[data-testid="stMetric"]{padding:.45rem;border-radius:.6rem;border:1px solid rgba(128,128,128,.2)}
</style>""",unsafe_allow_html=True)

LOCAL=pd.read_csv("data/nifty500_symbols.csv").symbol.dropna().tolist()
NIFTY_URL="https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv"

def symbol_clean(s): return str(s).upper().replace(".NS","").strip()

@st.cache_data(ttl=86400,show_spinner=False)
def universe():
    try:
        r=requests.get(NIFTY_URL,headers={"User-Agent":"Mozilla/5.0"},timeout=12)
        r.raise_for_status()
        df=pd.read_csv(io.BytesIO(r.content))
        col=next((c for c in df.columns if str(c).lower() in ["symbol","symbol "]),None)
        if col:
            vals=[symbol_clean(x)+".NS" for x in df[col].dropna()]
            vals=sorted(set(vals))
            if len(vals)>=450:return vals
    except Exception: pass
    return LOCAL

@st.cache_data(ttl=900,show_spinner=False)
def prices(symbol,period="5y"):
    d=yf.download(symbol,period=period,auto_adjust=False,progress=False)
    if isinstance(d.columns,pd.MultiIndex):d.columns=[c[0] for c in d.columns]
    return d[["Open","High","Low","Close","Volume"]].dropna()

def ind(d):
    d=d.copy()
    d["SMA20"]=d.Close.rolling(20).mean();d["SMA50"]=d.Close.rolling(50).mean();d["SMA200"]=d.Close.rolling(200).mean()
    delta=d.Close.diff();g=delta.clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean();l=(-delta.clip(upper=0)).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    d["RSI"]=100-100/(1+g/l.replace(0,np.nan));prev=d.Close.shift()
    tr=pd.concat([(d.High-d.Low),(d.High-prev).abs(),(d.Low-prev).abs()],axis=1).max(axis=1)
    d["ATR"]=tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean();d["ATR%"]=100*d.ATR/d.Close
    d["VOL20"]=d.Volume.rolling(20).mean();d["VOL_RATIO"]=d.Volume/d.VOL20
    d["BREAKOUT20"]=d.High.rolling(20).max().shift(1);d["RET63"]=d.Close.pct_change(63)
    return d.dropna()

@st.cache_data(ttl=900,show_spinner=False)
def benchmark(): return ind(prices("^NSEI"))

def regime():
    x=benchmark().iloc[-1]
    if x.Close>x.SMA200 and x.SMA50>x.SMA200 and x.Close>x.SMA50:return "BULLISH","🟢"
    if x.Close>x.SMA200:return "NEUTRAL","🟡"
    return "BEARISH","🔴"

@st.cache_data(ttl=1800,show_spinner=False)
def fundamentals(symbol):
    try:i=yf.Ticker(symbol).info
    except Exception:i={}
    return {"P/E":i.get("trailingPE"),"Forward P/E":i.get("forwardPE"),"ROE":i.get("returnOnEquity"),
            "ROA":i.get("returnOnAssets"),"Debt/Equity":i.get("debtToEquity"),"Revenue growth":i.get("revenueGrowth"),
            "Earnings growth":i.get("earningsGrowth"),"Profit margin":i.get("profitMargins"),"Market cap":i.get("marketCap")}

def fscore(f):
    s=0
    if pd.notna(f["ROE"]):s+=20 if f["ROE"]>=.15 else 12 if f["ROE"]>=.10 else 0
    if pd.notna(f["Revenue growth"]) and f["Revenue growth"]>0:s+=15
    if pd.notna(f["Earnings growth"]) and f["Earnings growth"]>0:s+=15
    if pd.notna(f["Profit margin"]) and f["Profit margin"]>.10:s+=15
    if pd.notna(f["Debt/Equity"]):s+=15 if f["Debt/Equity"]<=80 else 8 if f["Debt/Equity"]<=150 else 0
    if pd.notna(f["P/E"]) and 0<f["P/E"]<35:s+=20
    return min(s,100)

def sector(sym):
    s=symbol_clean(sym)
    groups={"RELIANCE":"Energy","ONGC":"Energy","COALINDIA":"Energy","NTPC":"Utilities","POWERGRID":"Utilities","ADANIGREEN":"Utilities","ADANIPOWER":"Utilities",
    "HDFCBANK":"Financials","ICICIBANK":"Financials","SBIN":"Financials","AXISBANK":"Financials","KOTAKBANK":"Financials","BAJFINANCE":"Financials","BAJAJFINSV":"Financials",
    "INFY":"IT","TCS":"IT","HCLTECH":"IT","WIPRO":"IT","TECHM":"IT","LTIM":"IT","PERSISTENT":"IT","COFORGE":"IT",
    "SUNPHARMA":"Healthcare","DRREDDY":"Healthcare","CIPLA":"Healthcare","APOLLOHOSP":"Healthcare","DIVISLAB":"Healthcare","LUPIN":"Healthcare",
    "TATAMOTORS":"Auto","MARUTI":"Auto","M&M":"Auto","EICHERMOT":"Auto","HEROMOTOCO":"Auto","BAJAJ-AUTO":"Auto","TVSMOTOR":"Auto",
    "TATASTEEL":"Metals","JSWSTEEL":"Metals","HINDALCO":"Metals","JINDALSTEL":"Metals","VEDL":"Metals",
    "ITC":"Consumer","HINDUNILVR":"Consumer","NESTLEIND":"Consumer","BRITANNIA":"Consumer","DABUR":"Consumer","MARICO":"Consumer","TITAN":"Consumer",
    "LT":"Industrials","SIEMENS":"Industrials","ABB":"Industrials","HAL":"Industrials","BEL":"Industrials","CUMMINSIND":"Industrials","CGPOWER":"Industrials"}
    return groups.get(s,"Other")

@st.cache_data(ttl=1800,show_spinner=False)
def sector_rs(sym):
    sec=sector(sym); peers=[x for x in universe() if sector(x)==sec][:10]
    try: own=ind(prices(sym)).iloc[-1].RET63
    except: return np.nan,sec
    vals=[]
    for p in peers:
        try: vals.append(ind(prices(p)).iloc[-1].RET63)
        except: pass
    return (own-np.mean(vals) if vals else np.nan),sec

def event_risk(sym):
    s=symbol_clean(sym);url="https://www.nseindia.com/api/corporate-announcements"
    h={"User-Agent":"Mozilla/5.0","Accept":"application/json,text/plain,*/*","Referer":"https://www.nseindia.com/"}
    try:
        q=requests.Session();q.headers.update(h);q.get("https://www.nseindia.com",timeout=8)
        r=q.get(url,params={"index":"equities","symbol":s},timeout=12);r.raise_for_status()
        data=r.json();rows=data if isinstance(data,list) else data.get("data",[])
        texts=[str(x.get("desc") or x.get("subject") or "") for x in rows[:20]]
        terms={"fraud":5,"default":5,"insolvency":5,"resignation":2,"pledge":3,"investigation":4,"penalty":3,"fire":3,"accident":3,"downgrade":4,"acquisition":1,"merger":1,"debt":2,"litigation":3}
        hits=[];pen=0
        for t in texts:
            low=t.lower()
            for k,v in terms.items():
                if k in low:hits.append(k);pen+=v
        return min(pen,15),sorted(set(hits)),pd.DataFrame([{"Subject":t} for t in texts[:10]])
    except Exception:return 0,[],pd.DataFrame()


@st.cache_data(ttl=900,show_spinner=False)
def batch_scan_universe(symbols, chunk_size=50):
    """Fast first-pass scan. Uses batched Yahoo downloads to avoid hundreds of sequential requests."""
    rows=[]
    symbols=list(dict.fromkeys(symbols))
    for start in range(0,len(symbols),chunk_size):
        chunk=symbols[start:start+chunk_size]
        try:
            raw=yf.download(chunk,period="1y",auto_adjust=False,progress=False,group_by="column",threads=True)
            if raw.empty: continue
            for sym in chunk:
                try:
                    if isinstance(raw.columns,pd.MultiIndex):
                        # yfinance usually returns field x ticker for multi-ticker downloads
                        if sym not in raw.columns.get_level_values(-1): continue
                        d=raw.xs(sym,axis=1,level=-1).dropna()
                    else:
                        d=raw.copy()
                    d=d[["Open","High","Low","Close","Volume"]].dropna()
                    if len(d)<210: continue
                    x=ind(d).iloc[-1]
                    rows.append({"Symbol":symbol_clean(sym),"_symbol":sym,"Close":float(x.Close),"SMA50":float(x.SMA50),"SMA200":float(x.SMA200),
                                 "RSI":float(x.RSI),"VOL_RATIO":float(x.VOL_RATIO),"ATR%":float(x["ATR%"]),"BREAKOUT20":float(x.BREAKOUT20),"RET63":float(x.RET63)})
                except Exception:
                    continue
        except Exception:
            continue
    return pd.DataFrame(rows)

@st.cache_data(ttl=900,show_spinner=False)
def auto_top10(limit=10):
    """Rank the NSE universe with a fast batch pass, then apply full V5 scoring to a small shortlist.
    The batch pass avoids hundreds of sequential price requests; fundamentals/events are only fetched
    for the strongest candidates so this remains practical on Streamlit Community Cloud and phones.
    """
    syms=universe(); base=batch_scan_universe(syms)
    if base.empty: return pd.DataFrame()
    bench=benchmark().iloc[-1]
    base["RS_NIFTY"]=base["RET63"]-float(bench.RET63)
    base["Sector"]=[sector(x) for x in base["Symbol"]]
    sector_median=base.groupby("Sector")["RET63"].transform("median")
    base["Sector_RS"]=base["RET63"]-sector_median
    # First-pass ranking: the same technical building blocks used by the V5 model.
    base["T0"]=((base.Close>base.SMA50)&(base.SMA50>base.SMA200)).astype(int)*20
    base["T0"]+=(base.Close>base.BREAKOUT20).astype(int)*15
    base["T0"]+=(base.VOL_RATIO>=1.5).astype(int)*10
    base["T0"]+=np.where(base.RSI.between(55,75),10,np.where(base.RSI.between(50,55),5,0))
    base["T0"]+=(base.RS_NIFTY>0).astype(int)*10
    base["T0"]+=(base.Sector_RS>0).astype(int)*10
    base["T0"]+=np.where(base["ATR%"]<5,10,5)
    base=base.sort_values("T0",ascending=False).head(max(20,limit*2)).copy()

    rg,_=regime(); enriched=[]
    for _,row in base.iterrows():
        sym=row["_symbol"]
        try:
            f=fundamentals(sym); fs=fscore(f)
            # Event checks are deliberately limited to the short list.
            penalty,hits,_=event_risk(sym)
            technical=float(row["T0"])
            market=10 if rg=="BULLISH" else 5 if rg=="NEUTRAL" else 0
            score=max(0,min(100,technical*.65+fs*.25+market-penalty))
            reasons=[]
            if row.Close>row.SMA50>row.SMA200: reasons.append("uptrend")
            if row.Close>row.BREAKOUT20: reasons.append("20D breakout")
            if row.VOL_RATIO>=1.5: reasons.append("volume expansion")
            if row.RS_NIFTY>0: reasons.append("beats NIFTY")
            if row.Sector_RS>0: reasons.append("beats sector")
            if hits: reasons.append("event-risk flag")
            entry=float(row.Close); stop=entry-2*float(row["ATR%"])/100*entry; target=entry+2*(entry-stop)
            enriched.append({"Symbol":row["Symbol"],"Sector":row["Sector"],"Score":round(score,1),"Technical":round(technical,1),"Fundamental":fs,
                "RS vs NIFTY %":round(row.RS_NIFTY*100,2),"Sector RS %":round(row.Sector_RS*100,2),"RSI":round(row.RSI,1),
                "Vol X":round(row.VOL_RATIO,2),"ATR %":round(row["ATR%"],2),"Entry":round(entry,2),"Stop":round(stop,2),"Target":round(target,2),
                "Event penalty":penalty,"Signal":"BUY CANDIDATE" if score>=75 and rg!="BEARISH" else "WATCH","Why":", ".join(reasons)})
        except Exception:
            continue
    if not enriched: return pd.DataFrame()
    out=pd.DataFrame(enriched).sort_values("Score",ascending=False).head(limit).reset_index(drop=True)
    out.insert(0,"Rank",np.arange(1,len(out)+1))
    return out

def signal(sym):
    d=ind(prices(sym));x=d.iloc[-1];m=benchmark().iloc[-1];rg,_=regime();f=fundamentals(sym);fs=fscore(f);sr,sec=sector_rs(sym)
    rs=x.RET63-m.RET63
    technical=0
    technical+=20 if x.Close>x.SMA50>x.SMA200 else 0
    technical+=15 if x.Close>x.BREAKOUT20 else 0
    technical+=10 if x.VOL_RATIO>=1.5 else 0
    technical+=10 if 55<=x.RSI<=75 else 5 if 50<=x.RSI<55 else 0
    technical+=10 if rs>0 else 0
    technical+=10 if pd.notna(sr) and sr>0 else 0
    technical+=10 if x["ATR%"]<5 else 5
    market=10 if rg=="BULLISH" else 5 if rg=="NEUTRAL" else 0
    penalty,hits,_=event_risk(sym)
    score=max(0,min(100,technical*.65+fs*.25+market-penalty))
    reasons=[]
    if x.Close>x.SMA50>x.SMA200:reasons.append("uptrend")
    if x.Close>x.BREAKOUT20:reasons.append("20D breakout")
    if x.VOL_RATIO>=1.5:reasons.append("volume expansion")
    if rs>0:reasons.append("beats NIFTY")
    if pd.notna(sr) and sr>0:reasons.append("beats sector")
    if hits:reasons.append("event-risk flag")
    entry=float(x.Close);stop=entry-2*float(x.ATR);target=entry+2*(entry-stop)
    return {"Symbol":symbol_clean(sym),"Sector":sec,"Score":round(score,1),"Technical":round(technical,1),"Fundamental":fs,
    "RS vs NIFTY %":round(rs*100,2),"Sector RS %":round(sr*100,2) if pd.notna(sr) else np.nan,"RSI":round(x.RSI,1),
    "Vol X":round(x.VOL_RATIO,2),"ATR %":round(x["ATR%"],2),"Entry":round(entry,2),"Stop":round(stop,2),"Target":round(target,2),
    "Event penalty":penalty,"Signal":"BUY CANDIDATE" if score>=75 and rg!="BEARISH" else "WATCH","Why":", ".join(reasons)}

def risk_size(cap,riskpct,entry,stop,maxpos):
    rps=abs(entry-stop);budget=cap*riskpct/100;sh=int(budget/rps) if rps else 0
    sh=min(sh,int(cap*maxpos/100/entry)) if entry else 0
    return sh,sh*entry,sh*rps

def costs(value,turnover_bps,slippage_bps): return value*(turnover_bps+slippage_bps)/10000

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
                gross=(exit_px-pos["entry"])*pos["shares"];turn=exit_px*pos["shares"]+pos["entry"]*pos["shares"];cash+=exit_px*pos["shares"]-costs(turn,fee_bps,slip_bps)
                trades.append([pos["date"],d.index[i],pos["entry"],exit_px,pos["shares"],gross-costs(turn,fee_bps,slip_bps),reason]);pos=None
        if pos is None and r.Close>r.BREAKOUT20 and r.Close>r.SMA50>r.SMA200 and r.VOL_RATIO>=1.5:
            en=float(d.iloc[i+1].Open);stop=en-2*float(r.ATR);target=en+2*(en-stop);sh=int((cash*riskpct/100)/(en-stop));sh=min(sh,int(cash*maxpos/100/en)) if en else 0
            if sh:
                cost=en*sh;cash-=cost+costs(cost,fee_bps,slip_bps);pos={"date":d.index[i+1],"entry":en,"stop":stop,"target":target,"shares":sh}
        equity.append([d.index[i],cash+(pos["shares"]*r.Close if pos else 0)])
    eq=pd.DataFrame(equity,columns=["Date","Equity"]).set_index("Date");tr=pd.DataFrame(trades,columns=["Entry","Exit","EntryPrice","ExitPrice","Shares","PnL","Reason"])
    return eq,tr

st.title("📈 NSE Positional Trader V5")
st.caption("Final research build • mobile-first • portfolio risk • walk-forward-ready • no live orders")
if st.button("🔄 Refresh all cached data"):st.cache_data.clear();st.rerun()
tab=st.segmented_control("Section",["🏠 Dashboard","🔎 Scanner","🔍 Stock","📊 Backtest","💼 Portfolio","📝 Journal","🤖 AI"],default="🏠 Dashboard")

if tab=="🏠 Dashboard":
    rg,ico=regime();x=benchmark().iloc[-1]
    a,b,c=st.columns(3);a.metric("NIFTY 50",f"{x.Close:,.0f}");b.metric("Regime",f"{ico} {rg}");c.metric("Data",str(benchmark().index[-1].date()))
    st.info("V5 uses free provider data by default. It is designed for research/paper trading, not guaranteed real-time execution.")
    st.subheader("🏆 V5 Top 10 today")
    st.caption("One-tap shortlist: scans the available NSE universe, ranks candidates, then enriches the strongest setups with the full V5 score. These are candidates, not guaranteed buys.")
    if st.button("🚀 Scan NSE → Top 10",key="dashboard_top10"):
        with st.spinner("Scanning NSE universe and calculating V5 scores…"):
            top=auto_top10(10)
        if top.empty:
            st.error("No candidates were returned. Refresh data and try again later; free market-data providers can rate-limit large scans.")
        else:
            cols=["Rank","Symbol","Score","Technical","Fundamental","RS vs NIFTY %","Sector RS %","RSI","Vol X","Entry","Stop","Target","Event penalty","Signal","Why"]
            st.dataframe(top[cols],use_container_width=True,hide_index=True)
            st.download_button("⬇️ Export Top 10",top.to_csv(index=False),"v5_top10.csv","text/csv",key="top10_export")
            st.session_state["top10"]=top
    elif "top10" in st.session_state and not st.session_state.top10.empty:
        top=st.session_state.top10
        st.dataframe(top[["Rank","Symbol","Score","RSI","Vol X","Entry","Stop","Target","Signal","Why"]],use_container_width=True,hide_index=True)

elif tab=="🔎 Scanner":
    u=universe();st.caption(f"Universe available: {len(u)} symbols. The app attempts to refresh the official Nifty 500 constituent CSV; otherwise it uses the bundled fallback.")
    mode=st.radio("Scan mode",["🏆 Automatic Top 10","🎯 Custom selection"],horizontal=True)
    if mode=="🏆 Automatic Top 10":
        st.caption("Recommended for daily use. The app performs a fast batch scan first, then applies the full V5 scoring model to the strongest candidates.")
        if st.button("🚀 Run NSE Top 10",key="scanner_top10"):
            with st.spinner("Scanning NSE universe…"):
                out=auto_top10(10)
            if out.empty: st.error("No candidates returned. Try Refresh all cached data and run again later.")
            else:
                st.session_state["top10"]=out
                cols=["Rank","Symbol","Score","Technical","Fundamental","RS vs NIFTY %","Sector RS %","RSI","Vol X","Entry","Stop","Target","Event penalty","Signal","Why"]
                st.dataframe(out[cols],use_container_width=True,hide_index=True)
                st.download_button("⬇️ Export Top 10",out.to_csv(index=False),"v5_top10.csv","text/csv",key="scanner_top10_export")
    else:
        sel=st.multiselect("Scan universe",u,default=u[:12])
        if st.button("🚀 Run custom scanner",key="custom_scan"):
            rows=[]
            with st.spinner("Scanning selected symbols…"):
                for s in sel:
                    try: rows.append(signal(s))
                    except Exception as e: st.warning(f"{s}: {e}")
            if rows:
                out=pd.DataFrame(rows).sort_values("Score",ascending=False)
                st.dataframe(out,use_container_width=True,hide_index=True)
                st.download_button("⬇️ Export signals",out.to_csv(index=False),"v5_signals.csv","text/csv",key="custom_export")

elif tab=="🔍 Stock":
    sym=st.selectbox("NSE stock",universe());d=ind(prices(sym));x=d.iloc[-1];r=signal(sym);f=fundamentals(sym);pen,hits,ann=event_risk(sym)
    a,b,c,d1=st.columns(4);a.metric("Score",r["Score"]);b.metric("RSI",r["RSI"]);c.metric("Sector RS",f"{r['Sector RS %']:.1f}%");d1.metric("Signal",r["Signal"])
    fig=go.Figure();fig.add_trace(go.Candlestick(x=d.index,open=d.Open,high=d.High,low=d.Low,close=d.Close,name="Price"));fig.add_trace(go.Scatter(x=d.index,y=d.SMA50,name="SMA50"));fig.add_trace(go.Scatter(x=d.index,y=d.SMA200,name="SMA200"));fig.update_layout(height=420,xaxis_rangeslider_visible=False,margin=dict(l=5,r=5,t=5,b=5));st.plotly_chart(fig,use_container_width=True)
    st.subheader("Decision sheet");st.json(r)
    st.subheader("Fundamentals");st.dataframe(pd.DataFrame([f]).T.rename(columns={0:"Value"}),use_container_width=True)
    if hits:st.warning("Event-risk keywords: "+", ".join(hits))
    st.subheader("Recent announcement sample");st.dataframe(ann,use_container_width=True,hide_index=True)
    st.caption("Always verify important announcements on NSE/company filings before trading.")

elif tab=="📊 Backtest":
    sym=st.selectbox("Stock",universe());initial=st.number_input("Initial capital ₹",100000.,100000000.,1000000.,100000.);rp=st.number_input("Risk/trade %",.1,3.,.75,.05);mp=st.number_input("Max position %",5.,50.,20.,1.);fee=st.number_input("Fees + taxes (bps/turnover)",0.,100.,10.,1.);slip=st.number_input("Slippage (bps/turnover)",0.,100.,5.,1.)
    if st.button("▶️ Run cost-aware backtest"):
        eq,tr=backtest(sym,initial,rp,mp,fee,slip);dd=eq.Equity/eq.Equity.cummax()-1
        a,b,c,d=st.columns(4);a.metric("Final",f"₹{eq.Equity.iloc[-1]:,.0f}");b.metric("Return",f"{(eq.Equity.iloc[-1]/initial-1)*100:.1f}%");c.metric("Max DD",f"{dd.min()*100:.1f}%");d.metric("Trades",len(tr))
        if len(tr):st.metric("Win rate",f"{(tr.PnL>0).mean()*100:.1f}%")
        st.plotly_chart(go.Figure(go.Scatter(x=eq.index,y=eq.Equity,mode="lines")),use_container_width=True);st.dataframe(tr,use_container_width=True,hide_index=True)
        st.caption("This is a historical simulation, not a prediction. It does not model every real-world execution issue.")

elif tab=="💼 Portfolio":
    st.subheader("Paper portfolio risk")
    cap=st.number_input("Portfolio equity ₹",100000.,100000000.,1000000.,100000.);rp=st.number_input("Risk/trade %",.1,3.,.75,.05);mp=st.number_input("Max position %",5.,50.,20.,1.)
    if "portfolio" not in st.session_state:st.session_state.portfolio=[]
    sym=st.selectbox("Add candidate",universe());r=signal(sym)
    sh,val,loss=risk_size(cap,rp,r["Entry"],r["Stop"],mp)
    a,b,c=st.columns(3);a.metric("Suggested shares",sh);b.metric("Position",f"₹{val:,.0f}");c.metric("Risk",f"₹{loss:,.0f}")
    if st.button("➕ Add paper position"):
        st.session_state.portfolio.append({"Symbol":r["Symbol"],"Entry":r["Entry"],"Stop":r["Stop"],"Target":r["Target"],"Shares":sh,"Risk₹":loss,"Score":r["Score"]})
    if st.session_state.portfolio:
        pf=pd.DataFrame(st.session_state.portfolio);st.dataframe(pf,use_container_width=True,hide_index=True)
        st.metric("Total planned risk",f"₹{pf['Risk₹'].sum():,.0f}")
        st.download_button("⬇️ Export portfolio",pf.to_csv(index=False),"paper_portfolio.csv","text/csv")

elif tab=="📝 Journal":
    st.subheader("Trade journal")
    if "journal" not in st.session_state:st.session_state.journal=pd.DataFrame(columns=["Date","Symbol","Setup","Entry","Stop","Target","Shares","Result","R","Notes"])
    with st.form("journal"):
        sym=st.text_input("Symbol");setup=st.selectbox("Setup",["Breakout","Retest","Other"]);a,b=st.columns(2);en=a.number_input("Entry ₹",0.);sp=b.number_input("Stop ₹",0.);a,b=st.columns(2);tg=a.number_input("Target ₹",0.);sh=b.number_input("Shares",0,1000000,0);res=st.selectbox("Result",["OPEN","WIN","LOSS","BREAKEVEN"]);notes=st.text_area("Notes");ok=st.form_submit_button("Add")
    if ok and sym:
        risk=abs(en-sp)*sh;pnl=(tg-en)*sh if res=="WIN" else -risk if res=="LOSS" else 0
        st.session_state.journal=pd.concat([st.session_state.journal,pd.DataFrame([{"Date":datetime.now().date(),"Symbol":sym,"Setup":setup,"Entry":en,"Stop":sp,"Target":tg,"Shares":sh,"Result":res,"R":pnl/risk if risk else 0,"Notes":notes}])],ignore_index=True)
    st.dataframe(st.session_state.journal,use_container_width=True,hide_index=True);st.download_button("⬇️ Export journal",st.session_state.journal.to_csv(index=False),"trade_journal.csv","text/csv")

else:
    st.subheader("AI research assistant")
    sym=st.text_input("Stock","RELIANCE.NS")
    r=signal(sym) if sym in universe() else None
    prompt=f"""You are an NSE positional-trading research assistant.

Stock: {sym}
Holding period: 2–12 weeks.

V5 machine snapshot:
{json.dumps(r,indent=2,default=str) if r else "No machine snapshot available."}

Use verified current data and official company disclosures. Separate FACTS from INTERPRETATION. Never invent missing figures.

Assess quarterly financial trend, valuation vs peers/history, ROE/ROCE, margins, debt/cash flow, promoter/shareholding and institutional flows, sector strength, technical trend, breakout quality, recent corporate announcements, event risks, liquidity, and invalidation conditions.

Return:
1. Evidence table
2. Bull case
3. Bear case
4. Key risks
5. What would invalidate the setup
6. WATCH / BUY-CANDIDATE / AVOID conclusion
7. Confidence and missing information

Do not predict a future price and do not present the output as guaranteed investment advice."""
    st.code(prompt);st.download_button("⬇️ Save AI prompt",prompt,"v5_ai_research_prompt.txt","text/plain")

st.divider();st.caption("V5 is research/paper trading software. Data may be delayed, incomplete or unavailable. No live broker orders are placed.")
