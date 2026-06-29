import streamlit as st
from data_fetcher import fetch_yahoo_data, fetch_usd_eur_rate, fetch_technical_data
from report import render_report
from stock_scanner import render_scanner

st.set_page_config(
    page_title="Análisis Fundamental",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Inter:wght@300;400;600&display=swap');

  html, body, [class*="css"] { font-family:'Inter',sans-serif; background-color:#0a0e1a; color:#e2e8f0; }
  .stApp { background-color:#0a0e1a; }
  .hero { padding:2rem 0 1rem 0; border-bottom:1px solid #1e2d45; margin-bottom:1.5rem; }
  .hero h1 { font-family:'IBM Plex Mono',monospace; font-size:1.5rem; font-weight:600; color:#38bdf8; letter-spacing:-0.02em; margin:0; }
  .hero p  { font-size:0.83rem; color:#64748b; margin:0.25rem 0 0 0; }
  .metric-card { background:#111827; border:1px solid #1e2d45; border-radius:8px; padding:1rem 1.2rem; margin-bottom:0.8rem; }
  .metric-label { font-size:0.72rem; color:#64748b; text-transform:uppercase; letter-spacing:0.08em; margin-bottom:0.2rem; }
  .metric-value { font-family:'IBM Plex Mono',monospace; font-size:1.3rem; font-weight:600; color:#f1f5f9; }
  .section-header { font-family:'IBM Plex Mono',monospace; font-size:0.75rem; color:#38bdf8; text-transform:uppercase; letter-spacing:0.12em; padding:0.4rem 0; border-bottom:1px solid #1e2d45; margin:1.5rem 0 1rem 0; }
  .badge-buy  { background:#064e3b; color:#6ee7b7; padding:2px 10px; border-radius:4px; font-size:0.78rem; font-family:'IBM Plex Mono',monospace; }
  .badge-sell { background:#4c0519; color:#fca5a5; padding:2px 10px; border-radius:4px; font-size:0.78rem; font-family:'IBM Plex Mono',monospace; }
  .badge-hold { background:#1c1917; color:#fbbf24; padding:2px 10px; border-radius:4px; font-size:0.78rem; font-family:'IBM Plex Mono',monospace; }
  .verdict-box { background:#0f172a; border:1px solid #1e40af; border-left:4px solid #38bdf8; border-radius:8px; padding:1.4rem 1.6rem; margin:1.5rem 0; }
  .verdict-title { font-family:'IBM Plex Mono',monospace; font-size:0.7rem; color:#38bdf8; text-transform:uppercase; letter-spacing:0.1em; margin-bottom:0.6rem; }
  .verdict-main { font-size:1.1rem; font-weight:600; color:#f1f5f9; }
  .verdict-sub  { font-size:0.82rem; color:#94a3b8; margin-top:0.3rem; }
  .audit-ok  { color:#6ee7b7; }
  .audit-warn{ color:#fbbf24; }
  .audit-err { color:#fca5a5; }
  .stButton > button { background:#1d4ed8; color:#fff; border:none; border-radius:6px; padding:0.55rem 1.6rem; font-family:'IBM Plex Mono',monospace; font-size:0.85rem; font-weight:600; letter-spacing:0.04em; cursor:pointer; width:100%; }
  .stButton > button:hover { background:#2563eb; }
  .stTextInput > div > div > input { background:#111827; border:1px solid #1e2d45; border-radius:6px; color:#f1f5f9; font-family:'IBM Plex Mono',monospace; font-size:1rem; padding:0.5rem 0.8rem; }
  .row-kv { display:flex; justify-content:space-between; align-items:center; padding:0.45rem 0; border-bottom:1px solid #1a2540; font-size:0.88rem; }
  .row-kv:last-child { border-bottom:none; }
  .row-key { color:#94a3b8; }
  .row-val { font-family:'IBM Plex Mono',monospace; color:#f1f5f9; font-weight:600; }
  .row-val.green  { color:#6ee7b7; }
  .row-val.red    { color:#fca5a5; }
  .row-val.yellow { color:#fbbf24; }
  .progress-bar-bg   { background:#1e2d45; border-radius:4px; height:8px; margin-top:0.5rem; }
  .progress-bar-fill { height:8px; border-radius:4px; background:linear-gradient(90deg,#1d4ed8,#38bdf8); }
  .ttm-row { display:flex; justify-content:space-between; padding:0.35rem 0; font-family:'IBM Plex Mono',monospace; font-size:0.82rem; border-bottom:1px solid #1a2540; color:#94a3b8; }
  .ttm-row:last-child { border-bottom:none; color:#f1f5f9; font-weight:600; }
  .ttm-val { color:#e2e8f0; }

  /* Tooltips */
  .tooltip-wrap { display:inline-block; vertical-align:middle; }
  .tooltip-box {
    visibility:hidden; opacity:0; background:#1e293b; color:#e2e8f0;
    font-size:0.75rem; line-height:1.5; border:1px solid #334155; border-radius:6px;
    padding:0.5rem 0.75rem; position:absolute; z-index:9999; bottom:125%; left:50%;
    transform:translateX(-50%); width:260px; pointer-events:none; transition:opacity 0.15s;
    font-family:'Inter',sans-serif; font-weight:400; text-transform:none; letter-spacing:0;
    box-shadow:0 4px 12px rgba(0,0,0,0.4);
  }
  .tooltip-wrap:hover .tooltip-box { visibility:visible; opacity:1; }

  /* Tabs */
  .stTabs [data-baseweb="tab-list"] { background:#0a0e1a; border-bottom:1px solid #1e2d45; gap:0; }
  .stTabs [data-baseweb="tab"] { font-family:'IBM Plex Mono',monospace; font-size:0.8rem; color:#64748b; padding:0.6rem 1.4rem; border-bottom:2px solid transparent; }
  .stTabs [aria-selected="true"] { color:#38bdf8 !important; border-bottom:2px solid #38bdf8 !important; background:transparent !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
  <h1>▸ ANÁLISIS FUNDAMENTAL</h1>
  <p>Yahoo Finance · Análisis técnico · Rastreador de oportunidades</p>
</div>
""", unsafe_allow_html=True)

tab_analisis, tab_scanner = st.tabs(["📊  ANÁLISIS INDIVIDUAL", "🔍  RASTREADOR DE GANGAS"])

# ══════════════════════════════════════════════════════════════════════════════
# PESTAÑA 1 — ANÁLISIS INDIVIDUAL
# ══════════════════════════════════════════════════════════════════════════════
with tab_analisis:
    col1, col2 = st.columns([3, 1])
    with col1:
        ticker_input = st.text_input(
            "Ticker", placeholder="ej. AAPL, MU, MSFT, ASML...",
            label_visibility="collapsed", key="ticker_input",
        )
    with col2:
        buscar = st.button("ANALIZAR →", key="btn_analizar")

    if buscar and ticker_input:
        ticker = ticker_input.strip().upper()

        with st.spinner(f"Cargando datos para {ticker}…"):
            yahoo_data = fetch_yahoo_data(ticker)

        if yahoo_data is None:
            st.error(f"No se encontró el ticker **{ticker}** en Yahoo Finance.")
            st.stop()

        company_name = yahoo_data.get("company_name", ticker)
        st.markdown(f"""
        <div style="margin:1rem 0 0.5rem 0;">
          <span style="font-family:'IBM Plex Mono',monospace;font-size:0.8rem;color:#38bdf8;">TICKER ENCONTRADO</span><br>
          <span style="font-size:1.15rem;font-weight:600;color:#f1f5f9;">{ticker} → {company_name}</span>
          <span style="font-size:0.8rem;color:#64748b;margin-left:0.6rem;">{yahoo_data.get('sector','')}</span>
        </div>
        """, unsafe_allow_html=True)

        with st.spinner("Calculando análisis técnico y tipo de cambio…"):
            fx_rate, fx_meta = fetch_usd_eur_rate()
            tech_data        = fetch_technical_data(ticker)

        render_report(ticker, company_name, yahoo_data, fx_rate, tech_data, fx_meta)

    elif buscar and not ticker_input:
        st.warning("Introduce un ticker para continuar.")

# ══════════════════════════════════════════════════════════════════════════════
# PESTAÑA 2 — RASTREADOR DE GANGAS
# ══════════════════════════════════════════════════════════════════════════════
with tab_scanner:
    if "fx_rate" not in st.session_state:
        fx_rate, _ = fetch_usd_eur_rate()
        st.session_state.fx_rate = fx_rate
    render_scanner(fx_rate=st.session_state.fx_rate)
