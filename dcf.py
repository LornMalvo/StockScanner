"""
dcf.py — v2.2
Valoración rigurosa con DCF real y análisis de múltiplos históricos propios.

DCF:
  - FCF real de los últimos 12 meses (Yahoo Finance)
  - WACC = Ke×(E/V) + Kd×(D/V)×(1-t)
      · Ke = Rf + β × (Rm - Rf)   [CAPM]
      · Rf = tipo bono USA 10 años en tiempo real (^TNX vía yfinance)
      · Prima de riesgo de mercado (Rm-Rf) = 5.5% (media histórica S&P 500)
      · Kd = coste de deuda implícito (intereses / deuda total)
  - Tres escenarios: pesimista / base / optimista
  - Valor terminal con tasa de perpetuidad conservadora (2.5%)

Histórico de múltiplos propios:
  - PER medio de los últimos 5 años de la empresa (precio / EPS TTM)
  - Compara PER actual vs su propia media histórica
"""

import yfinance as yf
import streamlit as st
import pandas as pd
from datetime import datetime, timezone
import db


# ─────────────────────────────────────────────────────────────────────────────
# TIPO LIBRE DE RIESGO — Bono USA 10 años en tiempo real
# ─────────────────────────────────────────────────────────────────────────────

def fetch_risk_free_rate() -> float | None:
    """
    Obtiene el rendimiento del bono del Tesoro USA a 10 años en tiempo real.
    Ticker: ^TNX (expresado en %). Devuelve None si no se puede obtener —
    NO usa un fallback silencioso aquí: cada consumidor (calc_dcf,
    _adjust_sector_profile en report.py) decide explícitamente cómo
    reaccionar ante la ausencia de dato, para poder ser honesto en la UI
    sobre si se está usando un tipo de interés real o uno de respaldo.
    """
    try:
        tnx  = yf.Ticker("^TNX")
        info = tnx.info
        rate = info.get("regularMarketPrice") or info.get("previousClose")
        if rate and 0 < rate < 20:
            return rate / 100   # ^TNX viene en %, lo convertimos a decimal
    except Exception:
        pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# CÁLCULO DE WACC
# ─────────────────────────────────────────────────────────────────────────────

def calc_wacc(y: dict, rf: float) -> dict:
    """
    Calcula el WACC con datos de Yahoo Finance.
    Devuelve dict con WACC y sus componentes para transparencia total.
    """
    beta        = y.get("beta") or 1.0
    market_cap  = y.get("market_cap") or 0
    total_debt  = y.get("total_debt") or 0
    interest_exp= y.get("interest_expense") or 0   # puede no estar en Yahoo
    tax_rate    = 0.21   # tipo impositivo aproximado USA

    # Coste del capital propio — CAPM
    erp = 0.055   # equity risk premium histórico S&P 500 (Damodaran)
    ke  = rf + beta * erp

    # Coste de la deuda — implícito por intereses / deuda, o estimado
    if total_debt > 0 and interest_exp and interest_exp > 0:
        kd_pre = interest_exp / total_debt
        kd_pre = max(0.02, min(kd_pre, 0.12))   # sanity check 2-12%
    else:
        kd_pre = rf + 0.015   # spread crédito conservador sobre Rf

    kd_after = kd_pre * (1 - tax_rate)   # escudo fiscal

    # Pesos en estructura de capital
    total_value = market_cap + total_debt
    if total_value == 0:
        e_w = 1.0
        d_w = 0.0
    else:
        e_w = market_cap / total_value
        d_w = total_debt / total_value

    wacc = ke * e_w + kd_after * d_w

    # Sanity check: WACC entre 4% y 20%
    wacc = max(0.04, min(wacc, 0.20))

    return {
        "wacc":      round(wacc, 4),
        "ke":        round(ke, 4),
        "kd_pre":    round(kd_pre, 4),
        "kd_after":  round(kd_after, 4),
        "e_weight":  round(e_w, 4),
        "d_weight":  round(d_w, 4),
        "beta":      round(beta, 2),
        "rf":        round(rf, 4),
        "erp":       erp,
        "tax_rate":  tax_rate,
    }


