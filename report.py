"""
report.py
Renderiza el informe completo en Streamlit con el diseño oscuro.
"""

import streamlit as st
from analysis import (
    calc_entry_signal, calc_trend, fetch_peer_data, get_peers,
    render_entry_signal, render_trend, render_peers,
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
          <span style="font-size:0.65rem;color:#1e3a5f;border:1px solid #1e3a5f;
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
        "pe_fair": 28, "pe_high": 50,
        "peg_ok": 1.5, "margin_ok": 0.12, "roe_ok": 0.15,
        "ev_ebitda_fair": 22,
        "methods": ["peg", "per", "ev_ebitda"],
        "nota": "Tecnología cotiza con prima estructural por crecimiento. PEG < 1.5 y márgenes > 12% son señales positivas.",
    },
    "Communication Services": {
        "pe_fair": 22, "pe_high": 40,
        "peg_ok": 1.3, "margin_ok": 0.10, "roe_ok": 0.12,
        "ev_ebitda_fair": 18,
        "methods": ["peg", "ev_ebitda", "per"],
        "nota": "Servicios de comunicación valora el crecimiento de usuarios y EBITDA. Los múltiplos varían mucho entre plataformas y telecos.",
    },
    "Consumer Cyclical": {
        "pe_fair": 20, "pe_high": 35,
        "peg_ok": 1.2, "margin_ok": 0.06, "roe_ok": 0.12,
        "ev_ebitda_fair": 14,
        "methods": ["per", "ev_ebitda", "peg"],
        "nota": "Cíclico al consumo: los márgenes caen en recesión. PER < 20 con ROE > 12% es señal sólida.",
    },
    "Consumer Defensive": {
        "pe_fair": 22, "pe_high": 32,
        "peg_ok": 2.0, "margin_ok": 0.07, "roe_ok": 0.15,
        "ev_ebitda_fair": 16,
        "methods": ["per", "ev_ebitda", "peg"],
        "nota": "Defensivo al consumo: se valora por estabilidad y dividendos. PER hasta 22 es razonable.",
    },
    "Healthcare": {
        "pe_fair": 24, "pe_high": 45,
        "peg_ok": 1.8, "margin_ok": 0.10, "roe_ok": 0.12,
        "ev_ebitda_fair": 18,
        "methods": ["peg", "per", "ev_ebitda"],
        "nota": "Salud tiene prima por pipeline y patentes. Farmacéuticas puras pueden tener PER alto justificado.",
    },
    "Financials": {
        "pe_fair": 14, "pe_high": 22,
        "peg_ok": 1.0, "margin_ok": 0.15, "roe_ok": 0.10,
        "ev_ebitda_fair": 10,
        "methods": ["nav", "per", "peg"],
        "nota": "Financieras se valoran por Price/Book y ROE. EV/EBITDA menos relevante; se prefiere P/B < 1.5 + ROE > 10%.",
    },
    "Industrials": {
        "pe_fair": 20, "pe_high": 32,
        "peg_ok": 1.5, "margin_ok": 0.07, "roe_ok": 0.12,
        "ev_ebitda_fair": 14,
        "methods": ["per", "ev_ebitda", "peg"],
        "nota": "Industriales valoran flujo de caja operativo y márgenes estables. PER < 20 y D/E < 1 son buenas señales.",
    },
    "Energy": {
        "pe_fair": 14, "pe_high": 22,
        "peg_ok": 1.0, "margin_ok": 0.08, "roe_ok": 0.10,
        "ev_ebitda_fair": 6,
        "methods": ["ev_ebitda", "per", "dcf_lite"],
        "nota": "Energía se valora principalmente por EV/EBITDA (ciclo de commodity). EV/EBITDA < 6 es barato para el sector.",
    },
    "Basic Materials": {
        "pe_fair": 16, "pe_high": 26,
        "peg_ok": 1.2, "margin_ok": 0.06, "roe_ok": 0.10,
        "ev_ebitda_fair": 8,
        "methods": ["ev_ebitda", "per", "peg"],
        "nota": "Materiales básicos depende del ciclo. EV/EBITDA es la métrica principal; los márgenes fluctúan con el precio del commodity.",
    },
    "Real Estate": {
        "pe_fair": 30, "pe_high": 55,
        "peg_ok": 2.5, "margin_ok": 0.20, "roe_ok": 0.08,
        "ev_ebitda_fair": 20,
        "methods": ["ev_ebitda", "dcf_lite", "per"],
        "nota": "REITs y real estate se valoran por FFO/AFFO y EV/EBITDA. El PER convencional puede ser engañoso por la depreciación.",
    },
    "Utilities": {
        "pe_fair": 18, "pe_high": 28,
        "peg_ok": 2.0, "margin_ok": 0.10, "roe_ok": 0.08,
        "ev_ebitda_fair": 12,
        "methods": ["per", "ev_ebitda", "dcf_lite"],
        "nota": "Utilities cotizan por estabilidad regulatoria y dividendos. PER < 18 y yield > 3% son señales atractivas.",
    },
    # Fallback genérico
    "_default": {
        "pe_fair": 20, "pe_high": 35,
        "peg_ok": 1.5, "margin_ok": 0.08, "roe_ok": 0.10,
        "ev_ebitda_fair": 14,
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


# ─── Motor de valoración por sector ──────────────────────────────────────────

def _calc_fair_value(y: dict, profile: dict) -> tuple[float | None, list[str]]:
    """
    Calcula el valor objetivo usando los métodos relevantes para el sector.
    Devuelve (fair_value, lista_de_métodos_usados).
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

    methods_used = []
    targets      = []

    for method in profile["methods"]:

        # PER × EPS con PE justo del sector
        if method == "per" and eps_fwd and eps_fwd > 0:
            fair_pe = profile["pe_fair"]
            # Si la empresa crece más que la media del sector, le damos un 10% de prima
            if earn_growth > 0.20:
                fair_pe *= 1.10
            val = fair_pe * eps_fwd
            if val > 0:
                targets.append(val)
                methods_used.append(f"PER sectorial ({fair_pe:.0f}×EPS) → {val:,.2f}")

        # PEG: precio justo = EPS × PEG_sector × tasa_crecimiento × 100
        elif method == "peg" and peg and eps_fwd and eps_fwd > 0 and earn_growth > 0:
            # PEG justo del sector como referencia
            val = eps_fwd * profile["peg_ok"] * (earn_growth * 100)
            if val > 0:
                targets.append(val)
                methods_used.append(f"PEG sectorial ({profile['peg_ok']}×crecimiento) → {val:,.2f}")

        # EV/EBITDA sectorial
        elif method == "ev_ebitda" and ev_ebitda and ebitda and ebitda > 0:
            fair_ev_ebitda = profile["ev_ebitda_fair"]
            # Valor implícito de mercado ajustando el múltiplo justo vs el actual
            ratio = fair_ev_ebitda / ev_ebitda if ev_ebitda else 1
            val   = price * ratio
            if val > 0:
                targets.append(val)
                methods_used.append(f"EV/EBITDA sectorial ({fair_ev_ebitda}×) → {val:,.2f}")

        # FCF Yield (DCF simplificado): precio justo = FCF / yield_esperado
        elif method == "dcf_lite" and fcf > 0 and market_cap > 0:
            fcf_yield_target = 0.04  # rentabilidad FCF esperada del 4%
            shares = market_cap / price if price else 1
            fcf_per_share = fcf / shares
            val = fcf_per_share / fcf_yield_target
            if val > 0:
                targets.append(val)
                methods_used.append(f"FCF Yield (4%) → {val:,.2f}")

        # Price/Book para financieras: P/B justo = ROE / coste_capital
        elif method == "nav" and price_book and roe > 0:
            cost_of_equity = 0.10  # WACC simplificado 10%
            fair_pb = roe / cost_of_equity
            val = price * (fair_pb / price_book) if price_book else price
            if val > 0:
                targets.append(val)
                methods_used.append(f"Price/Book justo (ROE/Ke={fair_pb:.2f}×) → {val:,.2f}")

    # El precio objetivo de consenso de analistas tiene siempre peso en el promedio
    if target_mean and target_mean > 0:
        targets.append(target_mean)
        methods_used.append(f"Consenso analistas → {target_mean:,.2f}")

    if not targets:
        return None, []

    # Media ponderada: consenso pesa 1, cada método pesa 1 (igual peso)
    fair_value = sum(targets) / len(targets)
    return fair_value, methods_used


# ─── Salud fundamental ajustada al sector ────────────────────────────────────

def _calc_health_score(y: dict, profile: dict) -> tuple[int, list[str]]:
    """Calcula la salud fundamental (0-100) con umbrales del sector."""
    score    = 0
    breakdown = []

    profit_m   = y.get("profit_margin") or 0
    roe        = y.get("roe") or 0
    rev_yoy    = y.get("revenue_yoy") or 0
    earn_yoy   = y.get("earnings_yoy") or 0
    peg        = y.get("peg_ratio")
    short_r    = y.get("short_ratio") or 0
    debt_eq    = y.get("debt_equity") or 0
    curr_ratio = y.get("current_ratio") or 0
    fcf        = y.get("free_cash_flow") or 0

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

    # Crecimiento ingresos (0-20 pts) — sector cíclico/defensivo tiene baremo distinto
    if rev_yoy >= 30:    pts = 20
    elif rev_yoy >= 15:  pts = 15
    elif rev_yoy >= 8:   pts = 10
    elif rev_yoy >= 3:   pts = 5
    elif rev_yoy >= 0:   pts = 2
    else:                pts = 0
    score += pts
    breakdown.append(f"Crec. ingresos {rev_yoy:.1f}%: +{pts}/20")

    # Crecimiento beneficios (0-20 pts)
    if earn_yoy >= 40:   pts = 20
    elif earn_yoy >= 20: pts = 15
    elif earn_yoy >= 10: pts = 10
    elif earn_yoy >= 0:  pts = 5
    else:                pts = 0
    score += pts
    breakdown.append(f"Crec. beneficios {earn_yoy:.1f}%: +{pts}/20")

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

    score = min(100, score)
    return score, breakdown


# ─── Evaluación final ─────────────────────────────────────────────────────────

def _evaluate(y: dict, sec: dict | None) -> dict:
    """Diagnóstico completo ajustado al sector."""

    price       = y.get("price") or 0
    sector_raw  = y.get("sector", "")
    profile, sector_label = _get_sector_profile(sector_raw)

    short_ratio = y.get("short_ratio") or 0
    week52_high = y.get("52w_high") or price
    week52_low  = y.get("52w_low") or price
    pe_forward  = y.get("pe_forward")
    pe_trailing = y.get("pe_trailing")
    price_book  = y.get("price_book")

    # ── Salud fundamental ────────────────────────────────────────────────
    health_score, health_breakdown = _calc_health_score(y, profile)

    # ── Valor objetivo ───────────────────────────────────────────────────
    fair_value, methods_used = _calc_fair_value(y, profile)

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
        diag_color = "#6ee7b7"
        diag_icon  = "▲▲"
    elif upside >= 12:
        diag       = "INFRAVALORADA — Potencial alcista significativo"
        diag_color = "#86efac"
        diag_icon  = "▲"
    elif upside >= 3:
        diag       = "LIGERAMENTE INFRAVALORADA — Entrada atractiva"
        diag_color = "#bef264"
        diag_icon  = "↑"
    elif upside >= -3:
        diag       = "PRECIO JUSTO — En rango de valor razonable"
        diag_color = "#fbbf24"
        diag_icon  = "="
    elif upside >= -15:
        diag       = "EN OBSERVACIÓN — Precio por encima del valor objetivo"
        diag_color = "#fb923c"
        diag_icon  = "↓"
    elif upside >= -30:
        diag       = "SOBREVALORADA — Riesgo de corrección moderada"
        diag_color = "#f87171"
        diag_icon  = "▼"
    else:
        diag       = "MUY SOBREVALORADA — Riesgo de corrección severa"
        diag_color = "#fca5a5"
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
    }


# ─── Render principal ─────────────────────────────────────────────────────────

def render_report(ticker, company_name, y: dict, sec: dict | None, cross: dict | None, fx_rate: float | None = None, tech: dict | None = None):
    st.markdown("---")

    # ── Auditoría de fuentes ─────────────────────────────────────────────
    _section("AUDITORÍA DE DATOS")
    currency_y = y.get("currency", "USD")

    if cross:
        status_map = {
            "OK":      ("✔ DATOS VERIFICADOS", "audit-ok"),
            "WARN":    ("⚠ DIFERENCIA MENOR", "audit-warn"),
            "ERROR":   ("✘ DIFERENCIA SIGNIFICATIVA", "audit-err"),
            "NO_DATA": ("— SIN DATOS SEC", "audit-warn"),
        }
        label, cls = status_map.get(cross["status"], ("—", ""))
        fx_label = f"&nbsp;|&nbsp; USD/EUR: {fx_rate:.4f}" if fx_rate else ""

        html = f"""
        <div class="metric-card">
          <div class="metric-label">ACTIVO: {company_name} &nbsp;|&nbsp; MONEDA: {currency_y}{fx_label}</div>
          <div class="row-kv">
            <span class="row-key">SEC EDGAR TTM Revenue</span>
            <span class="row-val">{_fmt_big(cross.get('sec_ttm'),'')}</span>
          </div>
          <div class="row-kv">
            <span class="row-key">Yahoo Finance TTM Revenue</span>
            <span class="row-val">{_fmt_big(cross.get('yahoo_ttm'),'')}</span>
          </div>
          <div class="row-kv">
            <span class="row-key">Diferencia</span>
            <span class="row-val {'audit-ok' if cross['status']=='OK' else 'audit-warn'}">{_fmt_big(cross.get('diff'),'') if cross.get('diff') is not None else 'N/A'} ({_fmt_num(cross.get('pct'), 2, suffix='%') if cross.get('pct') is not None else 'N/A'})</span>
          </div>
          <div style="margin-top:0.5rem;">
            <span class="{cls}" style="font-family:'IBM Plex Mono',monospace;font-size:0.85rem;font-weight:600;">{label}</span>
          </div>
        </div>
        """
        st.markdown(html, unsafe_allow_html=True)
    else:
        fx_label = f"&nbsp;|&nbsp; USD/EUR: {fx_rate:.4f}" if fx_rate else ""
        st.markdown(f"""
        <div class="metric-card">
          <div class="metric-label">ACTIVO: {company_name} &nbsp;|&nbsp; MONEDA: {currency_y}{fx_label}</div>
          <span class="audit-warn" style="font-size:0.85rem;">Usando solo Yahoo Finance — SEC no disponible para este ticker</span>
        </div>
        """, unsafe_allow_html=True)

    # ── Desglose TTM ────────────────────────────────────────────────────
    # Prioriza SEC si está disponible (más oficial), si no usa Yahoo
    if sec and sec.get("quarters"):
        quarters_to_show = sec["quarters"]
        source_label = "SEC EDGAR"
    else:
        quarters_to_show = y.get("ttm_quarters", [])
        source_label = "Yahoo Finance"

    if quarters_to_show:
        _section(f"DESGLOSE TTM — {source_label}")
        rows_html = ""
        ttm_total = 0
        for i, q in enumerate(quarters_to_show[:4]):
            val = q.get("value", 0) or 0
            ttm_total += val
            label_q = f"Q{4-i} ({q.get('date','')[:10]})"
            rows_html += f'<div class="ttm-row"><span>{label_q}</span><span class="ttm-val">{_fmt_big(val,"")}</span></div>'
        rows_html += f'<div class="ttm-row"><span>TOTAL TTM</span><span class="ttm-val">{_fmt_big(ttm_total,"")}</span></div>'
        st.markdown(f'<div class="metric-card">{rows_html}</div>', unsafe_allow_html=True)

    # ── Columnas principales ─────────────────────────────────────────────
    col_a, col_b = st.columns(2)

    with col_a:
        # A. Mercado y consenso
        _section("A · MERCADO Y CONSENSO")
        html = ""
        rec = y.get("recommendation", "N/A")
        html += _kv("Precio Actual",     _fmt_price(y.get("price"), currency_y, fx_rate))
        html += _kv("Objetivo Analistas",_fmt_price(y.get("target_mean"), currency_y, fx_rate))
        html += _kv("Rango", f"{_fmt_price(y.get('target_low'), currency_y, fx_rate)} – {_fmt_price(y.get('target_high'), currency_y, fx_rate)}")
        html += _kv("Recomendación", _badge(rec))
        html += _kv("Nº Analistas", str(y.get("analyst_count") or "N/A"))
        st.markdown(f'<div class="metric-card">{html}</div>', unsafe_allow_html=True)

        # C. Rentabilidad
        _section("C · RENTABILIDAD")
        html = ""
        html += _kv("Profit Margin",    _fmt_num((y.get("profit_margin") or 0)*100, 2, suffix="%"),    _color_pct(y.get("profit_margin")))
        html += _kv("Operating Margin", _fmt_num((y.get("operating_margin") or 0)*100, 2, suffix="%"), _color_pct(y.get("operating_margin")))
        html += _kv("EBITDA Margin",    _fmt_num((y.get("ebitda_margin") or 0)*100, 2, suffix="%"),    _color_pct(y.get("ebitda_margin")))
        html += _kv("ROE",              _fmt_num((y.get("roe") or 0)*100, 2, suffix="%"),              _color_pct(y.get("roe")))
        html += _kv("ROA",              _fmt_num((y.get("roa") or 0)*100, 2, suffix="%"),              _color_pct(y.get("roa")))
        st.markdown(f'<div class="metric-card">{html}</div>', unsafe_allow_html=True)

        # E. Crecimiento
        _section("E · CRECIMIENTO YoY")
        html = ""
        rev_yoy  = y.get("revenue_yoy")
        earn_yoy = y.get("earnings_yoy")
        html += _kv("Revenue Growth",  _fmt_num(rev_yoy, 2, suffix="%") if rev_yoy is not None else "N/A",  _color_pct(rev_yoy))
        html += _kv("Earnings Growth", _fmt_num(earn_yoy, 2, suffix="%") if earn_yoy is not None else "N/A", _color_pct(earn_yoy))
        html += _kv("EPS (TTM)",       _fmt_price(y.get("eps_ttm"), currency_y, fx_rate))
        html += _kv("EPS (Forward)",   _fmt_price(y.get("eps_forward"), currency_y, fx_rate))
        st.markdown(f'<div class="metric-card">{html}</div>', unsafe_allow_html=True)

    with col_b:
        # B. Valoración
        _section("B · VALORACIÓN")
        html = ""
        html += _kv("PER Trailing",  _fmt_num(y.get("pe_trailing"), 2))
        html += _kv("PER Forward",   _fmt_num(y.get("pe_forward"), 2))
        html += _kv("PEG Ratio",     _fmt_num(y.get("peg_ratio"), 4))
        html += _kv("Price/Sales",   _fmt_num(y.get("price_sales"), 4))
        html += _kv("Price/Book",    _fmt_num(y.get("price_book"), 4))
        html += _kv("EV/Revenue",    _fmt_num(y.get("ev_revenue"), 4))
        html += _kv("EV/EBITDA",     _fmt_num(y.get("ev_ebitda"), 4))
        html += _kv("Market Cap",    _fmt_big(y.get("market_cap"), "$", fx_rate))
        st.markdown(f'<div class="metric-card">{html}</div>', unsafe_allow_html=True)

        # D. Balance
        _section("D · BALANCE Y CAJA")
        html = ""
        html += _kv("Total Cash",          _fmt_big(y.get("total_cash"), "$", fx_rate))
        html += _kv("Total Debt",          _fmt_big(y.get("total_debt"), "$", fx_rate))
        html += _kv("Debt/Equity",         _fmt_num(y.get("debt_equity"), 2))
        html += _kv("Current Ratio",       _fmt_num(y.get("current_ratio"), 2))
        html += _kv("Free Cash Flow",      _fmt_big(y.get("free_cash_flow"), "$", fx_rate))
        html += _kv("Operating Cash Flow", _fmt_big(y.get("operating_cf"), "$", fx_rate))
        st.markdown(f'<div class="metric-card">{html}</div>', unsafe_allow_html=True)

        # F. Dividendos y otros
        _section("F · DIVIDENDOS Y OTROS")
        html = ""
        dy = y.get("dividend_yield")
        html += _kv("Dividend Yield", _fmt_num((dy or 0)*100, 2, suffix="%") if dy else "N/A")
        html += _kv("Dividend Rate",  _fmt_price(y.get("dividend_rate"), currency_y, fx_rate) if y.get("dividend_rate") else "N/A")
        html += _kv("Short Ratio",    _fmt_num(y.get("short_ratio"), 2))
        html += _kv("Beta",           _fmt_num(y.get("beta"), 2))
        html += _kv("52W High",       _fmt_price(y.get("52w_high"), currency_y, fx_rate))
        html += _kv("52W Low",        _fmt_price(y.get("52w_low"), currency_y, fx_rate))
        st.markdown(f'<div class="metric-card">{html}</div>', unsafe_allow_html=True)

    # ── G. Análisis Técnico ──────────────────────────────────────────────
    _section("G · ANÁLISIS TÉCNICO")

    if tech and not tech.get("error"):
        col_t1, col_t2 = st.columns(2)

        with col_t1:
            # RSI
            rsi_val = tech.get("rsi")
            rsi_lbl = tech.get("rsi_label", "N/A")
            rsi_cls = tech.get("rsi_css", "")

            # Barra RSI
            rsi_pct = min(max(rsi_val or 0, 0), 100)
            if rsi_pct >= 70:
                bar_color = "#fca5a5"
            elif rsi_pct <= 30:
                bar_color = "#6ee7b7"
            else:
                bar_color = "#38bdf8"

            st.markdown(f"""
            <div class="metric-card">
              <div class="metric-label">RSI (14 períodos)</div>
              <div style="display:flex;align-items:baseline;gap:0.6rem;">
                <div class="metric-value">{_fmt_num(rsi_val, 2)}</div>
                <span class="row-val {rsi_cls}" style="font-size:0.82rem;">{rsi_lbl}</span>
              </div>
              <div class="progress-bar-bg" style="margin-top:0.6rem;position:relative;">
                <div style="height:8px;border-radius:4px;background:{bar_color};width:{rsi_pct}%;"></div>
              </div>
              <div style="display:flex;justify-content:space-between;font-size:0.7rem;color:#64748b;margin-top:0.2rem;">
                <span>0 — Sobreventa</span><span>50</span><span>Sobrecompra — 100</span>
              </div>
              <div style="margin-top:0.5rem;font-size:0.78rem;color:#94a3b8;">
                ▸ RSI &lt; 30: sobreventa (posible rebote) &nbsp;|&nbsp; RSI &gt; 70: sobrecompra (posible corrección)
              </div>
            </div>
            """, unsafe_allow_html=True)

        with col_t2:
            # MM50 y MM200
            mm50  = tech.get("mm50")
            mm200 = tech.get("mm200")
            d50   = tech.get("dist_mm50")
            d200  = tech.get("dist_mm200")
            cross_sig = tech.get("cross_signal")

            html = ""
            html += _kv("MM50",  _fmt_price(mm50, currency_y, fx_rate), f"row-val {tech.get('mm50_css','')}")
            html += _kv("Distancia MM50", _fmt_num(d50, 2, suffix="%") if d50 is not None else "N/A",
                        "row-val green" if (d50 or 0) >= 0 else "row-val red")
            html += _kv("Señal MM50", tech.get("mm50_signal","N/A"), f"row-val {tech.get('mm50_css','')}")
            html += _kv("MM200", _fmt_price(mm200, currency_y, fx_rate) if mm200 else "N/A", f"row-val {tech.get('mm200_css','')}")
            html += _kv("Distancia MM200", _fmt_num(d200, 2, suffix="%") if d200 is not None else "N/A",
                        "row-val green" if (d200 or 0) >= 0 else "row-val red")
            html += _kv("Señal MM200", tech.get("mm200_signal","N/A"), f"row-val {tech.get('mm200_css','')}")

            if cross_sig:
                cross_label, cross_css = cross_sig
                html += _kv("Cruce MM50/MM200", cross_label, f"row-val {cross_css}")

            st.markdown(f'<div class="metric-card">{html}</div>', unsafe_allow_html=True)

    elif tech and tech.get("error"):
        st.markdown(f'<div class="metric-card"><span class="audit-warn">No se pudo calcular el análisis técnico: {tech["error"]}</span></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="metric-card"><span class="audit-warn">Análisis técnico no disponible.</span></div>', unsafe_allow_html=True)

    # ── Evaluación final ─────────────────────────────────────────────────
    ev = _evaluate(y, sec)

    _section("EVALUACIÓN FINAL")

    health_score = ev["health_score"]
    fair         = ev["fair_value"]
    upside       = ev["upside"]
    vs_hist      = ev["vs_hist"]
    price_now    = y.get("price") or 0
    diag_color   = ev.get("diag_color", "#f1f5f9")
    diag_icon    = ev.get("diag_icon", "")

    # ── Bloque sector ────────────────────────────────────────────────────
    st.markdown(f"""
    <div class="metric-card" style="border-left:3px solid #38bdf8;">
      <div class="metric-label">CONTEXTO SECTORIAL</div>
      <div style="font-size:0.95rem;font-weight:600;color:#f1f5f9;margin-bottom:0.4rem;">
        {ev['sector_label']}
      </div>
      <div style="font-size:0.8rem;color:#94a3b8;line-height:1.6;">{ev['sector_nota']}</div>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:0.5rem;margin-top:0.8rem;">
        <div style="background:#0f172a;border-radius:6px;padding:0.4rem 0.6rem;">
          <div style="font-size:0.68rem;color:#64748b;text-transform:uppercase;">PER justo sector</div>
          <div style="font-family:'IBM Plex Mono',monospace;color:#38bdf8;font-weight:600;">{ev['pe_ref']}×</div>
        </div>
        <div style="background:#0f172a;border-radius:6px;padding:0.4rem 0.6rem;">
          <div style="font-size:0.68rem;color:#64748b;text-transform:uppercase;">PEG aceptable</div>
          <div style="font-family:'IBM Plex Mono',monospace;color:#38bdf8;font-weight:600;">&lt;{ev['peg_ok']}</div>
        </div>
        <div style="background:#0f172a;border-radius:6px;padding:0.4rem 0.6rem;">
          <div style="font-size:0.68rem;color:#64748b;text-transform:uppercase;">EV/EBITDA justo</div>
          <div style="font-family:'IBM Plex Mono',monospace;color:#38bdf8;font-weight:600;">{ev['ev_ebitda_fair']}×</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Salud fundamental con desglose ────────────────────────────────────
    bar_color_health = "#6ee7b7" if health_score >= 70 else "#fbbf24" if health_score >= 45 else "#fca5a5"
    breakdown_html = "".join([
        f'<div style="font-size:0.75rem;color:#94a3b8;padding:0.2rem 0;border-bottom:1px solid #1a2540;">▸ {b}</div>'
        for b in ev["health_breakdown"]
    ])

    with st.expander(f"SALUD FUNDAMENTAL: {health_score}/100 — ver desglose por criterio", expanded=False):
        st.markdown(f"""
        <div style="background:#111827;border-radius:8px;padding:0.8rem 1rem;">
          <div style="display:flex;align-items:baseline;gap:0.8rem;margin-bottom:0.5rem;">
            <span style="font-family:'IBM Plex Mono',monospace;font-size:1.6rem;
                         font-weight:600;color:{bar_color_health};">{health_score}</span>
            <span style="color:#64748b;font-size:0.85rem;">/ 100 — umbrales ajustados al sector <b style="color:#f1f5f9;">{ev['sector_label']}</b></span>
          </div>
          <div style="background:#1e2d45;border-radius:4px;height:8px;margin-bottom:1rem;">
            <div style="height:8px;border-radius:4px;background:{bar_color_health};width:{health_score}%;"></div>
          </div>
          {breakdown_html}
        </div>
        """, unsafe_allow_html=True)

    # ── Métodos de valoración usados ──────────────────────────────────────
    methods_html = "".join([
        f'<div style="font-size:0.76rem;color:#94a3b8;padding:0.18rem 0;">▸ {m}</div>'
        for m in ev.get("methods_used", [])
    ]) or '<div style="font-size:0.76rem;color:#64748b;">No hay datos suficientes para calcular valor objetivo.</div>'

    with st.expander("METODOLOGÍA DE VALORACIÓN — ver cálculo del valor objetivo", expanded=False):
        st.markdown(f"""
        <div style="background:#111827;border-radius:8px;padding:0.8rem 1rem;">
          <div style="font-size:0.72rem;color:#38bdf8;text-transform:uppercase;
                      letter-spacing:0.08em;margin-bottom:0.5rem;">
            Métodos aplicados (sector: {ev['sector_label']})
          </div>
          {methods_html}
          <div style="margin-top:0.6rem;font-size:0.72rem;color:#64748b;">
            El valor objetivo es la media aritmética de todos los métodos disponibles
            más el consenso de analistas cuando existe.
          </div>
        </div>
        """, unsafe_allow_html=True)

    # ── Comparativa vs sector ─────────────────────────────────────────────
    vs_items = ev.get("vs_sector", "")
    if vs_items and " · " in vs_items:
        items = vs_items.split(" · ")
        vs_html = "".join([
            f'<div style="font-size:0.8rem;color:#e2e8f0;padding:0.25rem 0;'
            f'border-bottom:1px solid #1a2540;">▸ {item}</div>'
            for item in items
        ])
    else:
        vs_html = f'<div style="font-size:0.8rem;color:#94a3b8;">{vs_items}</div>'

    st.markdown(f"""
    <div class="metric-card">
      <div class="metric-label">MÚLTIPLOS ACTUALES VS BENCHMARKS DEL SECTOR</div>
      {vs_html}
    </div>
    """, unsafe_allow_html=True)

    # ── Veredicto principal ───────────────────────────────────────────────
    upside_str = f"{upside:+.2f}%" if upside is not None else "N/A"
    fair_usd   = f"{currency_y} {fair:,.2f}" if fair else "N/A"
    fair_eur   = f" (€{fair*fx_rate:,.2f})" if (fair and fx_rate and currency_y == "USD") else ""
    fair_str   = f"{fair_usd}{fair_eur}" if fair else "N/A"
    hist_str   = f"{vs_hist:+.2f}% vs media 52W" if vs_hist is not None else "N/A"
    price_eur  = f" (€{price_now*fx_rate:,.2f})" if (fx_rate and currency_y == "USD") else ""
    upside_color = "#6ee7b7" if (upside or 0) > 0 else "#fca5a5"

    st.markdown(f"""
    <div class="verdict-box" style="border-left-color:{diag_color};">
      <div class="verdict-title">DIAGNÓSTICO GENERAL</div>
      <div style="display:flex;align-items:center;gap:0.7rem;margin-bottom:0.5rem;">
        <span style="font-family:'IBM Plex Mono',monospace;font-size:1.4rem;
                     font-weight:700;color:{diag_color};">{diag_icon}</span>
        <span class="verdict-main" style="color:{diag_color};">{ev['diag']}</span>
      </div>

      <div class="verdict-sub" style="margin-top:0.6rem;">
        <span style="color:#94a3b8;">Precio actual:</span>
        <span style="font-family:'IBM Plex Mono',monospace;font-weight:600;color:#f1f5f9;">
          {currency_y} {price_now:,.2f}{price_eur}
        </span>
        &nbsp;·&nbsp;
        <span style="color:#94a3b8;">Valor objetivo (sector-ajustado):</span>
        <span style="font-family:'IBM Plex Mono',monospace;font-weight:600;color:#f1f5f9;">
          {fair_str}
        </span>
        <span style="font-family:'IBM Plex Mono',monospace;font-weight:700;color:{upside_color};">
          ({upside_str})
        </span>
      </div>

      <div class="verdict-sub">
        <span style="color:#94a3b8;">Vs. media 52W:</span>
        <span style="font-family:'IBM Plex Mono',monospace;font-weight:600;color:#fbbf24;">
          {hist_str}
        </span>
      </div>

      <div class="verdict-sub" style="margin-top:0.4rem;">
        <span style="color:#94a3b8;">Presión vendedora (short ratio):</span>
        <span style="color:#e2e8f0;"> riesgo técnico estimado {ev['risk']}%</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    sec_label = "SEC EDGAR + Yahoo Finance" if sec else "Yahoo Finance"

    # ── H · Señal de confluencia de entrada ──────────────────────────────
    signal = calc_entry_signal(y, tech, ev)
    render_entry_signal(signal)

    # ── I · Tendencia trimestral ──────────────────────────────────────────
    trend = calc_trend(sec)
    render_trend(trend)

    # ── J · Comparativa con competidores ─────────────────────────────────
    with st.spinner("Cargando datos de competidores…"):
        peers_tickers = get_peers(ticker, y.get("sector",""), y.get("company_name",""))
        peers_data    = fetch_peer_data(peers_tickers)
    render_peers(ticker, y, peers_data, fx_rate, ev)

    st.caption(f"Datos: {sec_label} · {ticker} · USD/EUR: {fx_rate:.4f} · Valoración ajustada al sector {ev['sector_label']} · No constituye asesoramiento financiero.")
