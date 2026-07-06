"""
report.py — v1.9
Renderiza el informe completo en Streamlit con el diseño claro.
"""

import streamlit as st
import plotly.graph_objects as go
import yfinance as yf
from analysis import (
    calc_entry_signal, calc_trend, fetch_peer_data, get_manual_competitors,
    render_entry_signal, render_trend, render_peers,
    fetch_company_description, fetch_recent_news, fetch_earnings_analysis,
    fetch_last_cross_date, render_company_description, render_news,
    get_sector_benchmarks, fetch_analyst_revisions,
    calc_short_squeeze, render_short_squeeze,
)
from dcf import (
    fetch_historical_multiples,
    render_historical_multiples,
)
from pdf_export import render_pdf_download_button
from gemini_valuation import render_ai_valuation


# ─── Gráfico de cotización con MM50/MM200 ────────────────────────────────────

def _render_price_chart(tech: dict, ticker: str, currency: str = "USD"):
    """
    Gráfico interactivo de cotización a 1 año con MM50 y MM200 superpuestas.
    Zoom, pan y tooltip con fecha + precio al pasar el cursor (nativo de Plotly).
    """
    history = tech.get("price_history", [])
    if not history:
        return

    dates  = [h["date"]  for h in history]
    closes = [h["close"] for h in history]
    mm50s  = [h["mm50"]  for h in history]
    mm200s = [h["mm200"] for h in history]

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=dates, y=closes, mode="lines", name="Precio",
        line=dict(color="#0284c7", width=2),
        hovertemplate="<b>%{x}</b><br>Precio: " + currency + " %{y:.2f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=dates, y=mm50s, mode="lines", name="MM50",
        line=dict(color="#d97706", width=1.4, dash="solid"),
        hovertemplate="<b>%{x}</b><br>MM50: " + currency + " %{y:.2f}<extra></extra>",
    ))
    if any(v is not None for v in mm200s):
        fig.add_trace(go.Scatter(
            x=dates, y=mm200s, mode="lines", name="MM200",
            line=dict(color="#dc2626", width=1.4, dash="solid"),
            hovertemplate="<b>%{x}</b><br>MM200: " + currency + " %{y:.2f}<extra></extra>",
        ))

    fig.update_layout(
        height=380,
        margin=dict(l=10, r=10, t=10, b=10),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        font=dict(family="Inter, sans-serif", size=12, color="#1e293b"),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0,
                    font=dict(size=11)),
        xaxis=dict(
            showgrid=False, showline=True, linecolor="#e2e8f0",
            rangeslider=dict(visible=False),
            rangeselector=dict(
                buttons=[
                    dict(count=1, label="1M", step="month", stepmode="backward"),
                    dict(count=3, label="3M", step="month", stepmode="backward"),
                    dict(count=6, label="6M", step="month", stepmode="backward"),
                    dict(step="all", label="1A"),
                ],
                bgcolor="#f4f6f9", activecolor="#dbeafe",
                font=dict(size=10, color="#334155"),
            ),
        ),
        yaxis=dict(
            showgrid=True, gridcolor="#f1f5f9", showline=True, linecolor="#e2e8f0",
            tickprefix=f"{currency} ",
        ),
    )

    st.plotly_chart(fig, use_container_width=True, config={
        "displayModeBar": True,
        "modeBarButtonsToRemove": ["lasso2d", "select2d"],
        "displaylogo": False,
        "scrollZoom": True,
    })
    st.markdown(
        '<div style="font-size:0.68rem;color:#94a3b8;margin-top:-0.5rem;margin-bottom:0.8rem;">'
        '📈 Arrastra para hacer zoom · Doble clic para restablecer · Usa los botones 1M/3M/6M/1A '
        'para cambiar el rango · Pasa el cursor para ver fecha y precio exactos</div>',
        unsafe_allow_html=True
    )


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _fmt_num(val, decimals=2, prefix="", suffix=""):
    if val is None:
        return "N/A"
    try:
        return f"{prefix}{val:,.{decimals}f}{suffix}"
    except Exception:
        return "N/A"


def _fmt_big(val, prefix="$", fx_rate: float | None = None):
    """Formatea números grandes en B / M, con conversión EUR opcional."""
    if val is None:
        return "N/A"
    try:
        val = float(val)
        if abs(val) >= 1e12:
            base = f"{prefix}{val/1e12:.2f}T"
        elif abs(val) >= 1e9:
            base = f"{prefix}{val/1e9:.2f}B"
        elif abs(val) >= 1e6:
            base = f"{prefix}{val/1e6:.2f}M"
        else:
            base = f"{prefix}{val:,.0f}"
        if fx_rate and prefix == "$":
            eur_val = val * fx_rate
            if abs(eur_val) >= 1e12:
                eur_str = f"€{eur_val/1e12:.2f}T"
            elif abs(eur_val) >= 1e9:
                eur_str = f"€{eur_val/1e9:.2f}B"
            elif abs(eur_val) >= 1e6:
                eur_str = f"€{eur_val/1e6:.2f}M"
            else:
                eur_str = f"€{eur_val:,.0f}"
            return f'{base} <span style="color:#64748b;font-size:0.85em;">({eur_str})</span>'
        return base
    except Exception:
        return "N/A"


def _fmt_price(val, currency="USD", fx_rate: float | None = None) -> str:
    """Formatea precio con conversión EUR si la moneda es USD."""
    if val is None:
        return "N/A"
    try:
        val = float(val)
        base = f"{currency} {val:,.2f}"
        if fx_rate and currency == "USD":
            eur_val = val * fx_rate
            return f'{base} <span style="color:#64748b;font-size:0.85em;">(€{eur_val:,.2f})</span>'
        return base
    except Exception:
        return "N/A"


def _color_pct(val):
    if val is None:
        return "row-val"
    return "row-val green" if val >= 0 else "row-val red"


def _badge(rec: str) -> str:
    rec_up = (rec or "").upper()
    if "BUY" in rec_up or "STRONG" in rec_up:
        cls = "badge-buy"
    elif "SELL" in rec_up:
        cls = "badge-sell"
    else:
        cls = "badge-hold"
    return f'<span class="{cls}">{rec_up}</span>'


# ─── Tooltips por métrica ─────────────────────────────────────────────────────

TOOLTIPS = {
    "Precio Actual":      "Último precio de cierre. Referencia base para todos los cálculos de valoración.",
    "Objetivo Analistas": "Precio medio objetivo fijado por los analistas que cubren el valor. Por encima del precio actual indica potencial alcista según consenso.",
    "Rango":              "Rango de precios objetivo entre el analista más bajista y el más alcista. Un rango estrecho indica mayor consenso.",
    "Recomendación":      "Consenso de recomendación de los analistas: Strong Buy > Buy > Hold > Sell > Strong Sell.",
    "Nº Analistas":       "Número de analistas que cubren el valor. Más analistas = mayor fiabilidad del consenso.",

    "PER Trailing":       "Price/Earnings Trailing: precio dividido entre el beneficio de los últimos 12 meses. Bueno: <15 (value), normal: 15-25, caro: >35. Depende mucho del sector.",
    "PER Forward":        "Price/Earnings Forward: precio dividido entre el beneficio estimado próximos 12 meses. Más relevante que el trailing. Bueno: <15, normal: 15-25.",
    "PEG Ratio":          "PER dividido entre tasa de crecimiento anual. Neutraliza la prima de crecimiento. PEG < 1 = potencialmente infravalorada, PEG > 2 = cara respecto a su crecimiento.",
    "Price/Sales":        "Capitalización dividida entre ventas. Útil para empresas sin beneficios. Bueno: <2×, normal: 2-5×, caro: >10×. Varía mucho por sector.",
    "Price/Book":         "Precio dividido entre valor contable. P/B < 1 puede indicar ganga (o problemas). Normal: 1-3×. Financieras suelen estar cerca de 1×.",
    "EV/Revenue":         "Valor empresa dividido entre ingresos. Similar a P/S pero incluye deuda. Bueno: <3×, normal: 3-8×. Sectores de alto margen aceptan múltiplos mayores.",
    "EV/EBITDA":          "Valor empresa dividido entre EBITDA. Métrica de valoración universal. Bueno: <8×, normal: 8-15×, caro: >20×. Energía: <6×, Tech: hasta 25× es normal.",
    "Market Cap":         "Valor total de mercado de todas las acciones en circulación. Define el tamaño: <$2B micro/small cap, $2-10B mid cap, >$10B large cap.",

    "Profit Margin":      "Beneficio neto / ingresos. Mide cuánto queda tras todos los gastos. Bueno: >15%, aceptable: 5-15%, malo: <5%. Tech suele superar el 20%.",
    "Operating Margin":   "Beneficio operativo / ingresos. Excluye intereses e impuestos. Bueno: >15%, indica eficiencia operativa. Compara siempre dentro del mismo sector.",
    "EBITDA Margin":      "EBITDA / ingresos. Proxy del flujo de caja operativo bruto. Bueno: >20%, excelente: >35%. Útil para comparar empresas con diferente estructura de capital.",
    "ROE":                "Beneficio neto / patrimonio neto. Mide eficiencia del capital propio. Bueno: >15%, excelente: >25%. Muy alto puede indicar exceso de apalancamiento.",
    "ROA":                "Beneficio neto / activos totales. Más conservador que el ROE. Bueno: >5%, excelente: >10%. No se distorsiona con el apalancamiento.",

    "Total Cash":         "Efectivo y equivalentes en balance. Más caja = más seguridad y flexibilidad para invertir o recomprar acciones.",
    "Total Debt":         "Deuda total (corto + largo plazo). Compara siempre con el EBITDA (ratio deuda/EBITDA <3× es manejable).",
    "Debt/Equity":        "Deuda total / patrimonio neto (en %). Bueno: <50%, aceptable: 50-100%, preocupante: >200%. Utilities y REITs aceptan más deuda.",
    "Current Ratio":      "Activos corrientes / pasivos corrientes. Mide liquidez a corto plazo. Bueno: >1.5×, aceptable: 1-1.5×, riesgo: <1×.",
    "Free Cash Flow":     "Flujo de caja operativo menos inversiones (capex). El dinero real que genera el negocio. FCF positivo y creciente es la señal más sólida de calidad.",
    "Operating Cash Flow":"Efectivo generado por las operaciones antes de inversiones. Diferente al beneficio contable: más difícil de manipular.",

    "Revenue Growth":     "Crecimiento de ingresos año sobre año. Bueno: >10%, excelente: >25%. Crecimiento negativo es señal de alerta salvo restructuración deliberada.",
    "Earnings Growth":    "Crecimiento del beneficio neto año sobre año. Idealmente superior al crecimiento de ingresos (expansión de márgenes). >20% es excelente.",
    "EPS (TTM)":          "Beneficio por acción de los últimos 12 meses. Base para calcular el PER trailing. EPS creciente = negocio mejorando.",
    "EPS (Forward)":      "Beneficio por acción estimado para los próximos 12 meses. Base para el PER Forward. Es una estimación: puede revisarse al alza o a la baja.",

    "Dividend Yield":     "Dividendo anual / precio acción. Rentabilidad por dividendo. >3% es atractivo como renta, pero un yield muy alto puede indicar riesgo de recorte.",
    "Dividend Rate":      "Dividendo anual en términos absolutos por acción.",
    "Short Ratio":        "Días necesarios para cubrir las posiciones cortas al volumen medio. <3 días = poca presión bajista, >7 días = alta presión bajista (señal de alerta).",
    "Beta":               "Volatilidad relativa vs el mercado. Beta >1 = más volátil que el índice, Beta <1 = más estable. Beta negativo = movimiento inverso al mercado.",
    "52W High":           "Precio máximo de los últimos 52 semanas. Cotizar cerca del máximo puede indicar momentum positivo o sobrecompra.",
    "52W Low":            "Precio mínimo de los últimos 52 semanas. Cotizar cerca del mínimo puede indicar una oportunidad o una empresa en problemas.",

    "MM50":               "Media Móvil de 50 sesiones. Tendencia de medio plazo. Precio sobre MM50 = tendencia alcista, bajo = bajista.",
    "Distancia MM50":     "% de diferencia entre el precio actual y la MM50. Muy por debajo de la MM50 puede ser zona de rebote.",
    "Señal MM50":         "Interpretación direccional respecto a la MM50. Alcista si el precio está por encima.",
    "MM200":              "Media Móvil de 200 sesiones. Tendencia de largo plazo. Es el indicador técnico más seguido por institucionales.",
    "Distancia MM200":    "% de diferencia entre el precio actual y la MM200. Por debajo = zona de soporte histórico relevante.",
    "Señal MM200":        "Interpretación direccional respecto a la MM200. Alcista si el precio está por encima.",
    "Cruce MM50/MM200":   "Golden Cross (MM50 > MM200) = señal alcista histórica. Death Cross (MM50 < MM200) = señal bajista. Son señales de largo plazo.",
}