# ─────────────────────────────────────────────────────────────────────────────
# TASA DE CRECIMIENTO FCF
# ─────────────────────────────────────────────────────────────────────────────

def _growth_scenarios(y: dict) -> dict:
    """
    Genera tres tasas de crecimiento FCF basadas en datos reales.
    Base: media de crecimiento de ingresos YoY y beneficios YoY.
    """
    rev_yoy  = (y.get("revenue_yoy")  or 0) / 100
    earn_yoy = (y.get("earnings_yoy") or 0) / 100

    # Tasa base = media ponderada (60% ingresos, 40% beneficios)
    if earn_yoy > -1 and rev_yoy > -1:   # evitar datos absurdos
        base_raw = rev_yoy * 0.6 + earn_yoy * 0.4
    elif rev_yoy > -1:
        base_raw = rev_yoy
    else:
        base_raw = 0.05   # fallback conservador 5%

    # Cada escenario se acota de forma INDEPENDIENTE a partir de la tasa
    # BRUTA (base_raw), no del valor de "base" ya acotado con su propio
    # suelo del -5% — si pesimista y optimista se derivaran del "base" ya
    # topado, ambos podían colapsar en el mismo número cuando la empresa
    # ya tiene un crecimiento TTM muy deprimido (p.ej. una fase de fuerte
    # inversión con beneficios temporalmente muy negativos): "base" se
    # quedaba anclado en el suelo del -5% y "pesimista = base − 10pp"
    # topaba en ese MISMO suelo, dando Pesimista = Base idénticos.
    base        = max(-0.05, min(base_raw,       0.35))
    pessimistic = max(-0.25, min(base_raw - 0.10, 0.25))
    optimistic  = max(-0.05, min(base_raw + 0.10, 0.40))

    # Salvaguarda final: garantizar SIEMPRE pesimista < base < optimista
    # con una separación mínima de 3pp entre escenarios consecutivos,
    # incluso en casos límite donde los suelos/techos independientes de
    # arriba pudieran cruzarse entre sí
    if pessimistic >= base - 0.03:
        pessimistic = base - 0.03
    if optimistic <= base + 0.03:
        optimistic = base + 0.03

    return {
        "pessimistic": pessimistic,
        "base":        base,
        "optimistic":  optimistic,
    }


