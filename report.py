"""
report.py — v1.9
Renderiza el informe completo en Streamlit con el diseño claro.
"""

import streamlit as st
import plotly.graph_objects as go
import yfinance as yf
import statistics
from data_fetcher import fetch_balance_sheet_history
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


# ─── Gráfico de cotización con MM50/MM200 ────────────────────────────────────

def _render_price_chart(tech: dict, ticker: str, currency: str = "USD", entry_exit_plan: dict | None = None):
    """
    Gráfico interactivo de cotización a 1 año con MM50 y MM200 superpuestas.
    Zoom, pan y tooltip con fecha + precio al pasar el cursor (nativo de Plotly).
    Opcionalmente puede superponer los niveles del Plan de Entrada y Salida
    Sugerido — desactivado por defecto, activable con un botón, para no
    saturar el gráfico cuando no interesa verlo.
    """
    history = tech.get("price_history", [])
    if not history:
        return

    dates  = [h["date"]  for h in history]
    closes = [h["close"] for h in history]
    mm50s  = [h["mm50"]  for h in history]
    mm200s = [h["mm200"] for h in history]

    show_plan = False
    if entry_exit_plan:
        toggle_key = f"show_plan_chart_{ticker}"
        show_plan = st.toggle(
            "Mostrar Plan de Entrada y Salida Sugerido",
            value=st.session_state.get(toggle_key, False),
            key=toggle_key,
        )

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

    if show_plan and entry_exit_plan:
        for i, lvl in enumerate(entry_exit_plan.get("entry_plan", [])):
            fig.add_hline(
                y=lvl["price"], line=dict(color="#059669", width=1.2, dash="dot"),
                annotation_text=f"Entrada {i+1}: {currency} {lvl['price']:,.2f}",
                annotation_position="top left",
                annotation=dict(font=dict(size=9, color="#059669")),
            )
        for obj in (entry_exit_plan.get("exit_plan") or []):
            fig.add_hline(
                y=obj["price"], line=dict(color="#0284c7", width=1.2, dash="dot"),
                annotation_text=f"{obj['label']}: {currency} {obj['price']:,.2f}",
                annotation_position="top left",
                annotation=dict(font=dict(size=9, color="#0284c7")),
            )
        if entry_exit_plan.get("stop_loss"):
            fig.add_hline(
                y=entry_exit_plan["stop_loss"], line=dict(color="#dc2626", width=1.6, dash="dash"),
                annotation_text=f"Stop Loss: {currency} {entry_exit_plan['stop_loss']:,.2f}",
                annotation_position="bottom left",
                annotation=dict(font=dict(size=9, color="#dc2626")),
            )

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
    "Acciones en circulación": "Número total de acciones emitidas por la empresa que cotizan en el mercado. Market Cap = precio × acciones en circulación. Una cifra creciente año a año indica dilución (ver Salud Fundamental).",
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

def _robust_aggregate(weighted: list[float]) -> float:
    """
    Agrega los valores de los distintos métodos de valoración usando la
    MEDIANA en vez de la media aritmética simple.

    Por qué: aunque cada método individual tenga sus propias salvaguardas
    (topes de crecimiento, chequeos de sensatez de EPS, etc.), la media
    aritmética simple sigue siendo estructuralmente frágil — CUALQUIER
    método que produzca un valor atípico (por un motivo no previsto
    todavía) puede seguir distorsionando el resultado final por completo,
    ya que un solo outlier extremo desplaza la media proporcionalmente a
    su magnitud, sin límite. La mediana es inmune a esto: un valor atípico,
    por extremo que sea, cuenta como un solo voto posicional, no arrastra
    el resultado hacia sí. El peso doble del consenso de analistas (cuando
    aplica) ya viene reflejado en duplicar su entrada en la lista antes de
    llegar aquí, así que sigue pesando el doble también bajo mediana.
    """
    if not weighted:
        return None
    return statistics.median(weighted)


