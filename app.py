import datetime
import math
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
from plotly.subplots import make_subplots
from streamlit_autorefresh import st_autorefresh

st.set_page_config(
    page_title="Stock Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── TradingView-style CSS ──────────────────────────────────────────────────────
st.markdown("""
<style>
  .stApp { background-color: #131722; color: #d1d4dc; }
  [data-testid="stSidebar"] { background-color: #1e222d; border-right: 1px solid #2a2e39; }
  [data-testid="metric-container"] {
    background-color: #1e222d; border: 1px solid #2a2e39;
    border-radius: 6px; padding: 12px 16px;
  }
  [data-testid="stMetricLabel"]  { color: #787b86 !important; font-size: 11px !important; text-transform: uppercase; letter-spacing: 0.5px; }
  [data-testid="stMetricValue"]  { color: #d1d4dc !important; font-size: 18px !important; font-weight: 600; }
  [data-testid="stMetricDelta"]  { font-size: 13px !important; }
  .stTabs [data-baseweb="tab-list"] { background-color: #1e222d; border-bottom: 1px solid #2a2e39; gap: 0; }
  .stTabs [data-baseweb="tab"] { color: #787b86; padding: 10px 20px; font-size: 13px; border: none; }
  .stTabs [aria-selected="true"] { color: #d1d4dc !important; border-bottom: 2px solid #2962ff !important; background: transparent !important; }
  h1,h2,h3 { color: #d1d4dc !important; }
  p, li, span { color: #d1d4dc; }
  .stMarkdown hr { border-color: #2a2e39; }
  [data-testid="stSidebarContent"] label { color: #d1d4dc !important; }
  .stSelectbox > div > div { background-color: #2a2e39 !important; color: #d1d4dc !important; border-color: #363a45 !important; }
  .stTextInput > div > div > input { background-color: #2a2e39 !important; color: #d1d4dc !important; border-color: #363a45 !important; }
  .stButton > button { background-color: #2a2e39; color: #d1d4dc; border: 1px solid #363a45; border-radius: 4px; font-size: 12px; }
  .stButton > button:hover { background-color: #363a45; border-color: #2962ff; }
  .verdict-box {
    border-radius: 8px; padding: 20px 28px; margin-bottom: 20px;
    display: flex; align-items: center; gap: 20px;
  }
  .signal-row { padding: 8px 12px; border-radius: 4px; margin: 4px 0; font-size: 13px; }
  .signal-bull { background: rgba(38,166,154,0.12); border-left: 3px solid #26a69a; color: #d1d4dc; }
  .signal-bear { background: rgba(239,83,80,0.12);  border-left: 3px solid #ef5350; color: #d1d4dc; }
  .signal-neut { background: rgba(255,215,0,0.08);  border-left: 3px solid #ffd700; color: #d1d4dc; }
  .target-card {
    background: #1e222d; border: 1px solid #2a2e39; border-radius: 6px;
    padding: 14px 18px; text-align: center;
  }
</style>
""", unsafe_allow_html=True)

st_autorefresh(interval=60_000, limit=None, key="live_refresh")

# ── Chart theme (TradingView colors) ──────────────────────────────────────────
TV = dict(
    plot_bgcolor="#131722", paper_bgcolor="#131722",
    font=dict(color="#787b86", family="Trebuchet MS,sans-serif", size=11),
    xaxis=dict(gridcolor="#1e222d", linecolor="#2a2e39", showgrid=True,
               zeroline=False, tickcolor="#787b86", tickfont=dict(color="#787b86")),
    yaxis=dict(gridcolor="#1e222d", linecolor="#2a2e39", showgrid=True,
               zeroline=False, tickcolor="#787b86", tickfont=dict(color="#787b86"),
               side="right"),
    legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="#787b86", size=11)),
    margin=dict(l=12, r=60, t=12, b=0),
    hovermode="x unified",
    hoverlabel=dict(bgcolor="#1e222d", font_color="#d1d4dc", bordercolor="#2a2e39"),
)

# ── Helpers ────────────────────────────────────────────────────────────────────
def _v(val, fmt=".2f", suffix=""):
    if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
        return "—"
    return f"{val:{fmt}}{suffix}"

def _B(val):
    if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
        return "—"
    if val >= 1e12: return f"${val/1e12:.2f}T"
    if val >= 1e9:  return f"${val/1e9:.2f}B"
    if val >= 1e6:  return f"${val/1e6:.2f}M"
    return f"${val:,.0f}"

def _P(val):
    if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
        return "—"
    return f"{val*100:.1f}%"

def _market_status():
    et  = ZoneInfo("America/New_York")
    now = datetime.datetime.now(et)
    t, wd = now.time(), now.weekday()
    if wd >= 5:                                             return "⬤ Closed",      "#ef5350"
    if datetime.time(9,30) <= t < datetime.time(16,0):     return "⬤ Market Open", "#26a69a"
    if datetime.time(4,0)  <= t < datetime.time(9,30):     return "⬤ Pre-Market",  "#ffd700"
    if datetime.time(16,0) <= t < datetime.time(20,0):     return "⬤ After-Hours", "#ffd700"
    return "⬤ Closed", "#ef5350"

@st.cache_data(ttl=55)
def _load(ticker, period):
    t = yf.Ticker(ticker)
    return t.history(period=period, auto_adjust=True), t.info, (t.news or [])

def _rsi(c, n=14):
    d = c.diff()
    g = d.clip(lower=0).rolling(n).mean()
    l = (-d.clip(upper=0)).rolling(n).mean()
    return 100 - 100 / (1 + g / l.replace(0, 1e-10))

def _macd(c):
    m = c.ewm(span=12,adjust=False).mean() - c.ewm(span=26,adjust=False).mean()
    s = m.ewm(span=9, adjust=False).mean()
    return m, s, m - s

def _bb(c, n=20, w=2.0):
    mid = c.rolling(n).mean(); sd = c.rolling(n).std()
    return mid, mid + w*sd, mid - w*sd

# ── Weekly picks universe ─────────────────────────────────────────────────────
SCAN_UNIVERSE = [
    "NVDA","AMD","INTC","MU","MRVL","SMCI","NVTS","AVGO","ARM","TSM",
    "IONQ","QBTS","RGTI","QUBT","ARQQ","IBM",
    "ENPH","SEDG","FSLR","RUN","ARRY","FLNC","MAXN","TAN",
    "RKLB","ASTS","LUNR","RDW","ACHR","JOBY","SPCE","BA","GE",
    "PLTR","SOUN","BBAI","AI","KULR","SERV","IREN","WULF","GFAI",
    "BB","NOK","ERIC","LUMN",
    "TSLA","RIVN","LCID","CHPT","BLNK","EVGO","NIO","XPEV","LI",
    "MARA","RIOT","HUT","CIFR","BITF","MIGI","COIN","HOOD","SOFI",
    "AAPL","MSFT","GOOGL","META","AMZN","NFLX","PYPL","SQ","AFRM",
    "SNAP","PINS","UBER","LYFT","ABNB","DASH","GME","AMC","SKLZ",
    "DPRO","MARK","NNDM","CLOV","WKHS","OPEN","MVST","BFLY","ATER",
]

