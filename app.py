import streamlit as st
from data_fetcher import fetch_yahoo_data, fetch_usd_eur_rate, fetch_technical_data
from report import render_report, TOOLTIPS, fetch_peer_full_data
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
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Inter:wght@300;400;600&family=Sora:wght@600;700&display=swap');
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
  .stTabs [data-baseweb="tab-list"] { background:#f8fafc; border-bottom:1px solid #e2e8f0; gap:0; }
  .stTabs [data-baseweb="tab"] { font-family:'IBM Plex Mono',monospace; font-size:0.8rem; color:#64748b; padding:0.6rem 1.4rem; border-bottom:2px solid transparent; }
  .stTabs [aria-selected="true"] { color:#0284c7 !important; border-bottom:2px solid #0284c7 !important; background:transparent !important; }
  /* Comparación lado a lado */
  .compare-divider { border:none; border-left:1px solid #e2e8f0; margin:0 0.5rem; }

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

  /* Estrella dorada en la pestaña FAVORITOS (5º tab, la estrella es
     el primer carácter de la etiqueta) */
  .stTabs [data-baseweb="tab-list"] button:nth-child(5) p::first-letter {
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
  <p>Yahoo Finance · Análisis técnico · Portfolio Tracker · Comparador</p>
</div>
""", unsafe_allow_html=True)

tab_analisis, tab_compare, tab_scanner, tab_portfolio, tab_favorites = st.tabs([
    "📊  ANÁLISIS",
    "⚖️  COMPARADOR",
    "🔍  RASTREADOR",
    "💼  PORTFOLIO",
    "★  FAVORITOS",
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
# PESTAÑA 2 — MODO COMPARACIÓN DIRECTA
# ══════════════════════════════════════════════════════════════════════════════
with tab_compare:
    st.markdown("""
    <div style="font-size:0.82rem;color:#64748b;margin-bottom:1rem;">
    Compara varias empresas en paralelo, lado a lado.
    </div>
    """, unsafe_allow_html=True)

    MAX_COMPARE = 6
    if "compare_tickers" not in st.session_state:
        st.session_state.compare_tickers = ["", ""]

    # ── Gestión de empresas a comparar (mínimo 2, máximo MAX_COMPARE) ────
    slot_cols = st.columns(len(st.session_state.compare_tickers))
    for i, col in enumerate(slot_cols):
        with col:
            st.session_state.compare_tickers[i] = st.text_input(
                f"Ticker {i+1}",
                value=st.session_state.compare_tickers[i],
                placeholder=["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA"][i % 6],
                label_visibility="collapsed",
                key=f"cmp_ticker_{i}",
            ).strip().upper()
            if len(st.session_state.compare_tickers) > 2:
                if st.button("✕ Quitar", key=f"cmp_remove_{i}", use_container_width=True):
                    st.session_state.compare_tickers.pop(i)
                    # Limpia las claves de los text_input: al desplazarse los
                    # índices, Streamlit reutilizaría el valor cacheado de
                    # cada key en vez del nuevo `value` pasado explícitamente.
                    for j in range(len(st.session_state.compare_tickers) + 1):
                        st.session_state.pop(f"cmp_ticker_{j}", None)
                    st.rerun()

    col_add, col_go, col_adv = st.columns([1, 1, 2])
    with col_add:
        if len(st.session_state.compare_tickers) < MAX_COMPARE:
            if st.button("➕ Añadir empresa", key="cmp_add_ticker", use_container_width=True):
                st.session_state.compare_tickers.append("")
                st.rerun()
    with col_go:
        btn_cmp = st.button("COMPARAR →", key="btn_compare", use_container_width=True)
    with col_adv:
        peers_full = st.toggle(
            "Incluir métricas avanzadas (Calidad del beneficio, PER actual/sector/histórico, "
            "Salud Fundamental, Piotroski F-Score, Valor Objetivo, Diagnóstico General, Señal de "
            "Entrada y Veredicto Final) — más lento, analiza cada empresa a fondo",
            value=st.session_state.get("cmp_peers_full", True),
            key="cmp_peers_full",
        )

    tickers_clean = [t for t in st.session_state.compare_tickers if t]
    tickers_clean = list(dict.fromkeys(tickers_clean))  # sin duplicados, conserva orden

    # ── Caché por ticker ───────────────────────────────────────────────
    # Los datos de cada empresa se guardan en session_state por separado.
    # Así, al añadir o quitar una empresa NO se rehace toda la tabla: solo
    # se pide a Yahoo Finance lo que todavía no esté en caché (la empresa
    # nueva), y al quitar una simplemente deja de mostrarse su columna sin
    # tocar las demás ni volver a consultar nada.
    if "compare_data" not in st.session_state:
        st.session_state.compare_data = {}       # ticker -> dict de datos
    if "compare_data_mode" not in st.session_state:
        st.session_state.compare_data_mode = {}  # ticker -> "basic" | "full"

    desired_mode = "full" if peers_full else "basic"

    if btn_cmp and len(tickers_clean) < 2:
        st.warning("Introduce al menos dos tickers distintos para comparar.")
    elif btn_cmp:
        to_fetch = [
            tk for tk in tickers_clean
            if st.session_state.compare_data_mode.get(tk) != desired_mode
        ]
        if to_fetch:
            spinner_msg = (f"Analizando a fondo {', '.join(to_fetch)} (puede tardar varios segundos)…"
                            if peers_full else f"Cargando {', '.join(to_fetch)}…")
            with st.spinner(spinner_msg):
                if peers_full:
                    for d in fetch_peer_full_data(to_fetch):
                        st.session_state.compare_data[d["ticker"]] = d
                        st.session_state.compare_data_mode[d["ticker"]] = "full"
                else:
                    for tk in to_fetch:
                        d = fetch_yahoo_data(tk)
                        if d:
                            d["ticker"] = tk
                            st.session_state.compare_data[tk] = d
                            st.session_state.compare_data_mode[tk] = "basic"

            missing = [tk for tk in to_fetch
                       if st.session_state.compare_data_mode.get(tk) != desired_mode]
            if missing:
                st.error(f"No se encontraron datos para: {', '.join(missing)}")

    # ── Renderizado — siempre a partir de lo que haya en caché, no solo
    # tras pulsar COMPARAR, para que quitar una empresa actualice la tabla
    # al instante sin perder el resto de datos ya cargados.
    found = [tk for tk in tickers_clean
             if tk in st.session_state.compare_data
             and st.session_state.compare_data_mode.get(tk) == desired_mode]
    show_advanced = peers_full and all(
        st.session_state.compare_data_mode.get(tk) == "full" for tk in found
    ) if found else False

    if len(found) >= 2:
        basic_data = st.session_state.compare_data

        def _big(v):
            if not v: return None
            v = float(v)
            if abs(v) >= 1e12: return f"${v/1e12:.2f}T"
            if abs(v) >= 1e9:  return f"${v/1e9:.2f}B"
            if abs(v) >= 1e6:  return f"${v/1e6:.1f}M"
            return f"${v:,.0f}"

        def _num(v, dec=2, prefix="", suffix=""):
            if v is None: return "N/A"
            try: return f"{prefix}{v:,.{dec}f}{suffix}"
            except Exception: return "N/A"

        hs = ("padding:0.35rem 0.6rem;font-size:0.75rem;color:#0284c7;"
              "text-align:right;border-bottom:1px solid #e2e8f0;white-space:nowrap;")

        def _tooltip_html(tip):
            if not tip:
                return ""
            tip_safe = tip.replace('"', "&quot;").replace("'", "&#39;")
            return (
                '<span class="tooltip-wrap" style="margin-left:0.25rem;position:relative;cursor:help;">'
                '<span style="font-size:0.6rem;color:#0284c7;border:1px solid #0284c7;'
                'border-radius:50%;padding:0 3px;font-family:\'IBM Plex Mono\',monospace;">?</span>'
                f'<span class="tooltip-box">{tip_safe}</span>'
                '</span>'
            )

        def cmp_row(label, tip, values, fmt=lambda v: _num(v), low_good=False):
            """Fila con una celda por empresa — verde la mejor, rojo la peor."""
            numeric = [v for v in values if isinstance(v, (int, float))]
            best = (min(numeric) if low_good else max(numeric)) if numeric else None
            worst = (max(numeric) if low_good else min(numeric)) if numeric else None
            cells = ""
            for v in values:
                col = "#0f172a"
                if isinstance(v, (int, float)) and best is not None and len(numeric) > 1:
                    if v == best: col = "#059669"
                    elif v == worst: col = "#dc2626"
                cells += (f'<td style="font-family:\'IBM Plex Mono\',monospace;text-align:right;'
                          f'padding:0.32rem 0.6rem;color:{col};font-weight:600;">{fmt(v)}</td>')
            tip_html = _tooltip_html(tip)
            return (f'<tr style="border-bottom:1px solid #eef1f5;">'
                    f'<td style="padding:0.32rem 0.6rem;font-size:0.8rem;color:#64748b;">{label}{tip_html}</td>'
                    f'{cells}</tr>')

        def cmp_row_fair_value(label, tip, d_list):
            """Fila especial del Valor Objetivo: incluye el % de upside/downside
            respecto al precio actual de cada empresa, junto al valor absoluto."""
            values = [d.get("fair_value") for d in d_list]
            numeric = [v for v in values if isinstance(v, (int, float))]
            best  = max(numeric) if numeric else None
            worst = min(numeric) if numeric else None
            cells = ""
            for d in d_list:
                fv, price = d.get("fair_value"), d.get("price")
                if fv is None:
                    cells += '<td style="color:#d1d9e0;text-align:right;padding:0.32rem 0.6rem;">N/A</td>'
                    continue
                col = "#0f172a"
                if best is not None and len(numeric) > 1:
                    if fv == best: col = "#059669"
                    elif fv == worst: col = "#dc2626"
                upside_html = ""
                if price:
                    upside = (fv - price) / price * 100
                    up_col = "#059669" if upside >= 0 else "#dc2626"
                    upside_html = f' <span style="color:{up_col};font-size:0.72rem;">({upside:+.1f}%)</span>'
                cells += (f'<td style="font-family:\'IBM Plex Mono\',monospace;text-align:right;'
                          f'padding:0.32rem 0.6rem;color:{col};font-weight:600;white-space:nowrap;">'
                          f'{_num(fv,2,"$")}{upside_html}</td>')
            tip_html = _tooltip_html(tip)
            return (f'<tr style="border-bottom:1px solid #eef1f5;">'
                    f'<td style="padding:0.32rem 0.6rem;font-size:0.8rem;color:#64748b;">{label}{tip_html}</td>'
                    f'{cells}</tr>')

        def cmp_group(title):
            colspan = len(found) + 1
            return (f"<tr><td colspan='{colspan}' style='padding:0.2rem 0.6rem;background:#f8fafc;"
                    f"font-size:0.65rem;color:#94a3b8;text-transform:uppercase;letter-spacing:0.08em;'>"
                    f"{title}</td></tr>")

        d_list = [basic_data[tk] for tk in found]

        # Precio actual: verde el MÁS BAJO (low_good=True) · Market Cap: verde el MÁS ALTO (low_good=False)
        rows  = cmp_row("Precio actual", TOOLTIPS.get("Precio Actual"),
                         [d.get("price") for d in d_list], fmt=lambda v: _num(v, 2, "$"), low_good=True)
        rows += cmp_row("Market Cap", TOOLTIPS.get("Market Cap"),
                         [d.get("market_cap") for d in d_list], fmt=lambda v: _big(v) or "N/A", low_good=False)
        rows += cmp_group("VALORACIÓN")
        rows += cmp_row("PER Forward", TOOLTIPS.get("PER Forward"),
                         [d.get("pe_forward") for d in d_list], fmt=lambda v: _num(v, 1, suffix="×"), low_good=True)
        rows += cmp_row("PEG Ratio", TOOLTIPS.get("PEG Ratio"),
                         [d.get("peg_ratio") for d in d_list], low_good=True)
        rows += cmp_row("EV/EBITDA", TOOLTIPS.get("EV/EBITDA"),
                         [d.get("ev_ebitda") for d in d_list], fmt=lambda v: _num(v, 1, suffix="×"), low_good=True)
        rows += cmp_row("Price/Sales", TOOLTIPS.get("Price/Sales"),
                         [d.get("price_sales") for d in d_list], fmt=lambda v: _num(v, 2, suffix="×"), low_good=True)
        rows += cmp_group("RENTABILIDAD")
        rows += cmp_row("Margen neto", TOOLTIPS.get("Profit Margin"),
                         [(d.get("profit_margin") or 0) * 100 for d in d_list], fmt=lambda v: _num(v, 1, suffix="%"))
        rows += cmp_row("Margen operativo", TOOLTIPS.get("Operating Margin"),
                         [(d.get("operating_margin") or 0) * 100 for d in d_list], fmt=lambda v: _num(v, 1, suffix="%"))
        rows += cmp_row("ROE", TOOLTIPS.get("ROE"),
                         [(d.get("roe") or 0) * 100 for d in d_list], fmt=lambda v: _num(v, 1, suffix="%"))
        rows += cmp_row("ROA", TOOLTIPS.get("ROA"),
                         [(d.get("roa") or 0) * 100 for d in d_list], fmt=lambda v: _num(v, 1, suffix="%"))
        rows += cmp_group("CRECIMIENTO")
        rows += cmp_row("Revenue YoY", TOOLTIPS.get("Revenue Growth"),
                         [d.get("revenue_yoy") for d in d_list], fmt=lambda v: _num(v, 1, suffix="%"))
        rows += cmp_row("Earnings YoY", TOOLTIPS.get("Earnings Growth"),
                         [d.get("earnings_yoy") for d in d_list], fmt=lambda v: _num(v, 1, suffix="%"))
        rows += cmp_row("EPS TTM", TOOLTIPS.get("EPS (TTM)"),
                         [d.get("eps_ttm") for d in d_list], fmt=lambda v: _num(v, 2, "$"))
        rows += cmp_group("BALANCE")
        rows += cmp_row("Free Cash Flow", TOOLTIPS.get("Free Cash Flow"),
                         [d.get("free_cash_flow") for d in d_list], fmt=lambda v: _big(v) or "N/A")
        rows += cmp_row("Deuda/Equity", TOOLTIPS.get("Debt/Equity"),
                         [d.get("debt_equity") for d in d_list], fmt=lambda v: _num(v, 1, suffix="%"), low_good=True)
        rows += cmp_row("Current Ratio", TOOLTIPS.get("Current Ratio"),
                         [d.get("current_ratio") for d in d_list], fmt=lambda v: _num(v, 2, suffix="×"))
        rows += cmp_group("TÉCNICO Y DIVIDENDO")
        rows += cmp_row("Beta", TOOLTIPS.get("Beta"),
                         [d.get("beta") for d in d_list], low_good=True)
        rows += cmp_row("Short Ratio", TOOLTIPS.get("Short Ratio"),
                         [d.get("short_ratio") for d in d_list], fmt=lambda v: _num(v, 1, suffix="d"), low_good=True)
        rows += cmp_row("Div. Yield", TOOLTIPS.get("Dividend Yield"),
                         [(d.get("dividend_yield") or 0) * 100 for d in d_list], fmt=lambda v: _num(v, 2, suffix="%"))
        rows += cmp_row("Div. Rate", TOOLTIPS.get("Dividend Rate"),
                         [d.get("dividend_rate") for d in d_list], fmt=lambda v: _num(v, 2, "$"))

        if show_advanced:
            rows += cmp_group("SALUD Y VALORACIÓN AVANZADA")
            rows += cmp_row("Calidad beneficio (FCF/NI)",
                "Free Cash Flow / Beneficio Neto anual. Mide si el beneficio contable se traduce en caja real. ≥0.9× = alta calidad, <0.5× = posibles ajustes contables agresivos.",
                [d.get("fcf_quality") for d in d_list], fmt=lambda v: _num(v, 2, suffix="×"))
            rows += cmp_row("PER Actual", TOOLTIPS.get("PER Trailing"),
                [d.get("pe_trailing") for d in d_list], fmt=lambda v: _num(v, 1, suffix="×"), low_good=True)
            rows += cmp_row("PER Sector",
                "PER 'justo' de referencia para el sector de esta empresa, ajustado por los tipos de interés actuales.",
                [d.get("pe_sector") for d in d_list], fmt=lambda v: _num(v, 1, suffix="×"))
            rows += cmp_row("PER Histórico",
                "Media del PER propio de la empresa en los últimos años. Sirve para ver si cotiza cara o barata respecto a su propio pasado, sin comparar con el sector.",
                [d.get("pe_historico") for d in d_list], fmt=lambda v: _num(v, 1, suffix="×"))
            rows += cmp_row("Salud Fundamental",
                "Score compuesto (0-100) de rentabilidad, crecimiento, balance y calidad del beneficio. >70 = sólida, 45-70 = normal, <45 = débil.",
                [d.get("health_score") for d in d_list], fmt=lambda v: _num(v, 0))
            rows += cmp_row("Piotroski F-Score",
                "9 criterios de fortaleza financiera (rentabilidad, apalancamiento, liquidez, eficiencia). ≥7 = fuerte, 4-6 = normal, <4 = débil.",
                [d.get("piotroski_str") for d in d_list], fmt=lambda v: v if v else "N/A")
            rows += cmp_row_fair_value("Valor Objetivo",
                "Mediana de varios métodos de valoración ajustados al sector, incluyendo el consenso de analistas si existe. El % entre paréntesis es el upside/downside respecto al precio actual.",
                d_list)
            rows += cmp_row("Diagnóstico General",
                "Comparación entre el precio actual y el Valor Objetivo calculado (infravalorada, precio justo, sobrevalorada...).",
                [d.get("diag") for d in d_list], fmt=lambda v: v if v else "N/A")
            rows += cmp_row("Señal de Entrada",
                "Nivel de oportunidad de compra según una combinación de checks técnicos y fundamentales (Entrada Ideal, Posible, Esperar...).",
                [d.get("signal_level") for d in d_list], fmt=lambda v: v if v else "N/A")
            rows += cmp_row("Veredicto Final",
                "Síntesis de Calidad (Salud Fundamental + Piotroski), Precio (Diagnóstico General) y Timing (Señal de Entrada) en una única conclusión.",
                [f'{d.get("vf_icon","")} {d.get("vf_level","")}'.strip() for d in d_list],
                fmt=lambda v: v if v and v.strip() else "N/A")

        header_cells = "".join(
            f'<th style="{hs}color:#0284c7;">{tk} — {(basic_data[tk].get("company_name") or basic_data[tk].get("name") or tk)[:20]}</th>'
            for tk in found
        )

        st.markdown(
            '<div class="metric-card" style="padding:0.5rem;">'
            '<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;">'
            '<thead><tr style="background:#f8fafc;">'
            f'<th style="{hs}text-align:left;color:#64748b;">Métrica</th>'
            f'{header_cells}'
            f'</tr></thead><tbody>{rows}</tbody></table></div>'
            '<div style="font-size:0.7rem;color:#64748b;margin-top:0.5rem;">'
            'Verde = mejor valor entre las empresas comparadas · Rojo = peor</div>'
            '</div>',
            unsafe_allow_html=True
        )

        # Análisis técnico rápido de cada empresa (RSI/MM50/MM200) — se
        # cachea igual que el resto, por ticker, para no perderlo al
        # añadir/quitar otras empresas del comparador.
        if "compare_tech" not in st.session_state:
            st.session_state.compare_tech = {}
        st.markdown('<div style="margin-top:1rem;"></div>', unsafe_allow_html=True)
        tech_cols = st.columns(len(found))
        for tk, col in zip(found, tech_cols):
            with col:
                if tk not in st.session_state.compare_tech:
                    with st.spinner(f"Técnico {tk}…"):
                        st.session_state.compare_tech[tk] = fetch_technical_data(tk)
                tech_d = st.session_state.compare_tech[tk]
                if tech_d and not tech_d.get("error"):
                    rsi_d = tech_d.get("rsi", "N/A")
                    mm50_d, mm200_d = tech_d.get("mm50"), tech_d.get("mm200")
                    price_d = basic_data[tk].get("price", 0)
                    st.markdown(
                        f'<div class="metric-card"><div class="metric-label">{tk} — Técnico</div>'
                        f'RSI: <b style="color:#0f172a;">{rsi_d}</b><br>'
                        f'MM50: <b style="color:{"#059669" if mm50_d and price_d > mm50_d else "#dc2626"};">'
                        f'{"▲" if mm50_d and price_d > mm50_d else "▼"}</b> &nbsp;·&nbsp; '
                        f'MM200: <b style="color:{"#059669" if mm200_d and price_d > mm200_d else "#dc2626"};">'
                        f'{"▲" if mm200_d and price_d > mm200_d else "▼"}</b></div>',
                        unsafe_allow_html=True)
    elif tickers_clean and len(tickers_clean) >= 2:
        st.markdown(
            '<div class="metric-card">'
            '<span style="color:#64748b;">Pulsa COMPARAR → para cargar los datos de estas empresas.</span>'
            '</div>',
            unsafe_allow_html=True
        )


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
# PESTAÑA 5 — FAVORITOS
# ══════════════════════════════════════════════════════════════════════════════
with tab_favorites:
    render_favorites_tab()
