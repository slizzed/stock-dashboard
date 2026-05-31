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
    page_title="Stock Analysis Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Auto-refresh every 60 seconds ─────────────────────────────────────────────
st_autorefresh(interval=60_000, limit=None, key="live_refresh")

# ── Helpers ────────────────────────────────────────────────────────────────────

def _safe(val, fmt=".2f", suffix=""):
    if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
        return "—"
    return f"{val:{fmt}}{suffix}"

def _large(val):
    if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
        return "—"
    if val >= 1e12: return f"${val/1e12:.2f}T"
    if val >= 1e9:  return f"${val/1e9:.2f}B"
    if val >= 1e6:  return f"${val/1e6:.2f}M"
    return f"${val:,.0f}"

def _pct(val):
    if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
        return "—"
    return f"{val * 100:.1f}%"

def _market_status():
    et  = ZoneInfo("America/New_York")
    now = datetime.datetime.now(et)
    t   = now.time()
    wd  = now.weekday()  # 0=Mon … 6=Sun
    if wd >= 5:
        return "🔴 Closed (Weekend)", "#ef5350"
    open_t   = datetime.time(9, 30)
    close_t  = datetime.time(16, 0)
    pre_t    = datetime.time(4, 0)
    after_t  = datetime.time(20, 0)
    if open_t <= t < close_t:
        return "🟢 Market Open", "#26a69a"
    elif pre_t <= t < open_t:
        return "🟡 Pre-Market", "#ffd700"
    elif close_t <= t < after_t:
        return "🟡 After-Hours", "#ffd700"
    else:
        return "🔴 Market Closed", "#ef5350"

@st.cache_data(ttl=55)
def _load(ticker: str, period: str):
    t    = yf.Ticker(ticker)
    hist = t.history(period=period, auto_adjust=True)
    info = t.info
    news = t.news or []
    return hist, info, news

def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    return 100 - (100 / (1 + gain / loss.replace(0, 1e-10)))

def _macd(close: pd.Series):
    ema12  = close.ewm(span=12, adjust=False).mean()
    ema26  = close.ewm(span=26, adjust=False).mean()
    macd   = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal, macd - signal

def _bollinger(close: pd.Series, period: int = 20, width: float = 2.0):
    mid = close.rolling(period).mean()
    sd  = close.rolling(period).std()
    return mid, mid + width * sd, mid - width * sd

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("# 📈 Stock Analyzer")

    status_label, status_color = _market_status()
    st.markdown(
        f'<span style="color:{status_color};font-weight:bold;font-size:14px;">{status_label}</span>',
        unsafe_allow_html=True,
    )

    now_et = datetime.datetime.now(ZoneInfo("America/New_York"))
    st.caption(f"ET: {now_et.strftime('%b %d, %Y  %I:%M:%S %p')}")

    # Live countdown to next refresh
    components.html("""
    <script>
      var secs = 60;
      function tick() {
        secs--;
        if (secs < 0) secs = 60;
        var el = document.getElementById("cd");
        if (el) el.innerText = "Auto-refresh in " + secs + "s";
      }
      setInterval(tick, 1000);
    </script>
    <p id="cd" style="color:#888;font-size:11px;margin:4px 0 0 0;">Auto-refresh in 60s</p>
    """, height=22)

    st.markdown("---")

    raw = st.text_input("Ticker Symbol", value="NVDA", placeholder="Any US or global ticker")
    ticker = raw.upper().strip()

    period_label = st.selectbox(
        "Time Period",
        ["1 Month", "3 Months", "6 Months", "1 Year", "2 Years", "5 Years"],
        index=3,
    )
    period = {
        "1 Month": "1mo", "3 Months": "3mo", "6 Months": "6mo",
        "1 Year": "1y",   "2 Years": "2y",   "5 Years": "5y",
    }[period_label]

    st.markdown("---")
    st.markdown("**Quick picks**")
    qcols = st.columns(3)
    quick = ["NVDA","AAPL","TSLA","SOUN","IONQ","PLTR","AMD","MSFT","AAPL"]
    quick_tickers = ["NVDA","AAPL","TSLA","SOUN","IONQ","PLTR","AMD","MSFT","RIVN"]
    for i, sym in enumerate(quick_tickers):
        if qcols[i % 3].button(sym, key=f"q_{sym}", use_container_width=True):
            ticker = sym

    st.markdown("---")
    st.caption("Covers 10,000+ US & global stocks")
    st.caption("Data: Yahoo Finance · Free · No API key")

# ── Load data ──────────────────────────────────────────────────────────────────
if not ticker:
    st.info("Enter a ticker symbol in the sidebar.")
    st.stop()

with st.spinner(f"Loading {ticker}..."):
    try:
        hist, info, news = _load(ticker, period)
    except Exception as e:
        st.error(f"Error: {e}")
        st.stop()