SECTOR_ETFS = {
    "Technology":        "XLK",
    "Financials":        "XLF",
    "Energy":            "XLE",
    "Healthcare":        "XLV",
    "Communication":     "XLC",
    "Consumer Disc.":    "XLY",
    "Consumer Staples":  "XLP",
    "Industrials":       "XLI",
    "Materials":         "XLB",
    "Real Estate":       "XLRE",
    "Utilities":         "XLU",
}

INDICES = {"S&P 500": "SPY", "NASDAQ 100": "QQQ", "Russell 2000": "IWM", "Dow Jones": "DIA"}


def _quick_score(close, lrsi, lmacd, lsig, lma20, lma50):
    price = float(close.iloc[-1])
    score = 0
    if price > lma20: score += 1
    else:             score -= 1
    if price > lma50: score += 1
    else:             score -= 1
    if lma20 > lma50: score += 1
    else:             score -= 1
    if   lrsi < 30:            score += 2
    elif lrsi > 70:            score -= 2
    elif 45 <= lrsi <= 65:     score += 1
    if lmacd > lsig:  score += 1
    else:             score -= 1
    if len(close) >= 5:
        m5 = (price - float(close.iloc[-5])) / float(close.iloc[-5]) * 100
        if   m5 > 5:  score += 1
        elif m5 < -5: score -= 1
    return score


@st.cache_data(ttl=1800)
def _weekly_scan():
    syms = list(dict.fromkeys(SCAN_UNIVERSE))
    try:
        df = yf.download(" ".join(syms), period="21d", auto_adjust=True,
                         progress=False, threads=True, group_by="ticker")
    except Exception:
        return []

    picks = []
    for sym in syms:
        try:
            sym_df = df if len(syms) == 1 else (df[sym] if sym in df.columns.get_level_values(0) else None)
            if sym_df is None or sym_df.empty or len(sym_df) < 10:
                continue
            close  = sym_df["Close"].dropna()
            price  = float(close.iloc[-1])
            if not (0.50 <= price <= 999):
                continue
            ma20 = close.rolling(20).mean(); ma50 = close.rolling(50).mean()
            lma20 = float(ma20.dropna().iloc[-1]) if not ma20.dropna().empty else price
            lma50 = float(ma50.dropna().iloc[-1]) if not ma50.dropna().empty else price
            lrsi  = float(_rsi(close).dropna().iloc[-1]) if not _rsi(close).dropna().empty else 50
            ml, sl, _ = _macd(close)
            lmacd = float(ml.dropna().iloc[-1]) if not ml.dropna().empty else 0
            lsig  = float(sl.dropna().iloc[-1]) if not sl.dropna().empty else 0
            score = _quick_score(close, lrsi, lmacd, lsig, lma20, lma50)
            if score < 2:
                continue
            prev5     = float(close.iloc[-6]) if len(close) >= 6 else float(close.iloc[0])
            week_pct  = round((price - prev5) / prev5 * 100, 2)
            entry     = round(min(price, lma20) * 0.997, 2)
            stop      = round(lma50 * 0.97, 2)
            target    = round(price * 1.15, 2)
            picks.append(dict(symbol=sym, price=round(price,2), week_pct=week_pct,
                              score=score, rsi=round(lrsi,1), ma20=round(lma20,2),
                              entry=entry, stop=stop, target=target, name=sym, sector=""))
        except Exception:
            continue

    picks.sort(key=lambda x: x["score"], reverse=True)
    top = picks[:10]
    for p in top:
        try:
            inf = yf.Ticker(p["symbol"]).fast_info
            p["name"] = p["symbol"]
        except Exception:
            pass
    # Enrich names
    for p in top:
        try:
            p["name"] = yf.Ticker(p["symbol"]).info.get("shortName") or p["symbol"]
            p["sector"] = yf.Ticker(p["symbol"]).info.get("sector","")
        except Exception:
            pass
    return top


@st.cache_data(ttl=120)
def _market_overview():
    all_syms = list(INDICES.values()) + list(SECTOR_ETFS.values()) + ["^VIX"]
    try:
        df = yf.download(" ".join(all_syms), period="6mo", auto_adjust=True,
                         progress=False, threads=True, group_by="ticker")
    except Exception:
        return {}, {}

    def _pct_change(sym):
        try:
            s = df[sym]["Close"].dropna() if sym in df.columns.get_level_values(0) else pd.Series()
            if len(s) < 2: return None
            return round((float(s.iloc[-1]) - float(s.iloc[-2])) / float(s.iloc[-2]) * 100, 2)
        except Exception:
            return None

    def _week_pct(sym):
        try:
            s = df[sym]["Close"].dropna() if sym in df.columns.get_level_values(0) else pd.Series()
            if len(s) < 6: return None
            return round((float(s.iloc[-1]) - float(s.iloc[-6])) / float(s.iloc[-6]) * 100, 2)
        except Exception:
            return None

    def _price(sym):
        try:
            s = df[sym]["Close"].dropna() if sym in df.columns.get_level_values(0) else pd.Series()
            return round(float(s.iloc[-1]), 2) if not s.empty else None
        except Exception:
            return None

    def _sparkline(sym):
        try:
            s = df[sym]["Close"].dropna() if sym in df.columns.get_level_values(0) else pd.Series()
            return s.iloc[-20:].tolist() if len(s) >= 20 else s.tolist()
        except Exception:
            return []

    def _above_ma200(sym):
        try:
            s = df[sym]["Close"].dropna() if sym in df.columns.get_level_values(0) else pd.Series()
            if len(s) < 200: return None
            return float(s.iloc[-1]) > float(s.rolling(200).mean().iloc[-1])
        except Exception:
            return None

    indices = {}
    for name, sym in INDICES.items():
        indices[name] = dict(sym=sym, price=_price(sym), day_pct=_pct_change(sym),
                             week_pct=_week_pct(sym), sparkline=_sparkline(sym),
                             above_ma200=_above_ma200(sym))

    vix_price = _price("^VIX")
    vix_day   = _pct_change("^VIX")

    sectors = {}
    for name, sym in SECTOR_ETFS.items():
        sectors[name] = dict(sym=sym, day_pct=_pct_change(sym),
                             week_pct=_week_pct(sym), price=_price(sym))

    return indices, sectors, vix_price, vix_day