def _kv(label, value, color_class="row-val"):
    """Fila clave-valor con tooltip opcional al pasar el cursor."""
    tip = TOOLTIPS.get(label, "")
    tip_html = ""
    if tip:
        tip_safe = tip.replace('"', '&quot;').replace("'", "&#39;")
        tip_html = f"""
        <span class="tooltip-wrap" style="margin-left:0.3rem;position:relative;cursor:help;">
          <span style="font-size:0.65rem;color:#0284c7;border:1px solid #0284c7;
                       border-radius:50%;padding:0 3px;font-family:'IBM Plex Mono',monospace;">?</span>
          <span class="tooltip-box">{tip}</span>
        </span>"""
    return f"""
    <div class="row-kv">
      <span class="row-key">{label}{tip_html}</span>
      <span class="{color_class}">{value}</span>
    </div>"""


def _section(title):
    st.markdown(f'<div class="section-header">{title}</div>', unsafe_allow_html=True)


# ─── Benchmarks por sector ────────────────────────────────────────────────────
#
# Cada sector tiene sus propios rangos "normales" para:
#   pe_fair   → PER razonable para el sector
#   pe_high   → PER caro para el sector
#   peg_ok    → PEG aceptable
#   margin_ok → Margen neto mínimo aceptable
#   roe_ok    → ROE mínimo aceptable
#   ev_ebitda_fair → EV/EBITDA razonable
#   methods   → qué métodos de valoración usar (por orden de relevancia)
#               "per"=PER×EPS, "peg"=PEG, "ev_ebitda"=EV/EBITDA, "ev_rev"=EV/Revenue
#               "dcf_lite"=FCF yield, "nav"=Price/Book para financieras
#   notas     → texto explicativo para el usuario

SECTOR_PROFILES = {
    "Technology": {
        "pe_fair": 28, "pe_high": 50, "g": 0.040,
        "peg_ok": 1.5, "margin_ok": 0.12, "roe_ok": 0.15,
        "ev_ebitda_fair": 22, "ev_sales_fair": 8,
        "methods": ["peg", "per", "ev_ebitda"],
        "nota": "Tecnología cotiza con prima estructural por crecimiento. PEG < 1.5 y márgenes > 12% son señales positivas.",
    },
    "Communication Services": {
        "pe_fair": 22, "pe_high": 40, "g": 0.035,
        "peg_ok": 1.3, "margin_ok": 0.10, "roe_ok": 0.12,
        "ev_ebitda_fair": 18, "ev_sales_fair": 5,
        "methods": ["peg", "ev_ebitda", "per"],
        "nota": "Servicios de comunicación valora el crecimiento de usuarios y EBITDA. Los múltiplos varían mucho entre plataformas y telecos.",
    },
    "Consumer Cyclical": {
        "pe_fair": 20, "pe_high": 35, "g": 0.030,
        "peg_ok": 1.2, "margin_ok": 0.06, "roe_ok": 0.12,
        "ev_ebitda_fair": 14, "ev_sales_fair": 2.5,
        "methods": ["per", "ev_ebitda", "peg"],
        "nota": "Cíclico al consumo: los márgenes caen en recesión. PER < 20 con ROE > 12% es señal sólida.",
    },
    "Consumer Defensive": {
        "pe_fair": 22, "pe_high": 32, "g": 0.025,
        "peg_ok": 2.0, "margin_ok": 0.07, "roe_ok": 0.15,
        "ev_ebitda_fair": 16, "ev_sales_fair": 2,
        "methods": ["per", "ev_ebitda", "peg"],
        "nota": "Defensivo al consumo: se valora por estabilidad y dividendos. PER hasta 22 es razonable.",
    },
    "Healthcare": {
        "pe_fair": 24, "pe_high": 45, "g": 0.035,
        "peg_ok": 1.8, "margin_ok": 0.10, "roe_ok": 0.12,
        "ev_ebitda_fair": 18, "ev_sales_fair": 6,
        "methods": ["peg", "per", "ev_ebitda"],
        "nota": "Salud tiene prima por pipeline y patentes. Farmacéuticas puras pueden tener PER alto justificado.",
    },
    "Financials": {
        "pe_fair": 14, "pe_high": 22, "g": 0.030,
        "peg_ok": 1.0, "margin_ok": 0.15, "roe_ok": 0.10,
        "ev_ebitda_fair": 10, "ev_sales_fair": 3,
        "methods": ["nav", "per", "peg"],
        "nota": "Financieras se valoran por Price/Book y ROE. EV/EBITDA menos relevante; se prefiere P/B < 1.5 + ROE > 10%.",
    },
    "Industrials": {
        "pe_fair": 20, "pe_high": 32, "g": 0.028,
        "peg_ok": 1.5, "margin_ok": 0.07, "roe_ok": 0.12,
        "ev_ebitda_fair": 14, "ev_sales_fair": 2,
        "methods": ["per", "ev_ebitda", "peg"],
        "nota": "Industriales valoran flujo de caja operativo y márgenes estables. PER < 20 y D/E < 1 son buenas señales.",
    },
    "Energy": {
        "pe_fair": 14, "pe_high": 22, "g": 0.015,
        "peg_ok": 1.0, "margin_ok": 0.08, "roe_ok": 0.10,
        "ev_ebitda_fair": 6, "ev_sales_fair": 1.5,
        "methods": ["ev_ebitda", "per", "dcf_lite"],
        "nota": "Energía se valora principalmente por EV/EBITDA (ciclo de commodity). EV/EBITDA < 6 es barato para el sector.",
    },
    "Basic Materials": {
        "pe_fair": 16, "pe_high": 26, "g": 0.020,
        "peg_ok": 1.2, "margin_ok": 0.06, "roe_ok": 0.10,
        "ev_ebitda_fair": 8, "ev_sales_fair": 1.5,
        "methods": ["ev_ebitda", "per", "peg"],
        "nota": "Materiales básicos depende del ciclo. EV/EBITDA es la métrica principal; los márgenes fluctúan con el precio del commodity.",
    },
    "Real Estate": {
        "pe_fair": 30, "pe_high": 55, "g": 0.025,
        "peg_ok": 2.5, "margin_ok": 0.20, "roe_ok": 0.08,
        "ev_ebitda_fair": 20, "ev_sales_fair": 8,
        "methods": ["ev_ebitda", "dcf_lite", "per"],
        "nota": "REITs y real estate se valoran por FFO/AFFO y EV/EBITDA. El PER convencional puede ser engañoso por la depreciación.",
    },
    "Utilities": {
        "pe_fair": 18, "pe_high": 28, "g": 0.020,
        "peg_ok": 2.0, "margin_ok": 0.10, "roe_ok": 0.08,
        "ev_ebitda_fair": 12, "ev_sales_fair": 3,
        "methods": ["per", "ev_ebitda", "dcf_lite"],
        "nota": "Utilities cotizan por estabilidad regulatoria y dividendos. PER < 18 y yield > 3% son señales atractivas.",
    },
    # Fallback genérico
    "_default": {
        "pe_fair": 20, "pe_high": 35, "g": 0.030,
        "peg_ok": 1.5, "margin_ok": 0.08, "roe_ok": 0.10,
        "ev_ebitda_fair": 14, "ev_sales_fair": 3,
        "methods": ["per", "peg", "ev_ebitda"],
        "nota": "Sector no clasificado. Se aplican benchmarks genéricos.",
    },
}

def _get_sector_profile(sector: str) -> dict:
    """Devuelve el perfil del sector, buscando coincidencia parcial."""
    for key in SECTOR_PROFILES:
        if key != "_default" and key.lower() in (sector or "").lower():
            return SECTOR_PROFILES[key], key
    return SECTOR_PROFILES["_default"], sector or "Desconocido"


# ─── Ajuste dinámico de benchmarks por tipos de interés ──────────────────────
# Los múltiplos "justos" (PER, EV/EBITDA) derivan implícitamente de un coste
# de capital exigido. Cuando los tipos de interés suben, ese coste de capital
# sube, y matemáticamente el múltiplo "justo" debe bajar para una misma tasa
# de crecimiento esperada (modelo de Gordon: PER justo ≈ 1/(r-g), con
# r = Rf + β×ERP vía CAPM). Aquí aplicamos esa lógica de forma simplificada
# y acotada a los benchmarks estáticos por sector.

_RF_BASELINE = 0.040   # tipo libre de riesgo de referencia (media histórica ~20 años)
_ERP         = 0.055   # prima de riesgo de mercado (media histórica S&P 500, Damodaran)
_ADJ_MIN     = 0.75    # cota inferior del factor de ajuste (máx -25%)
_ADJ_MAX     = 1.25    # cota superior del factor de ajuste (máx +25%)


def fetch_risk_free_rate() -> float | None:
    """
    Rendimiento del bono del Tesoro USA a 10 años en tiempo real (^TNX).
    Devuelve None si no se puede obtener — en ese caso no se ajustan los
    benchmarks y se usan los valores estáticos originales.
    """
    try:
        t    = yf.Ticker("^TNX")
        info = t.info
        rate = info.get("regularMarketPrice") or info.get("previousClose")
        if rate and 0 < rate < 20:
            return rate / 100
    except Exception as e:
        print(f"[RiskFreeRate] Error: {e}")
    return None


def _adjust_sector_profile(profile: dict, rf_current: float | None) -> tuple[dict, dict | None]:
    """
    Ajusta pe_fair, pe_high y ev_ebitda_fair según el tipo libre de riesgo
    actual vs el de referencia, usando el modelo de Gordon simplificado.
    peg_ok NO se ajusta (ya normaliza por crecimiento, evita doble contar
    el efecto de tipos).

    Devuelve (profile_ajustado, info_ajuste). info_ajuste es None si no
    se pudo aplicar el ajuste (sin dato de Rf o beta), para que la UI
    pueda mostrar honestamente que se están usando benchmarks estáticos.
    """
    if rf_current is None:
        return profile, None

    g = profile.get("g", 0.030)
    r_baseline = _RF_BASELINE + _ERP
    r_current  = rf_current   + _ERP

    # Evitar división por cero o valores degenerados si Rf muy cercano a g
    if (r_baseline - g) <= 0.001 or (r_current - g) <= 0.001:
        return profile, None

    factor_raw = (r_baseline - g) / (r_current - g)
    factor     = max(_ADJ_MIN, min(_ADJ_MAX, factor_raw))

    adjusted = dict(profile)
    adjusted["pe_fair"]        = round(profile["pe_fair"] * factor, 1)
    adjusted["pe_high"]        = round(profile["pe_high"] * factor, 1)
    adjusted["ev_ebitda_fair"] = round(profile["ev_ebitda_fair"] * factor, 1)
    # peg_ok se mantiene sin cambios deliberadamente

    info = {
        "rf_current":  rf_current,
        "rf_baseline": _RF_BASELINE,
        "g":           g,
        "factor":      factor,
        "factor_raw":  factor_raw,
        "capped":      abs(factor - factor_raw) > 0.001,
        "pe_fair_original": profile["pe_fair"],
        "ev_ebitda_fair_original": profile["ev_ebitda_fair"],
    }
    return adjusted, info


# ─── Motor de valoración por sector ──────────────────────────────────────────