if hist is None or hist.empty:
    st.error(f"**{ticker}** not found. Check the symbol and try again.")
    st.stop()

# ── Core values ────────────────────────────────────────────────────────────────
close   = hist["Close"]
current = float(close.iloc[-1])
prev    = float(close.iloc[-2]) if len(close) >= 2 else current
day_pct = (current - prev) / prev * 100 if prev else 0

name     = info.get("shortName") or info.get("longName") or ticker
sector   = info.get("sector", "")
industry = info.get("industry", "")
exchange = info.get("exchange", "")

ma20  = close.rolling(20).mean()
ma50  = close.rolling(50).mean()
ma200 = close.rolling(200).mean()
rsi_s                        = _rsi(close)
macd_line, sig_line, macd_hs = _macd(close)
bb_mid, bb_up, bb_dn         = _bollinger(close)

last_rsi  = float(rsi_s.dropna().iloc[-1])  if not rsi_s.dropna().empty  else None
last_ma20 = float(ma20.dropna().iloc[-1])   if not ma20.dropna().empty   else None
last_ma50 = float(ma50.dropna().iloc[-1])   if not ma50.dropna().empty   else None
last_ma200 = float(ma200.dropna().iloc[-1]) if not ma200.dropna().empty  else None

# ── Header ─────────────────────────────────────────────────────────────────────
h1, h2 = st.columns([3, 1])
with h1:
    st.markdown(f"## {name} &nbsp;&nbsp; `{ticker}`")
    st.caption("  ·  ".join(x for x in [sector, industry, exchange] if x))
with h2:
    updated = datetime.datetime.now().strftime("%I:%M:%S %p")
    st.markdown(
        f'<div style="text-align:right;padding-top:12px;">'
        f'<span style="color:#888;font-size:12px;">Updated {updated}</span></div>',
        unsafe_allow_html=True,
    )

arrow = "▲" if day_pct >= 0 else "▼"
sign  = "+" if day_pct >= 0 else ""
c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Price",       f"${current:.2f}", f"{arrow} {sign}{day_pct:.2f}%")
c2.metric("Market Cap",  _large(info.get("marketCap")))
c3.metric("Volume",      _safe(float(hist["Volume"].iloc[-1]), ",.0f") if "Volume" in hist else "—")
c4.metric("Avg Volume",  _safe(info.get("averageVolume"), ",.0f") if info.get("averageVolume") else "—")
c5.metric("52W High",    f"${info.get('fiftyTwoWeekHigh', 0):.2f}")
c6.metric("52W Low",     f"${info.get('fiftyTwoWeekLow', 0):.2f}")
st.markdown("---")

# ── Tabs ───────────────────────────────────────────────────────────────────────
t1, t2, t3, t4 = st.tabs(["📊 Overview", "📉 Technicals", "📋 Fundamentals", "📰 News & Analysts"])

# ══════════════════════════════════════════════════════════════════════
# TAB 1 — OVERVIEW
# ══════════════════════════════════════════════════════════════════════
with t1:
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        vertical_spacing=0.04, row_heights=[0.75, 0.25],
    )
    fig.add_trace(go.Candlestick(
        x=hist.index, open=hist["Open"], high=hist["High"],
        low=hist["Low"], close=hist["Close"], name=ticker,
        increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
        showlegend=False,
    ), row=1, col=1)

    for ma_s, label, color in [
        (ma20,  "MA20",  "#ffd700"),
        (ma50,  "MA50",  "#42a5f5"),
        (ma200, "MA200", "#ef9a9a"),
    ]:
        fig.add_trace(go.Scatter(
            x=hist.index, y=ma_s, name=label,
            line=dict(color=color, width=1.3), opacity=0.85,
        ), row=1, col=1)

    vol_colors = [
        "#26a69a" if float(c) >= float(o) else "#ef5350"
        for c, o in zip(hist["Close"], hist["Open"])
    ]
    fig.add_trace(go.Bar(
        x=hist.index, y=hist["Volume"],
        marker_color=vol_colors, showlegend=False,
    ), row=2, col=1)

    fig.update_layout(
        template="plotly_dark", height=540,
        xaxis_rangeslider_visible=False,
        margin=dict(l=0, r=0, t=8, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0),
    )
    fig.update_yaxes(title_text="Price ($)", row=1, col=1)
    fig.update_yaxes(title_text="Volume",    row=2, col=1)
    st.plotly_chart(fig, use_container_width=True)

    low52  = info.get("fiftyTwoWeekLow")
    high52 = info.get("fiftyTwoWeekHigh")
    if low52 and high52 and high52 > low52:
        pos = (current - low52) / (high52 - low52)
        st.markdown(f"**52-Week Range** &nbsp; `${low52:.2f}` ──── `${current:.2f}` ──── `${high52:.2f}`")
        st.progress(min(max(pos, 0.0), 1.0))