def _trade_setup(close, hist, rsi_s, macd_line, sig_line, ma20, ma50, ma200):
    price   = float(close.iloc[-1])
    lma20   = float(ma20.dropna().iloc[-1])  if not ma20.dropna().empty  else price
    lma50   = float(ma50.dropna().iloc[-1])  if not ma50.dropna().empty  else price
    lma200  = float(ma200.dropna().iloc[-1]) if not ma200.dropna().empty else None
    lrsi    = float(rsi_s.dropna().iloc[-1]) if not rsi_s.dropna().empty else 50
    lmacd   = float(macd_line.dropna().iloc[-1]) if not macd_line.dropna().empty else 0
    lsig    = float(sig_line.dropna().iloc[-1])  if not sig_line.dropna().empty  else 0

    score, sigs = 0, []

    # Price vs MAs
    if price > lma20:
        score += 1; sigs.append(("bull", f"Price ${price:.2f} above MA20 ${lma20:.2f}"))
    else:
        score -= 1; sigs.append(("bear", f"Price ${price:.2f} below MA20 ${lma20:.2f}"))
    if price > lma50:
        score += 1; sigs.append(("bull", f"Price above MA50 ${lma50:.2f}"))
    else:
        score -= 1; sigs.append(("bear", f"Price below MA50 ${lma50:.2f}"))
    if lma200:
        if price > lma200:
            score += 1; sigs.append(("bull", f"Price above MA200 ${lma200:.2f} — long-term uptrend"))
        else:
            score -= 1; sigs.append(("bear", f"Price below MA200 ${lma200:.2f} — long-term downtrend"))

    # MA alignment (golden/death cross)
    if lma20 > lma50:
        score += 1; sigs.append(("bull", "MA20 above MA50 — golden cross alignment"))
    else:
        score -= 1; sigs.append(("bear", "MA20 below MA50 — death cross alignment"))

    # RSI
    if lrsi < 30:
        score += 2; sigs.append(("bull", f"RSI {lrsi:.0f} — Oversold, high-probability bounce zone"))
    elif lrsi > 70:
        score -= 2; sigs.append(("bear", f"RSI {lrsi:.0f} — Overbought, elevated risk"))
    elif 45 <= lrsi <= 65:
        score += 1; sigs.append(("bull", f"RSI {lrsi:.0f} — Healthy momentum range"))
    elif 30 <= lrsi < 45:
        sigs.append(("neut", f"RSI {lrsi:.0f} — Recovering from weakness"))
    else:
        sigs.append(("neut", f"RSI {lrsi:.0f} — Approaching overbought"))

    # MACD
    if lmacd > lsig:
        score += 1; sigs.append(("bull", f"MACD ({lmacd:.3f}) above signal ({lsig:.3f}) — bullish momentum"))
    else:
        score -= 1; sigs.append(("bear", f"MACD ({lmacd:.3f}) below signal ({lsig:.3f}) — bearish momentum"))

    # 5-day momentum
    if len(close) >= 5:
        m5 = (float(close.iloc[-1]) - float(close.iloc[-5])) / float(close.iloc[-5]) * 100
        if m5 > 5:
            score += 1; sigs.append(("bull", f"Strong 5-day momentum: +{m5:.1f}%"))
        elif m5 < -5:
            score -= 1; sigs.append(("bear", f"Weak 5-day momentum: {m5:.1f}%"))

    # Verdict
    if   score >= 5:  v, vc, vs = "STRONG BUY",  "#26a69a", "green"
    elif score >= 2:  v, vc, vs = "BUY",          "#4caf50", "green"
    elif score <= -5: v, vc, vs = "STRONG SELL",  "#ef5350", "red"
    elif score <= -2: v, vc, vs = "SELL",          "#f44336", "red"
    else:             v, vc, vs = "NEUTRAL / HOLD","#ffd700", "yellow"

    # Entry zone
    bullish = score > 0
    if bullish:
        entry_lo  = round(min(price, lma20) * 0.995, 2)
        entry_hi  = round(price * 1.005, 2)
        stop      = round(lma50 * 0.97, 2)
        t1 = round(price * 1.10, 2)
        t2 = round(price * 1.22, 2)
        t3 = round(price * 1.40, 2)
    else:
        entry_lo  = round(price * 0.998, 2)
        entry_hi  = round(price * 1.002, 2)
        stop      = round(lma20 * 1.04, 2)
        t1 = round(price * 0.90, 2)
        t2 = round(price * 0.80, 2)
        t3 = round(price * 0.65, 2)

    risk   = abs(price - stop)
    reward = abs(t1 - price)
    rr     = round(reward / risk, 1) if risk > 0 else 0

    # Narrative
    if bullish:
        narrative = (
            f"**{v}** — {len([s for s in sigs if s[0]=='bull'])} bullish signals active. "
            f"Ideal entry between **${entry_lo}–${entry_hi}**. "
            f"Place stop below **${stop}** (MA50 support). "
            f"First target **${t1}** (+{(t1/price-1)*100:.0f}%), "
            f"extended target **${t2}** (+{(t2/price-1)*100:.0f}%). "
            f"Risk/Reward: **1:{rr}**."
        )
    else:
        narrative = (
            f"**{v}** — {len([s for s in sigs if s[0]=='bear'])} bearish signals active. "
            f"Avoid new longs until price reclaims **${lma20:.2f}** (MA20). "
            f"Downside targets: **${t1}** ({(t1/price-1)*100:.0f}%), **${t2}** ({(t2/price-1)*100:.0f}%). "
            f"Stop for any short position: **${stop}** above MA20."
        )

    return dict(verdict=v, verdict_color=vc, verdict_style=vs, score=score,
                signals=sigs, entry_lo=entry_lo, entry_hi=entry_hi,
                stop=stop, t1=t1, t2=t2, t3=t3, rr=rr,
                bullish=bullish, narrative=narrative, rsi=lrsi)

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("<h2 style='color:#d1d4dc;margin-bottom:4px;'>📈 Stock Analyzer</h2>", unsafe_allow_html=True)
    status_label, status_color = _market_status()
    now_et = datetime.datetime.now(ZoneInfo("America/New_York"))
    st.markdown(
        f'<span style="color:{status_color};font-size:13px;font-weight:600;">{status_label}</span>'
        f'<span style="color:#555;font-size:11px;margin-left:8px;">{now_et.strftime("%I:%M:%S %p ET")}</span>',
        unsafe_allow_html=True,
    )
    components.html("""
    <script>
      var s=60; function tick(){s--;if(s<0)s=60;var e=document.getElementById('cd');if(e)e.innerText='Refreshes in '+s+'s';}
      setInterval(tick,1000);
    </script>
    <p id="cd" style="color:#555;font-size:11px;margin:2px 0 0 0;">Refreshes in 60s</p>
    """, height=20)

    st.markdown("<hr style='border-color:#2a2e39;margin:10px 0;'>", unsafe_allow_html=True)

    raw = st.text_input("", value="NVDA", placeholder="Enter ticker…",
                        label_visibility="collapsed")
    ticker = raw.upper().strip()

    period_label = st.selectbox("Period", ["1M","3M","6M","1Y","2Y","5Y"], index=3,
                                label_visibility="visible")
    period = {"1M":"1mo","3M":"3mo","6M":"6mo","1Y":"1y","2Y":"2y","5Y":"5y"}[period_label]

    st.markdown("<p style='color:#555;font-size:11px;margin:8px 0 4px 0;'>QUICK PICKS</p>", unsafe_allow_html=True)
    qrow1 = st.columns(3)
    qrow2 = st.columns(3)
    quick = [("NVDA","q1"),("AAPL","q2"),("TSLA","q3"),("SOUN","q4"),("IONQ","q5"),("PLTR","q6")]
    for i,(sym,k) in enumerate(quick):
        row = qrow1 if i < 3 else qrow2
        if row[i%3].button(sym, key=k, use_container_width=True):
            ticker = sym

    st.markdown("<hr style='border-color:#2a2e39;margin:10px 0;'>", unsafe_allow_html=True)
    st.markdown("<p style='color:#555;font-size:10px;'>10,000+ US & global stocks · Yahoo Finance · Not financial advice</p>", unsafe_allow_html=True)

