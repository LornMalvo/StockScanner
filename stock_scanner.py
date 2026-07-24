"""
stock_scanner.py
Rastreador de mercado: escanea el S&P 500 y/o una lista personalizada
reutilizando EL MISMO motor de análisis que la pestaña de Análisis
Individual (Salud Fundamental, Piotroski, Valor Objetivo/Diagnóstico,
Señal de Entrada y Veredicto Final), en vez de un sistema de puntuación
propio y aislado ("Ganga Score").

ANTES: el rastreador calculaba su propio "Ganga Score" (0-100 pts, F1-F5
fundamentales + T1-T4 técnicos + penalizaciones) con umbrales fijos e
independientes del motor usado en Análisis Individual. Esto provocaba
resultados contradictorios entre pestañas (una empresa podía salir "GANGA
EXCEPCIONAL" aquí y "EVITAR" en el análisis individual de la misma
empresa), porque literalmente eran dos sistemas de valoración distintos.

AHORA: cada ticker se evalúa con el mismo pipeline que usa Análisis
Individual (fetch_yahoo_data + fetch_technical_data +
fetch_balance_sheet_history + fetch_historical_multiples → _evaluate →
calc_entry_signal → calc_valoracion_final), así que el resultado del
Rastreador es exactamente el mismo Veredicto que verías si analizaras esa
empresa una a una. Es más lento por ticker (más llamadas a Yahoo Finance
por acción) pero elimina la incoherencia entre pestañas.
"""

import streamlit as st
from concurrent.futures import ThreadPoolExecutor, as_completed

from data_fetcher import fetch_yahoo_data, fetch_technical_data, fetch_balance_sheet_history
from dcf import fetch_historical_multiples
from analysis import calc_entry_signal
from report import _evaluate, calc_valoracion_final, _get_sector_profile

# Nº de tickers evaluados en paralelo. Las llamadas a Yahoo Finance son de
# red (I/O), no de CPU, así que varios hilos a la vez reducen el tiempo de
# pared aunque el nº total de peticiones sea el mismo. Un valor moderado
# evita saturar/mostrar rate-limiting de Yahoo.
_MAX_WORKERS = 6

# ─────────────────────────────────────────────────────────────────────────────
# UNIVERSO S&P 500
# ─────────────────────────────────────────────────────────────────────────────

SP500_TICKERS = [
    "AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","BRK-B","JPM","AVGO",
    "LLY","V","UNH","XOM","MA","JNJ","PG","COST","HD","MRK","ABBV","CVX",
    "KO","PEP","BAC","WMT","ORCL","CRM","ACN","MCD","CSCO","ABT","GE","TMO",
    "AMD","ADBE","TXN","PM","NEE","WFC","DIS","AMGN","MS","GS","RTX","BMY",
    "LOW","ISRG","INTC","QCOM","UNP","CAT","SPGI","HON","ELV","SBUX","AXP",
    "DE","PLD","AMT","MDLZ","BKNG","GILD","ADI","REGN","PGR","TJX","SYK",
    "MMC","CVS","ZTS","MO","VRTX","CI","SO","CB","ADP","LRCX","ETN","BDX",
    "CME","ITW","EOG","NOC","APD","SLB","MCO","BSX","HUM","USB","NSC","FDX",
    "TGT","MU","KLAC","PANW","CRWD","SNPS","CDNS","FTNT","MRVL","ON","GD",
    "EMR","A","PSA","PCG","WM","DUK","AEP","EXC","SRE","ES","XEL","D",
    "ROST","IDXX","MTD","ANSS","KEYS","VRSN","EPAM","NFLX","PYPL","SQ",
    "UBER","LYFT","ABNB","DASH","SHOP","SE","GRAB","DDOG","NET","SNOW",
    "ZM","OKTA","TWLO","HubS","BILL","ZS","COUP","MDB","ESTC","GTLB",
    "TEAM","ATLASSIAN","WDAY","NOW","VEEV","HUBS","DOCS","AI","PATH",
    "IBM","HPQ","HPE","DELL","WDC","STX","NTAP","PSTG","SMCI","ANET",
    "SWKS","QRVO","MPWR","WOLF","ENPH","FSLR","SEDG","RUN","PLUG","BE",
    "F","GM","STLA","TM","HMC","RIVN","LCID","NIO","LI","XPEV","BYD",
    "BA","LMT","GD","HII","L3HARRIS","LDOS","SAIC","CACI","MANT","KTOS",
    "PFE","MRNA","BNTX","AZN","NVO","SNY","RHHBY","GSK","BMY","LLY",
    "JNJ","ABT","MDT","EW","HOLX","DXCM","PODD","INSP","NTRA","EXAS",
    "UNH","HUM","CNC","MOH","ELV","CI","HIG","ALL","PRU","MET","AFG",
    "JPM","BAC","WFC","C","GS","MS","BLK","SCHW","IBKR","HOOD","COIN",
    "V","MA","AXP","DFS","COF","SYF","ALLY","SOFI","AFRM","UPST","LC",
    "SPG","O","VICI","PLD","PSA","EQR","AVB","MAA","ESS","UDR","CPT",
    "AMT","CCI","SBAC","DLR","EQIX","CONE","QTS","REXR","FR","EGP",
    "XOM","CVX","COP","EOG","PXD","OXY","DVN","MPC","VLO","PSX","HES",
    "FCX","NEM","GOLD","AEM","WPM","FNV","RGLD","HL","PAAS","AG",
    "NUE","STLD","CLF","X","CMC","RS","WOR","CRS","ATI","HAYN",
    "WMT","TGT","COST","KR","ACI","SFM","CASY","WEIS","VLGEA","INGR",
    "MCD","YUM","QSR","DPZ","SBUX","CMG","SHAK","WING","FAT","LOCO",
]