# ─────────────────────────────────────────────────────────────────────────────
# DCF PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def calc_dcf(y: dict, rf: float | None = None) -> dict | None:
    """
    Calcula el valor intrínseco por DCF con 3 escenarios.

    Metodología:
      1. FCF TTM como base (Free Cash Flow últimos 12 meses)
      2. Proyección 10 años con tasa de crecimiento por escenario
      3. Valor terminal: Gordon Growth Model con g=2.5%
      4. Descuento al WACC real
      5. Ajuste por caja neta y deuda (equity value)
      6. Dividir por acciones en circulación → precio objetivo por acción

    Limitaciones explícitas mostradas en la UI:
      - FCF de un solo año puede ser atípico (inversiones extraordinarias)
      - Las tasas de crecimiento futuras son estimaciones con alto margen de error
      - El WACC es sensible al beta, que varía con el mercado
    """
    fcf        = y.get("free_cash_flow")
    market_cap = y.get("market_cap") or 0
    price      = y.get("price") or 0
    shares     = market_cap / price if price else 0
    total_cash = y.get("total_cash") or 0
    total_debt = y.get("total_debt") or 0
    net_cash   = total_cash - total_debt

    if not fcf or not price or not shares or shares == 0:
        return None

    if rf is None:
        rf = fetch_risk_free_rate()
    rf_is_fallback = False
    if rf is None:
        rf = 0.045   # fallback conservador — se marca explícitamente para
        rf_is_fallback = True   # que la UI pueda avisar de que no es el tipo real en vivo

    wacc_data  = calc_wacc(y, rf)
    wacc       = wacc_data["wacc"]
    scenarios  = _growth_scenarios(y)
    g_terminal = 0.025   # tasa crecimiento perpetuo conservadora

    # Proyección 10 años para cada escenario
    projection_years = 10
    results = {}

    for scenario, g_rate in scenarios.items():
        fcf_t     = float(fcf)
        pv_fcfs   = []
        yearly    = []

        for t in range(1, projection_years + 1):
            # Crecimiento decreciente: los primeros 5 años al ritmo proyectado,
            # los siguientes 5 reduciendo progresivamente hacia g_terminal
            if t <= 5:
                g = g_rate
            else:
                # Convergencia lineal hacia g_terminal en años 6-10
                weight = (t - 5) / 5
                g      = g_rate * (1 - weight) + g_terminal * weight

            fcf_t  = fcf_t * (1 + g)
            pv_fcf = fcf_t / ((1 + wacc) ** t)
            pv_fcfs.append(pv_fcf)
            yearly.append({
                "year":   t,
                "g":      round(g * 100, 1),
                "fcf":    round(fcf_t),
                "pv_fcf": round(pv_fcf),
            })

        # Valor terminal (Gordon Growth Model)
        fcf_terminal  = fcf_t * (1 + g_terminal)
        terminal_val  = fcf_terminal / (wacc - g_terminal)
        pv_terminal   = terminal_val / ((1 + wacc) ** projection_years)

        # Enterprise Value = suma PV FCFs + PV terminal
        ev = sum(pv_fcfs) + pv_terminal

        # Equity Value = EV + caja neta
        equity_val    = ev + net_cash
        price_target  = equity_val / shares if shares else 0

        results[scenario] = {
            "price_target":  round(price_target, 2),
            "equity_value":  round(equity_val),
            "ev":            round(ev),
            "pv_fcfs_sum":   round(sum(pv_fcfs)),
            "pv_terminal":   round(pv_terminal),
            "terminal_val":  round(terminal_val),
            "g_rate":        round(g_rate * 100, 1),
            "upside":        round((price_target - price) / price * 100, 1) if price else None,
            "yearly":        yearly,
        }

    return {
        "scenarios":    results,
        "wacc":         wacc_data,
        "rf":           round(rf * 100, 2),
        "rf_is_fallback": rf_is_fallback,
        "g_terminal":   g_terminal * 100,
        "fcf_base":     fcf,
        "net_cash":     net_cash,
        "shares":       round(shares),
        "price":        price,
        "years":        projection_years,
    }


# ─────────────────────────────────────────────────────────────────────────────
# HISTÓRICO DE MÚLTIPLOS PROPIOS
# ─────────────────────────────────────────────────────────────────────────────

def fetch_historical_multiples(ticker: str, y: dict, sector_pe_fair: float | None = None) -> dict | None:
    """
    PER histórico propio de los últimos 5 años + comparación con el PER
    ACTUAL y el PER "justo" del sector.

    La parte cara (histórico de precios mensuales + EPS anual, vía
    yfinance) se cachea en Supabase con caché persistente
    (data_type='historical_multiples' — solo cambia con cada cierre de
    año fiscal, no tiene sentido pedirla en cada carga). La comparación
    con el PER actual y el PER del sector se recalcula siempre en
    caliente con `y`/`sector_pe_fair` frescos, para no comparar contra
    una fotografía antigua del PER de hoy.
    """
    ticker = ticker.upper().strip()

    cached = db.cache_get(ticker, "historical_multiples")
    if cached is not None:
        per_history = cached.get("history")
    else:
        per_history = _fetch_per_history_live(ticker, y)
        if per_history is not None:
            db.cache_set(ticker, "historical_multiples", {"history": per_history})

    if not per_history:
        return None

    return _build_multiples_result(per_history, y.get("pe_trailing"), sector_pe_fair)