def _calc_fair_value(y: dict, profile: dict) -> tuple[float | None, list[str], tuple[float, float] | None]:
    """
    Calcula el valor objetivo usando los métodos relevantes para el sector.
    Devuelve (fair_value, lista_de_métodos_usados, rango_min_max).

    PONDERACIÓN DEL CONSENSO DE ANALISTAS: si ≥10 analistas cubren el valor,
    el consenso se cuenta DOS VECES en el promedio (en vez de una) porque
    incorpora información (guidance de la empresa, modelos propios de cada
    analista, conversaciones con el management) que los múltiplos estáticos
    no capturan. Con <10 analistas el consenso es menos fiable estadísticamente
    y se mantiene con peso normal (1×).

    RANGO DE CONFIANZA: además de la media, se devuelve (min, max) de los
    métodos individuales sin ponderar, para mostrar la dispersión real entre
    métodos — un rango estrecho indica más consenso entre metodologías, uno
    amplio indica más incertidumbre real en la valoración.

    FALLBACK HYPER-GROWTH: si la empresa tiene EPS negativo o nulo (PER/PEG
    no aplicables) y el crecimiento de ingresos YoY supera el 25%, se sustituye
    la valoración por múltiplos de beneficio por EV/Sales — comparando el
    múltiplo EV/Sales actual de la empresa contra el EV/Sales "justo" del
    sector. Es el método estándar para valorar empresas pre-rentabilidad
    con alto crecimiento (ej. SaaS en expansión, biotecnológicas en fase
    de escalado comercial).
    """
    price       = y.get("price") or 0
    eps_fwd     = y.get("eps_forward")
    eps_ttm     = y.get("eps_ttm")
    pe_forward  = y.get("pe_forward")
    peg         = y.get("peg_ratio")
    ev_ebitda   = y.get("ev_ebitda")
    ebitda      = y.get("ebitda")
    market_cap  = y.get("market_cap") or 1
    ent_value   = y.get("enterprise_value") or 1
    fcf         = y.get("free_cash_flow") or 0
    price_book  = y.get("price_book")
    roe         = y.get("roe") or 0
    earn_growth = (y.get("earnings_yoy") or 0) / 100
    target_mean = y.get("target_mean")
    ev_revenue  = y.get("ev_revenue")
    rev_yoy     = y.get("revenue_yoy")
    analyst_n   = y.get("analyst_count") or 0

    methods_used = []
    targets      = []   # cada método individual, sin ponderar (para el rango)
    weighted     = []   # valores efectivamente promediados (con ponderación)

    def _add_consensus():
        """Añade el consenso de analistas con ponderación según cobertura."""
        if target_mean and target_mean > 0:
            targets.append(target_mean)
            if analyst_n >= 10:
                weighted.append(target_mean)
                weighted.append(target_mean)   # peso doble
                methods_used.append(
                    f"Consenso analistas ×2 peso — {analyst_n} analistas ⩾10 "
                    f"(precio objetivo medio) → {target_mean:,.2f}"
                )
            else:
                weighted.append(target_mean)
                methods_used.append(
                    f"Consenso analistas — {analyst_n} analistas "
                    f"(precio objetivo medio) → {target_mean:,.2f}"
                )

    # ── FALLBACK HYPER-GROWTH: EV/Sales cuando PER/PEG no aplican ──────────
    is_eps_negative = (eps_fwd is None or eps_fwd <= 0) and (eps_ttm is None or eps_ttm <= 0)
    is_hyper_growth = is_eps_negative and rev_yoy is not None and rev_yoy > 25

    if is_hyper_growth and ev_revenue and ev_revenue > 0:
        ev_sales_fair = profile.get("ev_sales_fair", 3)
        ratio = ev_sales_fair / ev_revenue
        val   = price * ratio
        if val > 0:
            targets.append(val)
            weighted.append(val)
            methods_used.append(
                f"EV/Sales hyper-growth ( {price:,.2f} (Precio) × [ {ev_sales_fair:.1f} (EV/Sales sector) "
                f"÷ {ev_revenue:.1f} (EV/Sales actual) ] , Rev YoY {rev_yoy:.0f}% > 25% ) → {val:,.2f}"
            )
        # En modo hyper-growth NO se usan PER/PEG aunque el sector los liste,
        # porque el EPS negativo los invalida por definición.
        _add_consensus()
        if not weighted:
            return None, [], None
        fair_value = sum(weighted) / len(weighted)
        rng = (min(targets), max(targets)) if len(targets) >= 2 else None
        return fair_value, methods_used, rng

    for method in profile["methods"]:

        # PER × EPS con PE justo del sector
        if method == "per" and eps_fwd and eps_fwd > 0:
            fair_pe = profile["pe_fair"]
            prima_txt = ""
            # Si la empresa crece más que la media del sector, le damos un 10% de prima
            if earn_growth > 0.20:
                fair_pe_base = fair_pe
                fair_pe *= 1.10
                prima_txt = f" [{fair_pe_base:.0f}×1.10 prima por crecimiento >20%]"
            val = fair_pe * eps_fwd
            if val > 0:
                targets.append(val)
                weighted.append(val)
                methods_used.append(
                    f"PER sectorial ( {fair_pe:.1f}{prima_txt} × {eps_fwd:,.2f} (EPS Forward) ) → {val:,.2f}"
                )

        # PEG: precio justo = EPS × PEG_sector × tasa_crecimiento × 100
        elif method == "peg" and peg and eps_fwd and eps_fwd > 0 and earn_growth > 0:
            # PEG justo del sector como referencia
            growth_pct = earn_growth * 100
            val = eps_fwd * profile["peg_ok"] * growth_pct
            if val > 0:
                targets.append(val)
                weighted.append(val)
                methods_used.append(
                    f"PEG sectorial ( {eps_fwd:,.2f} (EPS Forward) × {profile['peg_ok']:.1f} (PEG sector) "
                    f"× {growth_pct:.1f} (Crec. beneficios %) ) → {val:,.2f}"
                )

        # EV/EBITDA sectorial
        elif method == "ev_ebitda" and ev_ebitda and ebitda and ebitda > 0:
            fair_ev_ebitda = profile["ev_ebitda_fair"]
            # Valor implícito de mercado ajustando el múltiplo justo vs el actual
            ratio = fair_ev_ebitda / ev_ebitda if ev_ebitda else 1
            val   = price * ratio
            if val > 0:
                targets.append(val)
                weighted.append(val)
                methods_used.append(
                    f"EV/EBITDA sectorial ( {price:,.2f} (Precio) × [ {fair_ev_ebitda:.1f} (EV/EBITDA sector) "
                    f"÷ {ev_ebitda:.1f} (EV/EBITDA actual) ] ) → {val:,.2f}"
                )

        # FCF Yield (DCF simplificado): precio justo = FCF / yield_esperado
        elif method == "dcf_lite" and fcf > 0 and market_cap > 0:
            fcf_yield_target = 0.04  # rentabilidad FCF esperada del 4%
            shares = market_cap / price if price else 1
            fcf_per_share = fcf / shares
            val = fcf_per_share / fcf_yield_target
            if val > 0:
                targets.append(val)
                weighted.append(val)
                methods_used.append(
                    f"FCF Yield ( {fcf_per_share:,.2f} (FCF/acción) ÷ {fcf_yield_target*100:.0f}% "
                    f"(yield exigido) ) → {val:,.2f}"
                )

        # Price/Book para financieras: P/B justo = ROE / coste_capital
        elif method == "nav" and price_book and roe > 0:
            cost_of_equity = 0.10  # WACC simplificado 10%
            fair_pb = roe / cost_of_equity
            val = price * (fair_pb / price_book) if price_book else price
            if val > 0:
                targets.append(val)
                weighted.append(val)
                methods_used.append(
                    f"Price/Book justo ( {price:,.2f} (Precio) × [ {fair_pb:.2f} (ROE {roe*100:.1f}% ÷ Ke {cost_of_equity*100:.0f}%) "
                    f"÷ {price_book:.2f} (P/B actual) ] ) → {val:,.2f}"
                )

    _add_consensus()

    if not weighted:
        return None, [], None

    fair_value = sum(weighted) / len(weighted)
    rng = (min(targets), max(targets)) if len(targets) >= 2 else None
    return fair_value, methods_used, rng


# ─── Salud fundamental ajustada al sector ────────────────────────────────────

def _calc_growth_stability(quarters: list) -> tuple[float, str]:
    """
    Calcula un multiplicador de estabilidad (0.65-1.0) basado en la varianza
    de las tasas de crecimiento QoQ de los últimos trimestres disponibles.
    Un crecimiento estable (baja dispersión) mantiene el multiplicador en 1.0;
    un crecimiento errático (alta dispersión) lo reduce, porque es menos
    predecible y más arriesgado aunque el promedio sea igual de bueno que
    el de una empresa con crecimiento constante.
    Devuelve (multiplicador, descripción_corta).
    """
    if not quarters or len(quarters) < 3:
        return 1.0, "datos insuficientes"

    sorted_q = sorted(quarters, key=lambda q: q.get("date", ""))
    values = [q.get("value") for q in sorted_q if q.get("value") is not None]
    if len(values) < 3:
        return 1.0, "datos insuficientes"

    growth_rates = []
    for i in range(1, len(values)):
        prev, curr = values[i-1], values[i]
        if prev and prev != 0:
            growth_rates.append((curr - prev) / abs(prev) * 100)

    if len(growth_rates) < 2:
        return 1.0, "datos insuficientes"

    mean_g   = sum(growth_rates) / len(growth_rates)
    variance = sum((g - mean_g) ** 2 for g in growth_rates) / len(growth_rates)
    stddev   = variance ** 0.5

    if stddev <= 10:
        return 1.0, f"estable (σ={stddev:.0f}pp)"
    elif stddev <= 25:
        return 0.85, f"algo variable (σ={stddev:.0f}pp)"
    else:
        return 0.65, f"errático (σ={stddev:.0f}pp)"


