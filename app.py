import streamlit as st
from data_fetcher import fetch_yahoo_data, fetch_usd_eur_rate, fetch_technical_data
from report import render_report
from stock_scanner import render_scanner
from portfolio import render_portfolio
from favorites import render_favorite_star, render_favorites_tab

st.set_page_config(
    page_title="Stock Scanner",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Inter:wght@300;400;600&family=Sora:wght@600;700&family=Quicksand:wght@600;700&display=swap');
  html, body, [class*="css"] { font-family:'Inter',sans-serif; background-color:#f8fafc; color:#1e293b; }
  .stApp { background-color:#f8fafc; }
  .hero { padding:2rem 0 1rem 0; border-bottom:1px solid #e2e8f0; margin-bottom:1.5rem; }
  .hero h1 { font-family:'Sora',sans-serif; font-size:2.6rem; font-weight:700; color:#0284c7; letter-spacing:-0.02em; margin:0; }
  .hero p  { font-size:0.83rem; color:#64748b; margin:0.25rem 0 0 0; }
  .metric-card { background:#ffffff; border:1px solid #e2e8f0; border-radius:8px; padding:1rem 1.2rem; margin-bottom:0.8rem; }
  .metric-label { font-size:0.72rem; color:#64748b; text-transform:uppercase; letter-spacing:0.08em; margin-bottom:0.2rem; }
  .metric-value { font-family:'IBM Plex Mono',monospace; font-size:1.3rem; font-weight:600; color:#0f172a; }
  .section-header { font-family:'IBM Plex Mono',monospace; font-size:0.75rem; color:#0284c7; text-transform:uppercase; letter-spacing:0.12em; padding:0.4rem 0; border-bottom:1px solid #e2e8f0; margin:1.5rem 0 1rem 0; }
  .badge-buy  { background:#d1fae5; color:#059669; padding:2px 10px; border-radius:4px; font-size:0.78rem; font-family:'IBM Plex Mono',monospace; }
  .badge-sell { background:#fee2e2; color:#dc2626; padding:2px 10px; border-radius:4px; font-size:0.78rem; font-family:'IBM Plex Mono',monospace; }
  .badge-hold { background:#fef3c7; color:#d97706; padding:2px 10px; border-radius:4px; font-size:0.78rem; font-family:'IBM Plex Mono',monospace; }
  .verdict-box { background:#f4f6f9; border:1px solid #1d4ed8; border-left:4px solid #0284c7; border-radius:8px; padding:1.4rem 1.6rem; margin:1.5rem 0; }
  .verdict-title { font-family:'IBM Plex Mono',monospace; font-size:0.7rem; color:#0284c7; text-transform:uppercase; letter-spacing:0.1em; margin-bottom:0.6rem; }
  .verdict-main { font-size:1.1rem; font-weight:600; color:#0f172a; }
  .verdict-sub  { font-size:0.82rem; color:#64748b; margin-top:0.3rem; }
  .audit-ok  { color:#059669; }
  .audit-warn{ color:#d97706; }
  .audit-err { color:#dc2626; }
  .stButton > button { background:#1d4ed8; color:#fff; border:none; border-radius:6px; padding:0.55rem 1.6rem; font-family:'IBM Plex Mono',monospace; font-size:0.85rem; font-weight:600; letter-spacing:0.04em; cursor:pointer; width:100%; }
  .stButton > button:hover { background:#2563eb; }
  .stTextInput > div > div > input { background:#ffffff; border:1px solid #e2e8f0; border-radius:6px; color:#0f172a; font-family:'IBM Plex Mono',monospace; font-size:1rem; padding:0.5rem 0.8rem; }
  .row-kv { display:flex; justify-content:space-between; align-items:center; padding:0.45rem 0; border-bottom:1px solid #eef1f5; font-size:0.88rem; }
  .row-kv:last-child { border-bottom:none; }
  .row-key { color:#64748b; }
  .row-val { font-family:'IBM Plex Mono',monospace; color:#0f172a; font-weight:600; }
  .row-val.green  { color:#059669; }
  .row-val.red    { color:#dc2626; }
  .row-val.yellow { color:#d97706; }
  .progress-bar-bg   { background:#334155; border-radius:4px; height:8px; margin-top:0.5rem; }
  .progress-bar-fill { height:8px; border-radius:4px; background:linear-gradient(90deg,#1d4ed8,#0284c7); }
  .ttm-row { display:flex; justify-content:space-between; padding:0.35rem 0; font-family:'IBM Plex Mono',monospace; font-size:0.82rem; border-bottom:1px solid #eef1f5; color:#64748b; }
  .ttm-row:last-child { border-bottom:none; color:#0f172a; font-weight:600; }
  .ttm-val { color:#1e293b; }
  .tooltip-wrap { display:inline-block; vertical-align:middle; }
  .tooltip-box { visibility:hidden; opacity:0; background:#1e293b; color:#f8fafc; font-size:0.75rem; line-height:1.5; border:1px solid #e2e8f0; border-radius:6px; padding:0.5rem 0.75rem; position:absolute; z-index:9999; bottom:125%; left:50%; transform:translateX(-50%); width:260px; pointer-events:none; transition:opacity 0.15s; font-family:'Inter',sans-serif; font-weight:400; text-transform:none; letter-spacing:0; box-shadow:0 4px 12px rgba(0,0,0,0.15); }
  .tooltip-wrap:hover .tooltip-box { visibility:visible; opacity:1; }
  .stTabs [data-baseweb="tab-list"] { background:#f1f5f9 !important; border-bottom:none !important; gap:8px !important; padding:0.5rem !important; border-radius:14px !important; }
  .stTabs [data-baseweb="tab"] { font-family:'Quicksand',sans-serif !important; font-weight:700 !important; font-size:0.9rem !important; color:#64748b !important; padding:0.65rem 1.2rem !important; border-bottom:none !important; border-radius:20px !important; background:#ffffff !important; opacity:1 !important; box-shadow:none !important; transition:background 0.15s, color 0.15s; }
  .stTabs [data-baseweb="tab"] p { color:inherit !important; font-family:inherit !important; font-size:0.9rem !important; opacity:1 !important; }
  .stTabs [aria-selected="true"] { color:#ffffff !important; background:#0284c7 !important; border-bottom:none !important; }
  .stTabs [aria-selected="true"] p { color:#ffffff !important; }
  /* Comparación lado a lado */

  /* Icono de estrella de favoritos — junto al ticker analizado.
     Se aplica vía st.container(key=...), que Streamlit expone como
     clase real .st-key-<key> en el HTML (forma oficial y estable de
     dirigir CSS a un elemento concreto, ≥ Streamlit 1.37). */
  .st-key-fav_star_filled button, .st-key-fav_star_empty button {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    font-size: 3rem !important;
    line-height: 1 !important;
    padding: 0 0.3rem !important;
    min-height: unset !important;
    width: auto !important;
  }
  .st-key-fav_star_filled button p, .st-key-fav_star_empty button p {
    font-size: 3rem !important; line-height: 1 !important;
  }
  .st-key-fav_star_filled button { color: #eab308 !important; }
  .st-key-fav_star_empty button  { color: #cbd5e1 !important; }
  .st-key-fav_star_filled button:hover, .st-key-fav_star_empty button:hover {
    color: #eab308 !important; transform: scale(1.1);
  }

  /* Estrella dorada en la pestaña FAVORITOS (5º tab). Se inyecta vía
     ::before en vez de ::first-letter, porque ★ es un carácter de
     categoría Símbolo (no Letra) y ::first-letter no lo trata de forma
     fiable entre navegadores — por eso no se veía en amarillo. */
  .stTabs [data-baseweb="tab-list"] button:nth-of-type(5) p::before {
    content: "★  " !important;
    color: #eab308 !important;
  }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
  <div style="display:flex; align-items:center; gap:0.15rem;">
    <h1>▸ STOCK SCANNER</h1>
    <svg width="46" height="46" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M3 3V19.5C3 20.3284 3.67157 21 4.5 21H21" stroke="#0284c7" stroke-width="2" stroke-linecap="round"/>
      <path d="M4.5 18L9.5 13L13.5 16L19.5 8.5" stroke="#0284c7" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M15.5 8H19.5V12" stroke="#0284c7" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
  </div>
  <p>Yahoo Finance · Análisis técnico · Gestión de Cartera</p>
</div>
""", unsafe_allow_html=True)

tab_analisis, tab_scanner, tab_portfolio, tab_papertrading, tab_favorites = st.tabs([
    "📊  ANÁLISIS",
    "🔍  RASTREADOR",
    "💼  GESTIÓN DE CARTERA",
    "🎯  PAPER TRADING",
    "  FAVORITOS",
])

# ── Tipo de cambio compartido ──────────────────────────────────────────────
if "fx_rate" not in st.session_state or "fx_meta" not in st.session_state:
    fx_rate, fx_meta          = fetch_usd_eur_rate()
    st.session_state.fx_rate  = fx_rate
    st.session_state.fx_meta  = fx_meta
fx_rate = st.session_state.fx_rate
fx_meta = st.session_state.fx_meta


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

    st.markdown(
        '<div style="font-size:0.72rem;color:#94a3b8;margin-top:-0.6rem;margin-bottom:0.8rem;">'
        '🌍 También puedes analizar valores fuera del S&amp;P 500 con el sufijo de mercado de Yahoo Finance: '
        '<b>.MC</b> IBEX 35 (ej. SAN.MC) · <b>.PA</b> Euronext París (ej. MC.PA) · '
        '<b>.DE</b> Xetra Fráncfort (ej. SAP.DE) · <b>.L</b> Londres (ej. HSBA.L) · '
        '<b>.MI</b> Milán (ej. ENI.MI) · <b>.AS</b> Ámsterdam (ej. ASML.AS)</div>',
        unsafe_allow_html=True
    )

    # Si venimos de "Analizar" desde la pestaña Favoritos, forzar búsqueda automática
    jump_ticker = st.session_state.pop("_jump_to_analysis", None)
    if jump_ticker and not buscar:
        ticker_input = jump_ticker
        buscar = True

    if buscar and ticker_input:
        ticker = ticker_input.strip().upper()

        with st.spinner(f"Cargando datos para {ticker}…"):
            yahoo_data = fetch_yahoo_data(ticker)

        if yahoo_data is None:
            st.error(f"No se encontró **{ticker}** en Yahoo Finance.")
            st.stop()

        with st.spinner("Calculando análisis técnico…"):
            tech_data = fetch_technical_data(ticker)

        # Guardar en session_state para que persista entre re-ejecuciones
        # (necesario para que el Q&A no reinicie la app al pulsar botones)
        st.session_state["last_ticker"]      = ticker
        st.session_state["last_yahoo_data"]  = yahoo_data
        st.session_state["last_tech_data"]   = tech_data

    # Renderizar si hay datos en sesión (ya sea por búsqueda nueva o por botón Q&A)
    if "last_ticker" in st.session_state:
        ticker       = st.session_state["last_ticker"]
        yahoo_data   = st.session_state["last_yahoo_data"]
        tech_data    = st.session_state["last_tech_data"]
        company_name = yahoo_data.get("company_name", ticker)
        sector_name  = yahoo_data.get("sector", "")

        col_hdr1, col_hdr2 = st.columns([6, 0.6])
        with col_hdr1:
            st.markdown(f"""
            <div style="margin:1rem 0 0.5rem 0;">
              <span style="font-family:'IBM Plex Mono',monospace;font-size:0.85rem;color:#0284c7;">TICKER ANALIZADO</span><br>
              <span style="font-size:1.9rem;font-weight:700;color:#0f172a;">{ticker} → {company_name}</span>
              <span style="font-size:1.05rem;color:#64748b;margin-left:0.7rem;">{sector_name}</span>
            </div>
            """, unsafe_allow_html=True)
        with col_hdr2:
            st.markdown('<div style="margin-top:1.4rem;"></div>', unsafe_allow_html=True)
            render_favorite_star(ticker, company_name, sector_name)

        render_report(ticker, company_name, yahoo_data, fx_rate, tech_data, fx_meta)

    elif buscar and not ticker_input:
        st.warning("Introduce un ticker para continuar.")


# ══════════════════════════════════════════════════════════════════════════════
# PESTAÑA 2 — RASTREADOR DE GANGAS
# ══════════════════════════════════════════════════════════════════════════════
with tab_scanner:
    render_scanner(fx_rate=fx_rate)


# ══════════════════════════════════════════════════════════════════════════════
# PESTAÑA 3 — GESTIÓN DE CARTERA
# ══════════════════════════════════════════════════════════════════════════════
with tab_portfolio:
    render_portfolio(fx_rate=fx_rate)


# ══════════════════════════════════════════════════════════════════════════════
# PESTAÑA 4 — PAPER TRADING (SIMULADOR)
# ══════════════════════════════════════════════════════════════════════════════
with tab_papertrading:
    st.markdown("""
    <div style="font-family:'IBM Plex Mono',monospace;font-size:0.75rem;color:#0284c7;
                text-transform:uppercase;letter-spacing:0.1em;padding:1rem 0 0.5rem 0;">
    🎯 PAPER TRADING
    </div>
    <div style="font-size:0.82rem;color:#64748b;margin-bottom:1rem;">
    Simula operaciones a partir del plan de entrada/salida generado en Análisis Individual,
    sin arriesgar capital real.
    </div>
    """, unsafe_allow_html=True)

    st.info(
        "🚧 Sección en construcción. Próximamente podrás ejecutar el plan de entrada/salida "
        "de cualquier análisis directamente desde aquí y hacer seguimiento de su rendimiento."
    )


# ══════════════════════════════════════════════════════════════════════════════
# PESTAÑA 5 — FAVORITOS
# ══════════════════════════════════════════════════════════════════════════════
with tab_favorites:
    render_favorites_tab()