def _fetch_per_history_live(ticker: str, y: dict) -> list | None:
    """Parte cara y cacheable: PER anual real de los últimos 5 años vía yfinance."""
    try:
        t = yf.Ticker(ticker)

        # Histórico de precios (5 años)
        hist = t.history(period="5y", interval="1mo")
        if hist.empty or len(hist) < 12:
            return None

        # EPS anual histórico
        financials = t.financials   # annual income statement
        if financials is None or financials.empty:
            return None

        eps_row = None
        for label in ["Diluted EPS", "Basic EPS", "EPS"]:
            if label in financials.index:
                eps_row = financials.loc[label]
                break

        if eps_row is None:
            # Calcular EPS desde net income / shares
            ni_row = None
            for label in ["Net Income", "Net Income Common Stockholders"]:
                if label in financials.index:
                    ni_row = financials.loc[label]
                    break
            if ni_row is None:
                return None
            shares = y.get("market_cap", 0) / (y.get("price", 1) or 1)
            if shares > 0:
                eps_row = ni_row / shares
            else:
                return None

        # Para cada año fiscal, calcular el PER medio
        per_history = []
        for date, eps_val in eps_row.items():
            if not eps_val or eps_val <= 0:
                continue
            year = date.year
            # Precio medio del año
            year_prices = hist[hist.index.year == year]["Close"]
            if year_prices.empty:
                continue
            avg_price = float(year_prices.mean())
            per_val   = avg_price / float(eps_val)
            if 3 < per_val < 200:   # filtrar valores absurdos
                per_history.append({
                    "year":  year,
                    "per":   round(per_val, 1),
                    "price": round(avg_price, 2),
                    "eps":   round(float(eps_val), 2),
                })

        per_history.sort(key=lambda x: x["year"])
        return per_history or None

    except Exception as e:
        print(f"[Multiples] Error: {e}")
        return None


def _build_multiples_result(per_history: list, current_per: float | None,
                             sector_pe_fair: float | None) -> dict:
    """Parte barata y siempre fresca: agrega el histórico (cacheado o recién pedido) contra el PER actual."""
    per_values  = [h["per"] for h in per_history]
    per_mean    = round(sum(per_values) / len(per_values), 1)
    per_min     = round(min(per_values), 1)
    per_max     = round(max(per_values), 1)

    # Comparación PER actual vs media histórica
    if current_per and per_mean:
        discount = round((current_per - per_mean) / per_mean * 100, 1)
        if discount < -20:
            signal = ("MUY BARATO vs su historia", "#059669")
        elif discount < -5:
            signal = ("BARATO vs su historia", "#16a34a")
        elif discount < 5:
            signal = ("EN LÍNEA con su historia", "#d97706")
        elif discount < 20:
            signal = ("CARO vs su historia", "#ea580c")
        else:
            signal = ("MUY CARO vs su historia", "#dc2626")
    else:
        discount = None
        signal   = ("Sin comparativa", "#64748b")

    return {
        "history":       per_history,
        "per_mean":      per_mean,
        "per_min":       per_min,
        "per_max":       per_max,
        "per_current":   current_per,
        "sector_pe_fair":sector_pe_fair,
        "discount":      discount,
        "signal":        signal,
        "n_years":       len(per_history),
    }


# ─────────────────────────────────────────────────────────────────────────────
# RENDER — DCF
# ─────────────────────────────────────────────────────────────────────────────