def _calc_health_score(y: dict, profile: dict) -> tuple[int, list[str], list[str]]:
    """
    Calcula la salud fundamental (0-100) con umbrales del sector.
    Devuelve (score, breakdown, missing_fields) — missing_fields lista los
    campos que no tenían dato real (None) y se excluyeron del cálculo, para
    no penalizar falsamente una métrica desconocida como si fuera "0" o "mala".
    """
    score    = 0
    breakdown = []
    missing_fields = []

    profit_m_raw   = y.get("profit_margin")
    roe_raw        = y.get("roe")
    rev_yoy_raw    = y.get("revenue_yoy")
    earn_yoy_raw   = y.get("earnings_yoy")
    peg            = y.get("peg_ratio")
    short_r        = y.get("short_ratio") or 0
    debt_eq_raw    = y.get("debt_equity")
    curr_ratio_raw = y.get("current_ratio")
    fcf_raw        = y.get("free_cash_flow")
    ni_recent      = y.get("ni_year_cur")   # beneficio neto anual más reciente

    if profit_m_raw is None:   missing_fields.append("Margen neto")
    if roe_raw is None:        missing_fields.append("ROE")
    if rev_yoy_raw is None:    missing_fields.append("Crecimiento ingresos")
    if earn_yoy_raw is None:   missing_fields.append("Crecimiento beneficios")
    if debt_eq_raw is None:    missing_fields.append("Deuda/Equity")
    if curr_ratio_raw is None: missing_fields.append("Current Ratio")
    if fcf_raw is None:        missing_fields.append("Free Cash Flow")

    profit_m   = profit_m_raw   if profit_m_raw   is not None else 0
    roe        = roe_raw        if roe_raw        is not None else 0
    rev_yoy    = rev_yoy_raw    if rev_yoy_raw    is not None else 0
    earn_yoy   = earn_yoy_raw   if earn_yoy_raw   is not None else 0
    debt_eq    = debt_eq_raw    if debt_eq_raw    is not None else 0
    curr_ratio = curr_ratio_raw if curr_ratio_raw is not None else 0
    fcf        = fcf_raw        if fcf_raw        is not None else 0

    margin_ok = profile["margin_ok"]
    roe_ok    = profile["roe_ok"]
    peg_ok    = profile["peg_ok"]

    # Margen neto vs benchmark sector (0-20 pts)
    if profit_m >= margin_ok * 2:    pts = 20
    elif profit_m >= margin_ok:      pts = 14
    elif profit_m >= margin_ok * 0.5: pts = 7
    elif profit_m > 0:               pts = 3
    else:                            pts = 0
    score += pts
    breakdown.append(f"Margen neto {profit_m*100:.1f}% (ref. sector >{margin_ok*100:.0f}%): +{pts}/20")

    # ROE vs benchmark sector (0-15 pts)
    if roe >= roe_ok * 2:    pts = 15
    elif roe >= roe_ok:      pts = 11
    elif roe >= roe_ok * 0.5: pts = 5
    elif roe > 0:             pts = 2
    else:                     pts = 0
    score += pts
    breakdown.append(f"ROE {roe*100:.1f}% (ref. sector >{roe_ok*100:.0f}%): +{pts}/15")

    # Crecimiento ingresos ponderado por estabilidad (0-15 pts, antes 0-20)
    # Una empresa con crecimiento errático es más arriesgada que una con
    # crecimiento constante, aunque el promedio YoY sea idéntico.
    rev_quarters = y.get("ttm_quarters", [])
    rev_stab_mult, rev_stab_desc = _calc_growth_stability(rev_quarters)
    if rev_yoy >= 30:    pts_base = 15
    elif rev_yoy >= 15:  pts_base = 11
    elif rev_yoy >= 8:   pts_base = 7
    elif rev_yoy >= 3:   pts_base = 4
    elif rev_yoy >= 0:   pts_base = 1
    else:                pts_base = 0
    pts = round(pts_base * rev_stab_mult)
    score += pts
    breakdown.append(
        f"Crec. ingresos {rev_yoy:.1f}% × estabilidad {rev_stab_desc} "
        f"(×{rev_stab_mult:.2f}): +{pts}/15"
    )

    # Crecimiento beneficios ponderado por estabilidad (0-15 pts, antes 0-20)
    ni_quarters = y.get("net_income_q", [])
    earn_stab_mult, earn_stab_desc = _calc_growth_stability(ni_quarters)
    if earn_yoy >= 40:   pts_base = 15
    elif earn_yoy >= 20: pts_base = 11
    elif earn_yoy >= 10: pts_base = 7
    elif earn_yoy >= 0:  pts_base = 4
    else:                pts_base = 0
    pts = round(pts_base * earn_stab_mult)
    score += pts
    breakdown.append(
        f"Crec. beneficios {earn_yoy:.1f}% × estabilidad {earn_stab_desc} "
        f"(×{earn_stab_mult:.2f}): +{pts}/15"
    )

    # PEG vs benchmark sector (0-15 pts)
    if peg:
        if peg <= peg_ok * 0.5:   pts = 15
        elif peg <= peg_ok * 0.75: pts = 11
        elif peg <= peg_ok:        pts = 7
        elif peg <= peg_ok * 1.5:  pts = 3
        else:                      pts = 0
        score += pts
        breakdown.append(f"PEG {peg:.2f} (ref. sector <{peg_ok}): +{pts}/15")

    # Balance sano (0-10 pts)
    b_pts = 0
    if fcf > 0:           b_pts += 4
    if curr_ratio >= 1.5: b_pts += 3
    elif curr_ratio >= 1: b_pts += 1
    if debt_eq < 50:      b_pts += 3
    elif debt_eq < 100:   b_pts += 1
    score += b_pts
    breakdown.append(f"Balance (FCF/Liquidez/Deuda): +{b_pts}/10")

    # Calidad del beneficio: FCF / Beneficio neto anual (0-10 pts, NUEVO)
    # Un ratio alto indica que el beneficio contable se traduce en caja real;
    # un ratio bajo o negativo sugiere ajustes contables que inflan el
    # beneficio sin respaldo de generación de caja efectiva.
    fcf_quality = None
    if fcf_raw is not None and ni_recent and ni_recent > 0:
        fcf_quality = fcf_raw / ni_recent
        if fcf_quality >= 1.0:    q_pts = 10
        elif fcf_quality >= 0.9:  q_pts = 8
        elif fcf_quality >= 0.5:  q_pts = 5
        elif fcf_quality >= 0:    q_pts = 2
        else:                     q_pts = 0
        score += q_pts
        tip_fcf_health = (
            "FCF / Beneficio neto anual. Mide si el beneficio contable se traduce en caja real. "
            "≥1.0× = excelente (10 pts) · 0.9-1.0× = muy buena (8 pts) · 0.5-0.9× = moderada (5 pts) · "
            "0-0.5× = baja, posibles ajustes contables (2 pts) · negativo = alerta, consume caja (0 pts)."
        )
        tip_fcf_html = (
            f'<span title="{tip_fcf_health}" style="margin-left:0.3rem;cursor:help;'
            f'font-size:0.6rem;color:#94a3b8;border:1px solid #cbd5e1;'
            f'border-radius:50%;padding:0 3px;font-family:monospace;">?</span>'
        )
        breakdown.append(f"Calidad beneficio FCF/NI {fcf_quality:.2f}×{tip_fcf_html}: +{q_pts}/10")
    else:
        missing_fields.append("Calidad del beneficio (FCF/NI)")

    score = min(100, score)
    if missing_fields:
        breakdown.append(f"⚠ Datos no disponibles (excluidos del cálculo, no penalizados): {', '.join(missing_fields)}")
    return score, breakdown, missing_fields


# ─── Evaluación final ─────────────────────────────────────────────────────────

def _evaluate(y: dict) -> dict:
    """Diagnóstico completo ajustado al sector y a los tipos de interés actuales."""

    price       = y.get("price") or 0
    sector_raw  = y.get("sector", "")
    profile_static, sector_label = _get_sector_profile(sector_raw)

    # Ajuste dinámico de benchmarks por tipos de interés actuales (cacheado
    # en sesión para no consultar ^TNX en cada re-render de la página)
    if "_rf_current_cache" not in st.session_state:
        st.session_state["_rf_current_cache"] = fetch_risk_free_rate()
    rf_current = st.session_state["_rf_current_cache"]
    profile, rate_adjustment = _adjust_sector_profile(profile_static, rf_current)

    short_ratio = y.get("short_ratio") or 0
    week52_high = y.get("52w_high") or price
    week52_low  = y.get("52w_low") or price
    pe_forward  = y.get("pe_forward")
    pe_trailing = y.get("pe_trailing")
    price_book  = y.get("price_book")

    # ── Salud fundamental ────────────────────────────────────────────────
    health_score, health_breakdown, health_missing = _calc_health_score(y, profile)

    # ── Valor objetivo ───────────────────────────────────────────────────
    fair_value, methods_used, targets_range = _calc_fair_value(y, profile)

    # Flag informativo: ¿se usó el fallback hyper-growth (EV/Sales)?
    is_hyper_growth = any("hyper-growth" in m for m in methods_used)

    # ── Prima/descuento vs histórico 52W ─────────────────────────────────
    mid_52  = (week52_high + week52_low) / 2 if week52_high and week52_low else None
    vs_hist = ((price - mid_52) / mid_52 * 100) if mid_52 else None

    # ── Upside ───────────────────────────────────────────────────────────
    upside = ((fair_value - price) / price * 100) if fair_value else None

    # ── Diagnóstico — 7 niveles ───────────────────────────────────────────
    # Los umbrales se suavizan/endurecen según el perfil de valoración del sector
    pe_ref  = profile["pe_fair"]
    pe_high = profile["pe_high"]

    if upside is None:
        diag       = "SIN DATOS SUFICIENTES"
        diag_color = "#64748b"
        diag_icon  = "—"
    elif upside >= 30:
        diag       = "MUY INFRAVALORADA — Oportunidad excepcional"
        diag_color = "#059669"
        diag_icon  = "▲▲"
    elif upside >= 12:
        diag       = "INFRAVALORADA — Potencial alcista significativo"
        diag_color = "#16a34a"
        diag_icon  = "▲"
    elif upside >= 3:
        diag       = "LIGERAMENTE INFRAVALORADA — Entrada atractiva"
        diag_color = "#65a30d"
        diag_icon  = "↑"
    elif upside >= -3:
        diag       = "PRECIO JUSTO — En rango de valor razonable"
        diag_color = "#d97706"
        diag_icon  = "="
    elif upside >= -15:
        diag       = "EN OBSERVACIÓN — Precio por encima del valor objetivo"
        diag_color = "#ea580c"
        diag_icon  = "↓"
    elif upside >= -30:
        diag       = "SOBREVALORADA — Riesgo de corrección moderada"
        diag_color = "#dc2626"
        diag_icon  = "▼"
    else:
        diag       = "MUY SOBREVALORADA — Riesgo de corrección severa"
        diag_color = "#dc2626"
        diag_icon  = "▼▼"

    # ── Valoración relativa al sector ─────────────────────────────────────
    # Compara los múltiplos actuales contra los benchmarks del sector
    vs_sector_items = []

    if pe_forward:
        if pe_forward < pe_ref * 0.7:
            vs_sector_items.append(f"PER Forward {pe_forward:.1f}× muy barato vs sector ({pe_ref}×)")
        elif pe_forward < pe_ref:
            vs_sector_items.append(f"PER Forward {pe_forward:.1f}× barato vs sector ({pe_ref}×)")
        elif pe_forward < pe_high:
            vs_sector_items.append(f"PER Forward {pe_forward:.1f}× en rango normal del sector")
        else:
            vs_sector_items.append(f"PER Forward {pe_forward:.1f}× caro vs sector (ref. {pe_ref}×, techo {pe_high}×)")

    peg = y.get("peg_ratio")
    if peg:
        peg_ref = profile["peg_ok"]
        if peg < peg_ref * 0.6:
            vs_sector_items.append(f"PEG {peg:.2f} muy atractivo (ref. sector <{peg_ref})")
        elif peg < peg_ref:
            vs_sector_items.append(f"PEG {peg:.2f} atractivo (ref. sector <{peg_ref})")
        else:
            vs_sector_items.append(f"PEG {peg:.2f} por encima del umbral del sector ({peg_ref})")

    ev_ebitda = y.get("ev_ebitda")
    if ev_ebitda:
        ev_ref = profile["ev_ebitda_fair"]
        if ev_ebitda < ev_ref * 0.75:
            vs_sector_items.append(f"EV/EBITDA {ev_ebitda:.1f}× muy barato vs sector ({ev_ref}×)")
        elif ev_ebitda < ev_ref:
            vs_sector_items.append(f"EV/EBITDA {ev_ebitda:.1f}× razonable vs sector ({ev_ref}×)")
        else:
            vs_sector_items.append(f"EV/EBITDA {ev_ebitda:.1f}× elevado vs sector (ref. {ev_ref}×)")

    if "nav" in profile["methods"] and price_book:
        if price_book < 1.0:
            vs_sector_items.append(f"Price/Book {price_book:.2f}× por debajo de valor contable (oportunidad)")
        elif price_book < 1.5:
            vs_sector_items.append(f"Price/Book {price_book:.2f}× razonable para sector financiero")
        else:
            vs_sector_items.append(f"Price/Book {price_book:.2f}× elevado para sector financiero")

    vs_sector_str = " · ".join(vs_sector_items) if vs_sector_items else "Datos insuficientes para comparar"

    # ── Riesgo técnico ────────────────────────────────────────────────────
    risk = 0
    if short_ratio:
        risk += min(short_ratio * 1.5, 6)
    if week52_high and price:
        dist_high = (week52_high - price) / week52_high * 100
        risk += min(dist_high * 0.08, 5)
    risk = round(min(risk, 15), 1)

    return {
        "health_score":    health_score,
        "health_breakdown": health_breakdown,
        "fair_value":      fair_value,
        "methods_used":    methods_used,
        "upside":          upside,
        "diag":            diag,
        "diag_color":      diag_color,
        "diag_icon":       diag_icon,
        "vs_hist":         vs_hist,
        "vs_sector":       vs_sector_str,
        "risk":            risk,
        "sector_label":    sector_label,
        "sector_nota":     profile["nota"],
        "pe_ref":          pe_ref,
        "pe_high":         pe_high,
        "peg_ok":          profile["peg_ok"],
        "ev_ebitda_fair":  profile["ev_ebitda_fair"],
        "is_hyper_growth": is_hyper_growth,
        "health_missing":  health_missing,
        "targets_range":   targets_range,
        "rate_adjustment": rate_adjustment,
    }




# ─── Render principal ─────────────────────────────────────────────────────────