# ── Load ───────────────────────────────────────────────────────────────────────
if not ticker:
    st.info("Enter a ticker symbol.")
    st.stop()

with st.spinner(f"Loading {ticker}…"):
    try:
        hist, info, news = _load(ticker, period)
    except Exception as e:
        st.error(f"Error: {e}"); st.stop()

if hist is None or hist.empty:
    st.error(f"**{ticker}** not found."); st.stop()

close   = hist["Close"]
price   = float(close.iloc[-1])
prev    = float(close.iloc[-2]) if len(close) >= 2 else price
day_pct = (price - prev) / prev * 100 if prev else 0

name     = info.get("shortName") or info.get("longName") or ticker
sector   = info.get("sector","")
exchange = info.get("exchange","")

ma20  = close.rolling(20).mean()
ma50  = close.rolling(50).mean()
ma200 = close.rolling(200).mean()
rsi_s                    = _rsi(close)
macd_l, sig_l, macd_h   = _macd(close)
bb_mid, bb_up, bb_dn     = _bb(close)

# ── Header ─────────────────────────────────────────────────────────────────────
pct_color = "#26a69a" if day_pct >= 0 else "#ef5350"
sign = "+" if day_pct >= 0 else ""

st.markdown(
    f'<div style="display:flex;align-items:baseline;gap:16px;padding:4px 0 8px 0;">'
    f'<span style="color:#d1d4dc;font-size:22px;font-weight:700;">{name}</span>'
    f'<span style="color:#555;font-size:14px;">{ticker} · {exchange}</span>'
    f'<span style="color:#d1d4dc;font-size:26px;font-weight:700;margin-left:auto;">${price:.2f}</span>'
    f'<span style="color:{pct_color};font-size:16px;font-weight:600;">{sign}{day_pct:.2f}%</span>'
    f'<span style="color:#555;font-size:11px;">{datetime.datetime.now().strftime("%I:%M:%S %p")}</span>'
    f'</div>',
    unsafe_allow_html=True,
)

c1,c2,c3,c4,c5,c6 = st.columns(6)
c1.metric("Market Cap",     _B(info.get("marketCap")))
c2.metric("Volume",         _v(float(hist["Volume"].iloc[-1]),",.0f") if "Volume" in hist else "—")
c3.metric("Avg Volume",     _v(info.get("averageVolume"),",.0f") if info.get("averageVolume") else "—")
c4.metric("52W High",       f"${info.get('fiftyTwoWeekHigh',0):.2f}")
c5.metric("52W Low",        f"${info.get('fiftyTwoWeekLow',0):.2f}")
c6.metric("Beta",           _v(info.get("beta")))

st.markdown("<hr style='border-color:#2a2e39;margin:6px 0 0 0;'>", unsafe_allow_html=True)

# ── Tabs ───────────────────────────────────────────────────────────────────────
tabs = st.tabs(["📊  Chart", "🎯  Trade Setup", "📅  This Week", "🌍  Market Trends", "📉  Technicals", "📋  Fundamentals", "📰  News & Analysts"])

# ══════════════════════════════════════════════════════════════════════
# TAB 1 — CHART (TradingView style)
# ══════════════════════════════════════════════════════════════════════
with tabs[0]:
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        vertical_spacing=0.02, row_heights=[0.78, 0.22])

    fig.add_trace(go.Candlestick(
        x=hist.index, open=hist["Open"], high=hist["High"],
        low=hist["Low"], close=hist["Close"], name=ticker,
        increasing=dict(line=dict(color="#26a69a", width=1), fillcolor="#26a69a"),
        decreasing=dict(line=dict(color="#ef5350", width=1), fillcolor="#ef5350"),
        showlegend=False, whiskerwidth=0.3,
    ), row=1, col=1)

    for ma_s, label, color, dash in [
        (ma20,  "MA20",  "#f0b429", "solid"),
        (ma50,  "MA50",  "#2962ff", "solid"),
        (ma200, "MA200", "#e040fb", "solid"),
    ]:
        fig.add_trace(go.Scatter(
            x=hist.index, y=ma_s, name=label,
            line=dict(color=color, width=1.4, dash=dash), opacity=0.9,
        ), row=1, col=1)

    vol_up   = [float(v) if float(c)>=float(o) else None for v,c,o in zip(hist["Volume"],hist["Close"],hist["Open"])]
    vol_down = [float(v) if float(c)< float(o) else None for v,c,o in zip(hist["Volume"],hist["Close"],hist["Open"])]
    fig.add_trace(go.Bar(x=hist.index, y=vol_up,   name="Vol ▲",
        marker_color="rgba(38,166,154,0.5)", showlegend=False), row=2, col=1)
    fig.add_trace(go.Bar(x=hist.index, y=vol_down, name="Vol ▼",
        marker_color="rgba(239,83,80,0.5)",  showlegend=False), row=2, col=1)

    fig.update_layout(
        **TV, height=580,
        xaxis_rangeslider_visible=False,
        xaxis2=dict(gridcolor="#1e222d", linecolor="#2a2e39", tickcolor="#787b86",
                    tickfont=dict(color="#787b86")),
        yaxis2=dict(gridcolor="#1e222d", linecolor="#2a2e39", side="right",
                    tickcolor="#787b86", tickfont=dict(color="#787b86")),
        barmode="overlay",
    )
    fig.update_yaxes(tickprefix="$", tickformat=",.2f", row=1, col=1)
    st.plotly_chart(fig, use_container_width=True)

    lo52  = info.get("fiftyTwoWeekLow")
    hi52  = info.get("fiftyTwoWeekHigh")
    if lo52 and hi52 and hi52 > lo52:
        pos = (price - lo52) / (hi52 - lo52)
        st.markdown(
            f'<div style="display:flex;justify-content:space-between;color:#787b86;font-size:12px;margin-bottom:4px;">'
            f'<span>52W Low &nbsp;<strong style="color:#ef5350;">${lo52:.2f}</strong></span>'
            f'<span style="color:#d1d4dc;font-weight:600;">${price:.2f}</span>'
            f'<span>52W High &nbsp;<strong style="color:#26a69a;">${hi52:.2f}</strong></span>'
            f'</div>', unsafe_allow_html=True,
        )
        st.progress(min(max(pos, 0.0), 1.0))

