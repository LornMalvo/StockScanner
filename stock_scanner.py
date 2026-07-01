"""
stock_scanner.py
Rastreador de gangas: puntúa acciones del S&P 500 y/o lista personalizada
usando criterios fundamentales + técnicos propios.
"""

import yfinance as yf
import pandas as pd
import time
import streamlit as st
from analysis import SCANNER_TOOLTIPS

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


# ─────────────────────────────────────────────────────────────────────────────
# SISTEMA DE PUNTUACIÓN — "GANGA SCORE" (0-100)
# ─────────────────────────────────────────────────────────────────────────────
#
# CRITERIOS FUNDAMENTALES (hasta 55 pts)
#  F1. Valoración atractiva — PEG < 1.5             (0-15 pts)
#  F2. Margen de beneficio neto > 10%               (0-10 pts)
#  F3. Crecimiento de ingresos YoY > 10%            (0-10 pts)
#  F4. ROE sólido > 12%                             (0-10 pts)
#  F5. Balance sano — Deuda/Equity < 1 o FCF > 0   (0-10 pts)
#
# CRITERIOS TÉCNICOS / PRECIO (hasta 45 pts)
#  T1. Distancia al máximo anual — no en máximos    (0-15 pts)
#  T2. Corrección reciente desde máximo 3 meses     (0-15 pts)
#  T3. RSI en zona de oportunidad (< 50)            (0-10 pts)
#  T4. Precio bajo MM50 o MM200 (posible rebote)    (0- 5 pts)
#
# PENALIZACIONES
#  P1. RSI > 70 (sobrecompra)                       (-10 pts)
#  P2. Short Ratio > 5 (apuestas bajistas altas)    (- 5 pts)
#  P3. Precio en máximo 52W (±3%)                   (-10 pts)
#
# CLASIFICACIÓN FINAL:
#  80-100 → GANGA EXCEPCIONAL  ⭐⭐⭐
#  65-79  → OPORTUNIDAD        ⭐⭐
#  50-64  → INTERESANTE        ⭐
#  35-49  → NEUTRAL            —
#  < 35   → EVITAR             ✗