# Eliminar duplicados manteniendo orden
seen = set()
SP500_TICKERS = [t for t in SP500_TICKERS if not (t in seen or seen.add(t))]


def build_ticker_list(use_sp500: bool, custom_raw: str) -> list[str]:
    """Combina S&P 500 y/o lista personalizada, elimina duplicados."""
    tickers = []
    if use_sp500:
        tickers += SP500_TICKERS
    if custom_raw:
        custom = [t.strip().upper() for t in custom_raw.replace(",", " ").split() if t.strip()]
        tickers += custom
    # Deduplicar preservando orden
    seen = set()
    return [t for t in tickers if not (t in seen or seen.add(t))]


# ─────────────────────────────────────────────────────────────────────────────
# EVALUACIÓN POR TICKER — mismo motor que Análisis Individual
# ─────────────────────────────────────────────────────────────────────────────

# Orden de prioridad de cada dimensión del veredicto (0 = mejor). Se usa
# solo para ORDENAR resultados dentro del rastreador — la clasificación en
# sí (icon/level/color/message) la sigue decidiendo _VALORACION_FINAL_TABLA
# en report.py, exactamente igual que en Análisis Individual.
_CALIDAD_ORDER = {"alta": 0, "media": 1, "baja": 2}
_PRECIO_ORDER  = {"barata": 0, "justa": 1, "cara": 2, "sin_datos": 3}
_TIMING_ORDER  = {"bueno": 0, "neutro": 1, "malo": 2, "sin_datos": 3}


def _rank_key(r: dict) -> tuple:
    vf = r["vf"]
    return (
        _CALIDAD_ORDER.get(vf["calidad"], 9),
        _PRECIO_ORDER.get(vf["precio"], 9),
        _TIMING_ORDER.get(vf["timing"], 9),
        -vf["calidad_score"],
    )


def _quick_fetch(ticker: str) -> dict | None:
    """
    Parte BARATA del pipeline: una sola llamada a Yahoo Finance
    (fetch_yahoo_data, ya cacheada 15 min). Con esto ya sabemos precio,
    sector y consenso de analistas — suficiente para descartar tickers por
    "Solo Strong Buy" o filtro de sector SIN pagar el coste de las otras
    3-4 llamadas (técnico, balance histórico, múltiplos).
    """
    y = fetch_yahoo_data(ticker)
    if not y or not y.get("price"):
        return None
    return y