# ══════════════════════════════════════════════════════════════════════
# TAB 2 — TRADE SETUP
# ══════════════════════════════════════════════════════════════════════
with tabs[1]:
    ts = _trade_setup(close, hist, rsi_s, macd_l, sig_l, ma20, ma50, ma200)

    bull_bg   = "rgba(38,166,154,0.15)"  if ts["bullish"] else "rgba(239,83,80,0.15)"
    bull_bord = "#26a69a"                 if ts["bullish"] else "#ef5350"

    st.markdown(
        f'<div style="background:{bull_bg};border:1px solid {bull_bord};border-radius:8px;'
        f'padding:20px 24px;margin-bottom:20px;">'
        f'<div style="font-size:28px;font-weight:800;color:{ts["verdict_color"]};letter-spacing:1px;">'
        f'{ts["verdict"]}</div>'
        f'<div style="color:#787b86;font-size:12px;margin-top:4px;">'
        f'Signal Score: {ts["score"]:+d} &nbsp;·&nbsp; RSI: {ts["rsi"]:.0f}</div>'
        f'</div>', unsafe_allow_html=True,
    )

    st.markdown(f'<p style="color:#d1d4dc;font-size:14px;margin-bottom:20px;">{ts["narrative"]}</p>',
                unsafe_allow_html=True)

    # Entry / Stop / Targets
    e1, e2, e3, e4, e5 = st.columns(5)

    e1.markdown(
        f'<div class="target-card">'
        f'<div style="color:#787b86;font-size:10px;text-transform:uppercase;letter-spacing:0.5px;">Entry Zone</div>'
        f'<div style="color:#ffd700;font-size:18px;font-weight:700;margin-top:6px;">${ts["entry_lo"]} – ${ts["entry_hi"]}</div>'
        f'<div style="color:#555;font-size:11px;margin-top:2px;">Buy range</div>'
        f'</div>', unsafe_allow_html=True,
    )
    e2.markdown(
        f'<div class="target-card">'
        f'<div style="color:#787b86;font-size:10px;text-transform:uppercase;letter-spacing:0.5px;">Stop Loss</div>'
        f'<div style="color:#ef5350;font-size:18px;font-weight:700;margin-top:6px;">${ts["stop"]}</div>'
        f'<div style="color:#555;font-size:11px;margin-top:2px;">'
        f'{((ts["stop"]-price)/price*100):+.1f}% from current</div>'
        f'</div>', unsafe_allow_html=True,
    )
    for tgt, label in [(ts["t1"],"Target 1"),(ts["t2"],"Target 2"),(ts["t3"],"Target 3")]:
        pct = (tgt - price) / price * 100
        col = e3 if label=="Target 1" else (e4 if label=="Target 2" else e5)
        col.markdown(
            f'<div class="target-card">'
            f'<div style="color:#787b86;font-size:10px;text-transform:uppercase;letter-spacing:0.5px;">{label}</div>'
            f'<div style="color:#26a69a;font-size:18px;font-weight:700;margin-top:6px;">${tgt}</div>'
            f'<div style="color:#555;font-size:11px;margin-top:2px;">{pct:+.1f}%</div>'
            f'</div>', unsafe_allow_html=True,
        )

    st.markdown(
        f'<div style="color:#787b86;font-size:12px;margin-top:12px;">'
        f'Risk / Reward Ratio: &nbsp;<strong style="color:#d1d4dc;">1 : {ts["rr"]}</strong>'
        f'&nbsp; (Target 1)</div>', unsafe_allow_html=True,
    )

    st.markdown("<hr style='border-color:#2a2e39;margin:20px 0;'>", unsafe_allow_html=True)
    st.markdown("<p style='color:#787b86;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;'>Signal Breakdown</p>",
                unsafe_allow_html=True)

    for kind, msg in ts["signals"]:
        css = {"bull": "signal-bull", "bear": "signal-bear", "neut": "signal-neut"}[kind]
        icon = {"bull": "▲", "bear": "▼", "neut": "●"}[kind]
        st.markdown(f'<div class="{css} signal-row">{icon} &nbsp; {msg}</div>',
                    unsafe_allow_html=True)

    st.markdown(
        '<p style="color:#363a45;font-size:10px;margin-top:16px;">'
        'Not financial advice. Signal scores are algorithmic estimates based on technical indicators only.</p>',
        unsafe_allow_html=True,
    )