# ══════════════════════════════════════════════════════════════════════
# TAB 2 — TECHNICALS
# ══════════════════════════════════════════════════════════════════════
with t2:
    signals = []
    if last_rsi is not None:
        if last_rsi < 30:
            signals.append(("🟢", f"RSI {last_rsi:.0f} — Oversold, potential bounce"))
        elif last_rsi > 70:
            signals.append(("🔴", f"RSI {last_rsi:.0f} — Overbought, caution"))
        else:
            signals.append(("🟡", f"RSI {last_rsi:.0f} — Neutral zone"))

    if last_ma20 and last_ma50:
        if current > last_ma20 and current > last_ma50:
            signals.append(("🟢", f"Above MA20 (${last_ma20:.2f}) and MA50 (${last_ma50:.2f}) — Uptrend"))
        elif current < last_ma20 and current < last_ma50:
            signals.append(("🔴", f"Below MA20 and MA50 — Downtrend"))
        else:
            signals.append(("🟡", "Between MA20 and MA50 — Mixed"))

    if last_ma200:
        if current > last_ma200:
            signals.append(("🟢", f"Above MA200 (${last_ma200:.2f}) — Long-term uptrend"))
        else:
            signals.append(("🔴", f"Below MA200 (${last_ma200:.2f}) — Long-term downtrend"))

    bullish = sum(1 for icon, _ in signals if icon == "🟢")
    bearish = sum(1 for icon, _ in signals if icon == "🔴")
    verdict = (
        "🟢 Overall Bullish" if bullish > bearish else
        "🔴 Overall Bearish" if bearish > bullish else
        "🟡 Mixed / Neutral"
    )

    st.markdown(f"### Signal Summary — {verdict}")
    for icon, msg in signals:
        st.markdown(f"{icon} &nbsp; {msg}")
    st.markdown("---")

    fig_bb = go.Figure()
    fig_bb.add_trace(go.Scatter(x=hist.index, y=bb_up, name="Upper Band",
        line=dict(color="rgba(150,150,200,0.5)", width=1, dash="dot")))
    fig_bb.add_trace(go.Scatter(x=hist.index, y=bb_dn, name="Lower Band",
        line=dict(color="rgba(150,150,200,0.5)", width=1, dash="dot"),
        fill="tonexty", fillcolor="rgba(100,100,180,0.07)"))
    fig_bb.add_trace(go.Scatter(x=hist.index, y=bb_mid, name="Mid (MA20)",
        line=dict(color="#888", width=1)))
    fig_bb.add_trace(go.Scatter(x=hist.index, y=close, name="Price",
        line=dict(color="#26a69a", width=1.5)))
    fig_bb.update_layout(template="plotly_dark", height=280,
        title="Price + Bollinger Bands (20, 2σ)",
        margin=dict(l=0, r=0, t=36, b=0), xaxis_rangeslider_visible=False)
    st.plotly_chart(fig_bb, use_container_width=True)

    fig_rsi = go.Figure()
    fig_rsi.add_hrect(y0=70, y1=100, fillcolor="rgba(239,83,80,0.07)", line_width=0)
    fig_rsi.add_hrect(y0=0,  y1=30,  fillcolor="rgba(38,166,154,0.07)", line_width=0)
    fig_rsi.add_hline(y=70, line_color="#ef5350", line_dash="dash", line_width=1, opacity=0.6)
    fig_rsi.add_hline(y=30, line_color="#26a69a", line_dash="dash", line_width=1, opacity=0.6)
    fig_rsi.add_hline(y=50, line_color="#555",    line_dash="dot",  line_width=1, opacity=0.4)
    fig_rsi.add_trace(go.Scatter(x=hist.index, y=rsi_s, name="RSI (14)",
        line=dict(color="#ffd700", width=1.5)))
    fig_rsi.update_layout(template="plotly_dark", height=240, title="RSI (14)",
        yaxis=dict(range=[0, 100]), margin=dict(l=0, r=0, t=36, b=0))
    st.plotly_chart(fig_rsi, use_container_width=True)

    hist_colors = ["#26a69a" if v >= 0 else "#ef5350" for v in macd_hs.fillna(0)]
    fig_macd = go.Figure()
    fig_macd.add_trace(go.Bar(x=hist.index, y=macd_hs, name="Histogram",
        marker_color=hist_colors, opacity=0.65))
    fig_macd.add_trace(go.Scatter(x=hist.index, y=macd_line, name="MACD",
        line=dict(color="#42a5f5", width=1.5)))
    fig_macd.add_trace(go.Scatter(x=hist.index, y=sig_line, name="Signal",
        line=dict(color="#ef9a9a", width=1.5)))
    fig_macd.update_layout(template="plotly_dark", height=240, title="MACD (12, 26, 9)",
        margin=dict(l=0, r=0, t=36, b=0))
    st.plotly_chart(fig_macd, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════
# TAB 3 — FUNDAMENTALS
# ══════════════════════════════════════════════════════════════════════
with t3:
    st.markdown("### Valuation")
    f1, f2, f3, f4 = st.columns(4)
    f1.metric("P/E Ratio (TTM)",   _safe(info.get("trailingPE")))
    f2.metric("Forward P/E",       _safe(info.get("forwardPE")))
    f3.metric("Price / Sales",     _safe(info.get("priceToSalesTrailing12Months")))
    f4.metric("Price / Book",      _safe(info.get("priceToBook")))

    st.markdown("### Earnings & Revenue")
    f1, f2, f3, f4 = st.columns(4)
    f1.metric("EPS (TTM)",         _safe(info.get("trailingEps"), ".2f", " $"))
    f2.metric("Revenue (TTM)",     _large(info.get("totalRevenue")))
    f3.metric("Revenue Growth",    _pct(info.get("revenueGrowth")))
    f4.metric("Earnings Growth",   _pct(info.get("earningsGrowth")))

    st.markdown("### Margins")
    f1, f2, f3, f4 = st.columns(4)
    f1.metric("Gross Margin",      _pct(info.get("grossMargins")))
    f2.metric("Operating Margin",  _pct(info.get("operatingMargins")))
    f3.metric("Net Margin",        _pct(info.get("profitMargins")))
    f4.metric("EBITDA",            _large(info.get("ebitda")))

    st.markdown("### Balance Sheet & Risk")
    f1, f2, f3, f4 = st.columns(4)
    f1.metric("Debt / Equity",     _safe(info.get("debtToEquity")))
    f2.metric("Current Ratio",     _safe(info.get("currentRatio")))
    f3.metric("Return on Equity",  _pct(info.get("returnOnEquity")))
    f4.metric("Beta",              _safe(info.get("beta")))

    st.markdown("### Share Info")
    f1, f2, f3, f4 = st.columns(4)
    f1.metric("Shares Outstanding", _large(info.get("sharesOutstanding")))
    f2.metric("Float",              _large(info.get("floatShares")))
    f3.metric("Short % of Float",   _pct(info.get("shortPercentOfFloat")))
    f4.metric("Dividend Yield",     _pct(info.get("dividendYield")))

# ══════════════════════════════════════════════════════════════════════
# TAB 4 — NEWS & ANALYSTS
# ══════════════════════════════════════════════════════════════════════
with t4:
    rec_raw    = info.get("recommendationKey", "") or ""
    rec_label  = rec_raw.replace("_", " ").upper()
    n_analysts = info.get("numberOfAnalystOpinions")
    t_low  = info.get("targetLowPrice")
    t_mean = info.get("targetMeanPrice")
    t_high = info.get("targetHighPrice")

    st.markdown("### Analyst Ratings")
    a1, a2 = st.columns([1, 2])
    with a1:
        if rec_label:
            c = {"STRONG BUY": "green", "BUY": "green",
                 "HOLD": "orange", "SELL": "red", "STRONG SELL": "red"}.get(rec_label, "gray")
            st.markdown(f"**Consensus:** :{c}[**{rec_label}**]")
        if n_analysts:
            st.metric("Number of Analysts", n_analysts)
    with a2:
        if t_mean and t_low and t_high:
            upside = (t_mean - current) / current * 100 if current else 0
            st.metric("Mean Price Target", f"${t_mean:.2f}", f"{upside:+.1f}% from current")
            st.markdown(f"`${t_low:.2f}` low &nbsp;·&nbsp; `${t_mean:.2f}` mean &nbsp;·&nbsp; `${t_high:.2f}` high")
            rng = t_high - t_low
            if rng > 0:
                pos = max(0.0, min((current - t_low) / rng, 1.0))
                st.progress(pos, text=f"Current ${current:.2f} within analyst target range")

    st.markdown("---")
    st.markdown("### Recent News")
    if not news:
        st.info("No recent news available.")
    else:
        for item in news[:12]:
            title     = item.get("title", "No title")
            publisher = item.get("publisher", "")
            pub_ts    = item.get("providerPublishTime", 0)
            link      = item.get("link", "#")
            try:
                pub_str = datetime.datetime.fromtimestamp(pub_ts).strftime("%b %d, %Y · %I:%M %p")
            except Exception:
                pub_str = ""
            st.markdown(
                f"**[{title}]({link})**  \n"
                f"<span style='color:#888;font-size:12px;'>{publisher} &nbsp;·&nbsp; {pub_str}</span>",
                unsafe_allow_html=True,
            )
            st.markdown("---")