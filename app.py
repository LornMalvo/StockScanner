import streamlit as st
from data_fetcher import fetch_yahoo_data, fetch_usd_eur_rate, fetch_technical_data
from report import render_report
from stock_scanner import render_scanner
from portfolio import render_portfolio

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
  .tooltip-wrap { display:inline-block; vertical-align:middle; }
  .tooltip-box { visibility:hidden; opacity:0; background:#1e293b; color:#e2e8f0; font-size:0.75rem; line-height:1.5; border:1px solid #334155; border-radius:6px; padding:0.5rem 0.75rem; position:absolute; z-index:9999; bottom:125%; left:50%; transform:translateX(-50%); width:260px; pointer-events:none; transition:opacity 0.15s; font-family:'Inter',sans-serif; font-weight:400; text-transform:none; letter-spacing:0; box-shadow:0 4px 12px rgba(0,0,0,0.4); }
  .tooltip-wrap:hover .tooltip-box { visibility:visible; opacity:1; }
  .stTabs [data-baseweb="tab-list"] { background:#0a0e1a; border-bottom:1px solid #1e2d45; gap:0; }
  .stTabs [data-baseweb="tab"] { font-family:'IBM Plex Mono',monospace; font-size:0.8rem; color:#64748b; padding:0.6rem 1.4rem; border-bottom:2px solid transparent; }
  .stTabs [aria-selected="true"] { color:#38bdf8 !important; border-bottom:2px solid #38bdf8 !important; background:transparent !important; }
  /* Comparación lado a lado */
  .compare-divider { border:none; border-left:1px solid #1e2d45; margin:0 0.5rem; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
  <h1>▸ ANÁLISIS FUNDAMENTAL</h1>
  <p>Yahoo Finance · Análisis técnico · DCF · Portfolio Tracker · Comparador</p>
</div>
""", unsafe_allow_html=True)

tab_analisis, tab_compare, tab_scanner, tab_portfolio, tab_diag = st.tabs([
    "📊  ANÁLISIS",
    "⚖️  COMPARADOR",
    "🔍  RASTREADOR",
    "💼  PORTFOLIO",
    "🔧  DIAGNÓSTICO",
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

        st.markdown(f"""
        <div style="margin:1rem 0 0.5rem 0;">
          <span style="font-family:'IBM Plex Mono',monospace;font-size:0.8rem;color:#38bdf8;">TICKER ANALIZADO</span><br>
          <span style="font-size:1.15rem;font-weight:600;color:#f1f5f9;">{ticker} → {company_name}</span>
          <span style="font-size:0.8rem;color:#64748b;margin-left:0.6rem;">{yahoo_data.get('sector','')}</span>
        </div>
        """, unsafe_allow_html=True)

        render_report(ticker, company_name, yahoo_data, fx_rate, tech_data, fx_meta)

    elif buscar and not ticker_input:
        st.warning("Introduce un ticker para continuar.")


# ══════════════════════════════════════════════════════════════════════════════
# PESTAÑA 2 — MODO COMPARACIÓN DIRECTA
# ══════════════════════════════════════════════════════════════════════════════
with tab_compare:
    st.markdown("""
    <div style="font-size:0.82rem;color:#64748b;margin-bottom:1rem;">
    Analiza dos empresas en paralelo para comparar sus métricas clave directamente.
    </div>
    """, unsafe_allow_html=True)

    cc1, cc2, cc3, cc4 = st.columns([3, 1, 3, 1])
    with cc1:
        ticker_a = st.text_input("Ticker A", placeholder="AAPL",
                                  label_visibility="collapsed", key="cmp_a").strip().upper()
    with cc2:
        btn_cmp  = st.button("COMPARAR →", key="btn_compare")
    with cc3:
        ticker_b = st.text_input("Ticker B", placeholder="MSFT",
                                  label_visibility="collapsed", key="cmp_b").strip().upper()
    with cc4:
        st.write("")  # spacer

    if btn_cmp and ticker_a and ticker_b:
        if ticker_a == ticker_b:
            st.warning("Introduce dos tickers distintos.")
        else:
            with st.spinner(f"Cargando {ticker_a} y {ticker_b}…"):
                data_a = fetch_yahoo_data(ticker_a)
                data_b = fetch_yahoo_data(ticker_b)

            if not data_a:
                st.error(f"No se encontró {ticker_a}")
            elif not data_b:
                st.error(f"No se encontró {ticker_b}")
            else:
                # Tabla comparativa de métricas clave
                def _cmp_row(label, val_a, val_b, fmt="{:.2f}", low_good=False, suffix=""):
                    """Fila de comparación — verde la mejor."""
                    def fv(v):
                        if v is None: return "N/A"
                        try:    return fmt.format(v) + suffix
                        except: return str(v)
                    col_a = col_b = "#f1f5f9"
                    if val_a is not None and val_b is not None:
                        try:
                            if low_good:
                                col_a = "#6ee7b7" if val_a < val_b else "#fca5a5"
                                col_b = "#6ee7b7" if val_b < val_a else "#fca5a5"
                            else:
                                col_a = "#6ee7b7" if val_a > val_b else "#fca5a5"
                                col_b = "#6ee7b7" if val_b > val_a else "#fca5a5"
                        except Exception:
                            pass
                    return (
                        f'<tr style="border-bottom:1px solid #1a2540;">'
                        f'<td style="padding:0.32rem 0.6rem;font-size:0.8rem;color:#64748b;">{label}</td>'
                        f'<td style="font-family:\'IBM Plex Mono\',monospace;text-align:right;'
                        f'padding:0.32rem 0.6rem;color:{col_a};font-weight:600;">{fv(val_a)}</td>'
                        f'<td style="font-family:\'IBM Plex Mono\',monospace;text-align:right;'
                        f'padding:0.32rem 0.6rem;color:{col_b};font-weight:600;">{fv(val_b)}</td>'
                        f'</tr>'
                    )

                def _big(v):
                    if not v: return None
                    v = float(v)
                    if abs(v) >= 1e12: return f"${v/1e12:.2f}T"
                    if abs(v) >= 1e9:  return f"${v/1e9:.2f}B"
                    if abs(v) >= 1e6:  return f"${v/1e6:.1f}M"
                    return f"${v:,.0f}"

                na, nb = data_a.get("company_name",ticker_a)[:22], data_b.get("company_name",ticker_b)[:22]
                hs = "padding:0.35rem 0.6rem;font-size:0.75rem;color:#38bdf8;text-align:right;border-bottom:1px solid #1e2d45;"

                rows = (
                    _cmp_row("Precio actual",   data_a.get("price"),         data_b.get("price"),        fmt="${:,.2f}", low_good=False)
                  + _cmp_row("Market Cap",      _big(data_a.get("market_cap")), _big(data_b.get("market_cap")), fmt="{}", low_good=False)
                  + "<tr><td colspan='3' style='padding:0.2rem;background:#0a0e1a;font-size:0.65rem;color:#334155;text-transform:uppercase;letter-spacing:0.08em;'>VALORACIÓN</td></tr>"
                  + _cmp_row("PER Forward",     data_a.get("pe_forward"),    data_b.get("pe_forward"),   fmt="{:.1f}×", low_good=True)
                  + _cmp_row("PEG Ratio",       data_a.get("peg_ratio"),     data_b.get("peg_ratio"),    fmt="{:.2f}",  low_good=True)
                  + _cmp_row("EV/EBITDA",       data_a.get("ev_ebitda"),     data_b.get("ev_ebitda"),    fmt="{:.1f}×", low_good=True)
                  + _cmp_row("Price/Sales",     data_a.get("price_sales"),   data_b.get("price_sales"),  fmt="{:.2f}×", low_good=True)
                  + "<tr><td colspan='3' style='padding:0.2rem;background:#0a0e1a;font-size:0.65rem;color:#334155;text-transform:uppercase;letter-spacing:0.08em;'>RENTABILIDAD</td></tr>"
                  + _cmp_row("Margen neto",     (data_a.get("profit_margin") or 0)*100,  (data_b.get("profit_margin") or 0)*100,  fmt="{:.1f}%", low_good=False)
                  + _cmp_row("Margen operativo",(data_a.get("operating_margin") or 0)*100,(data_b.get("operating_margin") or 0)*100,fmt="{:.1f}%",low_good=False)
                  + _cmp_row("ROE",             (data_a.get("roe") or 0)*100,            (data_b.get("roe") or 0)*100,            fmt="{:.1f}%", low_good=False)
                  + _cmp_row("ROA",             (data_a.get("roa") or 0)*100,            (data_b.get("roa") or 0)*100,            fmt="{:.1f}%", low_good=False)
                  + "<tr><td colspan='3' style='padding:0.2rem;background:#0a0e1a;font-size:0.65rem;color:#334155;text-transform:uppercase;letter-spacing:0.08em;'>CRECIMIENTO</td></tr>"
                  + _cmp_row("Revenue YoY",     data_a.get("revenue_yoy"),   data_b.get("revenue_yoy"),  fmt="{:+.1f}%",low_good=False)
                  + _cmp_row("Earnings YoY",    data_a.get("earnings_yoy"),  data_b.get("earnings_yoy"), fmt="{:+.1f}%",low_good=False)
                  + _cmp_row("EPS TTM",         data_a.get("eps_ttm"),       data_b.get("eps_ttm"),      fmt="${:.2f}", low_good=False)
                  + "<tr><td colspan='3' style='padding:0.2rem;background:#0a0e1a;font-size:0.65rem;color:#334155;text-transform:uppercase;letter-spacing:0.08em;'>BALANCE</td></tr>"
                  + _cmp_row("Free Cash Flow",  _big(data_a.get("free_cash_flow")), _big(data_b.get("free_cash_flow")), fmt="{}", low_good=False)
                  + _cmp_row("Deuda/Equity",    data_a.get("debt_equity"),   data_b.get("debt_equity"),  fmt="{:.1f}%", low_good=True)
                  + _cmp_row("Current Ratio",   data_a.get("current_ratio"), data_b.get("current_ratio"),fmt="{:.2f}×", low_good=False)
                  + "<tr><td colspan='3' style='padding:0.2rem;background:#0a0e1a;font-size:0.65rem;color:#334155;text-transform:uppercase;letter-spacing:0.08em;'>TÉCNICO</td></tr>"
                  + _cmp_row("Beta",            data_a.get("beta"),          data_b.get("beta"),         fmt="{:.2f}",  low_good=True)
                  + _cmp_row("Short Ratio",     data_a.get("short_ratio"),   data_b.get("short_ratio"),  fmt="{:.1f}d", low_good=True)
                  + _cmp_row("Div. Yield",      (data_a.get("dividend_yield") or 0)*100,(data_b.get("dividend_yield") or 0)*100, fmt="{:.2f}%", low_good=False)
                )

                st.markdown(
                    '<div class="metric-card" style="padding:0.5rem;">'
                    '<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;">'
                    '<thead><tr style="background:#0a0e1a;">'
                    f'<th style="{hs}text-align:left;color:#64748b;">Métrica</th>'
                    f'<th style="{hs}color:#38bdf8;">{ticker_a} — {na}</th>'
                    f'<th style="{hs}color:#fbbf24;">{ticker_b} — {nb}</th>'
                    f'</tr></thead><tbody>{rows}</tbody></table></div>'
                    '<div style="font-size:0.7rem;color:#64748b;margin-top:0.5rem;">'
                    'Verde = mejor valor entre los dos · Rojo = peor</div>'
                    '</div>',
                    unsafe_allow_html=True
                )

                # Análisis técnico de ambos
                st.markdown('<div style="margin-top:1rem;"></div>', unsafe_allow_html=True)
                col_ta, col_tb = st.columns(2)
                with col_ta:
                    with st.spinner(f"Técnico {ticker_a}…"):
                        tech_a = fetch_technical_data(ticker_a)
                    if tech_a and not tech_a.get("error"):
                        rsi_a = tech_a.get("rsi","N/A")
                        mm50_a, mm200_a = tech_a.get("mm50"), tech_a.get("mm200")
                        price_a = data_a.get("price", 0)
                        st.markdown(
                            f'<div class="metric-card"><div class="metric-label">{ticker_a} — Técnico</div>'
                            f'RSI: <b style="color:#f1f5f9;">{rsi_a}</b> &nbsp;·&nbsp; '
                            f'MM50: <b style="color:{"#6ee7b7" if mm50_a and price_a > mm50_a else "#fca5a5"};">'
                            f'{"▲" if mm50_a and price_a > mm50_a else "▼"}</b> &nbsp;·&nbsp; '
                            f'MM200: <b style="color:{"#6ee7b7" if mm200_a and price_a > mm200_a else "#fca5a5"};">'
                            f'{"▲" if mm200_a and price_a > mm200_a else "▼"}</b></div>',
                            unsafe_allow_html=True)
                with col_tb:
                    with st.spinner(f"Técnico {ticker_b}…"):
                        tech_b = fetch_technical_data(ticker_b)
                    if tech_b and not tech_b.get("error"):
                        rsi_b = tech_b.get("rsi","N/A")
                        mm50_b, mm200_b = tech_b.get("mm50"), tech_b.get("mm200")
                        price_b = data_b.get("price", 0)
                        st.markdown(
                            f'<div class="metric-card"><div class="metric-label">{ticker_b} — Técnico</div>'
                            f'RSI: <b style="color:#f1f5f9;">{rsi_b}</b> &nbsp;·&nbsp; '
                            f'MM50: <b style="color:{"#6ee7b7" if mm50_b and price_b > mm50_b else "#fca5a5"};">'
                            f'{"▲" if mm50_b and price_b > mm50_b else "▼"}</b> &nbsp;·&nbsp; '
                            f'MM200: <b style="color:{"#6ee7b7" if mm200_b and price_b > mm200_b else "#fca5a5"};">'
                            f'{"▲" if mm200_b and price_b > mm200_b else "▼"}</b></div>',
                            unsafe_allow_html=True)

    elif btn_cmp:
        st.warning("Introduce los dos tickers para comparar.")


# ══════════════════════════════════════════════════════════════════════════════
# PESTAÑA 3 — RASTREADOR DE GANGAS
# ══════════════════════════════════════════════════════════════════════════════
with tab_scanner:
    render_scanner(fx_rate=fx_rate)


# ══════════════════════════════════════════════════════════════════════════════
# PESTAÑA 4 — PORTFOLIO TRACKER
# ══════════════════════════════════════════════════════════════════════════════
with tab_portfolio:
    render_portfolio(fx_rate=fx_rate)


# ══════════════════════════════════════════════════════════════════════════════
# PESTAÑA 5 — DIAGNÓSTICO DE FUENTES DE DATOS
# ══════════════════════════════════════════════════════════════════════════════
with tab_diag:
    st.markdown("""
    <div style="font-size:0.82rem;color:#64748b;margin-bottom:1rem;">
    Herramienta de diagnóstico para verificar exactamente qué datos devuelve
    cada fuente de earnings (API directa de Yahoo vs yfinance) para un ticker.
    Útil para detectar errores de datos sin acceso a los logs del servidor.
    </div>
    """, unsafe_allow_html=True)

    diag_ticker = st.text_input("Ticker a diagnosticar", value="MU", key="diag_ticker").strip().upper()

    if st.button("🔍 Ejecutar diagnóstico de earnings", key="btn_diag"):
        from analysis import (
            _fetch_earnings_history_raw_api,
            _fetch_earnings_history_yf_fallback,
            fetch_earnings_analysis,
        )
        from data_fetcher import fetch_yahoo_data

        st.markdown("### 1. API directa de Yahoo (quoteSummary/earningsHistory)")
        with st.spinner("Consultando API directa..."):
            raw_result = _fetch_earnings_history_raw_api(diag_ticker)
        if raw_result:
            st.success(f"✅ {len(raw_result)} trimestres obtenidos")
            st.json(raw_result)
        else:
            st.error("❌ La API directa no devolvió datos (vacío o error de red)")

        st.markdown("### 2. Fallback yfinance (Ticker.earnings_dates)")
        with st.spinner("Consultando yfinance..."):
            yf_result = _fetch_earnings_history_yf_fallback(diag_ticker)
        if yf_result:
            st.success(f"✅ {len(yf_result)} trimestres obtenidos")
            st.json(yf_result)
        else:
            st.error("❌ yfinance tampoco devolvió datos")

        st.markdown("### 3. Resultado final de fetch_earnings_analysis()")
        with st.spinner("Cargando datos base..."):
            yahoo_data = fetch_yahoo_data(diag_ticker)
        if yahoo_data:
            ea = fetch_earnings_analysis(diag_ticker, yahoo_data)
            st.json(ea)
        else:
            st.error(f"❌ No se pudo cargar yahoo_data para {diag_ticker}")

        st.caption(
            "Si la sección 1 (API directa) devuelve datos correctos pero las fechas/EPS "
            "siguen mal en el análisis principal, el problema está en cómo se procesan "
            "esos datos en fetch_earnings_analysis. Si AMBAS fuentes (1 y 2) fallan, "
            "es un problema de red/disponibilidad del lado de Yahoo, no del código."
        )