# ══════════════════════════════════════════════════════════════════════
# TAB 3 — THIS WEEK'S PICKS
# ══════════════════════════════════════════════════════════════════════
with tabs[2]:
    st.markdown("<p style='color:#787b86;font-size:12px;'>Scans 80+ stocks · scored on RSI, MACD, MA alignment, momentum · cached 30 min</p>",
                unsafe_allow_html=True)

    with st.spinner("Scanning market for this week's best setups…"):
        weekly_picks = _weekly_scan()

    if not weekly_picks:
        st.warning("No strongly bullish picks found right now. Market may be in a bearish phase.")
    else:
        scan_time = datetime.datetime.now().strftime("%I:%M %p")
        st.markdown(f"<p style='color:#555;font-size:11px;margin-bottom:12px;'>Last scanned: {scan_time}</p>",
                    unsafe_allow_html=True)
        for rank, p in enumerate(weekly_picks, 1):
            sym      = p["symbol"]
            name     = p.get("name", sym)
            price    = p["price"]
            wpct     = p["week_pct"]
            score    = p["score"]
            entry    = p["entry"]
            stop     = p["stop"]
            target   = p["target"]
            rsi_v    = p["rsi"]
            sector_v = p.get("sector","")
            upside   = round((target - price) / price * 100, 1)
            risk_p   = round((price - stop) / price * 100, 1)
            wcolor   = "#26a69a" if wpct >= 0 else "#ef5350"
            wsign    = "+" if wpct >= 0 else ""
            score_c  = "#26a69a" if score >= 4 else ("#4caf50" if score >= 2 else "#ffd700")

            st.markdown(
                f'<div style="background:#1e222d;border:1px solid #2a2e39;border-left:3px solid {score_c};'
                f'border-radius:6px;padding:14px 18px;margin-bottom:10px;display:flex;align-items:center;gap:0;">'

                f'<div style="min-width:32px;color:#555;font-size:13px;font-weight:700;">#{rank}</div>'

                f'<div style="min-width:180px;">'
                f'<span style="color:#d1d4dc;font-size:15px;font-weight:700;">{sym}</span>'
                f'<span style="color:#555;font-size:11px;margin-left:8px;">{name[:22]}</span><br>'
                f'<span style="color:#555;font-size:10px;">{sector_v}</span>'
                f'</div>'

                f'<div style="min-width:100px;">'
                f'<div style="color:#d1d4dc;font-size:15px;font-weight:600;">${price:.2f}</div>'
                f'<div style="color:{wcolor};font-size:12px;">{wsign}{wpct:.1f}% wk</div>'
                f'</div>'

                f'<div style="min-width:90px;text-align:center;">'
                f'<div style="color:#ffd700;font-size:11px;text-transform:uppercase;letter-spacing:0.4px;">Entry</div>'
                f'<div style="color:#ffd700;font-size:14px;font-weight:600;">${entry}</div>'
                f'</div>'

                f'<div style="min-width:90px;text-align:center;">'
                f'<div style="color:#ef5350;font-size:11px;text-transform:uppercase;letter-spacing:0.4px;">Stop</div>'
                f'<div style="color:#ef5350;font-size:14px;font-weight:600;">${stop} <span style="font-size:10px;">(-{risk_p}%)</span></div>'
                f'</div>'

                f'<div style="min-width:90px;text-align:center;">'
                f'<div style="color:#26a69a;font-size:11px;text-transform:uppercase;letter-spacing:0.4px;">Target</div>'
                f'<div style="color:#26a69a;font-size:14px;font-weight:600;">${target} <span style="font-size:10px;">(+{upside}%)</span></div>'
                f'</div>'

                f'<div style="margin-left:auto;text-align:right;">'
                f'<div style="color:{score_c};font-size:18px;font-weight:800;">{score:+d}</div>'
                f'<div style="color:#555;font-size:10px;">RSI {rsi_v:.0f}</div>'
                f'</div>'

                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown('<p style="color:#363a45;font-size:10px;margin-top:12px;">Not financial advice. Technical signals only.</p>',
                unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════
# TAB 4 — MARKET TRENDS
# ══════════════════════════════════════════════════════════════════════
with tabs[3]:
    with st.spinner("Loading market data…"):
        try:
            indices, sectors, vix_price, vix_day = _market_overview()
        except Exception:
            indices, sectors, vix_price, vix_day = {}, {}, None, None

    # ── Major indices ──────────────────────────────────────────────────
    st.markdown("#### Major Indices")
    idx_cols = st.columns(5)
    for i, (name, data) in enumerate(indices.items()):
        dp = data.get("day_pct") or 0
        wp = data.get("week_pct") or 0
        pr = data.get("price")
        col = idx_cols[i]
        c = "#26a69a" if dp >= 0 else "#ef5350"
        s = "+" if dp >= 0 else ""
        col.markdown(
            f'<div style="background:#1e222d;border:1px solid #2a2e39;border-radius:6px;padding:12px 14px;">'
            f'<div style="color:#787b86;font-size:10px;text-transform:uppercase;">{name}</div>'
            f'<div style="color:#d1d4dc;font-size:17px;font-weight:700;margin-top:4px;">${pr:,.2f}</div>'
            f'<div style="color:{c};font-size:13px;">{s}{dp:.2f}% today</div>'
            f'<div style="color:#555;font-size:11px;">{("+" if wp>=0 else "")}{wp:.1f}% this week</div>'
            f'</div>', unsafe_allow_html=True,
        )

    # VIX
    vix_c = "#ef5350" if (vix_price or 20) > 25 else ("#ffd700" if (vix_price or 20) > 18 else "#26a69a")
    vix_mood = "High Fear" if (vix_price or 0) > 25 else ("Elevated" if (vix_price or 0) > 18 else "Low Fear / Calm")
    idx_cols[4].markdown(
        f'<div style="background:#1e222d;border:1px solid #2a2e39;border-radius:6px;padding:12px 14px;">'
        f'<div style="color:#787b86;font-size:10px;text-transform:uppercase;">VIX Fear Index</div>'
        f'<div style="color:{vix_c};font-size:17px;font-weight:700;margin-top:4px;">{vix_price:.1f}</div>'
        f'<div style="color:{vix_c};font-size:13px;">{vix_mood}</div>'
        f'<div style="color:#555;font-size:11px;">{"+" if (vix_day or 0)>=0 else ""}{vix_day:.1f}% today</div>'
        f'</div>' if vix_price else '<div style="color:#555;">—</div>', unsafe_allow_html=True,
    )

    # ── Market pulse ───────────────────────────────────────────────────
    spy_data   = indices.get("S&P 500", {})
    spy_above  = spy_data.get("above_ma200")
    qqq_data   = indices.get("NASDAQ 100", {})
    qqq_above  = qqq_data.get("above_ma200")

    bull_count = sum(1 for v in [spy_above, qqq_above] if v)
    pulse_color = "#26a69a" if bull_count >= 2 else ("#ffd700" if bull_count == 1 else "#ef5350")
    pulse_label = "Bull Market" if bull_count >= 2 else ("Mixed / Caution" if bull_count == 1 else "Bear Market")
    pulse_desc  = (
        "SPY and QQQ are both above their 200-day moving averages — broad market is in an uptrend. Risk-on conditions favor momentum and growth stocks."
        if bull_count >= 2 else
        "Mixed signals. One major index is below its 200-day MA. Be selective — focus on sector leaders with strong momentum."
        if bull_count == 1 else
        "Both SPY and QQQ are below their 200-day MAs — bear market conditions. Reduce risk, prioritize capital preservation."
    )

    st.markdown("<hr style='border-color:#2a2e39;margin:16px 0 12px 0;'>", unsafe_allow_html=True)
    st.markdown(
        f'<div style="background:rgba(0,0,0,0.25);border:1px solid {pulse_color};border-radius:8px;'
        f'padding:14px 20px;margin-bottom:16px;display:flex;align-items:center;gap:16px;">'
        f'<div style="color:{pulse_color};font-size:22px;font-weight:800;min-width:180px;">📡 {pulse_label}</div>'
        f'<div style="color:#787b86;font-size:13px;">{pulse_desc}</div>'
        f'</div>', unsafe_allow_html=True,
    )

    # ── Sector performance ─────────────────────────────────────────────
    st.markdown("#### Sector Performance")
    if sectors:
        sc1, sc2 = st.columns(2)

        # Today
        today_data = [(n, d.get("day_pct") or 0) for n, d in sectors.items()]
        today_data.sort(key=lambda x: x[1], reverse=True)
        names_t  = [x[0] for x in today_data]
        pcts_t   = [x[1] for x in today_data]
        colors_t = ["#26a69a" if p >= 0 else "#ef5350" for p in pcts_t]

        fig_sec_d = go.Figure(go.Bar(
            x=pcts_t, y=names_t, orientation="h",
            marker_color=colors_t, text=[f"{p:+.2f}%" for p in pcts_t],
            textposition="outside", textfont=dict(color="#d1d4dc", size=11),
        ))
        fig_sec_d.update_layout(
            **{**TV, "margin": dict(l=0,r=60,t=8,b=0)},
            height=320, title=dict(text="Today", font=dict(color="#787b86",size=12)),
            xaxis=dict(**TV["xaxis"], ticksuffix="%"),
            yaxis=dict(**TV["yaxis"], side="left"),
        )
        sc1.plotly_chart(fig_sec_d, use_container_width=True)

        # This week
        week_data = [(n, d.get("week_pct") or 0) for n, d in sectors.items()]
        week_data.sort(key=lambda x: x[1], reverse=True)
        names_w  = [x[0] for x in week_data]
        pcts_w   = [x[1] for x in week_data]
        colors_w = ["#26a69a" if p >= 0 else "#ef5350" for p in pcts_w]

        fig_sec_w = go.Figure(go.Bar(
            x=pcts_w, y=names_w, orientation="h",
            marker_color=colors_w, text=[f"{p:+.2f}%" for p in pcts_w],
            textposition="outside", textfont=dict(color="#d1d4dc", size=11),
        ))
        fig_sec_w.update_layout(
            **{**TV, "margin": dict(l=0,r=60,t=8,b=0)},
            height=320, title=dict(text="This Week", font=dict(color="#787b86",size=12)),
            xaxis=dict(**TV["xaxis"], ticksuffix="%"),
            yaxis=dict(**TV["yaxis"], side="left"),
        )
        sc2.plotly_chart(fig_sec_w, use_container_width=True)

        # Hot / Cold sectors
        today_sorted = sorted(sectors.items(), key=lambda x: x[1].get("day_pct") or 0, reverse=True)
        hot3  = today_sorted[:3]
        cold3 = today_sorted[-3:]

        st.markdown("#### 🔥 Hot Sectors Today")
        hc = st.columns(3)
        for i, (sname, sd) in enumerate(hot3):
            dp = sd.get("day_pct") or 0
            wp = sd.get("week_pct") or 0
            hc[i].markdown(
                f'<div style="background:rgba(38,166,154,0.1);border:1px solid #26a69a;border-radius:6px;padding:12px 14px;">'
                f'<div style="color:#26a69a;font-size:14px;font-weight:700;">{sname}</div>'
                f'<div style="color:#d1d4dc;font-size:18px;font-weight:700;">+{dp:.2f}%</div>'
                f'<div style="color:#555;font-size:11px;">Week: {("+" if wp>=0 else "")}{wp:.1f}%</div>'
                f'</div>', unsafe_allow_html=True,
            )

        st.markdown("#### 🥶 Weak Sectors Today")
        cc = st.columns(3)
        for i, (sname, sd) in enumerate(cold3):
            dp = sd.get("day_pct") or 0
            wp = sd.get("week_pct") or 0
            cc[i].markdown(
                f'<div style="background:rgba(239,83,80,0.1);border:1px solid #ef5350;border-radius:6px;padding:12px 14px;">'
                f'<div style="color:#ef5350;font-size:14px;font-weight:700;">{sname}</div>'
                f'<div style="color:#d1d4dc;font-size:18px;font-weight:700;">{dp:.2f}%</div>'
                f'<div style="color:#555;font-size:11px;">Week: {("+" if wp>=0 else "")}{wp:.1f}%</div>'
                f'</div>', unsafe_allow_html=True,
            )

# ══════════════════════════════════════════════════════════════════════
# TAB 5 — TECHNICALS
# ══════════════════════════════════════════════════════════════════════
with tabs[4]:
    fig_bb = go.Figure()
    fig_bb.add_trace(go.Scatter(x=hist.index, y=bb_up, name="Upper",
        line=dict(color="rgba(41,98,255,0.4)", width=1, dash="dot")))
    fig_bb.add_trace(go.Scatter(x=hist.index, y=bb_dn, name="Lower",
        line=dict(color="rgba(41,98,255,0.4)", width=1, dash="dot"),
        fill="tonexty", fillcolor="rgba(41,98,255,0.05)"))
    fig_bb.add_trace(go.Scatter(x=hist.index, y=bb_mid, name="Mid",
        line=dict(color="rgba(41,98,255,0.6)", width=1)))
    fig_bb.add_trace(go.Scatter(x=hist.index, y=close, name="Price",
        line=dict(color="#26a69a", width=1.5)))
    fig_bb.update_layout(**TV, height=260, title=dict(text="Bollinger Bands (20, 2σ)",
        font=dict(color="#787b86", size=12)), xaxis_rangeslider_visible=False)
    fig_bb.update_yaxes(tickprefix="$")
    st.plotly_chart(fig_bb, use_container_width=True)

    fig_rsi = go.Figure()
    fig_rsi.add_hrect(y0=70, y1=100, fillcolor="rgba(239,83,80,0.06)", line_width=0)
    fig_rsi.add_hrect(y0=0,  y1=30,  fillcolor="rgba(38,166,154,0.06)", line_width=0)
    fig_rsi.add_hline(y=70, line_color="#ef5350", line_dash="dash", line_width=0.8, opacity=0.5,
                      annotation_text="Overbought 70", annotation_font_color="#ef5350",
                      annotation_position="right")
    fig_rsi.add_hline(y=30, line_color="#26a69a", line_dash="dash", line_width=0.8, opacity=0.5,
                      annotation_text="Oversold 30", annotation_font_color="#26a69a",
                      annotation_position="right")
    fig_rsi.add_trace(go.Scatter(x=hist.index, y=rsi_s, name="RSI (14)",
        line=dict(color="#f0b429", width=1.5)))
    fig_rsi.update_layout(**TV, height=220, title=dict(text="RSI (14)",
        font=dict(color="#787b86", size=12)), yaxis=dict(**TV["yaxis"], range=[0,100]))
    st.plotly_chart(fig_rsi, use_container_width=True)

    hc = ["rgba(38,166,154,0.7)" if v >= 0 else "rgba(239,83,80,0.7)" for v in macd_h.fillna(0)]
    fig_macd = go.Figure()
    fig_macd.add_trace(go.Bar(x=hist.index, y=macd_h, marker_color=hc, name="Histogram", opacity=0.7))
    fig_macd.add_trace(go.Scatter(x=hist.index, y=macd_l, name="MACD",
        line=dict(color="#2962ff", width=1.5)))
    fig_macd.add_trace(go.Scatter(x=hist.index, y=sig_l, name="Signal",
        line=dict(color="#ff6d00", width=1.5)))
    fig_macd.update_layout(**TV, height=220, title=dict(text="MACD (12, 26, 9)",
        font=dict(color="#787b86", size=12)))
    st.plotly_chart(fig_macd, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════
# TAB 6 — FUNDAMENTALS
# ══════════════════════════════════════════════════════════════════════
with tabs[5]:
    st.markdown("#### Valuation")
    f1,f2,f3,f4 = st.columns(4)
    f1.metric("P/E (TTM)",       _v(info.get("trailingPE")))
    f2.metric("Forward P/E",     _v(info.get("forwardPE")))
    f3.metric("Price / Sales",   _v(info.get("priceToSalesTrailing12Months")))
    f4.metric("Price / Book",    _v(info.get("priceToBook")))

    st.markdown("#### Earnings & Revenue")
    f1,f2,f3,f4 = st.columns(4)
    f1.metric("EPS (TTM)",       _v(info.get("trailingEps"),".2f"," $"))
    f2.metric("Revenue (TTM)",   _B(info.get("totalRevenue")))
    f3.metric("Revenue Growth",  _P(info.get("revenueGrowth")))
    f4.metric("Earnings Growth", _P(info.get("earningsGrowth")))

    st.markdown("#### Margins")
    f1,f2,f3,f4 = st.columns(4)
    f1.metric("Gross Margin",    _P(info.get("grossMargins")))
    f2.metric("Op. Margin",      _P(info.get("operatingMargins")))
    f3.metric("Net Margin",      _P(info.get("profitMargins")))
    f4.metric("EBITDA",          _B(info.get("ebitda")))

    st.markdown("#### Balance Sheet & Risk")
    f1,f2,f3,f4 = st.columns(4)
    f1.metric("Debt / Equity",   _v(info.get("debtToEquity")))
    f2.metric("Current Ratio",   _v(info.get("currentRatio")))
    f3.metric("ROE",             _P(info.get("returnOnEquity")))
    f4.metric("Beta",            _v(info.get("beta")))

    st.markdown("#### Share Info")
    f1,f2,f3,f4 = st.columns(4)
    f1.metric("Shares Out.",     _B(info.get("sharesOutstanding")))
    f2.metric("Float",           _B(info.get("floatShares")))
    f3.metric("Short % Float",   _P(info.get("shortPercentOfFloat")))
    f4.metric("Dividend Yield",  _P(info.get("dividendYield")))

# ══════════════════════════════════════════════════════════════════════
# TAB 7 — NEWS & ANALYSTS
# ══════════════════════════════════════════════════════════════════════
with tabs[6]:
    rec_raw = (info.get("recommendationKey","") or "").replace("_"," ").upper()
    t_lo, t_mn, t_hi = info.get("targetLowPrice"), info.get("targetMeanPrice"), info.get("targetHighPrice")

    st.markdown("#### Analyst Ratings")
    a1, a2 = st.columns([1,2])
    with a1:
        if rec_raw:
            rc = {"STRONG BUY":"#26a69a","BUY":"#4caf50","HOLD":"#ffd700",
                  "SELL":"#f44336","STRONG SELL":"#ef5350"}.get(rec_raw,"#787b86")
            st.markdown(
                f'<div style="background:rgba(0,0,0,0.3);border:1px solid {rc};border-radius:6px;'
                f'padding:12px 16px;display:inline-block;min-width:140px;">'
                f'<div style="color:#787b86;font-size:10px;text-transform:uppercase;">Consensus</div>'
                f'<div style="color:{rc};font-size:20px;font-weight:700;margin-top:4px;">{rec_raw}</div>'
                f'</div>', unsafe_allow_html=True,
            )
        n = info.get("numberOfAnalystOpinions")
        if n: st.markdown(f'<p style="color:#787b86;font-size:12px;margin-top:8px;">{n} analysts</p>', unsafe_allow_html=True)

    with a2:
        if t_mn and t_lo and t_hi:
            upside = (t_mn - price) / price * 100
            st.metric("Mean Price Target", f"${t_mn:.2f}", f"{upside:+.1f}% upside")
            st.markdown(f'<span style="color:#787b86;font-size:12px;">Low <strong style="color:#ef5350;">${t_lo:.2f}</strong>'
                        f' &nbsp;·&nbsp; Mean <strong style="color:#d1d4dc;">${t_mn:.2f}</strong>'
                        f' &nbsp;·&nbsp; High <strong style="color:#26a69a;">${t_hi:.2f}</strong></span>',
                        unsafe_allow_html=True)
            rng = t_hi - t_lo
            if rng > 0:
                st.progress(max(0.0, min((price - t_lo) / rng, 1.0)))

    st.markdown("<hr style='border-color:#2a2e39;margin:16px 0;'>", unsafe_allow_html=True)
    st.markdown("#### Recent News")
    if not news:
        st.info("No recent news.")
    else:
        for item in news[:12]:
            title  = item.get("title","")
            pub    = item.get("publisher","")
            ts_raw = item.get("providerPublishTime",0)
            link   = item.get("link","#")
            try:    dt = datetime.datetime.fromtimestamp(ts_raw).strftime("%b %d · %I:%M %p")
            except: dt = ""
            st.markdown(
                f'<div style="padding:10px 0;border-bottom:1px solid #1e222d;">'
                f'<a href="{link}" target="_blank" style="color:#d1d4dc;font-size:14px;font-weight:500;'
                f'text-decoration:none;">{title}</a><br>'
                f'<span style="color:#555;font-size:11px;">{pub} · {dt}</span></div>',
                unsafe_allow_html=True,
            )