def _score_ticker(info: dict, hist: pd.DataFrame) -> dict:
    """
    Calcula el Ganga Score para un ticker dado su info y su histórico.
    Devuelve dict con score, desglose y clasificación.
    """
    score   = 0
    details = {}

    # ── Datos base ────────────────────────────────────────────────────────
    price       = info.get("currentPrice") or info.get("regularMarketPrice") or 0
    peg         = info.get("pegRatio")
    profit_m    = info.get("profitMargins") or 0
    rev_growth  = info.get("revenueGrowth") or 0          # decimal
    roe         = info.get("returnOnEquity") or 0
    debt_eq     = info.get("debtToEquity") or 0
    fcf         = info.get("freeCashflow") or 0
    short_ratio = info.get("shortRatio") or 0
    w52_high    = info.get("fiftyTwoWeekHigh") or price
    w52_low     = info.get("fiftyTwoWeekLow") or price
    pe_fwd      = info.get("forwardPE")
    pe_trail    = info.get("trailingPE")

    # ── F1: PEG / Valoración (0-15) ───────────────────────────────────────
    f1 = 0
    if peg is not None:
        if peg < 0.5:                f1 = 15
        elif peg < 0.8:              f1 = 13
        elif peg < 1.0:              f1 = 11
        elif peg < 1.2:              f1 = 8
        elif peg < 1.5:              f1 = 5
        elif peg < 2.0:              f1 = 2
    elif pe_fwd and pe_fwd < 12:     f1 = 10
    elif pe_fwd and pe_fwd < 18:     f1 = 6
    elif pe_fwd and pe_fwd < 25:     f1 = 3
    score += f1
    details["F1 Valoración (PEG)"] = (f1, 15, f"PEG={peg:.2f}" if peg else f"PEF={pe_fwd}")

    # ── F2: Margen neto (0-10) ────────────────────────────────────────────
    f2 = 0
    pm_pct = profit_m * 100
    if pm_pct >= 30:      f2 = 10
    elif pm_pct >= 20:    f2 = 8
    elif pm_pct >= 10:    f2 = 6
    elif pm_pct >= 5:     f2 = 3
    elif pm_pct > 0:      f2 = 1
    score += f2
    details["F2 Margen neto"] = (f2, 10, f"{pm_pct:.1f}%")

    # ── F3: Crecimiento ingresos (0-10) ───────────────────────────────────
    f3 = 0
    rg_pct = rev_growth * 100
    if rg_pct >= 40:      f3 = 10
    elif rg_pct >= 25:    f3 = 8
    elif rg_pct >= 15:    f3 = 6
    elif rg_pct >= 10:    f3 = 4
    elif rg_pct >= 5:     f3 = 2
    score += f3
    details["F3 Crec. Ingresos"] = (f3, 10, f"+{rg_pct:.1f}%")

    # ── F4: ROE (0-10) ────────────────────────────────────────────────────
    f4 = 0
    roe_pct = roe * 100
    if roe_pct >= 30:     f4 = 10
    elif roe_pct >= 20:   f4 = 8
    elif roe_pct >= 12:   f4 = 6
    elif roe_pct >= 8:    f4 = 3
    elif roe_pct > 0:     f4 = 1
    score += f4
    details["F4 ROE"] = (f4, 10, f"{roe_pct:.1f}%")

    # ── F5: Balance / FCF (0-10) ──────────────────────────────────────────
    f5 = 0
    if fcf > 0:           f5 += 5
    if debt_eq < 0.5:     f5 += 5
    elif debt_eq < 1.0:   f5 += 3
    elif debt_eq < 2.0:   f5 += 1
    score += f5
    details["F5 Balance/FCF"] = (f5, 10, f"D/E={debt_eq:.1f} FCF={'✔' if fcf>0 else '✘'}")

    # ── Técnicos: necesitan histórico ─────────────────────────────────────
    t1 = t2 = t3 = t4 = 0
    rsi_val  = None
    dist_max = None
    corr_3m  = None

    if hist is not None and not hist.empty and len(hist) >= 20:
        closes   = hist["Close"]
        price_now = float(closes.iloc[-1])

        # T1: Distancia al máximo anual (0-15)
        max_1y = float(closes.max())
        dist_max = (max_1y - price_now) / max_1y * 100  # % por debajo del máx
        if dist_max >= 30:    t1 = 15
        elif dist_max >= 20:  t1 = 12
        elif dist_max >= 10:  t1 = 8
        elif dist_max >= 5:   t1 = 4
        elif dist_max >= 2:   t1 = 1
        details["T1 Dist. máx. anual"] = (t1, 15, f"-{dist_max:.1f}% vs máx.")

        # T2: Corrección reciente (últimos 60 días) (0-15)
        if len(closes) >= 60:
            max_3m   = float(closes.tail(60).max())
            corr_3m  = (max_3m - price_now) / max_3m * 100
            if corr_3m >= 20:   t2 = 15
            elif corr_3m >= 12: t2 = 11
            elif corr_3m >= 7:  t2 = 7
            elif corr_3m >= 3:  t2 = 3
            details["T2 Corrección 3M"] = (t2, 15, f"-{corr_3m:.1f}% desde máx. 3M")

        # T3: RSI (0-10)
        if len(closes) >= 15:
            delta    = closes.diff()
            gain     = delta.clip(lower=0)
            loss     = (-delta).clip(lower=0)
            avg_gain = gain.ewm(com=13, min_periods=14).mean()
            avg_loss = loss.ewm(com=13, min_periods=14).mean()
            rs       = avg_gain / avg_loss
            rsi_s    = 100 - (100 / (1 + rs))
            rsi_val  = round(float(rsi_s.iloc[-1]), 1)
            if rsi_val <= 25:   t3 = 10
            elif rsi_val <= 30: t3 = 8
            elif rsi_val <= 40: t3 = 6
            elif rsi_val <= 50: t3 = 3
            details["T3 RSI"] = (t3, 10, f"RSI={rsi_val}")

        # T4: Precio vs MMs (0-5)
        mm50  = float(closes.tail(50).mean()) if len(closes) >= 50 else None
        mm200 = float(closes.tail(200).mean()) if len(closes) >= 200 else None
        if mm50 and price_now < mm50:    t4 += 3
        if mm200 and price_now < mm200:  t4 += 2
        if mm50 or mm200:
            details["T4 Precio vs MMs"] = (t4, 5, f"{'<MM50 ' if mm50 and price_now<mm50 else ''}{'<MM200' if mm200 and price_now<mm200 else ''}")

    score += t1 + t2 + t3 + t4

    # ── Penalizaciones ────────────────────────────────────────────────────
    pen = 0
    if rsi_val and rsi_val > 70:
        pen -= 10
        details["P1 RSI sobrecompra"] = (-10, 0, f"RSI={rsi_val}")
    if short_ratio > 5:
        pen -= 5
        details["P2 Short ratio alto"] = (-5, 0, f"SR={short_ratio:.1f}")
    if dist_max is not None and dist_max < 3:
        pen -= 10
        details["P3 En máximos"] = (-10, 0, f"Solo -{dist_max:.1f}% del máx.")

    score = max(0, min(100, score + pen))

    # ── Clasificación ─────────────────────────────────────────────────────
    if score >= 80:
        grade = "GANGA EXCEPCIONAL"
        stars = "⭐⭐⭐"
        grade_color = "#059669"
    elif score >= 65:
        grade = "OPORTUNIDAD"
        stars = "⭐⭐"
        grade_color = "#16a34a"
    elif score >= 50:
        grade = "INTERESANTE"
        stars = "⭐"
        grade_color = "#d97706"
    elif score >= 35:
        grade = "NEUTRAL"
        stars = "—"
        grade_color = "#64748b"
    else:
        grade = "EVITAR"
        stars = "✗"
        grade_color = "#dc2626"

    return {
        "score":       score,
        "grade":       grade,
        "stars":       stars,
        "grade_color": grade_color,
        "details":     details,
        "rsi":         rsi_val,
        "dist_max":    dist_max,
        "corr_3m":     corr_3m,
        "price":       price,
        "peg":         peg,
        "profit_m":    profit_m * 100,
        "rev_growth":  rev_growth * 100,
        "roe":         roe * 100,
        "sector":      info.get("sector", "N/A"),
        "name":        info.get("longName") or info.get("shortName", ""),
    }