def _calc_fair_value(y: dict, profile: dict, bh: dict | None = None, mult_data: dict | None = None) -> tuple[float | None, list[str], tuple[float, float] | None, float | None]:
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

    CRECIMIENTO SUAVIZADO (CAGR multi-año): el método PEG y la prima de
    crecimiento del PER ya NO usan el crecimiento de beneficios de un único
    año (earnings_yoy), porque un pico puntual no recurrente (ej. +292% de
    Broadcom impulsado por IA) inflaba el Valor Objetivo de forma
    desproporcionada al multiplicarse linealmente. Ahora se usa el CAGR
    entre el beneficio más antiguo y más reciente disponibles (hasta ~4
    años vía balance histórico), con fallback al dato de 1 año si no hay
    histórico multi-año limpio disponible para el ticker.

    FALLBACK HYPER-GROWTH: si la empresa tiene EPS negativo o nulo (PER/PEG
    no aplicables) y el crecimiento de ingresos YoY supera el 25%, se sustituye
    la valoración por múltiplos de beneficio por EV/Sales — comparando el
    múltiplo EV/Sales actual de la empresa contra el EV/Sales "justo" del
    sector. Es el método estándar para valorar empresas pre-rentabilidad
    con alto crecimiento (ej. SaaS en expansión, biotecnológicas en fase
    de escalado comercial).
    """
    bh = bh or {}
    price       = y.get("price") or 0
    eps_fwd     = y.get("eps_forward")
    eps_ttm     = y.get("eps_ttm")
    pe_forward_yahoo = y.get("pe_forward")   # PER Forward que Yahoo YA calcula internamente

    # ── Chequeo de sensatez de EPS Forward, anclado al PRECIO real ───────
    # El chequeo anterior solo comparaba eps_forward contra eps_ttm entre
    # sí — pero si Yahoo tiene el mismo problema de escala en AMBOS campos
    # a la vez (ej. un split de acciones no reflejado correctamente en el
    # histórico de EPS de ese ticker concreto), el ratio entre ellos sigue
    # pareciendo razonable y el chequeo cruzado no detecta nada, aunque los
    # dos números estén disparatados en términos absolutos — exactamente lo
    # que ocurría con AVGO/MU/STX (EPS Forward de 150+ con precios de
    # ~$100-150, implicando un PER de <1x, algo virtualmente imposible en
    # el mercado real).
    #
    # Ahora se ancla a dos referencias independientes que Yahoo no calcula
    # a partir de estos mismos campos:
    #   1. El PER implícito (precio / eps_forward) debe estar en un rango
    #      absoluto plausible para cualquier acción cotizada (2×-200×).
    #   2. Si Yahoo expone su propio forwardPE, el PER implícito no debe
    #      discrepar más de 3× de ese valor — forwardPE lo calcula Yahoo
    #      con su propia lógica interna, así que sirve de verificación
    #      cruzada independiente del campo EPS bruto.
    eps_sanity_warning = None
    if eps_fwd is not None and eps_fwd > 0 and price > 0:
        implied_pe = price / eps_fwd
        suspicious = implied_pe < 2 or implied_pe > 200
        if not suspicious and pe_forward_yahoo and pe_forward_yahoo > 0:
            cross_ratio = max(implied_pe, pe_forward_yahoo) / max(min(implied_pe, pe_forward_yahoo), 1e-9)
            if cross_ratio > 3:
                suspicious = True
        if suspicious:
            eps_sanity_warning = (
                f"⚠ EPS Forward ({eps_fwd:.2f}) implica un PER de {implied_pe:.1f}× "
                f"(Precio {price:.2f} ÷ EPS) "
                + (f"frente al PER Forward de {pe_forward_yahoo:.1f}× que da Yahoo directamente "
                   if pe_forward_yahoo else "")
                + "— posible dato erróneo de Yahoo (ej. split no reflejado en el histórico de EPS). "
                  "Se excluye EPS Forward de PER/PEG por seguridad."
            )
            eps_fwd = None   # invalidar para que PER/PEG no lo usen

    # Chequeo adicional (capa secundaria): EPS Forward vs EPS TTM, por si
    # el precio no está disponible para anclar el chequeo principal de arriba
    if eps_sanity_warning is None and eps_fwd is not None and eps_ttm is not None and eps_ttm != 0 and eps_fwd != 0:
        same_sign = (eps_fwd > 0) == (eps_ttm > 0)
        if same_sign:
            ratio = max(abs(eps_fwd), abs(eps_ttm)) / max(min(abs(eps_fwd), abs(eps_ttm)), 1e-9)
            if ratio > 4:
                eps_sanity_warning = (
                    f"⚠ EPS Forward ({eps_fwd:.2f}) difiere {ratio:.1f}× de EPS TTM ({eps_ttm:.2f}) "
                    f"— posible dato erróneo de Yahoo. Se excluye EPS Forward de PER/PEG por seguridad."
                )
                eps_fwd = None   # invalidar para que PER/PEG no lo usen

    pe_forward  = y.get("pe_forward")
    peg         = y.get("peg_ratio")
    ev_ebitda   = y.get("ev_ebitda")
    ebitda      = y.get("ebitda")
    market_cap  = y.get("market_cap") or 1
    ent_value   = y.get("enterprise_value") or 1
    fcf         = y.get("free_cash_flow") or 0
    price_book  = y.get("price_book")
    roe         = y.get("roe") or 0
    earn_growth_smoothed, earn_growth_method = _calc_smoothed_earnings_growth(y, bh)
    earn_growth = earn_growth_smoothed if earn_growth_smoothed is not None else 0
    target_mean = y.get("target_mean")
    ev_revenue  = y.get("ev_revenue")
    rev_yoy     = y.get("revenue_yoy")
    analyst_n   = y.get("analyst_count") or 0

    methods_used = []
    if eps_sanity_warning:
        methods_used.append(eps_sanity_warning)
    targets      = []   # cada método individual, sin ponderar (para el rango)
    weighted     = []   # valores para la mediana CON peso doble al consenso (≥10 analistas)
    weighted_single = []   # valores para la mediana SIN peso doble — consenso cuenta 1 vez siempre

    def _add_consensus():
        """Añade el consenso de analistas — con peso doble en 'weighted' (si ≥10
        analistas) y con peso simple en 'weighted_single', para poder comparar
        ambas medianas y ver cuánto influye esa ponderación en el resultado."""
        if target_mean and target_mean > 0:
            targets.append(target_mean)
            weighted_single.append(target_mean)
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
            weighted_single.append(val)
            methods_used.append(
                f"EV/Sales hyper-growth ( {price:,.2f} (Precio) × [ {ev_sales_fair:.1f} (EV/Sales sector) "
                f"÷ {ev_revenue:.1f} (EV/Sales actual) ] , Rev YoY {rev_yoy:.0f}% > 25% ) → {val:,.2f}"
            )
        # En modo hyper-growth NO se usan PER/PEG aunque el sector los liste,
        # porque el EPS negativo los invalida por definición.
        _add_consensus()
        if not weighted:
            return None, [], None, None
        fair_value = _robust_aggregate(weighted)
        fair_value_single = _robust_aggregate(weighted_single)
        rng = (min(targets), max(targets)) if len(targets) >= 2 else None
        return fair_value, methods_used, rng, fair_value_single

    for method in profile["methods"]:

        # PER × EPS con PE justo del sector
        if method == "per" and eps_fwd and eps_fwd > 0:
            fair_pe = profile["pe_fair"]
            prima_txt = ""
            # Prima de crecimiento CONTINUA (antes era un escalón binario:
            # +10% fijo si crecimiento >20%, dando la MISMA prima a una
            # empresa que crece al 21% que a una que crece al 90% — un
            # "acantilado" artificial). Ahora escala proporcionalmente al
            # exceso sobre el umbral del 20%, con un tope del 25% para no
            # reproducir el mismo problema de picos desproporcionados que
            # ya corregimos en el crecimiento suavizado (CAGR).
            PREMIUM_THRESHOLD = 0.20   # a partir de aquí empieza a aplicar prima
            PREMIUM_SCALE      = 0.5   # 0.5% de prima por cada 1% de exceso sobre el umbral
            PREMIUM_MAX        = 0.25  # tope máximo de prima: +25%
            if earn_growth > PREMIUM_THRESHOLD:
                excess = (earn_growth - PREMIUM_THRESHOLD) * 100   # puntos porcentuales de exceso
                premium = min(excess * PREMIUM_SCALE / 100, PREMIUM_MAX)
                fair_pe_base = fair_pe
                fair_pe *= (1 + premium)
                prima_txt = (f" [{fair_pe_base:.0f}×{1+premium:.2f} prima continua por crecimiento "
                             f"{earn_growth*100:.0f}%>20%, {earn_growth_method}]")
            val = fair_pe * eps_fwd
            if val > 0:
                targets.append(val)
                weighted.append(val)
                weighted_single.append(val)
                methods_used.append(
                    f"PER sectorial ( {fair_pe:.1f}{prima_txt} × {eps_fwd:,.2f} (EPS Forward) ) → {val:,.2f}"
                )

        # PEG: precio justo = EPS × PEG_sector × tasa_crecimiento × 100
        # TOPE DE SEGURIDAD (nuevo): incluso tras el suavizado CAGR, un
        # crecimiento anualizado sostenido por encima del 60% es
        # extraordinariamente raro en la práctica. Se acota como capa de
        # seguridad adicional, independiente de si el crecimiento venía de
        # CAGR multi-año o del fallback de 1 año — así un fallo puntual del
        # histórico de balance para un ticker concreto (p.ej. si Yahoo no
        # devuelve suficientes años limpios) no puede seguir disparando
        # valoraciones desproporcionadas como ya ha ocurrido.
        elif method == "peg" and peg and eps_fwd and eps_fwd > 0 and earn_growth > 0:
            GROWTH_CAP_PEG = 0.60
            growth_capped = min(earn_growth, GROWTH_CAP_PEG)
            growth_pct = growth_capped * 100
            cap_note = " (acotado, valor real mayor)" if earn_growth > GROWTH_CAP_PEG else ""
            val = eps_fwd * profile["peg_ok"] * growth_pct
            if val > 0:
                targets.append(val)
                weighted.append(val)
                weighted_single.append(val)
                methods_used.append(
                    f"PEG sectorial ( {eps_fwd:,.2f} (EPS Forward) × {profile['peg_ok']:.1f} (PEG sector) "
                    f"× {growth_pct:.1f} (Crec. beneficios, {earn_growth_method}{cap_note}) ) → {val:,.2f}"
                )

        # EV/EBITDA sectorial — FÓRMULA CORREGIDA: separa Enterprise Value
        # de Equity Value explícitamente en vez de escalar el precio
        # linealmente por el ratio de múltiplos. La fórmula anterior
        # (precio × EV/EBITDA_justo/actual) asume implícitamente que la
        # deuda neta escala proporcionalmente con el equity, lo cual es
        # matemáticamente falso salvo que la empresa no tenga deuda —
        # introduce un sesgo real en empresas apalancadas.
        # Fórmula correcta: Equity Value = EBITDA × Múltiplo objetivo − Deuda
        # Neta; Precio = Equity Value ÷ Acciones en circulación.
        elif method == "ev_ebitda" and ev_ebitda and ebitda and ebitda > 0:
            fair_ev_ebitda = profile["ev_ebitda_fair"]
            shares_out = y.get("shares_outstanding")
            net_debt   = (y.get("total_debt") or 0) - (y.get("total_cash") or 0)

            if shares_out and shares_out > 0:
                equity_value_target = ebitda * fair_ev_ebitda - net_debt
                val = equity_value_target / shares_out
                formula_note = (
                    f"EV/EBITDA sectorial ( [ {ebitda/1e9:,.2f}B (EBITDA) × {fair_ev_ebitda:.1f} "
                    f"(múltiplo sector) − {net_debt/1e9:,.2f}B (deuda neta) ] ÷ "
                    f"{shares_out/1e6:,.0f}M (acciones) ) → {{val:,.2f}}"
                )
            else:
                # Fallback si no hay acciones en circulación disponibles:
                # mantiene el atajo anterior, pero se marca explícitamente
                # como aproximación menos precisa en el propio texto.
                ratio = fair_ev_ebitda / ev_ebitda if ev_ebitda else 1
                val   = price * ratio
                formula_note = (
                    f"EV/EBITDA sectorial ( {price:,.2f} (Precio) × [ {fair_ev_ebitda:.1f} (EV/EBITDA sector) "
                    f"÷ {ev_ebitda:.1f} (EV/EBITDA actual) ] , aproximación sin deuda neta — "
                    f"sin datos de acciones en circulación ) → {{val:,.2f}}"
                )
            if val > 0:
                targets.append(val)
                weighted.append(val)
                weighted_single.append(val)
                methods_used.append(formula_note.format(val=val))

        # FCF Yield (DCF simplificado): precio justo = FCF / yield_esperado
        elif method == "dcf_lite" and fcf > 0 and market_cap > 0:
            fcf_yield_target = 0.04  # rentabilidad FCF esperada del 4%
            shares = market_cap / price if price else 1
            fcf_per_share = fcf / shares
            val = fcf_per_share / fcf_yield_target
            if val > 0:
                targets.append(val)
                weighted.append(val)
                weighted_single.append(val)
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
                weighted_single.append(val)
                methods_used.append(
                    f"Price/Book justo ( {price:,.2f} (Precio) × [ {fair_pb:.2f} (ROE {roe*100:.1f}% ÷ Ke {cost_of_equity*100:.0f}%) "
                    f"÷ {price_book:.2f} (P/B actual) ] ) → {val:,.2f}"
                )

    # PER histórico PROPIO (5 años) aplicado al beneficio esperado — a
    # diferencia del PER sectorial (que compara contra la media del sector),
    # este usa el múltiplo al que la propia empresa ha cotizado
    # históricamente, sin importar si el sector en su conjunto está caro o
    # barato en este momento. Se aplica independientemente del sector
    # (no depende de profile["methods"]) siempre que haya histórico de
    # precios suficiente. Usa EPS Forward si está disponible (y pasó el
    # chequeo de sensatez), si no cae a EPS TTM.
    if mult_data and mult_data.get("per_mean"):
        per_propio = mult_data["per_mean"]
        eps_para_per_propio = eps_fwd if (eps_fwd and eps_fwd > 0) else (eps_ttm if eps_ttm and eps_ttm > 0 else None)
        if eps_para_per_propio:
            val = per_propio * eps_para_per_propio
            if val > 0:
                targets.append(val)
                weighted.append(val)
                weighted_single.append(val)
                methods_used.append(
                    f"PER histórico propio (5 años) ( {per_propio:.1f} × "
                    f"{eps_para_per_propio:,.2f} ({'EPS Forward' if eps_fwd and eps_fwd>0 else 'EPS TTM'}) ) → {val:,.2f}"
                )

    _add_consensus()

    if not weighted:
        return None, [], None, None

    fair_value = _robust_aggregate(weighted)
    fair_value_single = _robust_aggregate(weighted_single)
    rng = (min(targets), max(targets)) if len(targets) >= 2 else None
    return fair_value, methods_used, rng, fair_value_single


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


def _pts_color(pts: float, max_pts: float) -> str:
    """Devuelve rojo/amarillo/verde según el % de puntos logrados sobre el máximo posible."""
    if max_pts <= 0:
        return "#64748b"
    pct = pts / max_pts
    if pct >= 0.7:  return "#059669"   # verde — bueno/destacable
    if pct >= 0.35: return "#d97706"   # amarillo — normal
    return "#dc2626"                    # rojo — malo


def _calc_smoothed_earnings_growth(y: dict, bh: dict) -> tuple[float | None, str]:
    """
    Crecimiento de beneficios "suavizado" para uso en valoración (PEG y
    prima del PER) — evita que un pico puntual de un solo año (ej. +292%
    de Broadcom impulsado por IA, o cualquier efecto base/adquisición/
    ajuste fiscal no recurrente) infle artificialmente el Valor Objetivo,
    ya que ese método multiplica linealmente por esta tasa.

    Usa CAGR (tasa de crecimiento anual compuesto) entre el beneficio neto
    más antiguo y el más reciente disponibles en bh["net_income_series"]
    (hasta ~4 años, lo que Yahoo exponga). Si no hay al menos 2 años
    limpios (año más antiguo positivo), cae al crecimiento YoY de un solo
    año — el mismo comportamiento que había antes de este cambio.

    Devuelve (tasa_decimal, descripción_del_método_usado).
    """
    series = bh.get("net_income_series") or []
    n = len(series)

    if n >= 2:
        ni_recent = series[0]
        ni_oldest = series[-1]
        n_years   = n - 1
        if ni_oldest > 0 and ni_recent > 0:
            cagr = (ni_recent / ni_oldest) ** (1 / n_years) - 1
            return cagr, f"CAGR {n_years} años"
        # Razón específica del fallback, para que sea diagnosticable en vez
        # de un genérico "sin histórico limpio" que no distingue si es un
        # problema de datos o un hecho real de la empresa (año con pérdidas)
        single_year = y.get("earnings_yoy")
        if ni_oldest <= 0 and ni_recent > 0:
            reason = f"1 año (año base con pérdidas hace {n_years} años, CAGR no aplicable)"
        elif ni_recent <= 0:
            reason = "1 año (beneficio neto actual negativo, CAGR no aplicable)"
        else:
            reason = "1 año (datos de balance no concluyentes)"
        if single_year is not None:
            return single_year / 100, reason
        return None, "sin datos"

    # Fallback: sin serie multi-año en absoluto (balance histórico no
    # disponible para este ticker, o Yahoo no expone la fila "Net Income")
    single_year = y.get("earnings_yoy")
    if single_year is not None:
        return single_year / 100, "1 año (sin balance histórico disponible para este ticker)"

    return None, "sin datos"


def _calc_roic(y: dict, bh: dict) -> tuple[float | None, str]:
    """
    ROIC (Return on Invested Capital) = NOPAT / Capital Invertido.
    A diferencia del ROE (que se infla con apalancamiento), ROIC mide la
    eficiencia real de asignación de capital de la directiva, independiente
    de cómo esté financiada la empresa.

    NOPAT = Operating Income x (1 - tipo impositivo ~21%). Se usa el
    Operating Income real del balance histórico si está disponible; si no,
    se aproxima con operating_margin x Revenue (menos preciso pero
    disponible siempre).

    Capital Invertido = Deuda Total + Patrimonio Neto - Caja. El Patrimonio
    Neto se usa del balance real si está disponible; si no, se aproxima
    como Market Cap / Price-Book (más ruidoso, pero evita descartar el
    cálculo quedando sin dato).
    """
    tax_rate = 0.21
    op_income = bh.get("operating_income_cur")
    if op_income is None:
        rev = y.get("rev_year_cur")
        op_margin = y.get("operating_margin")
        if rev and op_margin is not None:
            op_income = rev * op_margin
    if op_income is None:
        return None, "Sin datos suficientes (Operating Income no disponible)"

    nopat = op_income * (1 - tax_rate)

    equity = bh.get("total_equity_cur")
    if equity is None:
        mcap, pb = y.get("market_cap"), y.get("price_book")
        if mcap and pb and pb > 0:
            equity = mcap / pb
    total_debt = y.get("total_debt") or 0
    total_cash = y.get("total_cash") or 0

    if equity is None:
        return None, "Sin datos suficientes (Patrimonio Neto no disponible)"

    invested_capital = total_debt + equity - total_cash
    if invested_capital <= 0:
        return None, "Capital invertido no positivo (no calculable de forma fiable)"

    roic = nopat / invested_capital
    return roic, "OK"


def _calc_rule_of_40(y: dict) -> dict | None:
    """
    Regla del 40: Crecimiento de Ingresos YoY (%) + Margen FCF (%) >= 40.
    Se usa para auditar la calidad del crecimiento en empresas del fallback
    hyper-growth (EPS negativo + alto crecimiento): crecer rápido quemando
    caja de forma insostenible NO es lo mismo que crecer rápido de forma
    sana. Una empresa que crece al 30% con margen FCF del -20% suma solo 10
    (destruye valor pese al crecimiento aparente).
    """
    rev_yoy = y.get("revenue_yoy")
    fcf     = y.get("free_cash_flow")
    rev     = y.get("rev_year_cur")
    if rev_yoy is None or fcf is None or not rev:
        return None
    fcf_margin = fcf / rev * 100
    total = rev_yoy + fcf_margin
    return {
        "rev_growth": round(rev_yoy, 1),
        "fcf_margin": round(fcf_margin, 1),
        "total": round(total, 1),
        "passes": total >= 40,
    }


def calc_piotroski_score(y: dict, bh: dict) -> dict:
    """
    Piotroski F-Score (0-9): sistema de 9 criterios binarios sobre
    rentabilidad, apalancamiento/liquidez y eficiencia operativa, pensado
    para detectar deterioro financiero incluso en empresas que parecen
    baratas por otros motivos ("value traps").

    A diferencia del Altman Z-Score (descartado — requiere Beneficios
    Retenidos y más partidas del balance que Yahoo no siempre expone con
    fiabilidad), Piotroski usa métricas más básicas y accesibles. Aun así,
    3 de los 9 criterios necesitan Total Assets de 2 años, un dato que
    Yahoo no siempre tiene disponible para todos los tickers — por eso el
    score se muestra siempre como "X/9 evaluado", nunca forzando los 9
    puntos si falta información: cada criterio no evaluable se excluye
    limpiamente en vez de asumir un valor.
    """
    criteria = []   # (nombre, cumple: bool|None, detalle)

    # 1. ROA positivo
    roa = y.get("roa")
    if roa is not None:
        criteria.append(("ROA positivo", roa > 0, f"ROA: {roa*100:.1f}%"))
    else:
        criteria.append(("ROA positivo", None, "Sin dato de ROA"))

    # 2. Cash Flow Operativo positivo
    cfo = y.get("operating_cf")
    if cfo is not None:
        criteria.append(("Cash Flow Operativo positivo", cfo > 0, f"CFO: {cfo/1e6:,.0f}M"))
    else:
        criteria.append(("Cash Flow Operativo positivo", None, "Sin dato de CFO"))

    # 3. Delta ROA (mejora vs año anterior)
    ta_cur, ta_prior = bh.get("total_assets_cur"), bh.get("total_assets_prior")
    ni_cur, ni_prior = y.get("ni_year_cur"), bh.get("net_income_prior")
    if ta_cur and ta_prior and ni_cur is not None and ni_prior is not None:
        roa_cur   = ni_cur / ta_cur
        roa_prior = ni_prior / ta_prior
        criteria.append(("ROA mejora vs año anterior", roa_cur > roa_prior,
                          f"ROA actual {roa_cur*100:.1f}% vs anterior {roa_prior*100:.1f}%"))
    else:
        criteria.append(("ROA mejora vs año anterior", None, "Sin Total Assets de 2 años"))

    # 4. Calidad del beneficio: CFO > Beneficio Neto
    if cfo is not None and ni_cur is not None:
        criteria.append(("Calidad beneficio (CFO > Beneficio Neto)", cfo > ni_cur,
                          f"CFO {cfo/1e6:,.0f}M vs Beneficio Neto {ni_cur/1e6:,.0f}M"))
    else:
        criteria.append(("Calidad beneficio (CFO > Beneficio Neto)", None, "Datos insuficientes"))

    # 5. Apalancamiento reducido (Deuda LP / Activos, año actual vs anterior)
    ltd_cur, ltd_prior = bh.get("long_term_debt_cur"), bh.get("long_term_debt_prior")
    if ltd_cur is not None and ltd_prior is not None and ta_cur and ta_prior:
        lev_cur, lev_prior = ltd_cur / ta_cur, ltd_prior / ta_prior
        criteria.append(("Apalancamiento reducido", lev_cur < lev_prior,
                          f"Deuda LP/Activos actual {lev_cur*100:.1f}% vs anterior {lev_prior*100:.1f}%"))
    else:
        criteria.append(("Apalancamiento reducido", None, "Sin Deuda LP/Activos de 2 años"))

    # 6. Current Ratio mejora
    cr_cur, cr_prior = y.get("current_ratio"), bh.get("current_ratio_prior")
    if cr_cur is not None and cr_prior is not None:
        criteria.append(("Liquidez (Current Ratio) mejora", cr_cur > cr_prior,
                          f"Actual {cr_cur:.2f}x vs anterior {cr_prior:.2f}x"))
    else:
        criteria.append(("Liquidez (Current Ratio) mejora", None, "Sin Current Ratio del año anterior"))

    # 7. Sin nuevas emisiones de acciones (dilución)
    sh_cur, sh_prior = bh.get("shares_out_cur"), bh.get("shares_out_prior")
    if sh_cur is not None and sh_prior is not None and sh_prior > 0:
        dilution_pct = (sh_cur - sh_prior) / sh_prior * 100
        criteria.append(("Sin dilución significativa", dilution_pct <= 2,
                          f"Variación acciones en circulación: {dilution_pct:+.1f}%"))
    else:
        criteria.append(("Sin dilución significativa", None, "Sin histórico de acciones en circulación"))

    # 8. Margen bruto mejora
    gm_cur, gm_prior = bh.get("gross_margin_cur"), bh.get("gross_margin_prior")
    if gm_cur is not None and gm_prior is not None:
        criteria.append(("Margen bruto mejora", gm_cur > gm_prior,
                          f"Actual {gm_cur*100:.1f}% vs anterior {gm_prior*100:.1f}%"))
    else:
        criteria.append(("Margen bruto mejora", None, "Sin margen bruto del año anterior"))

    # 9. Rotación de activos mejora (Revenue / Total Assets)
    rev_cur = y.get("rev_year_cur")
    rev_prior = bh.get("revenue_prior_for_turnover")
    if rev_cur and rev_prior and ta_cur and ta_prior:
        turn_cur, turn_prior = rev_cur / ta_cur, rev_prior / ta_prior
        criteria.append(("Rotación de activos mejora", turn_cur > turn_prior,
                          f"Actual {turn_cur:.2f}x vs anterior {turn_prior:.2f}x"))
    else:
        criteria.append(("Rotación de activos mejora", None, "Sin datos suficientes"))

    evaluable = [c for c in criteria if c[1] is not None]
    score     = sum(1 for c in evaluable if c[1])
    n_eval    = len(evaluable)

    if n_eval == 0:
        level, color = "SIN DATOS", "#64748b"
    else:
        pct = score / n_eval
        if pct >= 0.78:   level, color = "FORTALEZA FINANCIERA ALTA", "#059669"
        elif pct >= 0.44: level, color = "FORTALEZA FINANCIERA MEDIA", "#d97706"
        else:             level, color = "FORTALEZA FINANCIERA BAJA", "#dc2626"

    return {
        "score": score, "n_evaluable": n_eval, "criteria": criteria,
        "level": level, "color": color,
    }


def _calc_health_score(y: dict, profile: dict, bh: dict | None = None) -> tuple[int, list[tuple[str, str]], list[str]]:
    """
    Calcula la salud fundamental (0-100) con umbrales del sector.
    Devuelve (score, breakdown, missing_fields). breakdown es una lista de
    tuplas (texto, color) -- rojo/amarillo/verde según lo buena que sea cada
    métrica concreta. missing_fields lista los campos sin dato real que se
    excluyeron del cálculo (no penalizan como "0").

    bh = balance histórico (fetch_balance_sheet_history), usado para ROIC
    y el chequeo de dilución. Si no se proporciona, ambos criterios se
    marcan como no evaluables sin romper el resto del cálculo.
    """
    bh = bh or {}
    score    = 0
    breakdown = []
    missing_fields = []

    profit_m_raw   = y.get("profit_margin")
    roe_raw        = y.get("roe")
    rev_yoy_raw    = y.get("revenue_yoy")
    earn_yoy_raw   = y.get("earnings_yoy")
    peg            = y.get("peg_ratio")
    debt_eq_raw    = y.get("debt_equity")
    curr_ratio_raw = y.get("current_ratio")
    quick_ratio_raw= y.get("quick_ratio")
    fcf_raw        = y.get("free_cash_flow")
    operating_cf_raw = y.get("operating_cf")
    ni_recent      = y.get("ni_year_cur")   # beneficio neto anual más reciente
    total_debt     = y.get("total_debt")
    total_cash     = y.get("total_cash")
    ebitda         = y.get("ebitda")

    if profit_m_raw is None:   missing_fields.append("Margen neto")
    if roe_raw is None:        missing_fields.append("ROE")
    if rev_yoy_raw is None:    missing_fields.append("Crecimiento ingresos")
    if earn_yoy_raw is None:   missing_fields.append("Crecimiento beneficios")
    if debt_eq_raw is None:    missing_fields.append("Deuda/Equity")
    if curr_ratio_raw is None: missing_fields.append("Current Ratio")
    if quick_ratio_raw is None:missing_fields.append("Quick Ratio")
    if fcf_raw is None:        missing_fields.append("Free Cash Flow")

    profit_m    = profit_m_raw    if profit_m_raw    is not None else 0
    roe         = roe_raw         if roe_raw         is not None else 0
    rev_yoy     = rev_yoy_raw     if rev_yoy_raw     is not None else 0
    earn_yoy    = earn_yoy_raw    if earn_yoy_raw    is not None else 0
    debt_eq     = debt_eq_raw     if debt_eq_raw     is not None else 0
    curr_ratio  = curr_ratio_raw  if curr_ratio_raw  is not None else 0
    quick_ratio = quick_ratio_raw if quick_ratio_raw is not None else 0
    fcf         = fcf_raw         if fcf_raw         is not None else 0

    margin_ok = profile["margin_ok"]
    roe_ok    = profile["roe_ok"]
    peg_ok    = profile["peg_ok"]

    # Margen neto vs benchmark sector (0-16 pts)
    if profit_m >= margin_ok * 2:    pts = 16
    elif profit_m >= margin_ok:      pts = 11
    elif profit_m >= margin_ok * 0.5: pts = 5
    elif profit_m > 0:               pts = 2
    else:                            pts = 0
    score += pts
    breakdown.append((f"Margen neto {profit_m*100:.1f}% (ref. sector >{margin_ok*100:.0f}%): +{pts}/16",
                       _pts_color(pts, 16)))

    # ROE vs benchmark sector (0-8 pts, reducido porque ROIC complementa)
    if roe >= roe_ok * 2:    pts = 8
    elif roe >= roe_ok:      pts = 5.5
    elif roe >= roe_ok * 0.5: pts = 2.5
    elif roe > 0:             pts = 1
    else:                     pts = 0
    score += pts
    breakdown.append((f"ROE {roe*100:.1f}% (ref. sector >{roe_ok*100:.0f}%): +{pts:.1f}/8",
                       _pts_color(pts, 8)))

    # ROIC (0-10 pts, NUEVO) -- mide eficiencia de asignación de capital
    # independiente del apalancamiento, a diferencia del ROE (que se infla
    # con deuda). Se compara contra el coste de capital tipico (~8-10%).
    roic_val, roic_status = _calc_roic(y, bh)
    if roic_val is not None:
        if roic_val >= 0.20:    r_pts = 10
        elif roic_val >= 0.12:  r_pts = 7
        elif roic_val >= 0.08:  r_pts = 4
        elif roic_val >= 0:     r_pts = 1
        else:                   r_pts = 0
        score += r_pts
        breakdown.append((f"ROIC {roic_val*100:.1f}% (capital invertido vs coste ~9%): +{r_pts:.1f}/10",
                           _pts_color(r_pts, 10)))
    else:
        missing_fields.append("ROIC")

    # Crecimiento ingresos ponderado por estabilidad (0-13 pts)
    rev_quarters = y.get("ttm_quarters", [])
    rev_stab_mult, rev_stab_desc = _calc_growth_stability(rev_quarters)
    if rev_yoy >= 30:    pts_base = 13
    elif rev_yoy >= 15:  pts_base = 9.5
    elif rev_yoy >= 8:   pts_base = 6.5
    elif rev_yoy >= 3:   pts_base = 4
    elif rev_yoy >= 0:   pts_base = 1
    else:                pts_base = 0
    pts = round(pts_base * rev_stab_mult, 1)
    score += pts
    breakdown.append((
        f"Crec. ingresos {rev_yoy:.1f}% × estabilidad {rev_stab_desc} (×{rev_stab_mult:.2f}): +{pts:.1f}/13",
        _pts_color(pts, 13)
    ))

    # Crecimiento beneficios ponderado por estabilidad (0-13 pts)
    ni_quarters = y.get("net_income_q", [])
    earn_stab_mult, earn_stab_desc = _calc_growth_stability(ni_quarters)
    if earn_yoy >= 40:   pts_base = 13
    elif earn_yoy >= 20: pts_base = 9.5
    elif earn_yoy >= 10: pts_base = 6.5
    elif earn_yoy >= 0:  pts_base = 4
    else:                pts_base = 0
    pts = round(pts_base * earn_stab_mult, 1)
    score += pts
    breakdown.append((
        f"Crec. beneficios {earn_yoy:.1f}% × estabilidad {earn_stab_desc} (×{earn_stab_mult:.2f}): +{pts:.1f}/13",
        _pts_color(pts, 13)
    ))

    # PEG vs benchmark sector (0-12 pts)
    if peg:
        if peg <= peg_ok * 0.5:   pts = 12
        elif peg <= peg_ok * 0.75: pts = 8.5
        elif peg <= peg_ok:        pts = 5.5
        elif peg <= peg_ok * 1.5:  pts = 2
        else:                      pts = 0
        score += pts
        breakdown.append((f"PEG {peg:.2f} (ref. sector <{peg_ok}): +{pts:.1f}/12", _pts_color(pts, 12)))

    # -- Balance y Liquidez ampliado (0-20 pts) --------------------------
    # 6 sub-métricas: FCF, Current Ratio, Quick Ratio, Debt/Equity,
    # Net Debt/EBITDA y Dilución (NUEVA).
    b_pts = 0

    # FCF positivo, con desglose CFO/CAPEX (0-3)
    # CAPEX = CFO - FCF (relación estándar: FCF = CFO - CAPEX). No penaliza
    # con la misma dureza un FCF negativo causado por CAPEX de expansión
    # (fábricas nuevas, centros de datos, ampliación de capacidad — negocio
    # operativo sano, solo invirtiendo fuerte) que uno causado por quema de
    # caja operativa real (CFO también negativo — el negocio del día a día
    # no genera caja, señal mucho más preocupante).
    operating_cf = operating_cf_raw if operating_cf_raw is not None else None
    capex_implied = None
    if operating_cf is not None and fcf_raw is not None:
        capex_implied = operating_cf - fcf_raw   # CAPEX ≈ CFO − FCF

    if fcf > 0:
        fcf_pts = 3
        fcf_label = "positivo"
    elif operating_cf is not None and operating_cf > 0:
        fcf_pts = 1.5   # crédito parcial: quema caja por expansión, no por operativa débil
        fcf_label = "negativo por CAPEX de expansión (CFO positivo)"
    else:
        fcf_pts = 0     # CFO también negativo/desconocido: quema de caja operativa real
        fcf_label = "negativo (operativa débil o sin datos de CFO)"

    b_pts += fcf_pts
    fcf_detail = f"Free Cash Flow {fcf_label}: +{fcf_pts:.1f}/3"
    if operating_cf is not None:
        fcf_detail += f" (CFO: {operating_cf/1e6:,.0f}M"
        if capex_implied is not None:
            fcf_detail += f", CAPEX≈{capex_implied/1e6:,.0f}M"
        fcf_detail += ")"
    breakdown.append((fcf_detail, _pts_color(fcf_pts, 3)))

    # Current Ratio (0-2.5)
    if curr_ratio >= 1.5:   cr_pts = 2.5
    elif curr_ratio >= 1:   cr_pts = 1.25
    else:                   cr_pts = 0
    b_pts += cr_pts
    breakdown.append((f"Current Ratio {curr_ratio:.2f}×: +{cr_pts:.1f}/2.5", _pts_color(cr_pts, 2.5)))

    # Quick Ratio (0-3)
    if quick_ratio_raw is not None:
        if quick_ratio >= 1.2:   qr_pts = 3
        elif quick_ratio >= 0.8: qr_pts = 1.9
        elif quick_ratio >= 0.5: qr_pts = 0.75
        else:                    qr_pts = 0
        b_pts += qr_pts
        breakdown.append((f"Quick Ratio {quick_ratio:.2f}×: +{qr_pts:.1f}/3", _pts_color(qr_pts, 3)))

    # Debt/Equity (0-2.5)
    if debt_eq < 50:      de_pts = 2.5
    elif debt_eq < 100:   de_pts = 1.25
    else:                 de_pts = 0
    b_pts += de_pts
    breakdown.append((f"Debt/Equity {debt_eq:.0f}%: +{de_pts:.1f}/2.5", _pts_color(de_pts, 2.5)))

    # Net Debt / EBITDA (0-5)
    net_debt_ebitda = None
    if total_debt is not None and ebitda and ebitda > 0:
        net_debt = total_debt - (total_cash or 0)
        net_debt_ebitda = net_debt / ebitda
        if net_debt_ebitda <= 1:      nde_pts = 5
        elif net_debt_ebitda <= 2:    nde_pts = 3.75
        elif net_debt_ebitda <= 4:    nde_pts = 1.5
        else:                          nde_pts = 0
        b_pts += nde_pts
        breakdown.append((
            f"Net Debt/EBITDA {net_debt_ebitda:.2f}×: +{nde_pts:.1f}/5",
            _pts_color(nde_pts, 5)
        ))
    else:
        missing_fields.append("Net Debt/EBITDA")

    # Dilución (0-4, NUEVO) -- variación de acciones en circulación vs año
    # anterior. Emitir acciones nuevas para financiar pérdidas diluye a los
    # accionistas actuales aunque el negocio "crezca" en ingresos.
    sh_cur, sh_prior = bh.get("shares_out_cur"), bh.get("shares_out_prior")
    if sh_cur is not None and sh_prior is not None and sh_prior > 0:
        dilution_pct = (sh_cur - sh_prior) / sh_prior * 100
        if dilution_pct <= 1:     dil_pts = 4
        elif dilution_pct <= 3:   dil_pts = 2.5
        elif dilution_pct <= 8:   dil_pts = 1
        else:                      dil_pts = 0
        b_pts += dil_pts
        breakdown.append((
            f"Dilución (acciones en circulación): {dilution_pct:+.1f}% vs año anterior: +{dil_pts:.1f}/4",
            _pts_color(dil_pts, 4)
        ))
    else:
        missing_fields.append("Dilución (histórico acciones)")

    score += b_pts

    # Calidad del beneficio: FCF / Beneficio neto anual (0-8 pts)
    fcf_quality = None
    if fcf_raw is not None and ni_recent and ni_recent > 0:
        fcf_quality = fcf_raw / ni_recent
        if fcf_quality >= 1.0:    q_pts = 8
        elif fcf_quality >= 0.9:  q_pts = 6.5
        elif fcf_quality >= 0.5:  q_pts = 4
        elif fcf_quality >= 0:    q_pts = 1.5
        else:                     q_pts = 0
        score += q_pts
        breakdown.append((f"Calidad beneficio FCF/NI {fcf_quality:.2f}×: +{q_pts:.1f}/8",
                           _pts_color(q_pts, 8)))
    else:
        missing_fields.append("Calidad del beneficio (FCF/NI)")

    score = min(100, round(score))
    if missing_fields:
        breakdown.append((f"⚠ Datos no disponibles (excluidos del cálculo, no penalizados): {', '.join(missing_fields)}",
                           "#64748b"))
    return score, breakdown, missing_fields


# ─── Evaluación final ─────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# VALORACIÓN FINAL — síntesis de los 4 sistemas (Salud Fundamental, Piotroski,
# Diagnóstico General, Señal de Entrada) en un único veredicto accionable.
# ─────────────────────────────────────────────────────────────────────────────
# Diseño: en vez de promediar los 4 sistemas (que comparten inputs entre sí y
# darían lugar a doble contabilización — ej. FCF positivo puntúa en Salud
# Fundamental Y en Piotroski), se agrupan en 3 dimensiones independientes:
#   CALIDAD (Salud Fundamental + Piotroski combinados) · PRECIO (Diagnóstico
#   General) · TIMING (Señal de Entrada). Cada una con 3 niveles, dando 27
#   combinaciones posibles con un veredicto y mensaje explícito para cada una
#   — nunca una media numérica sin matices.

def _classify_calidad(health_score: int, piotroski: dict) -> tuple[str, float]:
    """
    Combina Salud Fundamental (0-100) y Piotroski (X/N evaluable) en una
    única dimensión de Calidad (alta/media/baja). Si Piotroski no tiene
    suficientes criterios evaluables (<5 de 9) para ser fiable, se usa solo
    Salud Fundamental. Devuelve (nivel, score_compuesto) para transparencia.
    """
    pio_n = piotroski.get("n_evaluable", 0) if piotroski else 0
    pio_score = piotroski.get("score", 0) if piotroski else 0
    pio_pct = (pio_score / pio_n * 100) if pio_n > 0 else None

    if pio_pct is not None and pio_n >= 5:
        composite = health_score * 0.6 + pio_pct * 0.4
    else:
        composite = health_score

    if composite >= 65:
        return "alta", composite
    elif composite >= 40:
        return "media", composite
    else:
        return "baja", composite


def _classify_precio(diag_base: str) -> str:
    """Mapea el diagnóstico de 7 niveles a 3 categorías de Precio."""
    barata_set = {"MUY INFRAVALORADA", "INFRAVALORADA", "LIGERAMENTE INFRAVALORADA"}
    cara_set   = {"EN OBSERVACIÓN", "SOBREVALORADA", "MUY SOBREVALORADA"}
    if diag_base in barata_set:
        return "barata"
    elif diag_base == "PRECIO JUSTO":
        return "justa"
    elif diag_base in cara_set:
        return "cara"
    return "sin_datos"


def _classify_timing(signal_level: str) -> str:
    """Mapea el nivel de Señal de Entrada a 3 categorías de Timing."""
    if signal_level in ("ENTRADA IDEAL", "ENTRADA POSIBLE"):
        return "bueno"
    elif signal_level == "VIGILAR":
        return "neutro"
    elif signal_level == "NO ES MOMENTO":
        return "malo"
    return "sin_datos"


def calc_entry_exit_plan(y: dict, ev: dict, tech: dict | None) -> dict | None:
    """
    Plan de entrada (3 niveles escalonados con % de capital) y plan de
    salida (take profit + stop loss), combinando datos técnicos que la app
    ya calcula por separado — Soporte histórico, Fibonacci, MM50/MM200 —
    en un plan accionable único, en vez de dejar al usuario la tarea de
    cruzarlos manualmente.

    Por qué varios niveles y no uno solo: nadie sabe hasta dónde puede caer
    una acción antes de girar al alza. Escalonar la entrada permite
    promediar el coste: si cae más de lo esperado, se compra más barato con
    el capital reservado para los niveles inferiores.

    El reparto de capital entre niveles depende de la Calidad (Salud
    Fundamental + Piotroski, misma clasificación que en Valoración Final):
    empresas de más calidad reciben más peso en el nivel más cercano al
    precio actual (más confianza en que no caerá mucho más antes de girar);
    empresas de calidad baja reciben más peso en los niveles inferiores
    (más cautela, se exige más confirmación de que ha tocado suelo antes de
    comprometer capital importante).
    """
    price = y.get("price")
    if not price or not tech or tech.get("error"):
        return None

    health_score = ev.get("health_score", 0)
    piotroski    = ev.get("piotroski", {})
    calidad, _   = _classify_calidad(health_score, piotroski)

    CAPITAL_SPLITS = {
        "alta":  (50, 30, 20),
        "media": (35, 35, 30),
        "baja":  (20, 35, 45),
    }
    splits = CAPITAL_SPLITS.get(calidad, CAPITAL_SPLITS["media"])

    # ── Recopilar candidatos a soporte, todos por debajo del precio actual
    candidates = []
    mm50  = tech.get("mm50")
    mm200 = tech.get("mm200")
    if mm50 and mm50 < price:
        candidates.append(("MM50", mm50))
    if mm200 and mm200 < price:
        candidates.append(("MM200", mm200))

    fib_data = tech.get("fibonacci")
    if fib_data and fib_data.get("levels"):
        for label in ("50.0%", "61.8%", "78.6%"):
            lvl = fib_data["levels"].get(label)
            if lvl and lvl < price:
                candidates.append((f"Fibonacci {label}", lvl))

    support_data = tech.get("historical_support")
    if support_data and support_data.get("level") and support_data["level"] < price:
        candidates.append((f"Soporte histórico ({support_data['touches']}× rebotes)", support_data["level"]))

    if not candidates:
        return None

    # Ordenar de más cercano al precio (mayor) a más profundo (menor)
    candidates.sort(key=lambda c: c[1], reverse=True)

    # Seleccionar 3 niveles con separación mínima del 2% entre ellos, para
    # que no queden pegados si varias fuentes coinciden casi en el mismo precio
    MIN_GAP = 0.02
    levels = [candidates[0]]
    for label, lvl in candidates[1:]:
        if len(levels) >= 3:
            break
        if (levels[-1][1] - lvl) / levels[-1][1] >= MIN_GAP:
            levels.append((label, lvl))

    # Si no hay suficientes niveles distintos, completar con % fijos del
    # precio actual como aproximación razonable (mejor un plan con 3 niveles
    # aproximados que uno incompleto)
    while len(levels) < 3:
        fallback_pct = [0.97, 0.92, 0.85][len(levels)]
        levels.append((f"Aproximación (-{(1-fallback_pct)*100:.0f}%)", price * fallback_pct))

    entry_plan = [
        {"label": lbl, "price": round(lvl, 2), "capital_pct": splits[i]}
        for i, (lbl, lvl) in enumerate(levels[:3])
    ]

    # Precio medio de compra si se ejecutan los 3 niveles con el capital
    # indicado en cada uno (media ponderada por %, no media simple)
    avg_entry_price = round(
        sum(lvl["price"] * lvl["capital_pct"] for lvl in entry_plan) / 100, 2
    )

    # ── Plan de salida ────────────────────────────────────────────────────
    fair_value = ev.get("fair_value")
    exit_plan = None
    stop_loss = None
    stop_loss_source = None
    stop_loss_confidence = None
    if fair_value and fair_value > entry_plan[0]["price"]:
        # Objetivos intermedios como fracciones del camino hacia el Valor
        # Objetivo desde el nivel de entrada más cercano al precio actual
        entry_ref = entry_plan[0]["price"]
        camino = fair_value - entry_ref
        n_metodos = len(ev.get("methods_used", []))
        exit_plan = [
            {"label": "Objetivo 1", "price": round(entry_ref + camino * 0.5, 2), "capital_pct": 30,
             "explanation": ("50% del camino desde el Nivel 1 de entrada hasta el Valor Objetivo — "
                              "asegura parte de la ganancia pronto sin esperar a que se cumpla toda la tesis.")},
            {"label": "Objetivo 2", "price": round(entry_ref + camino * 0.8, 2), "capital_pct": 40,
             "explanation": ("80% del camino hacia el Valor Objetivo — la mayor parte del capital se "
                              "libera aquí, cuando ya se ha capturado casi toda la revalorización esperada.")},
            {"label": "Objetivo 3 (Valor Objetivo)", "price": round(fair_value, 2), "capital_pct": 30,
             "explanation": (f"Valor Objetivo calculado por el motor de valoración (mediana de "
                              f"{n_metodos} método{'s' if n_metodos != 1 else ''} aplicables a este sector, "
                              f"ver 'Cálculo del Valor Objetivo' más abajo) — el precio donde la tesis "
                              f"fundamental se considera cumplida.")},
        ]

        # Stop Loss: NO se ancla al "nivel que caiga en 3ª posición por
        # distancia" (podía ser cualquier tipo de candidato, incluida una
        # simple media móvil sin memoria de mercado real) — se prioriza
        # explícitamente por fiabilidad estructural, buscando entre TODOS
        # los candidatos disponibles (no solo los 3 elegidos para el plan
        # de entrada) el más fiable que esté a un precio igual o inferior
        # al Nivel 3, para que el Stop Loss nunca quede por encima de
        # ningún nivel de entrada planeado (si no, se activaría el stop
        # antes incluso de alcanzar los niveles de compra más profundos).
        nivel3_price = entry_plan[2]["price"]

        def _es_soporte_historico(lbl): return lbl.startswith("Soporte histórico")
        def _es_fibonacci_profundo(lbl): return "78.6%" in lbl or "61.8%" in lbl
        def _es_mm200(lbl): return lbl == "MM200"

        RELIABILITY_ORDER = [
            ("Alta — nivel con evidencia de rebotes reales", _es_soporte_historico),
            ("Media-alta — retroceso técnico profundo reconocido", _es_fibonacci_profundo),
            ("Moderada — media móvil simple, sin memoria de mercado real", _es_mm200),
        ]

        sl_source = None
        for confidence_txt, check in RELIABILITY_ORDER:
            matches = [(lbl, lvl) for lbl, lvl in candidates if check(lbl) and lvl <= nivel3_price]
            if matches:
                # Si hay varios que cumplen, el más profundo (más conservador)
                sl_source = min(matches, key=lambda x: x[1])
                stop_loss_confidence = confidence_txt
                break

        if sl_source is None:
            # Ningún candidato de mayor fiabilidad disponible por debajo del
            # Nivel 3 — fallback al comportamiento anterior, pero marcado
            # honestamente como de menor confianza en vez de presentarlo
            # igual que un nivel bien fundamentado
            sl_source = (entry_plan[2]["label"], nivel3_price)
            stop_loss_confidence = "Moderada — sin soporte estructural más fiable disponible por debajo de este nivel"

        stop_loss_source = sl_source[0]
        # Margen de seguridad adicional del 5% por debajo, para no saltar
        # por un simple pico de ruido de un día que perfore el nivel y
        # rebote enseguida
        stop_loss = round(sl_source[1] * 0.95, 2)

    return {
        "calidad": calidad,
        "entry_plan": entry_plan,
        "avg_entry_price": avg_entry_price,
        "exit_plan": exit_plan,
        "stop_loss": stop_loss,
        "stop_loss_source": stop_loss_source,
        "stop_loss_confidence": stop_loss_confidence,
        "current_price": price,
    }


def render_entry_exit_plan(plan: dict | None, currency: str = "USD", fx_rate: float | None = None):
    """Renderiza el plan de entrada/salida combinado."""
    _section("PLAN DE ENTRADA Y SALIDA SUGERIDO")

    if not plan:
        st.markdown(
            '<div class="metric-card"><span style="color:#64748b;">'
            'Sin datos técnicos suficientes para generar un plan de niveles '
            '(RSI, soportes o Fibonacci no disponibles para este ticker).</span></div>',
            unsafe_allow_html=True
        )
        return

    def _eur(val):
        """Conversión a EUR entre paréntesis, igual que en el resto de la app."""
        if fx_rate and currency == "USD":
            return f' <span style="color:#94a3b8;font-size:0.85em;">(€{val*fx_rate:,.2f})</span>'
        return ""

    calidad_labels = {"alta": "Alta", "media": "Media", "baja": "Baja"}

    price_now = plan["current_price"]
    st.markdown(
        '<div style="display:flex;justify-content:space-between;align-items:baseline;'
        'padding:0.5rem 0.7rem;background:#eff6ff;border-radius:6px;margin-bottom:0.7rem;">'
        '<span style="font-size:0.78rem;color:#64748b;">Precio actual de cotización</span>'
        f'<span style="font-family:\'IBM Plex Mono\',monospace;font-size:1rem;font-weight:700;color:#0284c7;">'
        f'{currency} {price_now:,.2f}{_eur(price_now)}</span>'
        '</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        f'<div style="font-size:0.72rem;color:#64748b;margin-bottom:0.6rem;">'
        f'Reparto de capital ajustado a Calidad <b style="color:#0284c7;">'
        f'{calidad_labels.get(plan["calidad"], plan["calidad"])}</b> — '
        f'{"más peso cerca del precio actual (mayor confianza)" if plan["calidad"]=="alta" else "más peso en niveles profundos (más cautela, se exige confirmación)" if plan["calidad"]=="baja" else "reparto equilibrado"}.</div>',
        unsafe_allow_html=True
    )

    entry_html = '<div style="font-size:0.7rem;color:#059669;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.5rem;">Plan de Entrada</div>'
    for i, lvl in enumerate(plan["entry_plan"]):
        dist_pct = (lvl["price"] - price_now) / price_now * 100
        entry_html += (
            '<div style="display:flex;justify-content:space-between;align-items:center;'
            'padding:0.5rem 0.7rem;background:#f4f6f9;border-radius:6px;margin-bottom:0.4rem;">'
            f'<div><span style="font-weight:600;color:#0f172a;">Nivel {i+1}</span> '
            f'<span style="font-size:0.72rem;color:#64748b;">— {lvl["label"]}</span></div>'
            f'<div style="text-align:right;">'
            f'<span style="font-family:\'IBM Plex Mono\',monospace;color:#0f172a;font-weight:600;">'
            f'{currency} {lvl["price"]:,.2f}{_eur(lvl["price"])}</span> '
            f'<span style="font-size:0.72rem;color:#dc2626;">({dist_pct:+.1f}%)</span><br>'
            f'<span style="background:#d1fae5;color:#059669;padding:1px 8px;border-radius:4px;'
            f'font-size:0.72rem;font-weight:700;">{lvl["capital_pct"]}% capital</span>'
            '</div></div>'
        )
    if plan.get("avg_entry_price"):
        entry_html += (
            '<div style="display:flex;justify-content:space-between;align-items:center;'
            'padding:0.5rem 0.7rem;background:#ecfdf5;border-radius:6px;margin-top:0.3rem;'
            'border:1px dashed #059669;">'
            '<span style="color:#059669;font-weight:700;">Precio medio si se ejecutan los 3 niveles</span>'
            f'<span style="font-family:\'IBM Plex Mono\',monospace;color:#059669;font-weight:700;">'
            f'{currency} {plan["avg_entry_price"]:,.2f}{_eur(plan["avg_entry_price"])}</span>'
            '</div>'
        )

    exit_html = ""
    if plan["exit_plan"]:
        exit_html = '<div style="font-size:0.7rem;color:#0284c7;text-transform:uppercase;letter-spacing:0.05em;margin:0.8rem 0 0.5rem 0;">Plan de Salida</div>'
        for obj in plan["exit_plan"]:
            upside_pct = (obj["price"] - price_now) / price_now * 100
            exit_html += (
                '<div style="padding:0.5rem 0.7rem;background:#eff6ff;border-radius:6px;margin-bottom:0.4rem;">'
                '<div style="display:flex;justify-content:space-between;align-items:center;">'
                f'<span style="color:#0f172a;font-weight:600;">{obj["label"]}</span>'
                f'<div style="text-align:right;">'
                f'<span style="font-family:\'IBM Plex Mono\',monospace;color:#0284c7;font-weight:600;">'
                f'{currency} {obj["price"]:,.2f}{_eur(obj["price"])}</span> '
                f'<span style="font-size:0.72rem;color:#059669;font-weight:700;">(+{upside_pct:.1f}% upside)</span><br>'
                f'<span style="background:#dbeafe;color:#0284c7;padding:1px 8px;border-radius:4px;'
                f'font-size:0.72rem;font-weight:700;">{obj["capital_pct"]}% capital</span></div>'
                '</div>'
                f'<div style="font-size:0.68rem;color:#64748b;margin-top:0.3rem;">{obj.get("explanation","")}</div>'
                '</div>'
            )
        if plan["stop_loss"]:
            sl_dist = (plan["stop_loss"] - price_now) / price_now * 100
            sl_source_txt = plan.get("stop_loss_source", "")
            sl_confidence_txt = plan.get("stop_loss_confidence", "")
            exit_html += (
                '<div style="padding:0.5rem 0.7rem;background:#fee2e2;border-radius:6px;margin-top:0.3rem;">'
                '<div style="display:flex;justify-content:space-between;align-items:center;">'
                '<span style="color:#dc2626;font-weight:700;">Stop Loss</span>'
                f'<span style="font-family:\'IBM Plex Mono\',monospace;color:#dc2626;font-weight:700;">'
                f'{currency} {plan["stop_loss"]:,.2f}{_eur(plan["stop_loss"])} ({sl_dist:+.1f}%)</span>'
                '</div>'
                f'<div style="font-size:0.68rem;color:#991b1b;margin-top:0.3rem;">'
                f'Anclado a: <b>{sl_source_txt}</b> (con 5% de margen adicional) · Fiabilidad: {sl_confidence_txt}</div>'
                '</div>'
            )

    st.markdown(
        f'<div class="metric-card">{entry_html}{exit_html}'
        '<div style="font-size:0.68rem;color:#94a3b8;margin-top:0.7rem;">'
        'Plan orientativo derivado de Soporte histórico, Fibonacci y medias móviles ya calculados, '
        'combinados con el Valor Objetivo. No es una recomendación de inversión. El Stop Loss se '
        'prioriza por fiabilidad estructural (Soporte histórico > Fibonacci profundo > MM200), no '
        'por cuál nivel esté simplemente más cerca — la fiabilidad indicada refleja cuánta confianza '
        'da ese tipo de nivel concreto, no una garantía.</div>'
        '</div>',
        unsafe_allow_html=True
    )


# Tabla de las 27 combinaciones: (calidad, precio, timing) -> (icono, nivel, color, mensaje)
_VALORACION_FINAL_TABLA = {
    ("alta", "barata", "bueno"):   ("🟢🟢", "COMPRAR YA", "#059669",
        "Oportunidad única: fundamentales excelentes, precio con descuento significativo y momento técnico favorable."),
    ("alta", "barata", "neutro"):  ("🟢", "COMPRAR", "#16a34a",
        "Buena oportunidad: fundamentales y precio alineados, vigilar el timing antes de entrar con todo."),
    ("alta", "barata", "malo"):    ("🟡", "VIGILAR", "#d97706",
        "Fundamentales y precio excelentes, pero mal momento técnico — esperar confirmación antes de entrar."),
    ("alta", "justa", "bueno"):    ("🟡", "A LA ESPERA", "#d97706",
        "En precio y momento justo: buena empresa, sin margen de seguridad en la valoración."),
    ("alta", "justa", "neutro"):   ("🟡", "A LA ESPERA", "#d97706",
        "Sin urgencia: esperar mejor precio o una señal técnica más clara."),
    ("alta", "justa", "malo"):     ("🟡", "A LA ESPERA", "#d97706",
        "Sin catalizador de precio ni de timing — no hay prisa por entrar."),
    ("alta", "cara", "bueno"):     ("🟠", "PRECAUCIÓN", "#ea580c",
        "Buen momentum pero valoración exigente — esperar corrección antes de entrar."),
    ("alta", "cara", "neutro"):    ("🟠", "PRECAUCIÓN", "#ea580c",
        "Esperar mejor precio, sin señal técnica que justifique entrar ya."),
    ("alta", "cara", "malo"):      ("🔴", "EVITAR POR AHORA", "#dc2626",
        "Buena empresa, pero cara y en mal momento — esperar corrección clara."),

    ("media", "barata", "bueno"):  ("🟢🟡", "COMPRA POSIBLE", "#65a30d",
        "Fundamentales aceptables con buen precio y timing — vigilar de cerca, posición moderada."),
    ("media", "barata", "neutro"): ("🟡", "PRECAUCIÓN LEVE", "#d97706",
        "Precio atractivo pero fundamentales no excepcionales — considerar posición reducida."),
    ("media", "barata", "malo"):   ("🟠", "PRECAUCIÓN", "#ea580c",
        "Barata sin confirmación técnica ni fundamentales sólidos — riesgo real de trampa de valor."),
    ("media", "justa", "bueno"):   ("🟡", "NEUTRAL", "#d97706",
        "Sin ventaja clara de precio ni calidad destacable — el buen timing no basta por sí solo."),
    ("media", "justa", "neutro"):  ("🟡", "NEUTRAL", "#d97706",
        "Sin ningún factor claramente a favor — mejor esperar."),
    ("media", "justa", "malo"):    ("🔴", "EVITAR POR AHORA", "#dc2626",
        "Sin argumentos de calidad, precio ni timing a favor."),
    ("media", "cara", "bueno"):    ("🟠", "PRECAUCIÓN", "#ea580c",
        "Buen timing técnico, pero se paga de más por fundamentales solo aceptables."),
    ("media", "cara", "neutro"):   ("🔴", "EVITAR POR AHORA", "#dc2626",
        "Cara y con fundamentales mediocres, sin señal técnica que lo compense."),
    ("media", "cara", "malo"):     ("🔴", "EVITAR", "#dc2626",
        "Combinación desfavorable en las tres dimensiones."),

    ("baja", "barata", "bueno"):   ("🟠", "PRECAUCIÓN", "#ea580c",
        "Posible value trap: barata por una razón, aunque el timing técnico sea favorable."),
    ("baja", "barata", "neutro"):  ("🔴", "PRECAUCIÓN ALTA", "#dc2626",
        "Fundamentales débiles y sin confirmación técnica — alto riesgo de trampa de valor."),
    ("baja", "barata", "malo"):    ("🔴", "EVITAR", "#dc2626",
        "Value trap probable, sin ningún catalizador que lo revierta."),
    ("baja", "justa", "bueno"):    ("🔴", "EVITAR POR AHORA", "#dc2626",
        "Fundamentales débiles no compensados por el precio, pese al buen timing."),
    ("baja", "justa", "neutro"):   ("🔴", "EVITAR", "#dc2626",
        "Fundamentales débiles y sin ninguna ventaja de precio."),
    ("baja", "justa", "malo"):     ("🔴🔴", "EVITAR", "#991b1b",
        "Sin ningún argumento a favor en ninguna dimensión."),
    ("baja", "cara", "bueno"):     ("🔴", "EVITAR", "#dc2626",
        "Fundamentales débiles y cara — el buen timing no compensa el riesgo de fondo."),
    ("baja", "cara", "neutro"):    ("🔴🔴", "EVITAR", "#991b1b",
        "Mala combinación de calidad y precio."),
    ("baja", "cara", "malo"):      ("🔴🔴", "EVITAR", "#991b1b",
        "Peor combinación posible: mala calidad, cara y mal momento técnico."),
}


def calc_valoracion_final(ev: dict, signal: dict) -> dict:
    """
    Sintetiza Salud Fundamental, Piotroski, Diagnóstico General y Señal de
    Entrada en un único veredicto accionable, usando la tabla de 27
    combinaciones (3 niveles × 3 dimensiones). Nunca es una media numérica:
    siempre un mensaje explícito y auditable con las 3 clasificaciones que
    lo componen, para que se pueda ver exactamente de dónde sale.
    """
    health_score = ev.get("health_score", 0)
    piotroski    = ev.get("piotroski", {})
    diag_base    = ev.get("diag_base", "")
    signal_level = signal.get("level", "")

    calidad, calidad_score = _classify_calidad(health_score, piotroski)
    precio  = _classify_precio(diag_base)
    timing  = _classify_timing(signal_level)

    # Fiabilidad: si alguna dimensión no tiene datos suficientes, el
    # veredicto se marca explícitamente como de fiabilidad reducida
    reliability_ok = precio != "sin_datos" and timing != "sin_datos"

    key = (calidad, precio, timing)
    if key in _VALORACION_FINAL_TABLA:
        icon, level, color, message = _VALORACION_FINAL_TABLA[key]
    else:
        # Combinación sin datos suficientes en alguna dimensión — no debería
        # ocurrir salvo precio/timing "sin_datos", pero se cubre por seguridad
        icon, level, color = "⚪", "SIN DATOS SUFICIENTES", "#64748b"
        message = "No se pudo determinar un veredicto fiable — faltan datos de precio objetivo o de señal técnica."

    return {
        "icon": icon, "level": level, "color": color, "message": message,
        "calidad": calidad, "calidad_score": round(calidad_score, 1),
        "precio": precio, "timing": timing,
        "reliability_ok": reliability_ok,
    }


def render_valoracion_final(vf: dict, ev: dict, signal: dict):
    """
    Renderiza el veredicto de Valoración Final con las 3 dimensiones que lo
    componen siempre visibles — nunca solo el mensaje final sin auditoría.
    """
    _section("VALORACIÓN FINAL")

    labels_calidad = {"alta": "Alta", "media": "Media", "baja": "Baja"}
    labels_precio  = {"barata": "Barata", "justa": "Precio justo", "cara": "Cara", "sin_datos": "Sin datos"}
    labels_timing  = {"bueno": "Buen timing", "neutro": "Timing neutro", "malo": "Mal timing", "sin_datos": "Sin datos"}

    if not vf.get("reliability_ok", True):
        st.markdown(
            '<div style="background:#fffbeb;border:1px solid #d97706;border-left:4px solid #d97706;'
            'border-radius:6px;padding:0.6rem 0.9rem;margin-bottom:0.8rem;font-size:0.78rem;'
            'color:#92400e;line-height:1.6;">'
            '⚠ FIABILIDAD REDUCIDA: falta el Valor Objetivo o la Señal de Entrada no se pudo calcular '
            'con suficientes datos — el veredicto puede no ser representativo.</div>',
            unsafe_allow_html=True
        )

    st.markdown(
        f'<div class="verdict-box" style="border-left-color:{vf["color"]};">'
        '<div class="verdict-title">VEREDICTO — SÍNTESIS DE LOS 4 SISTEMAS</div>'
        '<div style="display:flex;align-items:center;gap:0.7rem;margin-bottom:0.6rem;">'
        f'<span style="font-size:1.6rem;">{vf["icon"]}</span>'
        f'<span class="verdict-main" style="color:{vf["color"]};font-size:1.3rem;">{vf["level"]}</span>'
        '</div>'
        f'<div style="font-size:0.9rem;color:#334155;line-height:1.6;margin-bottom:1rem;">{vf["message"]}</div>'
        '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:0.6rem;">'
        '<div style="background:#ffffff;border-radius:6px;padding:0.6rem 0.8rem;border:1px solid #e2e8f0;">'
        '<div style="font-size:0.65rem;color:#64748b;text-transform:uppercase;">Calidad</div>'
        f'<div style="font-size:0.9rem;color:#0f172a;font-weight:600;">{labels_calidad.get(vf["calidad"], vf["calidad"])}</div>'
        f'<div style="font-size:0.68rem;color:#94a3b8;">Score compuesto: {vf["calidad_score"]}/100</div>'
        '</div>'
        '<div style="background:#ffffff;border-radius:6px;padding:0.6rem 0.8rem;border:1px solid #e2e8f0;">'
        '<div style="font-size:0.65rem;color:#64748b;text-transform:uppercase;">Precio</div>'
        f'<div style="font-size:0.9rem;color:#0f172a;font-weight:600;">{labels_precio.get(vf["precio"], vf["precio"])}</div>'
        f'<div style="font-size:0.68rem;color:#94a3b8;">Diagnóstico: {ev.get("diag_base","N/A")}</div>'
        '</div>'
        '<div style="background:#ffffff;border-radius:6px;padding:0.6rem 0.8rem;border:1px solid #e2e8f0;">'
        '<div style="font-size:0.65rem;color:#64748b;text-transform:uppercase;">Timing</div>'
        f'<div style="font-size:0.9rem;color:#0f172a;font-weight:600;">{labels_timing.get(vf["timing"], vf["timing"])}</div>'
        f'<div style="font-size:0.68rem;color:#94a3b8;">Señal: {signal.get("level","N/A")}</div>'
        '</div>'
        '</div>'
        '<div style="font-size:0.68rem;color:#94a3b8;margin-top:0.9rem;">'
        'Calidad = combinación de Salud Fundamental y Piotroski F-Score (60%/40% si Piotroski tiene '
        '≥5 criterios evaluables, si no solo Salud Fundamental) · Precio = Diagnóstico General · '
        'Timing = Señal de Entrada. Nunca es una media directa de los 4 sistemas — se agrupan así '
        'para evitar contar dos veces el mismo dato subyacente (ej. FCF positivo puntúa tanto en '
        'Salud Fundamental como en Piotroski).</div>'
        '</div>',
        unsafe_allow_html=True
    )


def _evaluate(y: dict, bh: dict | None = None, mult_data: dict | None = None) -> dict:
    """Diagnóstico completo ajustado al sector y a los tipos de interés actuales."""
    bh = bh or {}

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

    # ── Salud fundamental (incluye ROIC y Dilución si hay balance histórico)
    health_score, health_breakdown, health_missing = _calc_health_score(y, profile, bh)

    # ── Piotroski F-Score (0-9, herramienta independiente de fortaleza
    # financiera — no se mezcla en el score de Salud Fundamental) ─────────
    piotroski = calc_piotroski_score(y, bh)

    # ── Valor objetivo ───────────────────────────────────────────────────
    fair_value, methods_used, targets_range, fair_value_single = _calc_fair_value(y, profile, bh, mult_data)

    # Flag informativo: ¿se usó el fallback hyper-growth (EV/Sales)?
    is_hyper_growth = any("hyper-growth" in m for m in methods_used)

    # Regla del 40 — solo relevante/calculada cuando se usa el fallback
    # hyper-growth, para auditar si ese crecimiento es sano o destruye valor
    rule_of_40 = _calc_rule_of_40(y) if is_hyper_growth else None

    # ── Prima/descuento vs histórico 52W ─────────────────────────────────
    mid_52  = (week52_high + week52_low) / 2 if week52_high and week52_low else None
    vs_hist = ((price - mid_52) / mid_52 * 100) if mid_52 else None

    # ── Upside ───────────────────────────────────────────────────────────
    upside = ((fair_value - price) / price * 100) if fair_value else None

    # ── Diagnóstico — 7 niveles, con umbrales ajustados por sector ─────────
    # ANTES: los umbrales (30/12/3/-3/-15/-30) eran fijos para todas las
    # empresas pese a que el comentario original afirmaba que se ajustaban
    # por sector — pe_ref/pe_high se calculaban pero nunca se usaban en esta
    # clasificación (código muerto). AHORA sí se ajustan de verdad: sectores
    # con más amplitud de valoración histórica (ratio pe_high/pe_fair alto,
    # p.ej. Technology) requieren un upside/downside MAYOR para considerarse
    # "muy infra/sobrevalorados", porque sus múltiplos oscilan más de forma
    # normal. Sectores estables (p.ej. Utilities) usan bandas más estrechas.
    pe_ref  = profile["pe_fair"]
    pe_high = profile["pe_high"]

    sector_vol_ratio    = pe_high / pe_ref if pe_ref else 1.65
    _BASELINE_VOL_RATIO = 1.65   # media aproximada entre todos los sectores
    threshold_factor    = max(0.85, min(1.20, sector_vol_ratio / _BASELINE_VOL_RATIO))

    t_muy_infra  = 30 * threshold_factor
    t_infra      = 12 * threshold_factor
    t_lig_infra  = 3  * threshold_factor
    t_justo      = 3  * threshold_factor   # banda simétrica alrededor de 0
    t_observ     = 15 * threshold_factor
    t_sobreval   = 30 * threshold_factor

    if upside is None:
        diag       = "SIN DATOS SUFICIENTES"
        diag_color = "#64748b"
        diag_icon  = "—"
        diag_base  = diag
    elif upside >= t_muy_infra:
        diag_base  = "MUY INFRAVALORADA"
        diag       = "MUY INFRAVALORADA — Oportunidad excepcional"
        diag_color = "#059669"
        diag_icon  = "▲▲"
    elif upside >= t_infra:
        diag_base  = "INFRAVALORADA"
        diag       = "INFRAVALORADA — Potencial alcista significativo"
        diag_color = "#16a34a"
        diag_icon  = "▲"
    elif upside >= t_lig_infra:
        diag_base  = "LIGERAMENTE INFRAVALORADA"
        diag       = "LIGERAMENTE INFRAVALORADA — Entrada atractiva"
        diag_color = "#65a30d"
        diag_icon  = "↑"
    elif upside >= -t_justo:
        diag_base  = "PRECIO JUSTO"
        diag       = "PRECIO JUSTO — En rango de valor razonable"
        diag_color = "#d97706"
        diag_icon  = "="
    elif upside >= -t_observ:
        diag_base  = "EN OBSERVACIÓN"
        diag       = "EN OBSERVACIÓN — Precio por encima del valor objetivo"
        diag_color = "#ea580c"
        diag_icon  = "↓"
    elif upside >= -t_sobreval:
        diag_base  = "SOBREVALORADA"
        diag       = "SOBREVALORADA — Riesgo de corrección moderada"
        diag_color = "#dc2626"
        diag_icon  = "▼"
    else:
        diag_base  = "MUY SOBREVALORADA"
        diag       = "MUY SOBREVALORADA — Riesgo de corrección severa"
        diag_color = "#dc2626"
        diag_icon  = "▼▼"

    # ── Modificador de Salud Fundamental sobre el diagnóstico ──────────────
    # El diagnóstico basado solo en upside puede ser engañoso: una empresa
    # "MUY INFRAVALORADA" con fundamentales muy débiles no es una oportunidad
    # clara, es un riesgo de "value trap". Igual que el veto de ADX en la
    # Señal de Entrada, aquí degradamos visiblemente la conclusión cuando
    # los fundamentales no la respaldan, en vez de mostrar solo el upside
    # sin matices. Simétricamente, una "MUY SOBREVALORADA" con fundamentales
    # excelentes se marca como menos arriesgada de lo que sugeriría el precio.
    health_modifier_applied = False
    if diag_base in ("MUY INFRAVALORADA", "INFRAVALORADA") and health_score < 40:
        diag = f"{diag_base} CON RIESGO — fundamentales débiles (salud {health_score}/100)"
        diag_color = "#d97706"
        diag_icon  = "⚠"
        health_modifier_applied = True
    elif diag_base in ("MUY SOBREVALORADA", "SOBREVALORADA") and health_score >= 75:
        diag = f"{diag_base}, PERO CON FUNDAMENTALES SÓLIDOS (salud {health_score}/100)"
        diag_color = "#d97706"
        diag_icon  = "⚠"
        health_modifier_applied = True

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
        "fair_value_single": fair_value_single,
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
        "health_modifier_applied": health_modifier_applied,
        "threshold_factor": threshold_factor,
        "diag_base":       diag_base,
        "piotroski":       piotroski,
        "rule_of_40":      rule_of_40,
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
        html += _kv("Acciones en circulación", _fmt_big(y.get("shares_outstanding"), ""))
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
    # DESGLOSE TRIMESTRAL TTM — Yahoo Finance
    # ════════════════════════════════════════════════════════════════════
    yahoo_quarters = y.get("ttm_quarters", []) or []
    if yahoo_quarters:
        _section("DESGLOSE TRIMESTRAL TTM &nbsp;<span style='font-size:0.7rem;'>🟡 Yahoo Finance</span>")
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

    last_q_fmt = ea.get("last_q_date_fmt", "N/A") if ea else "N/A"
    next_q_fmt = ea.get("next_q_date_fmt", "N/A") if ea else "N/A"
    next_q_estimated_flag = ea.get("next_q_estimated", False) if ea else False
    tiempo_desde = ea.get("tiempo_desde", "") if ea else ""
    tiempo_hasta = ea.get("tiempo_hasta", "") if ea else ""

    # Las tarjetas se muestran SIEMPRE, con "No disponible" explícito cuando
    # falte el dato — antes se ocultaba la sección entera si ambas fechas
    # fallaban (p. ej. sin cobertura de Finnhub para ese ticker concreto),
    # dejando al usuario sin saber si el dato no existía o si había un fallo.
    last_q_display = last_q_fmt if last_q_fmt != "N/A" else "No disponible"
    next_q_display = next_q_fmt if next_q_fmt != "N/A" else "No disponible"
    last_q_color   = "#0f172a" if last_q_fmt != "N/A" else "#94a3b8"
    next_q_color   = "#0f172a" if next_q_fmt != "N/A" else "#94a3b8"
    next_q_label   = "Próxima presentación (calculada, ~3 meses)" if next_q_estimated_flag else "Próxima presentación (estimada)"

    dates_html = (
        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:0.6rem;margin-bottom:0.9rem;">'
        '<div style="background:#f4f6f9;border-radius:6px;padding:0.6rem 0.8rem;">'
        '<div style="font-size:0.68rem;color:#64748b;text-transform:uppercase;">Última presentación</div>'
        f'<div style="font-size:0.9rem;color:{last_q_color};font-weight:600;">{last_q_display}</div>'
        f'<div style="font-size:0.7rem;color:#94a3b8;">{f"hace {tiempo_desde}" if tiempo_desde else ""}</div>'
        '</div>'
        '<div style="background:#f4f6f9;border-radius:6px;padding:0.6rem 0.8rem;">'
        f'<div style="font-size:0.68rem;color:#64748b;text-transform:uppercase;">{next_q_label}</div>'
        f'<div style="font-size:0.9rem;color:{next_q_color};font-weight:600;">{next_q_display}</div>'
        f'<div style="font-size:0.7rem;color:#94a3b8;">{f"en {tiempo_hasta}" if tiempo_hasta else ""}</div>'
        '</div>'
        '</div>'
        '<div style="font-size:0.68rem;color:#94a3b8;margin-bottom:0.8rem;">'
        '📅 Última presentación: fuente Finnhub (histórico de earnings). Próxima presentación: '
        'fuente Yahoo Finance cuando está disponible'
        + (', o <b>calculada automáticamente</b> como ~3 meses (91 días) tras la última '
           'presentación conocida cuando ninguna fuente da una fecha confirmada — el ciclo '
           'trimestral habitual de casi todas las cotizadas' if next_q_estimated_flag else
           ' — puede ser una fecha aún no confirmada oficialmente por la empresa (estimación '
           'basada en el ciclo trimestral habitual) hasta que se acerque la fecha')
        + '. Si algún dato aparece como "No disponible", la fuente correspondiente no tiene '
        'cobertura fiable para este ticker en este momento.</div>'
    )

    # Puntos positivos / a vigilar del último trimestre — mismo análisis que
    # ya se incluía en el PDF descargable, ahora también visible aquí. Nota:
    # estos datos pueden estar disponibles aunque las fechas de arriba
    # muestren "No disponible" — provienen de un camino de datos distinto
    # (fallback directo a Yahoo con trailingEps/epsForward cuando el
    # histórico de Finnhub no tiene cobertura para este ticker), así que
    # no es contradictorio ver ambos casos a la vez.
    eps_summary_html = ""
    if ea:
        eps_est  = ea.get("eps_estimate")
        eps_act  = ea.get("eps_actual")
        eps_surp = ea.get("eps_surprise")
        beat_eps = ea.get("beat_eps")
        positives = ea.get("positives", [])
        negatives = ea.get("negatives", [])
        warnings_list = ea.get("warnings", [])

        if eps_est is not None or eps_act is not None:
            beat_badge = (
                '<span style="background:#d1fae5;color:#059669;padding:2px 9px;border-radius:4px;'
                'font-size:0.72rem;font-weight:700;">✔ SUPERÓ</span>' if beat_eps is True else
                '<span style="background:#fee2e2;color:#dc2626;padding:2px 9px;border-radius:4px;'
                'font-size:0.72rem;font-weight:700;">✘ NO ALCANZÓ</span>' if beat_eps is False else ""
            )
            eps_summary_html += (
                '<div style="display:flex;align-items:center;gap:0.8rem;margin-bottom:0.7rem;'
                'padding:0.5rem 0.7rem;background:#f4f6f9;border-radius:6px;font-size:0.8rem;">'
                f'<span style="color:#64748b;">EPS estimado:</span> '
                f'<span style="font-family:\'IBM Plex Mono\',monospace;color:#334155;">'
                f'{f"${eps_est:.2f}" if eps_est is not None else "N/D"}</span>'
                f'<span style="color:#64748b;">Reportado:</span> '
                f'<span style="font-family:\'IBM Plex Mono\',monospace;color:#0f172a;font-weight:600;">'
                f'{f"${eps_act:.2f}" if eps_act is not None else "N/D"}</span>'
                + (f'<span style="font-family:\'IBM Plex Mono\',monospace;'
                   f'color:{"#059669" if (eps_surp or 0)>=0 else "#dc2626"};font-weight:600;">'
                   f'{eps_surp:+.1f}%</span>' if eps_surp is not None else '')
                + f' {beat_badge}'
                '</div>'
            )

        if warnings_list:
            for w in warnings_list:
                eps_summary_html += (
                    '<div style="background:#eff6ff;border-left:3px solid #0284c7;border-radius:4px;'
                    'padding:0.5rem 0.7rem;margin-bottom:0.7rem;font-size:0.76rem;color:#334155;'
                    f'line-height:1.6;">ℹ️ {w}</div>'
                )

        if positives or negatives:
            cols_html = '<div style="display:grid;grid-template-columns:1fr 1fr;gap:0.8rem;">'
            cols_html += '<div>'
            if positives:
                cols_html += ('<div style="font-size:0.7rem;color:#059669;text-transform:uppercase;'
                               'letter-spacing:0.05em;margin-bottom:0.4rem;">Puntos positivos</div>')
                for p in positives:
                    cols_html += (f'<div style="font-size:0.78rem;color:#334155;padding:0.2rem 0;">'
                                   f'<span style="color:#059669;">▸</span> {p}</div>')
            cols_html += '</div><div>'
            if negatives:
                cols_html += ('<div style="font-size:0.7rem;color:#dc2626;text-transform:uppercase;'
                               'letter-spacing:0.05em;margin-bottom:0.4rem;">Puntos a vigilar</div>')
                for n in negatives:
                    cols_html += (f'<div style="font-size:0.78rem;color:#334155;padding:0.2rem 0;">'
                                   f'<span style="color:#dc2626;">▸</span> {n}</div>')
            cols_html += '</div></div>'
            eps_summary_html += cols_html + '<div style="margin-bottom:0.9rem;"></div>'

    st.markdown(
        '<div class="metric-card">'
        f'{dates_html}'
        f'{eps_summary_html}'
        '<div style="font-size:0.85rem;color:#94a3b8;line-height:1.7;margin-bottom:0.8rem;">'
        f'Para el histórico completo de resultados de '
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
    # CÓMPUTO ADELANTADO: balance histórico, múltiplos propios, evaluación
    # y plan de entrada/salida — se calculan aquí (antes de Análisis
    # Técnico) para poder dibujar los niveles del plan directamente sobre
    # el gráfico de cotización. El RENDER visual de "Evaluación Final"
    # sigue apareciendo más abajo, en su posición original — solo se
    # adelanta el cálculo, no la sección en pantalla.
    # ════════════════════════════════════════════════════════════════════
    with st.spinner("Consultando balance histórico (ROIC, Piotroski, dilución)…"):
        bh = fetch_balance_sheet_history(ticker)

    # PER histórico PROPIO (5 años) calculado ANTES de _evaluate para poder
    # usarlo como método adicional del Valor Objetivo — se usa el PER "justo"
    # ESTÁTICO del sector aquí (sin el ajuste dinámico por tipos, que todavía
    # no existe en este punto porque depende de ev) solo para la comparación
    # informativa "vs sector" que ya se mostraba; el propio per_mean no
    # depende de ese ajuste. Se reutiliza el mismo mult_data más abajo en la
    # sección de "Histórico de Múltiplos Propios" sin volver a pedir datos.
    _static_profile, _ = _get_sector_profile(y.get("sector", ""))
    with st.spinner("Calculando múltiplos históricos…"):
        mult_data = fetch_historical_multiples(ticker, y, sector_pe_fair=_static_profile["pe_fair"])

    ev = _evaluate(y, bh, mult_data)
    entry_exit_plan = calc_entry_exit_plan(y, ev, tech)

    # ════════════════════════════════════════════════════════════════════
    # ANÁLISIS TÉCNICO
    # ════════════════════════════════════════════════════════════════════
    tech_date = tech.get("last_date","N/A") if tech and not tech.get("error") else "N/A"
    _section(f"ANÁLISIS TÉCNICO &nbsp;<span style='font-size:0.7rem;'>🟡 Yahoo Finance · último dato: {tech_date}</span>")

    if tech and not tech.get("error"):
        _render_price_chart(tech, ticker, currency_y, entry_exit_plan)

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
        support_d = tech.get("historical_support")

        def _tip(text):
            # ANTES usaba el atributo HTML nativo title="..." — funciona con
            # el ratón en escritorio, pero NO tiene ningún mecanismo de
            # activación en pantallas táctiles (no existe "hover" al tocar).
            # Se reescribe para reutilizar el sistema .tooltip-wrap /
            # .tooltip-box (CSS :hover ya definido en app.py), que sí
            # responde a un toque en la mayoría de navegadores móviles.
            safe = text.replace('"', '&quot;').replace("'", "&#39;")
            return (
                '<span class="tooltip-wrap" style="margin-left:0.3rem;position:relative;cursor:help;">'
                '<span style="font-size:0.6rem;color:#94a3b8;border:1px solid #cbd5e1;'
                'border-radius:50%;padding:0 3px;font-family:monospace;">?</span>'
                f'<span class="tooltip-box">{text}</span>'
                '</span>'
            )

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
            if support_d:
                sup_currency = currency_y
                sup_price_str = _fmt_price(support_d["level"], sup_currency, fx_rate)
                html3 += _kv(f"Soporte histórico{_tip('Nivel de precio donde la acción ha rebotado repetidamente en los últimos 2 años (mínimo 2 toques), agrupando mínimos locales dentro de un margen del 2.5%. A diferencia de las medias móviles o Fibonacci, es un nivel REAL donde el mercado ya ha demostrado interés comprador, no un cálculo proporcional o dinámico.')}",
                    sup_price_str, "row-val")
                html3 += _kv("Distancia al soporte", f'-{support_d["distance_pct"]:.1f}%', "row-val red")
                html3 += _kv("Nº de rebotes / último toque",
                    f'{support_d["touches"]}× · {support_d.get("last_touch_date","N/A")}', "row-val")
            elif tech and not tech.get("error"):
                html3 += _kv("Soporte histórico", "Sin soporte estructural claro detectado", "row-val")
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

    threshold_factor = ev.get("threshold_factor", 1.0)
    thresh_html = ""
    if abs(threshold_factor - 1.0) > 0.01:
        wider_narrower = "más amplios" if threshold_factor > 1 else "más estrechos"
        thresh_html = (
            f'<div style="margin-top:0.5rem;padding:0.5rem 0.7rem;background:#f4f6f9;'
            f'border-left:3px solid #94a3b8;border-radius:4px;font-size:0.72rem;color:#475569;line-height:1.6;">'
            f'ℹ️ <b>Umbrales de diagnóstico {wider_narrower} para este sector</b> (factor ×{threshold_factor:.2f}): '
            f'los sectores con mayor amplitud histórica de valoración (ratio PER techo/PER justo alto) necesitan '
            f'un upside o downside mayor para clasificarse como "muy infra/sobrevalorados", porque sus múltiplos '
            f'oscilan más de forma normal sin que eso implique una anomalía real.</div>'
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
        f'{thresh_html}'
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
        rule40 = ev.get("rule_of_40")
        if rule40:
            r40_color = "#059669" if rule40["passes"] else "#dc2626"
            r40_verdict = (
                "cumple la Regla del 40 — el crecimiento parece sano" if rule40["passes"]
                else "NO cumple la Regla del 40 — el crecimiento podría estar destruyendo valor"
            )
            reliability_notes.append((
                r40_color,
                f"{'✅' if rule40['passes'] else '⚠'} REGLA DEL 40 (auditoría de crecimiento hyper-growth): "
                f"Crecimiento ingresos {rule40['rev_growth']:+.1f}% + Margen FCF {rule40['fcf_margin']:+.1f}% "
                f"= {rule40['total']:+.1f}% (umbral: 40%). Esta empresa {r40_verdict}. "
                f"Crecer rápido quemando caja de forma insostenible no es lo mismo que crecer de forma sana."
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
        f'<div style="font-size:0.75rem;color:{b_color};padding:0.25rem 0;border-bottom:1px solid #eef1f5;">▸ {b_text}</div>'
        for b_text, b_color in ev["health_breakdown"]
    )
    fcf_quality_note = (
        '<div style="margin-top:0.8rem;padding:0.6rem 0.8rem;background:#f4f6f9;border-left:3px solid #94a3b8;'
        'border-radius:4px;font-size:0.72rem;color:#475569;line-height:1.65;">'
        '<b style="color:#334155;">Calidad del beneficio (FCF/Beneficio neto):</b> mide si el beneficio contable '
        'declarado se traduce realmente en caja generada por el negocio, o si es en parte producto de ajustes '
        'contables (amortizaciones, provisiones, partidas no monetarias) que inflan el resultado sin respaldo '
        'de flujo de caja real. Se calcula como Free Cash Flow ÷ Beneficio Neto anual. '
        '<b style="color:#059669;">≥1.0×</b> = excelente, todo el beneficio (o más) se convierte en caja · '
        '<b style="color:#059669;">0.9-1.0×</b> = muy buena · '
        '<b style="color:#d97706;">0.5-0.9×</b> = moderada, vigilar tendencia · '
        '<b style="color:#dc2626;">0-0.5×</b> = baja, posibles ajustes contables agresivos · '
        '<b style="color:#dc2626;">negativo</b> = alerta, la empresa consume caja pese a declarar beneficio.'
        '</div>'
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
            f'{bd_html}'
            f'<div style="font-size:0.68rem;color:#94a3b8;margin-top:0.5rem;">'
            '🔴 Rojo = dato débil &nbsp;·&nbsp; 🟡 Ámbar = normal &nbsp;·&nbsp; 🟢 Verde = bueno/destacable</div>'
            f'{fcf_quality_note}'
            '</div>',
            unsafe_allow_html=True
        )

    # Piotroski F-Score — herramienta independiente de fortaleza financiera,
    # no se mezcla con el score de Salud Fundamental (que es otra
    # metodología). Se muestra siempre como "X/9 evaluado" para no ocultar
    # que algunos criterios necesitan datos de balance histórico que Yahoo
    # no siempre expone para todos los tickers.
    pio = ev.get("piotroski", {})
    if pio.get("n_evaluable", 0) > 0:
        pio_rows = ""
        for name, status, detail in pio["criteria"]:
            if status is None:
                icon, color = "⚪", "#94a3b8"
                status_txt  = "No evaluable"
            elif status:
                icon, color = "✔", "#059669"
                status_txt  = "Cumple"
            else:
                icon, color = "✘", "#dc2626"
                status_txt  = "No cumple"
            pio_rows += (
                f'<div style="display:flex;justify-content:space-between;align-items:center;'
                f'padding:0.35rem 0;border-bottom:1px solid #eef1f5;font-size:0.78rem;">'
                f'<span style="color:#334155;">{icon} {name}</span>'
                f'<span style="color:{color};font-weight:600;text-align:right;">{status_txt}</span>'
                f'</div>'
                f'<div style="font-size:0.68rem;color:#94a3b8;padding:0 0 0.4rem 1.2rem;">{detail}</div>'
            )
        with st.expander(
            f"PIOTROSKI F-SCORE: {pio['score']}/{pio['n_evaluable']} evaluado — {pio['level']}",
            expanded=True
        ):
            st.markdown(
                '<div style="background:#ffffff;border-radius:8px;padding:0.8rem 1rem;">'
                f'<div style="display:flex;align-items:baseline;gap:0.8rem;margin-bottom:0.3rem;">'
                f'<span style="font-family:\'IBM Plex Mono\',monospace;font-size:1.6rem;font-weight:600;color:{pio["color"]};">{pio["score"]}/{pio["n_evaluable"]}</span>'
                f'<span style="color:#64748b;font-size:0.85rem;">{pio["level"]}</span>'
                '</div>'
                f'<div style="font-size:0.72rem;color:#94a3b8;margin-bottom:0.8rem;line-height:1.6;">'
                f'Sistema de 9 criterios binarios (rentabilidad, apalancamiento/liquidez, eficiencia '
                f'operativa) para detectar deterioro financiero, incluso en empresas que parecen '
                f'baratas por otros motivos. {9 - pio["n_evaluable"]} criterio(s) no evaluable(s) '
                f'por falta de balance histórico de Yahoo para este ticker — no se penaliza, '
                f'simplemente se excluye del cálculo.</div>'
                f'{pio_rows}'
                '</div>',
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
        fair_single = ev.get("fair_value_single")
        diff_html = ""
        if fair_single and fair and fair != fair_single:
            diff_pct = (fair - fair_single) / fair_single * 100
            fair_single_eur = f' <span style="color:#94a3b8;font-size:0.85em;">(€{fair_single*fx_rate:,.2f})</span>' if fx_rate and currency_y == "USD" else ""
            diff_color = "#059669" if diff_pct >= 0 else "#dc2626"
            diff_html = (
                '<div style="margin-top:0.5rem;display:flex;justify-content:space-between;align-items:baseline;">'
                '<span style="font-size:0.72rem;color:#94a3b8;">— si el consenso contase 1 sola vez '
                '(en vez de peso doble)</span>'
                f'<span style="font-family:\'IBM Plex Mono\',monospace;font-size:0.85rem;color:#64748b;">'
                f'{currency_y} {fair_single:,.2f}{fair_single_eur} '
                f'<span style="color:{diff_color};">({diff_pct:+.1f}%)</span></span>'
                '</div>'
            )
        fair_final_html = (
            '<div style="margin-top:0.8rem;padding-top:0.7rem;border-top:2px solid #dbeafe;">'
            '<div style="display:flex;justify-content:space-between;align-items:baseline;">'
            f'<span style="font-size:0.78rem;color:#0284c7;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">'
            f'Valor objetivo (mediana de {n_methods_final} método{"s" if n_methods_final != 1 else ""}, consenso ×2 peso)</span>'
            f'<span style="font-family:\'IBM Plex Mono\',monospace;font-size:1.1rem;font-weight:700;color:#0f172a;">'
            f'{currency_y} {fair:,.2f}{fair_eur_final}</span>'
            '</div>'
            f'{diff_html}'
            '</div>'
        )

    with st.expander("CÁLCULO DEL VALOR OBJETIVO", expanded=True):
        st.markdown(
            '<div style="background:#ffffff;border-radius:8px;padding:0.8rem 1rem;">'
            f'<div style="font-size:0.72rem;color:#0284c7;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:0.5rem;">'
            f'Métodos aplicados (sector: {ev["sector_label"]})</div>'
            f'{mh}'
            '<div style="margin-top:0.6rem;font-size:0.72rem;color:#64748b;">'
            'El valor objetivo principal es la <b>mediana</b> de los métodos disponibles más el '
            'consenso de analistas con <b>peso doble</b> (si hay ≥10 analistas) — la mediana se usa '
            'en vez de la media aritmética porque es inmune a que un solo método atípico distorsione '
            'el resultado. Se muestra también, a modo de contraste, la mediana alternativa dando al '
            'consenso el mismo peso que el resto de métodos (peso simple), para ver cuánto influye '
            'esa ponderación en el resultado final.</div>'
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
        # Mismo arreglo que _tip(): reemplaza el atributo title= nativo
        # (sin activación táctil) por el sistema .tooltip-wrap/.tooltip-box
        safe = text.replace('"', '&quot;').replace("'", "&#39;")
        return (
            '<span class="tooltip-wrap" style="margin-left:0.3rem;position:relative;cursor:help;'
            'vertical-align:middle;">'
            '<span style="font-size:0.6rem;color:#94a3b8;border:1px solid #cbd5e1;'
            'border-radius:50%;padding:0 3px;font-family:monospace;">?</span>'
            f'<span class="tooltip-box">{text}</span>'
            '</span>'
        )

    tip_vo = _vtip(
        f"Valor objetivo = mediana de hasta 4 métodos ajustados al sector {ev.get('sector_label','')} "
        f"(mediana en vez de media, para que un método atípico no distorsione el resultado). "
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

    # Precio objetivo de analistas + upside/downside (punto 8: visible aquí
    # directamente sin tener que hacer scroll hasta Mercado y Consenso)
    target_mean = y.get("target_mean")
    analyst_n   = y.get("analyst_count")
    analyst_html = ""
    if target_mean:
        analyst_upside = (target_mean - price_now) / price_now * 100 if price_now else None
        analyst_color  = "#059669" if (analyst_upside or 0) >= 0 else "#dc2626"
        target_eur = f' <span style="color:#94a3b8;font-size:0.85em;">(€{target_mean*fx_rate:,.2f})</span>' if fx_rate and currency_y=="USD" else ""
        n_note = f" ({analyst_n} analistas)" if analyst_n else ""
        analyst_html = (
            '<div class="verdict-sub" style="margin-top:0.3rem;">'
            f'<span style="color:#64748b;">Objetivo analistas{n_note}:</span>'
            f'<span style="font-family:\'IBM Plex Mono\',monospace;font-weight:600;color:#0f172a;"> '
            f'{currency_y} {target_mean:,.2f}{target_eur}</span>'
            f'<span style="font-family:\'IBM Plex Mono\',monospace;font-weight:700;color:{analyst_color};"> '
            f'({analyst_upside:+.2f}%)</span></div>'
        ) if analyst_upside is not None else ""

    # Aviso de modificador por salud fundamental (value trap / infravalorada con riesgo)
    health_mod_html = ""
    if ev.get("health_modifier_applied"):
        health_mod_html = (
            '<div style="margin-top:0.6rem;padding:0.5rem 0.7rem;background:#fffbeb;'
            'border-left:3px solid #d97706;border-radius:4px;font-size:0.75rem;color:#92400e;line-height:1.6;">'
            f'⚠ <b>Diagnóstico matizado por Salud Fundamental ({ev["health_score"]}/100):</b> '
            f'el upside/downside por sí solo sugeriría "{ev.get("diag_base","")}", pero los fundamentales '
            f'{"débiles" if ev["health_score"] < 40 else "sólidos"} de la empresa '
            f'{"añaden riesgo de value trap (barata por una buena razón)" if ev["health_score"] < 40 else "reducen el riesgo real de la aparente sobrevaloración"}.'
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
        f'{analyst_html}'
        f'<div class="verdict-sub"><span style="color:#64748b;">Vs. media 52W:</span>'
        f'<span style="font-family:\'IBM Plex Mono\',monospace;font-weight:600;color:#d97706;"> {hist_str}</span></div>'
        f'<div class="verdict-sub" style="margin-top:0.4rem;">'
        f'<span style="color:#64748b;">Riesgo técnico (short){tip_risk}:</span>'
        f'<span style="color:#1e293b;"> {ev["risk"]}%</span></div>'
        f'{health_mod_html}'
        '</div>',
        unsafe_allow_html=True
    )

    # ════════════════════════════════════════════════════════════════════
    # HISTÓRICO DE MÚLTIPLOS PROPIOS
    # ════════════════════════════════════════════════════════════════════
    # mult_data ya se calculó antes de _evaluate (para poder usar el PER
    # histórico propio como método del Valor Objetivo) — aquí solo se
    # actualiza el campo informativo "PER justo sector" con el valor YA
    # ajustado por tipos de interés (ev.get("pe_ref")), sin volver a pedir
    # datos a Yahoo.
    mult_data["sector_pe_fair"] = ev.get("pe_ref")
    render_historical_multiples(mult_data)

    # ════════════════════════════════════════════════════════════════════
    # SEÑAL DE ENTRADA
    # ════════════════════════════════════════════════════════════════════
    with st.spinner("Consultando momentum de revisiones de analistas…"):
        y["analyst_revisions"] = fetch_analyst_revisions(ticker)
    y["insiders_data"]  = company_info.get("insiders", [])
    y["next_q_date"]    = ea.get("next_q_date") if ea else None
    y["next_q_estimated"] = ea.get("next_q_estimated", False) if ea else False
    y["last_q_date"]    = ea.get("last_q_date") if ea else None
    signal = calc_entry_signal(y, tech, ev)
    render_entry_signal(signal)

    # ════════════════════════════════════════════════════════════════════
    # PLAN DE ENTRADA Y SALIDA SUGERIDO
    # ════════════════════════════════════════════════════════════════════
    # entry_exit_plan ya se calculó antes de Análisis Técnico (para poder
    # dibujar los niveles sobre el gráfico) — se reutiliza aquí sin volver
    # a calcularlo.
    render_entry_exit_plan(entry_exit_plan, currency_y, fx_rate)

    # ════════════════════════════════════════════════════════════════════
    # VALORACIÓN FINAL — síntesis de los 4 sistemas
    # ════════════════════════════════════════════════════════════════════
    vf = calc_valoracion_final(ev, signal)
    render_valoracion_final(vf, ev, signal)

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
        fx_rate, peers_data, vf
    )

    st.caption(
        f"Datos: Yahoo Finance · {ticker} · USD/EUR: {fx_rate:.4f} · "
        f"Sector: {ev['sector_label']} · No constituye asesoramiento financiero."
    )