def _full_evaluate(ticker: str, y: dict) -> dict:
    """
    Parte CARA del pipeline, solo para tickers que ya han pasado los
    filtros baratos: técnico, balance histórico y múltiplos propios →
    _evaluate() (Salud Fundamental, Piotroski, Valor Objetivo, Diagnóstico)
    → calc_entry_signal() (Señal de Entrada) → calc_valoracion_final()
    (Veredicto: Calidad × Precio × Timing). Mismo pipeline que usa
    render_report() en Análisis Individual.
    """
    tech = fetch_technical_data(ticker)
    bh   = fetch_balance_sheet_history(ticker)

    static_profile, _ = _get_sector_profile(y.get("sector", ""))
    mult_data = fetch_historical_multiples(
        ticker,
        market_cap=y.get("market_cap"),
        price=y.get("price"),
        pe_trailing=y.get("pe_trailing"),
        sector_pe_fair=static_profile["pe_fair"],
    )

    ev     = _evaluate(y, bh, mult_data)
    signal = calc_entry_signal(y, tech, ev)
    vf     = calc_valoracion_final(ev, signal)

    return {
        "ticker":         ticker,
        "name":           y.get("company_name") or ticker,
        "sector":         y.get("sector", "N/A"),
        "price":          y.get("price"),
        "peg":            y.get("peg_ratio"),
        "pe_forward":     y.get("pe_forward"),
        "recommendation": (y.get("recommendation") or "N/A").lower(),
        "analyst_count":  y.get("analyst_count") or 0,
        "y":  y,
        "ev": ev,
        "signal": signal,
        "vf": vf,
    }


def evaluate_ticker(ticker: str) -> dict | None:
    """Evalúa un ticker completo (usada fuera del escaneo masivo, ej. pruebas sueltas)."""
    y = _quick_fetch(ticker)
    if y is None:
        return None
    return _full_evaluate(ticker, y)


def _scan_one(
    ticker: str,
    only_strong_buy: bool,
    sector_filter: str,
    calidad_allowed: set,
    precio_allowed: set,
    timing_allowed: set,
    peg_max: float | None,
    pe_max: float | None,
) -> dict | None:
    """
    Evalúa un único ticker aplicando primero los filtros baratos (sobre
    los datos de fetch_yahoo_data) y solo si los pasa, ejecuta el resto
    del pipeline pesado. Pensada para lanzarse en un hilo del
    ThreadPoolExecutor — no debe llamar a ninguna función de Streamlit
    (st.*) directamente, solo a las funciones de fetch/cálculo.
    """
    try:
        y = _quick_fetch(ticker)
        if y is None:
            return None

        if only_strong_buy and (y.get("recommendation") or "").lower() != "strong_buy":
            return None
        if sector_filter and sector_filter.lower() not in (y.get("sector") or "").lower():
            return None

        r  = _full_evaluate(ticker, y)
        vf = r["vf"]
        if vf["calidad"] not in calidad_allowed:
            return None
        if vf["precio"] not in precio_allowed:
            return None
        if vf["timing"] not in timing_allowed:
            return None
        if peg_max and r["peg"] and r["peg"] > peg_max:
            return None
        if pe_max and r["pe_forward"] and r["pe_forward"] > pe_max:
            return None

        return r
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# ESCANEO DE UNIVERSO
# ─────────────────────────────────────────────────────────────────────────────

def scan_universe(
    tickers: list[str],
    top_n: int = 20,
    progress_cb=None,
    only_strong_buy: bool = False,
    sector_filter: str = "",
    calidad_allowed: set | None = None,
    precio_allowed: set | None = None,
    timing_allowed: set | None = None,
    peg_max: float | None = None,
    pe_max: float | None = None,
) -> list[dict]:
    """
    Escanea una lista de tickers reutilizando el motor de Análisis
    Individual y devuelve los mejores resultados ordenados por Veredicto
    (Calidad → Precio → Timing).

    Cada ticker se evalúa en un hilo del pool (_MAX_WORKERS a la vez): los
    filtros baratos (Strong Buy, sector) se comprueban dentro de cada tarea
    ANTES de lanzar el resto de llamadas pesadas (técnico, balance,
    múltiplos), así que un ticker descartado por esos filtros solo paga el
    coste de 1 llamada a Yahoo en vez de 4-5.

    progress_cb: función que recibe (n_completados, total, último_ticker)
    para actualizar la barra de progreso — se llama desde el hilo
    principal a medida que van terminando las tareas, nunca desde los
    hilos de trabajo.
    """
    calidad_allowed = calidad_allowed or {"alta", "media", "baja"}
    precio_allowed  = precio_allowed  or {"barata", "justa", "cara", "sin_datos"}
    timing_allowed  = timing_allowed  or {"bueno", "neutro", "malo", "sin_datos"}

    results = []
    total   = len(tickers)
    done    = 0

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futures = {
            pool.submit(
                _scan_one, ticker, only_strong_buy, sector_filter,
                calidad_allowed, precio_allowed, timing_allowed, peg_max, pe_max,
            ): ticker
            for ticker in tickers
        }
        for future in as_completed(futures):
            ticker = futures[future]
            done += 1
            if progress_cb:
                progress_cb(done, total, ticker)
            r = future.result()
            if r is not None:
                results.append(r)

    results.sort(key=_rank_key)
    return results[:top_n]