# ─────────────────────────────────────────────────────────────────────────────
# ESCANEO DE UNIVERSO
# ─────────────────────────────────────────────────────────────────────────────

def scan_universe(
    tickers: list[str],
    min_score: int = 50,
    top_n: int = 20,
    progress_cb=None,
) -> list[dict]:
    """
    Escanea una lista de tickers y devuelve los mejores resultados ordenados por score.
    progress_cb: función que recibe (i, total, ticker) para actualizar barra.
    """
    results = []
    total   = len(tickers)

    for i, ticker in enumerate(tickers):
        if progress_cb:
            progress_cb(i, total, ticker)
        try:
            t    = yf.Ticker(ticker)
            info = t.info
            if not info or (not info.get("currentPrice") and not info.get("regularMarketPrice")):
                continue
            # Histórico 1 año
            hist = t.history(period="1y", interval="1d")
            result = _score_ticker(info, hist)
            result["ticker"] = ticker
            if result["score"] >= min_score:
                results.append(result)
        except Exception:
            pass
        # Pequeña pausa para no saturar la API
        time.sleep(0.15)

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_n]


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
# RENDER DEL RASTREADOR
# ─────────────────────────────────────────────────────────────────────────────

def render_scanner(fx_rate: float | None = None):
    """Renderiza la pestaña del rastreador de gangas."""

    st.markdown("""
    <div style="margin-bottom:1.5rem;">
      <div style="font-family:'IBM Plex Mono',monospace;font-size:0.75rem;color:#0284c7;
                  text-transform:uppercase;letter-spacing:0.1em;margin-bottom:0.4rem;">
        SISTEMA DE PUNTUACIÓN — GANGA SCORE (0-100)
      </div>
      <div style="background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;padding:1rem 1.2rem;
                  font-size:0.82rem;color:#64748b;line-height:1.7;">
        <b style="color:#0f172a;">Criterios fundamentales (55 pts):</b>
        F1·Valoración/PEG (15) &nbsp;·&nbsp; F2·Margen neto (10) &nbsp;·&nbsp;
        F3·Crecimiento ingresos (10) &nbsp;·&nbsp; F4·ROE (10) &nbsp;·&nbsp; F5·Balance/FCF (10)<br>
        <b style="color:#0f172a;">Criterios técnicos / precio (45 pts):</b>
        T1·Distancia al máximo anual (15) &nbsp;·&nbsp; T2·Corrección reciente 3M (15) &nbsp;·&nbsp;
        T3·RSI zona oportunidad (10) &nbsp;·&nbsp; T4·Precio bajo MMs (5)<br>
        <b style="color:#dc2626;">Penalizaciones:</b>
        RSI sobrecompra (-10) &nbsp;·&nbsp; Short ratio alto (-5) &nbsp;·&nbsp; En máximos anuales (-10)
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Configuración del escaneo ─────────────────────────────────────────
    col1, col2 = st.columns([1, 1])
    with col1:
        use_sp500 = st.checkbox("Incluir S&P 500 (~200 tickers)", value=True)
        custom_raw = st.text_area(
            "Mi lista personalizada (separados por coma o espacio)",
            placeholder="ASML, SAP, LVMH, ITX, SAN...",
            height=80,
        )
    with col2:
        min_score = st.slider("Puntuación mínima para mostrar", 0, 80, 50, step=5)
        top_n     = st.slider("Máximo de resultados a mostrar", 5, 50, 20, step=5)
        sector_filter = st.text_input(
            "Filtrar por sector (opcional)",
            placeholder="Technology, Healthcare, Energy...",
        )

    iniciar = st.button("🔍  INICIAR RASTREO", use_container_width=True)

    if not iniciar:
        st.markdown("""
        <div style="text-align:center;padding:2rem;color:#64748b;font-size:0.88rem;">
          Configura los parámetros y pulsa <b style="color:#0284c7;">INICIAR RASTREO</b>.<br>
          El S&P 500 tarda ~5 min. Una lista corta tarda segundos.
        </div>
        """, unsafe_allow_html=True)
        return

    tickers = build_ticker_list(use_sp500, custom_raw)
    if not tickers:
        st.warning("Añade al menos un ticker o activa el S&P 500.")
        return

    st.info(f"Escaneando **{len(tickers)} tickers**… esto puede tardar unos minutos.", icon="⏳")

    # Barra de progreso
    prog_bar  = st.progress(0)
    prog_text = st.empty()

    def progress_cb(i, total, ticker):
        pct = int((i + 1) / total * 100)
        prog_bar.progress(pct)
        prog_text.markdown(
            f'<span style="font-family:\'IBM Plex Mono\',monospace;font-size:0.75rem;color:#64748b;">'
            f'Analizando {ticker} ({i+1}/{total})</span>',
            unsafe_allow_html=True,
        )

    results = scan_universe(tickers, min_score=min_score, top_n=top_n, progress_cb=progress_cb)
    prog_bar.empty()
    prog_text.empty()

    # Filtro por sector
    if sector_filter.strip():
        sf = sector_filter.strip().lower()
        results = [r for r in results if sf in (r.get("sector") or "").lower()]

    if not results:
        st.warning("No se encontraron acciones con esa puntuación mínima. Prueba a bajar el umbral.")
        return

    st.markdown(f"""
    <div style="font-family:'IBM Plex Mono',monospace;font-size:0.8rem;color:#0284c7;
                margin:1rem 0 0.5rem 0;">
      ✔ {len(results)} resultado{'s' if len(results)!=1 else ''} encontrado{'s' if len(results)!=1 else ''}
      &nbsp;·&nbsp; ordenados por Ganga Score
    </div>
    """, unsafe_allow_html=True)

    # ── Tabla de resultados ───────────────────────────────────────────────
    for r in results:
        ticker      = r["ticker"]
        name        = r["name"] or ticker
        score       = r["score"]
        grade       = r["grade"]
        stars       = r["stars"]
        gcolor      = r["grade_color"]
        price       = r["price"]
        sector      = r["sector"]
        peg         = r["peg"]
        pm          = r["profit_m"]
        rg          = r["rev_growth"]
        roe_v       = r["roe"]
        rsi_v       = r["rsi"]
        dist_max    = r["dist_max"]
        corr_3m     = r["corr_3m"]

        # Precio en EUR
        price_eur_str = ""
        if fx_rate and price:
            price_eur_str = f' <span style="color:#64748b;font-size:0.82em;">(€{price*fx_rate:,.2f})</span>'

        # Barra de score
        bar_color = gcolor

        # Desglose de criterios con tooltips
        details_html = ""
        for key, (pts, max_pts, note) in r["details"].items():
            if pts < 0:
                pt_color = "#dc2626"
                pt_str   = str(pts)
            elif pts == 0:
                pt_color = "#64748b"
                pt_str   = "0"
            else:
                pt_color = "#059669"
                pt_str   = f"+{pts}"
            # Tooltip
            tip = SCANNER_TOOLTIPS.get(key, "")
            tip_html = ""
            if tip:
                tip_safe = tip.replace('"','&quot;').replace("'","&#39;")
                tip_html = (
                    '<span class="tooltip-wrap" style="margin-left:0.3rem;position:relative;cursor:help;">'
                    '<span style="font-size:0.6rem;color:#0284c7;border:1px solid #0284c7;'
                    'border-radius:50%;padding:0 3px;font-family:\'IBM Plex Mono\',monospace;">?</span>'
                    f'<span class="tooltip-box">{tip}</span>'
                    '</span>'
                )
            details_html += (
                '<div style="display:flex;justify-content:space-between;align-items:center;'
                'padding:0.22rem 0;font-size:0.75rem;border-bottom:1px solid #eef1f5;">'
                f'<span style="color:#64748b;">{key}{tip_html}</span>'
                f'<span style="color:#64748b;margin:0 0.5rem;">{note}</span>'
                f'<span style="font-family:\'IBM Plex Mono\',monospace;font-weight:600;color:{pt_color};">{pt_str}/{max_pts}</span>'
                '</div>'
            )

        with st.expander(f"{stars}  {ticker} — {name[:40]}  ·  Score: {score}/100  ·  {grade}", expanded=False):
            st.markdown(f"""
            <div style="margin-bottom:0.8rem;">
              <span style="font-family:'IBM Plex Mono',monospace;font-size:1.4rem;
                           font-weight:600;color:#0f172a;">${price:,.2f}</span>
              {price_eur_str}
              <span style="font-size:0.78rem;color:#64748b;margin-left:0.6rem;">{sector}</span>
              <div style="margin-top:0.4rem;">
                <span style="font-family:'IBM Plex Mono',monospace;font-size:0.85rem;
                             font-weight:700;color:{gcolor};">{grade} {stars}</span>
              </div>
            </div>

            <div style="background:#334155;border-radius:4px;height:6px;margin-bottom:1rem;">
              <div style="height:6px;border-radius:4px;background:{bar_color};width:{score}%;"></div>
            </div>

            <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:0.5rem;
                        margin-bottom:1rem;font-size:0.82rem;">
              <div style="background:#f4f6f9;border-radius:6px;padding:0.5rem 0.7rem;">
                <div style="color:#64748b;font-size:0.7rem;">PEG</div>
                <div style="font-family:'IBM Plex Mono',monospace;color:#0f172a;font-weight:600;">
                  {f"{peg:.2f}" if peg else "N/A"}
                </div>
              </div>
              <div style="background:#f4f6f9;border-radius:6px;padding:0.5rem 0.7rem;">
                <div style="color:#64748b;font-size:0.7rem;">Margen neto</div>
                <div style="font-family:'IBM Plex Mono',monospace;color:#0f172a;font-weight:600;">
                  {f"{pm:.1f}%" if pm else "N/A"}
                </div>
              </div>
              <div style="background:#f4f6f9;border-radius:6px;padding:0.5rem 0.7rem;">
                <div style="color:#64748b;font-size:0.7rem;">Crec. ingresos</div>
                <div style="font-family:'IBM Plex Mono',monospace;
                            color:{'#059669' if (rg or 0)>0 else '#dc2626'};font-weight:600;">
                  {f"+{rg:.1f}%" if rg else "N/A"}
                </div>
              </div>
              <div style="background:#f4f6f9;border-radius:6px;padding:0.5rem 0.7rem;">
                <div style="color:#64748b;font-size:0.7rem;">ROE</div>
                <div style="font-family:'IBM Plex Mono',monospace;color:#0f172a;font-weight:600;">
                  {f"{roe_v:.1f}%" if roe_v else "N/A"}
                </div>
              </div>
              <div style="background:#f4f6f9;border-radius:6px;padding:0.5rem 0.7rem;">
                <div style="color:#64748b;font-size:0.7rem;">RSI</div>
                <div style="font-family:'IBM Plex Mono',monospace;
                            color:{'#059669' if rsi_v and rsi_v<40 else '#dc2626' if rsi_v and rsi_v>65 else '#0f172a'};
                            font-weight:600;">
                  {f"{rsi_v:.0f}" if rsi_v else "N/A"}
                </div>
              </div>
              <div style="background:#f4f6f9;border-radius:6px;padding:0.5rem 0.7rem;">
                <div style="color:#64748b;font-size:0.7rem;">Dist. máx. anual</div>
                <div style="font-family:'IBM Plex Mono',monospace;color:#059669;font-weight:600;">
                  {f"-{dist_max:.1f}%" if dist_max else "N/A"}
                </div>
              </div>
            </div>

            <div style="font-family:'IBM Plex Mono',monospace;font-size:0.7rem;color:#0284c7;
                        text-transform:uppercase;letter-spacing:0.1em;margin-bottom:0.4rem;">
              Desglose de criterios
            </div>
            {details_html}
            """, unsafe_allow_html=True)

    fx_str = f"{fx_rate:.4f}" if fx_rate else "N/A"
    st.caption(f"Ganga Score calculado con datos de Yahoo Finance · Tipo de cambio USD/EUR: {fx_str} · No constituye asesoramiento financiero.")