def render_report(ticker, company_name, y: dict,
                  fx_rate: float | None = None, tech: dict | None = None,
                  fx_meta: dict | None = None):

    st.markdown("---")

    currency_y = y.get("currency", "USD")
    meta_y     = y.get("meta", {}) or {}
    meta_tech  = {}
    if tech and not tech.get("error"):
        meta_tech = {k: tech.get(k) for k in ("last_date","days_old","freshness","trust","source")}

    from analysis import get_sector_benchmarks
    sbm = get_sector_benchmarks(y.get("sector",""))
    # ── helper: fila con benchmark de sector ─────────────────────────────
    def _kv_bench(label, value, bench_val, bench_label, color_class="row-val"):
        tip      = TOOLTIPS.get(label, "")
        tip_html = ""
        if tip:
            tip_html = (
                '<span class="tooltip-wrap" style="margin-left:0.3rem;position:relative;cursor:help;">'
                '<span style="font-size:0.65rem;color:#0284c7;border:1px solid #0284c7;'
                'border-radius:50%;padding:0 3px;font-family:\'IBM Plex Mono\',monospace;">?</span>'
                f'<span class="tooltip-box">{tip}</span></span>'
            )
        bench_html = ""
        if bench_val is not None:
            bench_html = (
                f'<span style="font-size:0.7rem;color:#94a3b8;margin-left:0.4rem;'
                f'font-family:\'IBM Plex Mono\',monospace;">sect:{bench_label}</span>'
            )
        return (
            '<div class="row-kv">'
            f'<span class="row-key">{label}{tip_html}</span>'
            f'<span class="{color_class}">{value}{bench_html}</span>'
            '</div>'
        )

    # ════════════════════════════════════════════════════════════════════
    # A · FIABILIDAD Y FRESCURA DE DATOS
    # ════════════════════════════════════════════════════════════════════
    _section("FIABILIDAD Y FRESCURA DE DATOS")

    pf = meta_y.get("price_freshness", {}) or {}
    ff = meta_y.get("fund_freshness",  {}) or {}
    tf = meta_tech.get("freshness",    {}) or {}
    xf = (fx_meta.get("freshness",     {}) or {}) if fx_meta else {}

    # Alertas de desfase
    alert_rows = ""
    for name, f in [("Precio de mercado", pf), ("Fundamentales", ff), ("Técnico RSI/MMs", tf)]:
        if f.get("ok") is False:
            col = f.get("color","#d97706")
            alert_rows += (
                f'<div style="background:#fffbeb;border:1px solid {col};border-left:4px solid {col};'
                f'border-radius:6px;padding:0.5rem 0.8rem;margin-bottom:0.4rem;font-size:0.8rem;">'
                f'<span style="color:{col};font-weight:700;">⚠ {name.upper()}</span>'
                f'<span style="color:#64748b;margin-left:0.5rem;">{f.get("label","")}</span>'
                f'<div style="color:#64748b;font-size:0.71rem;margin-top:0.15rem;">'
                f'Verifica este dato en la fuente original antes de operar.</div></div>'
            )
    if alert_rows:
        st.markdown(alert_rows, unsafe_allow_html=True)

    def _source_row(dato, trust, fecha, fresh):
        t_col  = trust.get("color","#64748b")
        t_icon = trust.get("icon","")
        t_lbl  = trust.get("label","")
        f_col  = fresh.get("color","#64748b") if fresh else "#64748b"
        f_icon = fresh.get("icon","") if fresh else ""
        f_lbl  = fresh.get("label","") if fresh else ""
        return (
            '<div style="display:grid;grid-template-columns:2fr 1fr 2fr;gap:0.4rem;'
            'padding:0.35rem 0;border-bottom:1px solid #eef1f5;align-items:center;">'
            f'<span style="font-size:0.8rem;color:#1e293b;">{dato}</span>'
            f'<span style="font-size:0.72rem;color:{t_col};font-family:\'IBM Plex Mono\',monospace;">{t_icon} {t_lbl}</span>'
            f'<span style="font-size:0.73rem;color:{f_col};">{f_icon} {f_lbl} '
            f'<span style="color:#64748b;font-size:0.68rem;">({fecha})</span></span>'
            '</div>'
        )

    TRUST_Y    = {"icon":"🟡","label":"Yahoo Finance", "color":"#d97706"}
    TRUST_CALC = {"icon":"🟠","label":"Calculado app", "color":"#ea580c"}
    TRUST_ESTI = {"icon":"🔴","label":"Estimado",      "color":"#dc2626"}

    rows = (
        _source_row("Precio actual",               TRUST_Y,    meta_y.get("price_date","N/A"),    pf)
      + _source_row("Fundamentales (ratios/margen)",TRUST_Y,    meta_y.get("earnings_date","N/A"), ff)
      + _source_row("Consenso analistas",           TRUST_ESTI, "Sin fecha exacta en Yahoo",       {})
      + _source_row("Crecimiento YoY / TTM",        TRUST_CALC, meta_y.get("earnings_date","N/A"), {})
      + (_source_row("Técnico — RSI, MM50/200",     TRUST_Y,    meta_tech.get("last_date","N/A"),  tf) if meta_tech else "")
      + (_source_row("Tipo de cambio USD/EUR",       TRUST_Y,    fx_meta.get("market_time","N/A") if fx_meta else "N/A", xf) if fx_meta else "")
    )
    hdr = (
        '<div style="display:grid;grid-template-columns:2fr 1fr 2fr;gap:0.4rem;'
        'padding:0.2rem 0;border-bottom:1px solid #e2e8f0;margin-bottom:0.2rem;">'
        '<span style="font-size:0.66rem;color:#94a3b8;text-transform:uppercase;letter-spacing:0.06em;">Dato</span>'
        '<span style="font-size:0.66rem;color:#94a3b8;text-transform:uppercase;letter-spacing:0.06em;">Fuente</span>'
        '<span style="font-size:0.66rem;color:#94a3b8;text-transform:uppercase;letter-spacing:0.06em;">Última actualización</span>'
        '</div>'
    )
    legend = (
        '<div style="margin-top:0.6rem;font-size:0.71rem;color:#64748b;">'
        '🟡 Yahoo Finance &nbsp;·&nbsp; 🟠 Calculado por la app &nbsp;·&nbsp; 🔴 Estimación analistas</div>'
        '<div style="margin-top:0.4rem;font-size:0.7rem;color:#94a3b8;line-height:1.55;">'
        '⚠ Yahoo Finance agrega datos de múltiples proveedores. Para cifras críticas, '
        'verifica directamente en los informes trimestrales (10-K/10-Q en SEC EDGAR).</div>'
    )
    st.markdown(
        f'<div class="metric-card" style="border-left:3px solid #cbd5e1;">'
        f'<div style="font-size:0.69rem;color:#94a3b8;margin-bottom:0.5rem;">'
        f'Consulta: <span style="color:#64748b;">{meta_y.get("fetch_time","N/A")}</span></div>'
        f'{hdr}{rows}{legend}</div>',
        unsafe_allow_html=True
    )

    # ════════════════════════════════════════════════════════════════════
    # B · DESCRIPCIÓN DE LA EMPRESA
    # ════════════════════════════════════════════════════════════════════
    with st.spinner("Cargando descripción, noticias y análisis de resultados…"):
        company_info = fetch_company_description(ticker)
        news_items   = fetch_recent_news(ticker)
        ea           = fetch_earnings_analysis(ticker, y)

    render_company_description(company_info, company_name)

    # ════════════════════════════════════════════════════════════════════
    # C · ÚLTIMAS NOTICIAS Y ANUNCIOS
    # ════════════════════════════════════════════════════════════════════
    render_news(news_items)

    # ════════════════════════════════════════════════════════════════════
    # E–H, J · MÉTRICAS EN DOS COLUMNAS
    # ════════════════════════════════════════════════════════════════════
    col_a, col_b = st.columns(2)

    with col_a:
        # E · Mercado y consenso
        _section("MERCADO Y CONSENSO &nbsp;<span style='font-size:0.7rem;'>🟡 Yahoo · 🔴 Consenso analistas</span>")
        rec = y.get("recommendation","N/A")
        target_mean_val = y.get("target_mean")
        price_now_val   = y.get("price")
        target_upside_html = _fmt_price(target_mean_val, currency_y, fx_rate)
        if target_mean_val and price_now_val:
            upside_analysts = (target_mean_val - price_now_val) / price_now_val * 100
            up_color = "#059669" if upside_analysts >= 0 else "#dc2626"
            target_upside_html += (
                f' <span style="color:{up_color};font-weight:700;font-size:0.85em;">'
                f'({upside_analysts:+.1f}%)</span>'
            )
        html  = _kv("Precio Actual",      _fmt_price(y.get("price"), currency_y, fx_rate))
        html += _kv("Objetivo Analistas", target_upside_html)
        html += _kv("Rango",
            f"{_fmt_price(y.get('target_low'),currency_y,fx_rate)} – {_fmt_price(y.get('target_high'),currency_y,fx_rate)}")
        html += _kv("Recomendación", _badge(rec))
        html += _kv("Nº Analistas", str(y.get("analyst_count") or "N/A"))
        st.markdown(f'<div class="metric-card">{html}</div>', unsafe_allow_html=True)

        # G · Rentabilidad
        _section("RENTABILIDAD &nbsp;<span style='font-size:0.7rem;'>🟡 Yahoo &nbsp;·&nbsp; <span style=\"color:#94a3b8;\">sect: media sector</span></span>")
        html  = _kv_bench("Profit Margin",
            _fmt_num((y.get("profit_margin") or 0)*100,2,suffix="%"),
            sbm.get("profit_m"), f"{sbm.get('profit_m')}%", _color_pct(y.get("profit_margin")))
        html += _kv_bench("Operating Margin",
            _fmt_num((y.get("operating_margin") or 0)*100,2,suffix="%"),
            sbm.get("op_m"), f"{sbm.get('op_m')}%", _color_pct(y.get("operating_margin")))
        html += _kv("EBITDA Margin",
            _fmt_num((y.get("ebitda_margin") or 0)*100,2,suffix="%"), _color_pct(y.get("ebitda_margin")))
        html += _kv_bench("ROE",
            _fmt_num((y.get("roe") or 0)*100,2,suffix="%"),
            sbm.get("roe"), f"{sbm.get('roe')}%", _color_pct(y.get("roe")))
        html += _kv("ROA",
            _fmt_num((y.get("roa") or 0)*100,2,suffix="%"), _color_pct(y.get("roa")))
        st.markdown(f'<div class="metric-card">{html}</div>', unsafe_allow_html=True)

    with col_b:
        # F · Valoración
        _section("VALORACIÓN &nbsp;<span style='font-size:0.7rem;'>🟡 Yahoo · 🔴 Forward estimado &nbsp;·&nbsp; <span style=\"color:#94a3b8;\">sect: media sector</span></span>")
        html  = _kv("PER Trailing", _fmt_num(y.get("pe_trailing"),2))
        html += _kv_bench("PER Forward", _fmt_num(y.get("pe_forward"),2),
            sbm.get("pe_fwd"), f"{sbm.get('pe_fwd')}x")
        html += _kv_bench("PEG Ratio",   _fmt_num(y.get("peg_ratio"),4),
            sbm.get("peg"),    f"{sbm.get('peg')}")
        html += _kv("Price/Sales",  _fmt_num(y.get("price_sales"),4))
        html += _kv("Price/Book",   _fmt_num(y.get("price_book"),4))
        html += _kv("EV/Revenue",   _fmt_num(y.get("ev_revenue"),4))
        html += _kv_bench("EV/EBITDA", _fmt_num(y.get("ev_ebitda"),4),
            sbm.get("ev_ebitda"), f"{sbm.get('ev_ebitda')}x")
        html += _kv("Market Cap",   _fmt_big(y.get("market_cap"),"$",fx_rate))
        st.markdown(f'<div class="metric-card">{html}</div>', unsafe_allow_html=True)

        # H · Balance y caja
        _section("BALANCE Y CAJA &nbsp;<span style='font-size:0.7rem;'>🟡 Yahoo Finance</span>")
        html  = _kv("Total Cash",          _fmt_big(y.get("total_cash"),       "$", fx_rate))
        html += _kv("Total Debt",          _fmt_big(y.get("total_debt"),       "$", fx_rate))
        html += _kv("Debt/Equity",         _fmt_num(y.get("debt_equity"),2))
        html += _kv("Current Ratio",       _fmt_num(y.get("current_ratio"),2))
        html += _kv("Free Cash Flow",      _fmt_big(y.get("free_cash_flow"),   "$", fx_rate))
        html += _kv("Operating Cash Flow", _fmt_big(y.get("operating_cf"),     "$", fx_rate))
        st.markdown(f'<div class="metric-card">{html}</div>', unsafe_allow_html=True)

        # J · Dividendos y otros
        _section("DIVIDENDOS Y OTROS &nbsp;<span style='font-size:0.7rem;'>🟡 Yahoo Finance</span>")
        dy   = y.get("dividend_yield")
        html  = _kv("Dividend Yield",
            _fmt_num((dy or 0)*100,2,suffix="%") if dy else "N/A")
        html += _kv("Dividend Rate",
            _fmt_price(y.get("dividend_rate"),currency_y,fx_rate) if y.get("dividend_rate") else "N/A")
        html += _kv("Short Ratio",  _fmt_num(y.get("short_ratio"),2))
        html += _kv("Beta",         _fmt_num(y.get("beta"),2))
        html += _kv("52W High",     _fmt_price(y.get("52w_high"), currency_y, fx_rate))
        html += _kv("52W Low",      _fmt_price(y.get("52w_low"),  currency_y, fx_rate))
        st.markdown(f'<div class="metric-card">{html}</div>', unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════
    # D · DESGLOSE TTM — Yahoo Finance
    # ════════════════════════════════════════════════════════════════════
    yahoo_quarters = y.get("ttm_quarters", []) or []
    if yahoo_quarters:
        _section("DESGLOSE TTM &nbsp;<span style='font-size:0.7rem;'>🟡 Yahoo Finance</span>")
        def ttm_fmt(v):
            return _fmt_big(v, "") if v is not None else "—"
        # Ordenar del trimestre más antiguo al más reciente por fecha real
        quarters_sorted = sorted(yahoo_quarters[:4], key=lambda q: q.get("date",""))
        rows_t = ""
        ytot   = 0
        for i, q in enumerate(quarters_sorted):
            val   = q.get("value") or 0
            ytot += val
            rows_t += (
                f'<div class="ttm-row">'
                f'<span>Q{i+1} ({q.get("date","")[:10]})</span>'
                f'<span class="ttm-val">{ttm_fmt(val)}</span></div>'
            )
        rows_t += (
            f'<div class="ttm-row"><span>TOTAL TTM</span>'
            f'<span style="color:#d97706;">{ttm_fmt(ytot)}</span></div>'
        )
        st.markdown(f'<div class="metric-card">{rows_t}</div>', unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════
    # I · CRECIMIENTO YoY
    # ════════════════════════════════════════════════════════════════════
    tip_yoy = (
        "Crecimiento Year-over-Year (YoY) calculado por la app comparando los "
        "DOS ÚLTIMOS AÑOS FISCALES COMPLETOS reportados por la empresa (no trimestres). "
        "Fórmula: (Año actual − Año anterior) / |Año anterior| × 100. "
        "Revenue Growth usa el total de ingresos anuales (Total Revenue) de los estados "
        "financieros anuales de Yahoo Finance. Earnings Growth usa el beneficio neto anual "
        "(Net Income). Ejemplo: si el FY2025 fue $100M y el FY2024 fue $80M, el crecimiento "
        "es +25%. Nota: estos datos pueden no coincidir exactamente con el \"Revenue Growth\" "
        "que muestra Yahoo en su web, ya que Yahoo a veces usa TTM trimestral en su interfaz "
        "mientras que aquí se usan años fiscales completos para mayor estabilidad."
    )
    tip_yoy_safe = tip_yoy.replace('"','&quot;')
    tip_yoy_html = (
        f'<span title="{tip_yoy_safe}" style="margin-left:0.4rem;cursor:help;'
        f'font-size:0.62rem;color:#ea580c;border:1px solid #ea580c;'
        f'border-radius:50%;padding:0 4px;font-family:monospace;'
        f'vertical-align:middle;">?</span>'
    )
    _section(f"CRECIMIENTO YoY &nbsp;<span style='font-size:0.7rem;'>🟠 Calculado por app{tip_yoy_html}</span>")
    rev_yoy  = y.get("revenue_yoy")
    earn_yoy = y.get("earnings_yoy")
    html  = _kv("Revenue Growth",
        _fmt_num(rev_yoy,2,suffix="%") if rev_yoy is not None else "N/A", _color_pct(rev_yoy))
    html += _kv("Earnings Growth",
        _fmt_num(earn_yoy,2,suffix="%") if earn_yoy is not None else "N/A", _color_pct(earn_yoy))
    html += _kv("EPS (TTM)",     _fmt_price(y.get("eps_ttm"),    currency_y, fx_rate))
    html += _kv("EPS (Forward)", _fmt_price(y.get("eps_forward"), currency_y, fx_rate))

    # Desglose con valores absolutos de los dos años fiscales comparados
    rev_cur, rev_prev   = y.get("rev_year_cur"), y.get("rev_year_prev")
    rev_dcur, rev_dprev = y.get("rev_date_cur"), y.get("rev_date_prev")
    ni_cur, ni_prev      = y.get("ni_year_cur"), y.get("ni_year_prev")
    ni_dcur, ni_dprev    = y.get("ni_date_cur"), y.get("ni_date_prev")

    breakdown_html = ""
    if rev_cur is not None or ni_cur is not None:
        def _fy_label(date_str):
            if not date_str: return "Año N/A"
            return f"FY {date_str[:4]}"

        breakdown_html = (
            '<div style="margin-top:0.9rem;font-size:0.7rem;color:#64748b;text-transform:uppercase;'
            'letter-spacing:0.08em;margin-bottom:0.4rem;">Desglose</div>'
            '<table style="width:100%;border-collapse:collapse;">'
            '<thead><tr style="border-bottom:1px solid #e2e8f0;">'
            '<th style="text-align:left;padding:0.25rem 0.5rem;font-size:0.67rem;color:#94a3b8;">Concepto</th>'
        )
        if rev_dprev:
            breakdown_html += f'<th style="text-align:right;padding:0.25rem 0.5rem;font-size:0.67rem;color:#94a3b8;">{_fy_label(rev_dprev)}</th>'
        if rev_dcur:
            breakdown_html += f'<th style="text-align:right;padding:0.25rem 0.5rem;font-size:0.67rem;color:#94a3b8;">{_fy_label(rev_dcur)}</th>'
        breakdown_html += (
            '<th style="text-align:right;padding:0.25rem 0.5rem;font-size:0.67rem;color:#94a3b8;">Variación</th>'
            '</tr></thead><tbody>'
        )

        if rev_cur is not None and rev_prev is not None:
            breakdown_html += (
                '<tr style="border-bottom:1px solid #eef1f5;">'
                '<td style="padding:0.4rem 0.5rem;font-size:0.82rem;color:#1e293b;">Revenue (Ingresos totales)</td>'
                f'<td style="padding:0.4rem 0.5rem;text-align:right;font-family:\'IBM Plex Mono\',monospace;color:#64748b;">{_fmt_big(rev_prev,"$")}</td>'
                f'<td style="padding:0.4rem 0.5rem;text-align:right;font-family:\'IBM Plex Mono\',monospace;color:#0f172a;font-weight:600;">{_fmt_big(rev_cur,"$")}</td>'
                f'<td style="padding:0.4rem 0.5rem;text-align:right;font-family:\'IBM Plex Mono\',monospace;color:{"#059669" if rev_yoy and rev_yoy>=0 else "#dc2626"};font-weight:600;">{rev_yoy:+.1f}%</td>'
                '</tr>'
            )
        if ni_cur is not None and ni_prev is not None:
            breakdown_html += (
                '<tr>'
                '<td style="padding:0.4rem 0.5rem;font-size:0.82rem;color:#1e293b;">Net Income (Beneficio neto)</td>'
                f'<td style="padding:0.4rem 0.5rem;text-align:right;font-family:\'IBM Plex Mono\',monospace;color:#64748b;">{_fmt_big(ni_prev,"$")}</td>'
                f'<td style="padding:0.4rem 0.5rem;text-align:right;font-family:\'IBM Plex Mono\',monospace;color:#0f172a;font-weight:600;">{_fmt_big(ni_cur,"$")}</td>'
                f'<td style="padding:0.4rem 0.5rem;text-align:right;font-family:\'IBM Plex Mono\',monospace;color:{"#059669" if earn_yoy and earn_yoy>=0 else "#dc2626"};font-weight:600;">{earn_yoy:+.1f}%</td>'
                '</tr>'
            )
        breakdown_html += '</tbody></table>'

    st.markdown(f'<div class="metric-card">{html}{breakdown_html}</div>', unsafe_allow_html=True)

    st.markdown(
        '<div style="font-size:0.71rem;color:#64748b;margin-top:-0.4rem;margin-bottom:0.8rem;padding:0 0.2rem;">'
        '📊 Comparación de los dos últimos años fiscales completos (no trimestral) · '
        'Fuente: estados financieros anuales de Yahoo Finance</div>',
        unsafe_allow_html=True
    )

    # ════════════════════════════════════════════════════════════════════
    # TENDENCIA Y EVOLUCIÓN TRIMESTRAL
    # ════════════════════════════════════════════════════════════════════
    trend = calc_trend(y)
    render_trend(trend)

    # ════════════════════════════════════════════════════════════════════
    # CONSULTA DE RESULTADOS
    # ════════════════════════════════════════════════════════════════════
    _section("CONSULTA DE RESULTADOS")
    seeking_alpha_url = f"https://seekingalpha.com/symbol/{ticker}/earnings"
    stocktwits_url     = f"https://stocktwits.com/symbol/{ticker}/earnings"
    st.markdown(
        '<div class="metric-card">'
        '<div style="font-size:0.85rem;color:#94a3b8;line-height:1.7;margin-bottom:0.8rem;">'
        f'Los datos de EPS estimado/reportado y el histórico de sorpresas de resultados '
        f'requieren una fuente de consenso de analistas en tiempo real que no podemos '
        f'garantizar al 100% de fiabilidad desde esta app. Para consultar los últimos '
        f'resultados presentados, los próximos programados y el histórico completo de '
        f'<b style="color:#0f172a;">{ticker}</b>, usa uno de estos enlaces directos:</div>'
        '<div style="display:flex;gap:0.7rem;flex-wrap:wrap;">'
        f'<a href="{seeking_alpha_url}" target="_blank" style="display:inline-block;'
        f'background:#1d4ed8;color:#fff;padding:0.6rem 1.4rem;border-radius:6px;'
        f'text-decoration:none;font-family:\'IBM Plex Mono\',monospace;font-size:0.85rem;'
        f'font-weight:600;letter-spacing:0.03em;">📊 Ver en Seeking Alpha →</a>'
        f'<a href="{stocktwits_url}" target="_blank" style="display:inline-block;'
        f'background:#059669;color:#fff;padding:0.6rem 1.4rem;border-radius:6px;'
        f'text-decoration:none;font-family:\'IBM Plex Mono\',monospace;font-size:0.85rem;'
        f'font-weight:600;letter-spacing:0.03em;">💬 Ver en StockTwits →</a>'
        '</div>'
        '<div style="font-size:0.7rem;color:#94a3b8;margin-top:0.7rem;">'
        'Seeking Alpha agrega consenso de múltiples proveedores (Refinitiv, FactSet) con '
        'actualización en tiempo real. StockTwits muestra el histórico de earnings en '
        'formato tabla (estimado/reportado/sorpresa) similar al que ya conoces.</div>'
        '</div>',
        unsafe_allow_html=True
    )

    # ════════════════════════════════════════════════════════════════════
    # ANÁLISIS TÉCNICO
    # ════════════════════════════════════════════════════════════════════
    tech_date = tech.get("last_date","N/A") if tech and not tech.get("error") else "N/A"
    _section(f"ANÁLISIS TÉCNICO &nbsp;<span style='font-size:0.7rem;'>🟡 Yahoo Finance · último dato: {tech_date}</span>")

    if tech and not tech.get("error"):
        _render_price_chart(tech, ticker, currency_y)

        col_t1, col_t2 = st.columns(2)

        with col_t1:
            rsi_val = tech.get("rsi")
            rsi_lbl = tech.get("rsi_label","N/A")
            rsi_pct = min(max(rsi_val or 0, 0), 100)
            bar_col = "#dc2626" if rsi_pct >= 70 else "#059669" if rsi_pct <= 30 else "#0284c7"
            rsi_css = tech.get("rsi_css","")
            st.markdown(
                '<div class="metric-card">'
                '<div class="metric-label">RSI (14 períodos)</div>'
                '<div style="display:flex;align-items:baseline;gap:0.6rem;">'
                f'<div class="metric-value">{_fmt_num(rsi_val,2)}</div>'
                f'<span class="row-val {rsi_css}" style="font-size:0.82rem;">{rsi_lbl}</span>'
                '</div>'
                '<div class="progress-bar-bg" style="margin-top:0.6rem;">'
                f'<div style="height:8px;border-radius:4px;background:{bar_col};width:{rsi_pct}%;"></div>'
                '</div>'
                '<div style="display:flex;justify-content:space-between;font-size:0.7rem;'
                'color:#64748b;margin-top:0.2rem;">'
                '<span>0 — Sobreventa</span><span>50</span><span>Sobrecompra — 100</span>'
                '</div>'
                '<div style="margin-top:0.5rem;font-size:0.78rem;color:#64748b;">'
                '▸ RSI &lt; 30: sobreventa (posible rebote) &nbsp;|&nbsp; RSI &gt; 70: sobrecompra'
                '</div></div>',
                unsafe_allow_html=True
            )

        with col_t2:
            mm50      = tech.get("mm50")
            mm200     = tech.get("mm200")
            d50       = tech.get("dist_mm50")
            d200      = tech.get("dist_mm200")
            cross_sig = tech.get("cross_signal")

            html  = _kv("MM50",  _fmt_price(mm50, currency_y, fx_rate), f"row-val {tech.get('mm50_css','')}")
            html += _kv("Distancia MM50",
                _fmt_num(d50,2,suffix="%") if d50 is not None else "N/A",
                "row-val green" if (d50 or 0) >= 0 else "row-val red")
            html += _kv("Señal MM50",  tech.get("mm50_signal","N/A"),  f"row-val {tech.get('mm50_css','')}")
            html += _kv("MM200", _fmt_price(mm200,currency_y,fx_rate) if mm200 else "N/A",
                f"row-val {tech.get('mm200_css','')}")
            html += _kv("Distancia MM200",
                _fmt_num(d200,2,suffix="%") if d200 is not None else "N/A",
                "row-val green" if (d200 or 0) >= 0 else "row-val red")
            html += _kv("Señal MM200", tech.get("mm200_signal","N/A"), f"row-val {tech.get('mm200_css','')}")
            if cross_sig:
                c_label, c_css = cross_sig
                html += _kv("Cruce MM50/MM200", c_label, f"row-val {c_css}")

            # Último cruce con fecha
            last_cross = fetch_last_cross_date(ticker)
            if last_cross.get("date"):
                lc_color = "green" if last_cross["type"] == "GOLDEN CROSS" else "red"
                html += _kv("Último cruce (fecha)",
                    f'{last_cross["type"]} — {last_cross["date"]}', f"row-val {lc_color}")

            st.markdown(f'<div class="metric-card">{html}</div>', unsafe_allow_html=True)

        # ── Nuevos indicadores: MACD, ADX, OBV, Fibonacci ────────────────
        macd_d = tech.get("macd")
        adx_v  = tech.get("adx")
        obv_d  = tech.get("obv")
        fib_d  = tech.get("fibonacci")

        def _tip(text):
            safe = text.replace('"', '&quot;')
            return (f'<span title="{safe}" style="margin-left:0.3rem;cursor:help;font-size:0.6rem;'
                    f'color:#94a3b8;border:1px solid #cbd5e1;border-radius:50%;padding:0 3px;'
                    f'font-family:monospace;">?</span>')

        col_t3, col_t4 = st.columns(2)
        with col_t3:
            html2 = ""
            if macd_d:
                macd_sig = ("Cruce alcista" if macd_d["bullish_cross"] else
                            "Divergencia alcista" if macd_d["bullish_divergence"] else
                            "Cruce bajista" if macd_d["bearish_cross"] else "Sin señal de giro")
                macd_col = "green" if (macd_d["bullish_cross"] or macd_d["bullish_divergence"]) else \
                           "red" if macd_d["bearish_cross"] else ""
                html2 += _kv(f"MACD{_tip('EMA(12)-EMA(26). El histograma mide la distancia entre el MACD y su línea de señal EMA(9). Un cruce alcista o una divergencia (precio cae, histograma sube) sugiere que el impulso bajista se agota.')}",
                    f'{macd_d["macd"]:.3f}', "row-val")
                html2 += _kv("Histograma", f'{macd_d["histogram"]:+.3f}',
                    "row-val green" if macd_d["histogram"] >= 0 else "row-val red")
                html2 += _kv("Señal MACD", macd_sig, f"row-val {macd_col}")
            if adx_v is not None:
                adx_lbl = "Tendencia fuerte" if adx_v > 25 else "Tendencia débil / lateral"
                html2 += _kv(f"ADX (14){_tip('Average Directional Index: mide la FUERZA de la tendencia, no su dirección. >25 = tendencia fuerte (alcista o bajista). <20 = mercado sin tendencia clara. Se usa para bloquear Entrada Ideal si hay tendencia bajista fuerte confirmada.')}",
                    f'{adx_v:.1f} ({adx_lbl})', "row-val")
            if html2:
                st.markdown(f'<div class="metric-card">{html2}</div>', unsafe_allow_html=True)

        with col_t4:
            html3 = ""
            if obv_d:
                obv_lbl = ("Posible acumulación" if obv_d["accumulation"] else
                           "Posible distribución" if obv_d["distribution"] else
                           "Alcista" if obv_d["obv_trend_up"] else "Bajista")
                obv_col = "green" if (obv_d["accumulation"] or obv_d["obv_trend_up"]) else "red"
                html3 += _kv(f"OBV (volumen){_tip('On-Balance Volume: acumula el volumen en días de subida y lo resta en días de bajada. Si el precio cae pero el OBV sube, sugiere que hay compras de manos fuertes pese al precio débil (acumulación). Si el precio sube pero el OBV cae, la subida no está respaldada por volumen real (distribución).')}",
                    obv_lbl, f"row-val {obv_col}")
                html3 += _kv("Precio 20 días", f'{obv_d["price_pct_20d"]:+.1f}%',
                    "row-val green" if obv_d["price_pct_20d"] >= 0 else "row-val red")
            if fib_d:
                near = fib_d.get("near_support")
                fib_lbl = f"En soporte {near}" if near else "Sin soporte Fibonacci cercano"
                html3 += _kv(f"Fibonacci 52W{_tip('Niveles de retroceso entre el máximo y mínimo de 52 semanas — estructura ESTÁTICA de mercado, a diferencia de las medias móviles (dinámicas). Se marca en soporte si el precio está a menos del 3% de los niveles 61.8% o 78.6%, las zonas de rebote técnico más vigiladas tras una corrección.')}",
                    fib_lbl, "row-val green" if near else "row-val")
            if html3:
                st.markdown(f'<div class="metric-card">{html3}</div>', unsafe_allow_html=True)

    elif tech and tech.get("error"):
        st.markdown(
            f'<div class="metric-card"><span class="audit-warn">No se pudo calcular el análisis técnico: {tech["error"]}</span></div>',
            unsafe_allow_html=True)
    else:
        st.markdown(
            '<div class="metric-card"><span class="audit-warn">Análisis técnico no disponible.</span></div>',
            unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════
    # SHORT INTEREST & SHORT SQUEEZE
    # ════════════════════════════════════════════════════════════════════
    sq_data = calc_short_squeeze(y)
    render_short_squeeze(sq_data)

    # ════════════════════════════════════════════════════════════════════
    # EVALUACIÓN FINAL + DIAGNÓSTICO GENERAL
    # ════════════════════════════════════════════════════════════════════
    ev = _evaluate(y)

    _section("EVALUACIÓN FINAL")

    health_score = ev["health_score"]
    fair         = ev["fair_value"]
    upside       = ev["upside"]
    vs_hist      = ev["vs_hist"]
    price_now    = y.get("price") or 0
    diag_color   = ev.get("diag_color","#0f172a")
    diag_icon    = ev.get("diag_icon","")

    # Contexto sectorial
    rate_adj = ev.get("rate_adjustment")
    rate_adj_html = ""
    if rate_adj:
        rf_cur   = rate_adj["rf_current"] * 100
        rf_base  = rate_adj["rf_baseline"] * 100
        factor   = rate_adj["factor"]
        pe_orig  = rate_adj["pe_fair_original"]
        capped_note = " (acotado al ±25% máximo)" if rate_adj["capped"] else ""
        direction = "reducidos" if factor < 1 else "aumentados" if factor > 1 else "sin cambios"
        rate_adj_html = (
            f'<div style="margin-top:0.6rem;padding:0.5rem 0.7rem;background:#eff6ff;'
            f'border-left:3px solid #0284c7;border-radius:4px;font-size:0.72rem;color:#334155;line-height:1.6;">'
            f'ℹ️ <b>Benchmarks {direction} por tipos actuales{capped_note}:</b> bono 10Y USA = {rf_cur:.2f}% '
            f'(referencia histórica: {rf_base:.1f}%). PER justo base {pe_orig}× → ajustado a {ev["pe_ref"]}× '
            f'(factor ×{factor:.2f}). Modelo de Gordon simplificado: coste de capital = Rf + prima riesgo 5.5%, '
            f'g={rate_adj["g"]*100:.1f}% para este sector. Aproximación, no sustituye un DCF completo.</div>'
        )
    else:
        rate_adj_html = (
            '<div style="margin-top:0.6rem;font-size:0.7rem;color:#94a3b8;">'
            'ℹ️ Benchmarks estáticos (sin ajuste por tipos — no se pudo obtener el bono 10Y USA en este momento).</div>'
        )

    st.markdown(
        '<div class="metric-card" style="border-left:3px solid #0284c7;">'
        '<div class="metric-label">CONTEXTO SECTORIAL</div>'
        f'<div style="font-size:0.95rem;font-weight:600;color:#0f172a;margin-bottom:0.4rem;">{ev["sector_label"]}</div>'
        f'<div style="font-size:0.8rem;color:#64748b;line-height:1.6;">{ev["sector_nota"]}</div>'
        '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:0.5rem;margin-top:0.8rem;">'
        '<div style="background:#f4f6f9;border-radius:6px;padding:0.4rem 0.6rem;">'
        f'<div style="font-size:0.68rem;color:#64748b;text-transform:uppercase;">PER justo sector</div>'
        f'<div style="font-family:\'IBM Plex Mono\',monospace;color:#0284c7;font-weight:600;">{ev["pe_ref"]}×</div></div>'
        '<div style="background:#f4f6f9;border-radius:6px;padding:0.4rem 0.6rem;">'
        f'<div style="font-size:0.68rem;color:#64748b;text-transform:uppercase;">PEG aceptable</div>'
        f'<div style="font-family:\'IBM Plex Mono\',monospace;color:#0284c7;font-weight:600;">&lt;{ev["peg_ok"]}</div></div>'
        '<div style="background:#f4f6f9;border-radius:6px;padding:0.4rem 0.6rem;">'
        f'<div style="font-size:0.68rem;color:#64748b;text-transform:uppercase;">EV/EBITDA justo</div>'
        f'<div style="font-family:\'IBM Plex Mono\',monospace;color:#0284c7;font-weight:600;">{ev["ev_ebitda_fair"]}×</div></div>'
        '</div>'
        f'{rate_adj_html}'
        '</div>',
        unsafe_allow_html=True
    )

    # ── Aviso de fiabilidad del cálculo de valor objetivo ───────────────────
    n_methods       = len(ev.get("methods_used", []))
    is_hyper_growth = ev.get("is_hyper_growth", False)
    fund_fresh      = meta_y.get("fund_freshness", {}) or {}
    fund_stale      = fund_fresh.get("ok") is False

    reliability_notes = []
    if fair is None:
        reliability_notes.append((
            "#dc2626",
            "⚠ VALOR OBJETIVO NO CALCULABLE: no hay datos suficientes (EPS, EV/EBITDA, "
            "consenso de analistas) para aplicar ningún método de valoración a esta empresa. "
            "El diagnóstico general no está disponible."
        ))
    elif is_hyper_growth:
        rev_yoy_val = y.get("revenue_yoy")
        rev_yoy_str = f"{rev_yoy_val:.1f}%" if rev_yoy_val is not None else "N/D"
        reliability_notes.append((
            "#0284c7",
            f"ℹ️ VALORACIÓN HYPER-GROWTH: esta empresa tiene EPS negativo o nulo, por lo que "
            f"PER/PEG no son aplicables. Se usó el método EV/Sales al detectar crecimiento de "
            f"ingresos superior al 25% YoY (actual: {rev_yoy_str}). Este método es menos preciso "
            f"que un DCF completo — trátalo como una referencia de orden de magnitud, no como "
            f"un precio exacto."
        ))
    elif n_methods <= 1:
        reliability_notes.append((
            "#d97706",
            f"⚠ FIABILIDAD LIMITADA: el valor objetivo se calculó con un único método "
            f"disponible ({ev['methods_used'][0].split(' →')[0] if ev.get('methods_used') else 'desconocido'}). "
            f"Con más de un método el resultado sería más robusto. Interpreta el upside con cautela."
        ))

    if fund_stale:
        reliability_notes.append((
            "#d97706",
            f"⚠ DATOS FUNDAMENTALES DESACTUALIZADOS: {fund_fresh.get('label','')}. "
            f"Los ratios de valoración pueden no reflejar los resultados más recientes de la empresa."
        ))

    for note_color, note_text in reliability_notes:
        st.markdown(
            f'<div style="background:#f4f6f9;border:1px solid {note_color};border-left:4px solid {note_color};'
            f'border-radius:6px;padding:0.6rem 0.9rem;margin-bottom:0.6rem;font-size:0.78rem;'
            f'color:{note_color};line-height:1.6;">{note_text}</div>',
            unsafe_allow_html=True
        )

    # Salud fundamental
    bar_col_h = "#059669" if health_score>=70 else "#d97706" if health_score>=45 else "#dc2626"
    bd_html = "".join(
        f'<div style="font-size:0.75rem;color:#64748b;padding:0.2rem 0;border-bottom:1px solid #eef1f5;">▸ {b}</div>'
        for b in ev["health_breakdown"]
    )
    with st.expander(f"SALUD FUNDAMENTAL: {health_score}/100 — ver desglose", expanded=True):
        st.markdown(
            '<div style="background:#ffffff;border-radius:8px;padding:0.8rem 1rem;">'
            f'<div style="display:flex;align-items:baseline;gap:0.8rem;margin-bottom:0.5rem;">'
            f'<span style="font-family:\'IBM Plex Mono\',monospace;font-size:1.6rem;font-weight:600;color:{bar_col_h};">{health_score}</span>'
            f'<span style="color:#64748b;font-size:0.85rem;">/ 100 — sector: <b style="color:#0f172a;">{ev["sector_label"]}</b></span>'
            '</div>'
            f'<div style="background:#334155;border-radius:4px;height:8px;margin-bottom:1rem;">'
            f'<div style="height:8px;border-radius:4px;background:{bar_col_h};width:{health_score}%;"></div></div>'
            f'{bd_html}</div>',
            unsafe_allow_html=True
        )

    # Metodología de valoración
    mh = "".join(f'<div style="font-size:0.76rem;color:#64748b;padding:0.3rem 0;border-bottom:1px solid #eef1f5;">▸ {m}</div>'
                 for m in ev.get("methods_used",[])
    ) or '<div style="font-size:0.76rem;color:#64748b;">Sin datos suficientes para calcular valor objetivo.</div>'

    fair_final_html = ""
    if fair:
        fair_eur_final = f' <span style="color:#94a3b8;font-size:0.85em;">(€{fair*fx_rate:,.2f})</span>' if fx_rate and currency_y == "USD" else ""
        n_methods_final = len(ev.get("methods_used", []))
        fair_final_html = (
            '<div style="margin-top:0.8rem;padding-top:0.7rem;border-top:2px solid #dbeafe;'
            'display:flex;justify-content:space-between;align-items:baseline;">'
            f'<span style="font-size:0.78rem;color:#0284c7;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">'
            f'Valor objetivo (media de {n_methods_final} método{"s" if n_methods_final != 1 else ""})</span>'
            f'<span style="font-family:\'IBM Plex Mono\',monospace;font-size:1.1rem;font-weight:700;color:#0f172a;">'
            f'{currency_y} {fair:,.2f}{fair_eur_final}</span>'
            '</div>'
        )

    with st.expander("METODOLOGÍA DE VALORACIÓN — ver cálculo del valor objetivo", expanded=True):
        st.markdown(
            '<div style="background:#ffffff;border-radius:8px;padding:0.8rem 1rem;">'
            f'<div style="font-size:0.72rem;color:#0284c7;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:0.5rem;">'
            f'Métodos aplicados (sector: {ev["sector_label"]})</div>'
            f'{mh}'
            '<div style="margin-top:0.6rem;font-size:0.72rem;color:#64748b;">'
            'El valor objetivo es la media aritmética de los métodos disponibles más el consenso de analistas.</div>'
            f'{fair_final_html}'
            '</div>',
            unsafe_allow_html=True
        )

    # Múltiplos vs sector
    vs_items = ev.get("vs_sector","")
    if " · " in vs_items:
        vs_html = "".join(
            f'<div style="font-size:0.8rem;color:#1e293b;padding:0.25rem 0;border-bottom:1px solid #eef1f5;">▸ {item}</div>'
            for item in vs_items.split(" · ")
        )
    else:
        vs_html = f'<div style="font-size:0.8rem;color:#64748b;">{vs_items}</div>'
    st.markdown(
        f'<div class="metric-card"><div class="metric-label">MÚLTIPLOS VS BENCHMARKS DEL SECTOR</div>{vs_html}</div>',
        unsafe_allow_html=True
    )

    # Diagnóstico general
    upside_str  = f"{upside:+.2f}%" if upside is not None else "N/A"
    fair_usd    = f"{currency_y} {fair:,.2f}" if fair else "N/A"
    fair_eur    = f" (€{fair*fx_rate:,.2f})" if (fair and fx_rate and currency_y=="USD") else ""
    fair_str    = f"{fair_usd}{fair_eur}" if fair else "N/A"
    hist_str    = f"{vs_hist:+.2f}% vs media 52W" if vs_hist is not None else "N/A"
    price_eur   = f" (€{price_now*fx_rate:,.2f})" if (fx_rate and currency_y=="USD") else ""
    up_color    = "#059669" if (upside or 0) > 0 else "#dc2626"

    # Métodos usados para construir el tooltip del valor objetivo
    methods_list = ev.get("methods_used", [])
    methods_text = " · ".join(methods_list) if methods_list else "Sin datos suficientes"

    def _vtip(text):
        safe = text.replace('"', '&quot;')
        return (
            f'<span title="{safe}" style="margin-left:0.3rem;cursor:help;'
            f'font-size:0.6rem;color:#94a3b8;border:1px solid #cbd5e1;'
            f'border-radius:50%;padding:0 3px;font-family:monospace;'
            f'vertical-align:middle;">?</span>'
        )

    tip_vo = _vtip(
        f"Valor objetivo = media aritmética de hasta 4 métodos ajustados al sector {ev.get('sector_label','')}. "
        f"Métodos aplicados: {methods_text}. "
        "Se excluyen los métodos para los que no hay datos disponibles. "
        "El consenso de analistas siempre se incluye si existe. "
        "Limitación: los múltiplos sectoriales son estáticos y no reflejan el ciclo de mercado actual."
    )

    tip_risk = _vtip(
        "Riesgo técnico (0-15%) = combinación de dos factores: "
        f"(1) Short Ratio × 1.5, acotado a 6% máx — actualmente Short Ratio = {y.get('short_ratio') or 0:.1f} días. "
        "Un short ratio alto indica presión bajista institucional. "
        "(2) Distancia al máximo 52W × 0.08, acotado a 5% máx — "
        "cuanto más lejos está el precio de sus máximos, mayor el riesgo de que los bajistas tengan razón. "
        "Ambos factores se suman: máximo posible = 11%, redondeado al 15% como techo."
    )

    # Banda de confianza: dispersión entre los métodos individuales (sin ponderar)
    targets_range = ev.get("targets_range")
    range_html = ""
    if targets_range:
        rmin, rmax = targets_range
        rmin_eur = f' <span style="color:#94a3b8;font-size:0.85em;">(€{rmin*fx_rate:,.2f})</span>' if fx_rate and currency_y=="USD" else ""
        rmax_eur = f' <span style="color:#94a3b8;font-size:0.85em;">(€{rmax*fx_rate:,.2f})</span>' if fx_rate and currency_y=="USD" else ""
        spread_pct = (rmax - rmin) / rmin * 100 if rmin else 0
        spread_note = (
            "consenso alto entre métodos" if spread_pct < 15
            else "dispersión moderada" if spread_pct < 35
            else "alta dispersión — mayor incertidumbre real"
        )
        range_html = (
            '<div class="verdict-sub" style="margin-top:0.3rem;">'
            f'<span style="color:#64748b;">Rango entre métodos:</span> '
            f'<span style="font-family:\'IBM Plex Mono\',monospace;color:#64748b;">'
            f'{currency_y} {rmin:,.2f}{rmin_eur} — {rmax:,.2f}{rmax_eur}</span> '
            f'<span style="font-size:0.78rem;color:#94a3b8;">({spread_note}, {spread_pct:.0f}% de rango)</span>'
            '</div>'
        )

    st.markdown(
        f'<div class="verdict-box" style="border-left-color:{diag_color};">'
        '<div class="verdict-title">DIAGNÓSTICO GENERAL</div>'
        '<div style="display:flex;align-items:center;gap:0.7rem;margin-bottom:0.5rem;">'
        f'<span style="font-family:\'IBM Plex Mono\',monospace;font-size:1.4rem;font-weight:700;color:{diag_color};">{diag_icon}</span>'
        f'<span class="verdict-main" style="color:{diag_color};">{ev["diag"]}</span>'
        '</div>'
        f'<div class="verdict-sub" style="margin-top:0.6rem;">'
        f'<span style="color:#64748b;">Precio actual:</span>'
        f'<span style="font-family:\'IBM Plex Mono\',monospace;font-weight:600;color:#0f172a;"> {currency_y} {price_now:,.2f}{price_eur}</span>'
        f'&nbsp;·&nbsp;<span style="color:#64748b;">Valor objetivo{tip_vo}:</span>'
        f'<span style="font-family:\'IBM Plex Mono\',monospace;font-weight:600;color:#0f172a;"> {fair_str}</span>'
        f'<span style="font-family:\'IBM Plex Mono\',monospace;font-weight:700;color:{up_color};"> ({upside_str})</span>'
        '</div>'
        f'{range_html}'
        f'<div class="verdict-sub"><span style="color:#64748b;">Vs. media 52W:</span>'
        f'<span style="font-family:\'IBM Plex Mono\',monospace;font-weight:600;color:#d97706;"> {hist_str}</span></div>'
        f'<div class="verdict-sub" style="margin-top:0.4rem;">'
        f'<span style="color:#64748b;">Riesgo técnico (short){tip_risk}:</span>'
        f'<span style="color:#1e293b;"> {ev["risk"]}%</span></div>'
        '</div>',
        unsafe_allow_html=True
    )

    # ════════════════════════════════════════════════════════════════════
    # VALORACIÓN POR IA — GEMINI PRO
    # ════════════════════════════════════════════════════════════════════
    render_ai_valuation(ticker, y.get("price"), currency_y)

    # ════════════════════════════════════════════════════════════════════
    # HISTÓRICO DE MÚLTIPLOS PROPIOS
    # ════════════════════════════════════════════════════════════════════
    with st.spinner("Calculando múltiplos históricos…"):
        mult_data = fetch_historical_multiples(ticker, y, sector_pe_fair=ev.get("pe_ref"))
    render_historical_multiples(mult_data)

    # ════════════════════════════════════════════════════════════════════
    # SEÑAL DE ENTRADA
    # ════════════════════════════════════════════════════════════════════
    with st.spinner("Consultando momentum de revisiones de analistas…"):
        y["analyst_revisions"] = fetch_analyst_revisions(ticker)
    signal = calc_entry_signal(y, tech, ev)
    render_entry_signal(signal)

    # ════════════════════════════════════════════════════════════════════
    # COMPARATIVA FRENTE A COMPETENCIA
    # ════════════════════════════════════════════════════════════════════
    peers_tickers = get_manual_competitors(ticker)
    if peers_tickers:
        with st.spinner("Cargando datos de competidores…"):
            peers_data = fetch_peer_data(peers_tickers)
    else:
        peers_data = []

    render_peers(ticker, y, peers_data, fx_rate, ev)

    # ════════════════════════════════════════════════════════════════════
    # EXPORTAR ANÁLISIS A PDF
    # ════════════════════════════════════════════════════════════════════
    st.markdown("---")
    st.markdown(
        '<div style="font-size:0.78rem;color:#64748b;margin-bottom:0.5rem;">'
        'Guarda una copia de este análisis con fecha y hora exactas para consultarlo más adelante '
        'o comparar la misma empresa en distintos momentos.</div>',
        unsafe_allow_html=True
    )
    render_pdf_download_button(
        ticker, company_name, y, ev, tech,
        sq_data, signal, trend, mult_data, ea,
        fx_rate
    )

    st.caption(
        f"Datos: Yahoo Finance · {ticker} · USD/EUR: {fx_rate:.4f} · "
        f"Sector: {ev['sector_label']} · No constituye asesoramiento financiero."
    )