# ─────────────────────────────────────────────────────────────────────────────
# RENDER DEL RASTREADOR
# ─────────────────────────────────────────────────────────────────────────────

def render_scanner(fx_rate: float | None = None):
    """Renderiza la pestaña del rastreador, con el motor de Análisis Individual."""

    st.markdown("""
    <div style="margin-bottom:1.5rem;">
      <div style="font-family:'IBM Plex Mono',monospace;font-size:0.75rem;color:#0284c7;
                  text-transform:uppercase;letter-spacing:0.1em;margin-bottom:0.4rem;">
        MOTOR DE ANÁLISIS — IDÉNTICO AL DE ANÁLISIS INDIVIDUAL
      </div>
      <div style="background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;padding:1rem 1.2rem;
                  font-size:0.82rem;color:#64748b;line-height:1.7;">
        Cada empresa se evalúa exactamente igual que en la pestaña <b style="color:#0f172a;">Análisis
        Individual</b>: <b style="color:#0f172a;">Salud Fundamental</b> (0-100, ajustada por sector) ·
        <b style="color:#0f172a;">Piotroski F-Score</b> · <b style="color:#0f172a;">Valor Objetivo y
        Diagnóstico</b> (mediana de varios métodos de valoración, ajustado por tipos de interés) ·
        <b style="color:#0f172a;">Señal de Entrada</b> técnica · y un
        <b style="color:#0f172a;">Veredicto Final</b> que combina Calidad × Precio × Timing.
        Al usar el mismo motor, el resultado nunca contradice al de Análisis Individual para la misma
        empresa.<br><br>
        ⚡ Los tickers se evalúan en paralelo y los que no cumplen "Strong Buy" o el filtro de sector se
        descartan tras 1 sola consulta (sin pagar el resto del análisis). Los datos de mercado se
        cachean 15 min y los de balance/múltiplos 12h, así que repetir un escaneo o cruzarte con un
        ticker ya analizado en Análisis Individual es prácticamente instantáneo.
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Configuración del escaneo ─────────────────────────────────────────
    col1, col2 = st.columns([1, 1])
    with col1:
        use_sp500 = st.checkbox("Incluir S&P 500 (~200 tickers)", value=False)
        custom_raw = st.text_area(
            "Mi lista personalizada (separados por coma o espacio)",
            placeholder="ASML, SAP, LVMH, ITX, SAN...",
            height=80,
        )
        sector_filter = st.text_input(
            "Filtrar por sector (opcional)",
            placeholder="Technology, Healthcare, Energy...",
        )
        only_strong_buy = st.checkbox(
            "Solo consenso analistas = Strong Buy",
            value=False,
            help="Descarta cualquier empresa cuyo consenso de recomendación de analistas "
                 "(dato de Yahoo Finance) no sea exactamente 'Strong Buy'.",
        )
    with col2:
        calidad_choice = st.selectbox(
            "Calidad Fundamental", ["Cualquiera", "Media o superior", "Solo Alta"], index=0,
            help="Calidad = combinación de Salud Fundamental y Piotroski F-Score, igual que en "
                 "el Veredicto Final de Análisis Individual.",
        )
        precio_choice = st.selectbox(
            "Valoración de precio", ["Cualquiera", "Excluir caras", "Solo infravaloradas"], index=0,
            help="Basado en el mismo Diagnóstico (Valor Objetivo vs precio actual) de Análisis Individual.",
        )
        timing_choice = st.selectbox(
            "Señal de Entrada", ["Cualquiera", "Excluir mal timing", "Solo con señal de entrada"], index=0,
            help="Basado en la misma Señal de Entrada técnica de Análisis Individual.",
        )
        col2a, col2b = st.columns(2)
        with col2a:
            peg_max = st.number_input("PEG máximo", min_value=0.0, value=0.0, step=0.1,
                                       help="0 = sin filtro")
        with col2b:
            pe_max = st.number_input("PER Forward máximo", min_value=0, value=0, step=1,
                                      help="0 = sin filtro")
        top_n = st.slider("Máximo de resultados a mostrar", 5, 50, 20, step=5)

    iniciar = st.button("🔍  INICIAR RASTREO", use_container_width=True)

    if not iniciar:
        st.markdown("""
        <div style="text-align:center;padding:2rem;color:#64748b;font-size:0.88rem;">
          Configura los parámetros y pulsa <b style="color:#0284c7;">INICIAR RASTREO</b>.
        </div>
        """, unsafe_allow_html=True)
        return

    tickers = build_ticker_list(use_sp500, custom_raw)
    if not tickers:
        st.warning("Añade al menos un ticker o activa el S&P 500.")
        return

    calidad_map = {
        "Cualquiera":        {"alta", "media", "baja"},
        "Media o superior":  {"alta", "media"},
        "Solo Alta":         {"alta"},
    }
    precio_map = {
        "Cualquiera":           {"barata", "justa", "cara", "sin_datos"},
        "Excluir caras":        {"barata", "justa"},
        "Solo infravaloradas":  {"barata"},
    }
    timing_map = {
        "Cualquiera":                  {"bueno", "neutro", "malo", "sin_datos"},
        "Excluir mal timing":          {"bueno", "neutro"},
        "Solo con señal de entrada":   {"bueno"},
    }

    st.info(f"Escaneando **{len(tickers)} tickers** con el motor de Análisis Individual… "
            f"esto puede tardar varios minutos.", icon="⏳")

    prog_bar  = st.progress(0)
    prog_text = st.empty()

    def progress_cb(done, total, ticker):
        pct = int(done / total * 100)
        prog_bar.progress(pct)
        prog_text.markdown(
            f'<span style="font-family:\'IBM Plex Mono\',monospace;font-size:0.75rem;color:#64748b;">'
            f'{done}/{total} completados (último: {ticker})</span>',
            unsafe_allow_html=True,
        )

    results = scan_universe(
        tickers,
        top_n=top_n,
        progress_cb=progress_cb,
        only_strong_buy=only_strong_buy,
        sector_filter=sector_filter.strip(),
        calidad_allowed=calidad_map[calidad_choice],
        precio_allowed=precio_map[precio_choice],
        timing_allowed=timing_map[timing_choice],
        peg_max=peg_max or None,
        pe_max=pe_max or None,
    )
    prog_bar.empty()
    prog_text.empty()

    if not results:
        st.warning("No se encontraron acciones que cumplan esos criterios. Prueba a relajar los filtros.")
        return

    st.markdown(f"""
    <div style="font-family:'IBM Plex Mono',monospace;font-size:0.8rem;color:#0284c7;
                margin:1rem 0 0.5rem 0;">
      ✔ {len(results)} resultado{'s' if len(results)!=1 else ''} encontrado{'s' if len(results)!=1 else ''}
      &nbsp;·&nbsp; ordenados por Veredicto (Calidad → Precio → Timing)
    </div>
    """, unsafe_allow_html=True)

    rec_labels = {
        "strong_buy": ("STRONG BUY", "#059669", "#d1fae5"),
        "buy":        ("BUY",        "#16a34a", "#dcfce7"),
        "hold":       ("HOLD",       "#d97706", "#fef3c7"),
        "sell":       ("SELL",       "#dc2626", "#fee2e2"),
        "strong_sell":("STRONG SELL","#dc2626", "#fee2e2"),
    }
    labels_calidad = {"alta": "Alta", "media": "Media", "baja": "Baja"}
    labels_precio  = {"barata": "Barata", "justa": "Precio justo", "cara": "Cara", "sin_datos": "Sin datos"}
    labels_timing  = {"bueno": "Buen timing", "neutro": "Timing neutro", "malo": "Mal timing", "sin_datos": "Sin datos"}

    # ── Tarjetas de resultados ────────────────────────────────────────────
    for r in results:
        ticker  = r["ticker"]
        name    = r["name"]
        price   = r["price"]
        sector  = r["sector"]
        vf      = r["vf"]
        ev      = r["ev"]
        signal  = r["signal"]
        peg     = r["peg"]
        rec     = r.get("recommendation", "n/a")
        analyst_n = r.get("analyst_count", 0)

        rec_label, rec_color, rec_bg = rec_labels.get(rec, ("SIN CONSENSO", "#94a3b8", "#f4f6f9"))
        rec_badge_html = (
            f'<span style="background:{rec_bg};color:{rec_color};padding:2px 9px;'
            f'border-radius:4px;font-size:0.72rem;font-weight:700;margin-left:0.6rem;">'
            f'{rec_label}{f" ({analyst_n})" if analyst_n else ""}</span>'
        )

        price_eur_str = ""
        if fx_rate and price:
            price_eur_str = f' <span style="color:#64748b;font-size:0.82em;">(€{price*fx_rate:,.2f})</span>'

        health = ev.get("health_score", 0)

        with st.expander(
            f"{vf['icon']}  {ticker} — {name[:40]}  ·  {vf['level']}",
            expanded=False,
        ):
            st.markdown(f"""
            <div style="margin-bottom:0.8rem;">
              <span style="font-family:'IBM Plex Mono',monospace;font-size:1.4rem;
                           font-weight:600;color:#0f172a;">${price:,.2f}</span>
              {price_eur_str}
              <span style="font-size:0.78rem;color:#64748b;margin-left:0.6rem;">{sector}</span>
              {rec_badge_html}
            </div>

            <div style="background:#f8fafc;border-left:4px solid {vf['color']};border-radius:6px;
                        padding:0.7rem 0.9rem;margin-bottom:1rem;">
              <div style="font-size:0.95rem;font-weight:700;color:{vf['color']};margin-bottom:0.3rem;">
                {vf['icon']} {vf['level']}
              </div>
              <div style="font-size:0.82rem;color:#334155;line-height:1.5;">{vf['message']}</div>
            </div>

            <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:0.5rem;margin-bottom:1rem;">
              <div style="background:#f4f6f9;border-radius:6px;padding:0.5rem 0.7rem;">
                <div style="color:#64748b;font-size:0.7rem;">Calidad</div>
                <div style="font-family:'IBM Plex Mono',monospace;color:#0f172a;font-weight:600;">
                  {labels_calidad.get(vf['calidad'], vf['calidad'])}
                </div>
                <div style="color:#94a3b8;font-size:0.68rem;">Salud: {health}/100</div>
              </div>
              <div style="background:#f4f6f9;border-radius:6px;padding:0.5rem 0.7rem;">
                <div style="color:#64748b;font-size:0.7rem;">Precio</div>
                <div style="font-family:'IBM Plex Mono',monospace;color:#0f172a;font-weight:600;">
                  {labels_precio.get(vf['precio'], vf['precio'])}
                </div>
                <div style="color:#94a3b8;font-size:0.68rem;">{ev.get('diag_base','N/A')}</div>
              </div>
              <div style="background:#f4f6f9;border-radius:6px;padding:0.5rem 0.7rem;">
                <div style="color:#64748b;font-size:0.7rem;">Timing</div>
                <div style="font-family:'IBM Plex Mono',monospace;color:#0f172a;font-weight:600;">
                  {labels_timing.get(vf['timing'], vf['timing'])}
                </div>
                <div style="color:#94a3b8;font-size:0.68rem;">{signal.get('level','N/A')}</div>
              </div>
            </div>

            <div style="background:#334155;border-radius:4px;height:6px;margin-bottom:0.3rem;">
              <div style="height:6px;border-radius:4px;background:{'#059669' if health>=70 else '#d97706' if health>=45 else '#dc2626'};width:{health}%;"></div>
            </div>
            <div style="font-size:0.68rem;color:#94a3b8;margin-bottom:0.8rem;">Salud Fundamental: {health}/100</div>

            <div style="display:flex;gap:1.2rem;font-size:0.78rem;color:#64748b;">
              <span>PEG: <b style="color:#0f172a;">{f"{peg:.2f}" if peg else "N/A"}</b></span>
              <span>Upside vs Valor Objetivo: <b style="color:#0f172a;">
                {f"{ev['upside']:+.1f}%" if ev.get('upside') is not None else "N/A"}</b></span>
            </div>
            """, unsafe_allow_html=True)

    fx_str = f"{fx_rate:.4f}" if fx_rate else "N/A"
    st.caption(f"Motor de análisis: Salud Fundamental + Piotroski + Valor Objetivo + Señal de Entrada "
               f"(idéntico al de Análisis Individual) · datos Yahoo Finance · Tipo de cambio USD/EUR: {fx_str} "
               f"· No constituye asesoramiento financiero.")