def render_dcf(dcf: dict | None, currency: str = "USD", fx_rate: float | None = None):
    st.markdown('<div class="section-header">VALORACIÓN DCF — TRES ESCENARIOS</div>',
                unsafe_allow_html=True)

    if not dcf:
        st.markdown(
            '<div class="metric-card"><span style="color:#64748b;">'
            'DCF no disponible — se necesita Free Cash Flow positivo y precio válido.</span></div>',
            unsafe_allow_html=True)
        return

    if dcf.get("rf_is_fallback"):
        st.markdown(
            '<div style="padding:0.45rem 0.7rem;background:#fff7ed;border-left:3px solid #ea580c;'
            'border-radius:4px;margin-bottom:0.6rem;font-size:0.72rem;color:#9a3412;">'
            '⚠ No se pudo obtener el bono 10Y USA en tiempo real — este DCF usa un tipo libre '
            'de riesgo de respaldo (4.5%), no el dato en vivo.</div>',
            unsafe_allow_html=True
        )

    price    = dcf["price"]
    wacc     = dcf["wacc"]
    rf       = dcf["rf"]
    g_t      = dcf["g_terminal"]
    fcf_base = dcf["fcf_base"]
    scenarios = dcf["scenarios"]

    def fmt_price(v):
        if v is None: return "N/A"
        s = f"{currency} {v:,.2f}"
        if fx_rate and currency == "USD":
            s += f' <span style="color:#64748b;font-size:0.82em;">(€{v*fx_rate:,.2f})</span>'
        return s

    def fmt_big(v):
        if not v: return "N/A"
        v = float(v)
        if abs(v) >= 1e12: return f"${v/1e12:.2f}T"
        if abs(v) >= 1e9:  return f"${v/1e9:.2f}B"
        if abs(v) >= 1e6:  return f"${v/1e6:.0f}M"
        return f"${v:,.0f}"

    # Parámetros del modelo
    wacc_pct = wacc["wacc"] * 100
    ke_pct   = wacc["ke"]   * 100
    kd_pct   = wacc["kd_after"] * 100

    def _tip(text: str) -> str:
        """Genera icono ? con tooltip nativo (title=) compatible con tablas y cards."""
        safe = text.replace('"', '&quot;')
        return (
            f'<span title="{safe}" style="margin-left:0.3rem;cursor:help;'
            f'font-size:0.6rem;color:#94a3b8;border:1px solid #cbd5e1;'
            f'border-radius:50%;padding:0 3px;font-family:monospace;'
            f'vertical-align:middle;">?</span>'
        )

    tip_fcf  = _tip(
        "Free Cash Flow de los últimos 12 meses (TTM). "
        "Es el dinero real generado por el negocio tras pagar gastos operativos e inversiones (capex). "
        "Es la base del DCF: todo el modelo proyecta cómo crecerá este número en los próximos 10 años."
    )
    tip_wacc = _tip(
        "Weighted Average Cost of Capital: coste medio ponderado del capital. "
        "Es la tasa de descuento que aplicamos a los flujos futuros. "
        "Combina el coste del capital propio (Ke) y el de la deuda (Kd) según su peso en la estructura financiera. "
        "A mayor WACC, menor es el valor presente de los flujos futuros. "
        "Rango habitual: 6-12%. >15% penaliza mucho la valoración."
    )
    tip_rf   = _tip(
        "Tasa libre de riesgo: rendimiento del bono del Tesoro USA a 10 años, obtenido en tiempo real (^TNX). "
        "Es la rentabilidad mínima exigida a cualquier inversión sin riesgo. "
        "Cuando sube (tipos altos), el WACC sube y los valores DCF bajan, y viceversa. "
        "Actualmente refleja el entorno de tipos vigente."
    )
    tip_beta = _tip(
        "β (Beta): volatilidad de la acción respecto al mercado. Beta=1 se mueve igual que el índice, "
        ">1 más volátil, <1 más estable. Afecta al Ke (coste del capital propio). "
        "Ke = Rf + β × ERP, donde ERP (prima de riesgo) = 5.5% (media histórica S&P 500). "
        "Kd(at) = coste de la deuda tras impuestos = Kd × (1 - tipo impositivo)."
    )

    st.markdown(
        f'<div class="metric-card" style="border-left:3px solid #0284c7;">'
        f'<div class="metric-label">PARÁMETROS DEL MODELO</div>'
        f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:0.5rem;margin-top:0.5rem;">'
        f'<div style="background:#f4f6f9;border-radius:6px;padding:0.45rem 0.6rem;">'
        f'<div style="font-size:0.67rem;color:#64748b;">FCF base (TTM){tip_fcf}</div>'
        f'<div style="font-family:\'IBM Plex Mono\',monospace;color:#0f172a;font-weight:600;font-size:0.9rem;">{fmt_big(fcf_base)}</div>'
        f'</div>'
        f'<div style="background:#f4f6f9;border-radius:6px;padding:0.45rem 0.6rem;">'
        f'<div style="font-size:0.67rem;color:#64748b;">WACC{tip_wacc}</div>'
        f'<div style="font-family:\'IBM Plex Mono\',monospace;color:#0284c7;font-weight:600;font-size:0.9rem;">{wacc_pct:.2f}%</div>'
        f'</div>'
        f'<div style="background:#f4f6f9;border-radius:6px;padding:0.45rem 0.6rem;">'
        f'<div style="font-size:0.67rem;color:#64748b;">Rf (bono 10Y USA){tip_rf}</div>'
        f'<div style="font-family:\'IBM Plex Mono\',monospace;color:#0f172a;font-weight:600;font-size:0.9rem;">{rf:.2f}%</div>'
        f'</div>'
        f'<div style="background:#f4f6f9;border-radius:6px;padding:0.45rem 0.6rem;">'
        f'<div style="font-size:0.67rem;color:#64748b;">β · Ke · Kd(at){tip_beta}</div>'
        f'<div style="font-family:\'IBM Plex Mono\',monospace;color:#0f172a;font-weight:600;font-size:0.9rem;">{wacc["beta"]} · {ke_pct:.1f}% · {kd_pct:.1f}%</div>'
        f'</div>'
        f'</div>'
        f'<div style="font-size:0.7rem;color:#94a3b8;margin-top:0.5rem;">'
        f'WACC = Ke×{wacc["e_weight"]*100:.0f}% + Kd(at)×{wacc["d_weight"]*100:.0f}% &nbsp;·&nbsp; '
        f'ERP = {wacc["erp"]*100:.1f}% (media histórica S&amp;P 500) &nbsp;·&nbsp; '
        f'g terminal = {g_t:.1f}% &nbsp;·&nbsp; Horizonte = {dcf["years"]} años'
        f'</div></div>',
        unsafe_allow_html=True
    )

    # Tres escenarios
    scenario_labels = {
        "pessimistic": ("PESIMISTA",  "#dc2626", "▼"),
        "base":        ("BASE",       "#d97706", "="),
        "optimistic":  ("OPTIMISTA",  "#059669", "▲"),
    }

    cols = st.columns(3)
    for i, (sc_key, (sc_name, sc_col, sc_icon)) in enumerate(scenario_labels.items()):
        sc = scenarios.get(sc_key, {})
        pt = sc.get("price_target", 0)
        up = sc.get("upside")
        g  = sc.get("g_rate", 0)
        pv_f = sc.get("pv_fcfs_sum", 0)
        pv_t = sc.get("pv_terminal", 0)
        ev   = sc.get("ev", 0)

        up_str = f"{up:+.1f}%" if up is not None else "N/A"
        up_col = "#059669" if (up or 0) > 0 else "#dc2626"

        with cols[i]:
            st.markdown(f"""
            <div style="background:#f4f6f9;border:2px solid {sc_col};border-radius:8px;
                        padding:1rem;text-align:center;margin-bottom:0.5rem;">
              <div style="font-family:'IBM Plex Mono',monospace;font-size:0.7rem;
                          color:{sc_col};text-transform:uppercase;letter-spacing:0.1em;">
                {sc_icon} {sc_name}
              </div>
              <div style="font-family:'IBM Plex Mono',monospace;font-size:1.5rem;
                          font-weight:700;color:{sc_col};margin:0.4rem 0;">
                {currency} {pt:,.2f}
              </div>
              <div style="font-size:0.75rem;color:{up_col};font-weight:700;">{up_str} vs precio actual</div>
              <div style="margin-top:0.6rem;font-size:0.72rem;color:#64748b;text-align:left;">
                Crec. FCF proyectado: <b style="color:#0f172a;">{g:+.1f}%</b><br>
                PV FCFs (10a): <b style="color:#0f172a;">{fmt_big(pv_f)}</b><br>
                PV terminal: <b style="color:#0f172a;">{fmt_big(pv_t)}</b><br>
                Enterprise Value: <b style="color:#0f172a;">{fmt_big(ev)}</b>
              </div>
            </div>
            """, unsafe_allow_html=True)

    # Aviso metodológico
    st.markdown("""
    <div style="background:#fffbeb;border:1px solid #d97706;border-radius:6px;
                padding:0.7rem 0.9rem;font-size:0.75rem;color:#d97706;margin-top:0.3rem;">
      <b>⚠ Limitaciones del DCF:</b> El FCF de un solo año puede ser atípico.
      Las tasas de crecimiento futuras son estimaciones con alto margen de error.
      Un cambio del 1% en el WACC puede mover el precio objetivo un 15-25%.
      Úsalo como referencia de orden de magnitud, no como precio exacto.
    </div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# RENDER — HISTÓRICO DE MÚLTIPLOS
# ─────────────────────────────────────────────────────────────────────────────

def render_historical_multiples(mult: dict | None):
    st.markdown('<div class="section-header">HISTÓRICO DE MÚLTIPLOS PROPIOS (PER 5 años)</div>',
                unsafe_allow_html=True)

    if not mult:
        st.markdown(
            '<div class="metric-card"><span style="color:#64748b;">'
            'Datos históricos insuficientes para calcular el PER medio.</span></div>',
            unsafe_allow_html=True)
        return

    sig_label, sig_color = mult["signal"]
    discount   = mult["discount"]
    per_cur    = mult["per_current"]
    per_mean   = mult["per_mean"]
    per_min    = mult["per_min"]
    per_max    = mult["per_max"]
    history    = mult["history"]
    sector_pe  = mult.get("sector_pe_fair")

    # Mini chart de barras horizontales
    bars = ""
    all_pers = [h["per"] for h in history]
    if per_cur:
        all_pers.append(per_cur)
    if sector_pe:
        all_pers.append(sector_pe)
    max_per = max(all_pers) if all_pers else 1

    for h in history:
        w   = min(h["per"] / max_per * 100, 100)
        col = "#0284c7"
        bars += (
            f'<div style="display:flex;align-items:center;gap:0.5rem;'
            f'padding:0.2rem 0;font-size:0.78rem;">'
            f'<span style="color:#64748b;min-width:2.5rem;">{h["year"]}</span>'
            f'<div style="flex:1;background:#e2e8f0;border-radius:3px;height:14px;">'
            f'<div style="width:{w}%;height:14px;background:{col};border-radius:3px;"></div></div>'
            f'<span style="font-family:\'IBM Plex Mono\',monospace;color:#0f172a;'
            f'min-width:3.5rem;text-align:right;">{h["per"]}×</span>'
            f'</div>'
        )

    # Barra del PER medio del sector (referencia)
    if sector_pe:
        w_sec = min(sector_pe / max_per * 100, 100)
        bars += (
            f'<div style="display:flex;align-items:center;gap:0.5rem;'
            f'padding:0.2rem 0;font-size:0.78rem;">'
            f'<span style="color:#7c3aed;font-weight:600;min-width:2.5rem;">SECTOR</span>'
            f'<div style="flex:1;background:#e2e8f0;border-radius:3px;height:14px;">'
            f'<div style="width:{w_sec}%;height:14px;background:#7c3aed;border-radius:3px;opacity:0.65;'
            f'background-image:repeating-linear-gradient(45deg,transparent,transparent 3px,'
            f'rgba(255,255,255,0.3) 3px,rgba(255,255,255,0.3) 6px);"></div></div>'
            f'<span style="font-family:\'IBM Plex Mono\',monospace;color:#7c3aed;'
            f'font-weight:600;min-width:3.5rem;text-align:right;">{sector_pe}×</span>'
            f'</div>'
        )

    # Barra del PER actual
    if per_cur:
        w_cur = min(per_cur / max_per * 100, 100)
        cur_col = sig_color
        bars += (
            f'<div style="display:flex;align-items:center;gap:0.5rem;'
            f'padding:0.25rem 0;font-size:0.78rem;border-top:1px solid #e2e8f0;margin-top:0.2rem;">'
            f'<span style="color:{cur_col};font-weight:700;min-width:2.5rem;">HOY</span>'
            f'<div style="flex:1;background:#e2e8f0;border-radius:3px;height:14px;">'
            f'<div style="width:{w_cur}%;height:14px;background:{cur_col};border-radius:3px;"></div></div>'
            f'<span style="font-family:\'IBM Plex Mono\',monospace;color:{cur_col};'
            f'font-weight:700;min-width:3.5rem;text-align:right;">{per_cur:.1f}×</span>'
            f'</div>'
        )

    discount_str = f"{discount:+.1f}%" if discount is not None else "N/A"
    per_cur_str  = f"{per_cur:.1f}×" if per_cur is not None else "N/A"
    sector_pe_str = f"{sector_pe}×" if sector_pe is not None else "N/A"

    # Comparación PER actual vs PER sector
    vs_sector_str = "N/A"
    vs_sector_color = "#64748b"
    if per_cur and sector_pe:
        vs_sector_pct = (per_cur - sector_pe) / sector_pe * 100
        vs_sector_str = f"{vs_sector_pct:+.1f}%"
        vs_sector_color = "#dc2626" if vs_sector_pct > 0 else "#059669"

    st.markdown(
        '<div class="metric-card">'
        '<div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr 1fr;gap:0.5rem;margin-bottom:0.8rem;">'
        f'<div style="background:#f4f6f9;border-radius:6px;padding:0.4rem 0.6rem;">'
        f'<div style="font-size:0.67rem;color:#64748b;">PER actual</div>'
        f'<div style="font-family:\'IBM Plex Mono\',monospace;color:{sig_color};font-weight:600;">{per_cur_str}</div></div>'
        f'<div style="background:#f4f6f9;border-radius:6px;padding:0.4rem 0.6rem;">'
        f'<div style="font-size:0.67rem;color:#64748b;">Media 5 años (propia)</div>'
        f'<div style="font-family:\'IBM Plex Mono\',monospace;color:#0f172a;font-weight:600;">{per_mean}×</div></div>'
        f'<div style="background:#f4f6f9;border-radius:6px;padding:0.4rem 0.6rem;">'
        f'<div style="font-size:0.67rem;color:#7c3aed;">PER medio sector</div>'
        f'<div style="font-family:\'IBM Plex Mono\',monospace;color:#7c3aed;font-weight:600;">{sector_pe_str}</div></div>'
        f'<div style="background:#f4f6f9;border-radius:6px;padding:0.4rem 0.6rem;">'
        f'<div style="font-size:0.67rem;color:#64748b;">Rango histórico</div>'
        f'<div style="font-family:\'IBM Plex Mono\',monospace;color:#64748b;font-weight:600;">{per_min}× – {per_max}×</div></div>'
        f'<div style="background:#f4f6f9;border-radius:6px;padding:0.4rem 0.6rem;">'
        f'<div style="font-size:0.67rem;color:#64748b;">Vs. sector</div>'
        f'<div style="font-family:\'IBM Plex Mono\',monospace;color:{vs_sector_color};font-weight:600;">{vs_sector_str}</div></div>'
        '</div>'
        f'<div style="font-size:0.8rem;font-weight:600;color:{sig_color};margin-bottom:0.6rem;">▸ {sig_label} '
        f'<span style="font-weight:400;color:#64748b;">(vs su propia historia · {discount_str})</span></div>'
        f'{bars}'
        f'<div style="font-size:0.68rem;color:#7c3aed;margin-top:0.5rem;">'
        f'▨ SECTOR = PER "justo" de referencia usado por la app para el sector de esta empresa</div>'
        '</div>',
        unsafe_allow_html=True
    )
