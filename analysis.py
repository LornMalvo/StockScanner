"""
analysis.py
Módulos de análisis avanzado:
  - Señal de confluencia de entrada
  - Tendencia trimestral (SEC EDGAR)
  - Comparativa de competidores por sector
"""

import yfinance as yf
import streamlit as st

# ─────────────────────────────────────────────────────────────────────────────
# COMPETIDORES POR SECTOR  (lista curada, ampliable)
# ─────────────────────────────────────────────────────────────────────────────

SECTOR_PEERS = {
    "Technology": {
        "Semiconductors":         ["NVDA","AMD","INTC","QCOM","AVGO","MU","AMAT","KLAC","LRCX","ASML"],
        "Software":               ["MSFT","ORCL","SAP","CRM","NOW","ADBE","WDAY","TEAM","SNOW","MDB"],
        "Hardware / Storage":     ["AAPL","DELL","HPQ","WDC","STX","NTAP","PSTG","SMCI","ANET"],
        "General Technology":     ["AAPL","MSFT","GOOGL","META","NVDA","AVGO","ORCL","CRM","ADBE","AMD"],
    },
    "Communication Services": {
        "General":                ["GOOGL","META","NFLX","DIS","CMCSA","T","VZ","TMUS","SNAP","PINS"],
    },
    "Consumer Cyclical": {
        "General":                ["AMZN","TSLA","HD","MCD","NKE","LOW","SBUX","CMG","BKNG","TJX"],
    },
    "Consumer Defensive": {
        "General":                ["WMT","COST","PG","KO","PEP","MO","PM","MDLZ","GIS","K"],
    },
    "Healthcare": {
        "Pharma":                 ["LLY","JNJ","PFE","MRK","ABBV","BMY","AZN","NVO","SNY","GSK"],
        "Biotech / Devices":      ["AMGN","GILD","REGN","VRTX","ISRG","MDT","ABT","BSX","EW","SYK"],
        "General Healthcare":     ["LLY","JNJ","UNH","ABBV","MRK","TMO","ABT","DHR","BMY","AMGN"],
    },
    "Financials": {
        "Banks":                  ["JPM","BAC","WFC","C","GS","MS","USB","TFC","PNC","COF"],
        "Insurance / Other":      ["BRK-B","V","MA","AXP","BLK","SCHW","CB","PRU","MET","ALL"],
        "General Financials":     ["JPM","BAC","GS","MS","BLK","V","MA","AXP","SCHW","BRK-B"],
    },
    "Industrials": {
        "General":                ["HON","GE","CAT","DE","RTX","LMT","NOC","UNP","FDX","UPS"],
    },
    "Energy": {
        "General":                ["XOM","CVX","COP","EOG","OXY","SLB","MPC","VLO","PSX","HES"],
    },
    "Basic Materials": {
        "General":                ["LIN","APD","SHW","FCX","NEM","NUE","STLD","ECL","PPG","ALB"],
    },
    "Real Estate": {
        "General":                ["PLD","AMT","EQIX","CCI","SPG","O","VICI","PSA","EQR","AVB"],
    },
    "Utilities": {
        "General":                ["NEE","SO","DUK","AEP","EXC","SRE","XEL","ES","D","PCG"],
    },
    "_default": {
        "General":                ["AAPL","MSFT","AMZN","GOOGL","META","NVDA","JPM","JNJ","V","XOM"],
    },
}

def get_peers(ticker: str, sector: str, company_name: str) -> list[str]:
    """Devuelve lista de competidores para un ticker dado su sector."""
    # Buscar sector en el mapa
    sector_map = None
    for key in SECTOR_PEERS:
        if key != "_default" and key.lower() in (sector or "").lower():
            sector_map = SECTOR_PEERS[key]
            break
    if not sector_map:
        sector_map = SECTOR_PEERS["_default"]

    # Elegir subsector: si hay uno solo, usarlo; si hay varios, usar el primero genérico
    if len(sector_map) == 1:
        peers = list(sector_map.values())[0]
    else:
        # Intentar detectar subsector por nombre de empresa o ticker
        name_lower = (company_name or "").lower()
        tick_lower = ticker.lower()
        chosen = None
        for subsector, tickers in sector_map.items():
            if subsector == "General Technology" or subsector == "General":
                continue
            sub_lower = subsector.lower()
            if any(w in name_lower or w in tick_lower for w in sub_lower.split("/")):
                chosen = tickers
                break
            # Comprobar si el ticker está en la lista de ese subsector
            if ticker.upper() in tickers:
                chosen = tickers
                break
        peers = chosen or list(sector_map.values())[-1]  # último suele ser el genérico

    # Excluir el ticker analizado
    return [p for p in peers if p.upper() != ticker.upper()][:8]


# ─────────────────────────────────────────────────────────────────────────────
# SEÑAL DE CONFLUENCIA DE ENTRADA
# ─────────────────────────────────────────────────────────────────────────────

def calc_entry_signal(y: dict, tech: dict | None, ev: dict) -> dict:
    """
    Calcula la señal de entrada por confluencia de factores.
    Requiere que se cumplan VARIOS criterios simultáneamente.
    Devuelve dict con nivel, score, factores cumplidos/fallidos.
    """
    price      = y.get("price") or 0
    week52_high = y.get("52w_high") or price
    week52_low  = y.get("52w_low") or price
    upside      = ev.get("upside")
    health      = ev.get("health_score", 0)
    fair_value  = ev.get("fair_value")

    rsi     = tech.get("rsi")    if tech and not tech.get("error") else None
    mm50    = tech.get("mm50")   if tech and not tech.get("error") else None
    mm200   = tech.get("mm200")  if tech and not tech.get("error") else None

    checks = []   # (nombre, cumplido: bool, descripción, peso)

    # ── F1: Precio con margen de seguridad (upside > 10%) ────────────────
    if upside is not None:
        ok = upside >= 10
        checks.append(("Margen de seguridad (upside > 10%)", ok,
            f"Upside estimado: {upside:+.1f}%" if upside else "Sin dato",
            3))  # peso alto

    # ── F2: No en máximos anuales (al menos 10% por debajo) ──────────────
    if week52_high and price:
        dist = (week52_high - price) / week52_high * 100
        ok = dist >= 10
        checks.append(("Alejado de máximos anuales (>10%)", ok,
            f"{dist:.1f}% por debajo del máximo 52W", 2))

    # ── F3: RSI en zona de oportunidad (< 50, ideal < 40) ────────────────
    if rsi is not None:
        ok = rsi < 50
        ideal = rsi < 40
        label = f"RSI = {rsi:.1f} ({'óptimo <40' if ideal else 'aceptable <50' if ok else 'elevado'})"
        checks.append(("RSI en zona de compra (< 50)", ok, label, 2))

    # ── F4: Precio bajo MM200 (zona de rebote) ────────────────────────────
    if mm200 is not None and price:
        ok = price < mm200
        label = f"Precio {'bajo' if ok else 'sobre'} MM200 ({mm200:,.2f})"
        checks.append(("Precio bajo MM200 (posible rebote)", ok, label, 2))

    # ── F5: Salud fundamental sólida (score > 55) ────────────────────────
    ok = health >= 55
    checks.append(("Salud fundamental sólida (>55/100)", ok,
        f"Score fundamental: {health}/100", 3))

    # ── F6: PEG atractivo ────────────────────────────────────────────────
    peg = y.get("peg_ratio")
    peg_ok_ref = ev.get("peg_ok", 1.5)
    if peg is not None:
        ok = peg < peg_ok_ref
        checks.append((f"PEG atractivo (< {peg_ok_ref})", ok,
            f"PEG actual: {peg:.2f}", 2))

    # ── F7: FCF positivo ─────────────────────────────────────────────────
    fcf = y.get("free_cash_flow") or 0
    ok = fcf > 0
    checks.append(("Free Cash Flow positivo", ok,
        f"FCF: {'positivo ✔' if ok else 'negativo ✘'}", 1))

    # ── F8: Corrección reciente (bajo MM50) ──────────────────────────────
    if mm50 is not None and price:
        ok = price < mm50
        label = f"Precio {'bajo' if ok else 'sobre'} MM50 ({mm50:,.2f})"
        checks.append(("Corrección reciente (precio < MM50)", ok, label, 1))

    # ── Cálculo de score ponderado ────────────────────────────────────────
    total_weight   = sum(c[3] for c in checks)
    achieved_weight = sum(c[3] for c in checks if c[1])
    n_checks       = len(checks)
    n_ok           = sum(1 for c in checks if c[1])

    score_pct = (achieved_weight / total_weight * 100) if total_weight else 0

    # ── Nivel de señal ────────────────────────────────────────────────────
    # Exige que los criterios de MAYOR PESO estén cumplidos
    heavy_ok = sum(1 for c in checks if c[1] and c[3] >= 2)
    heavy_total = sum(1 for c in checks if c[3] >= 2)

    if score_pct >= 80 and heavy_ok >= heavy_total - 1:
        level = "ENTRADA IDEAL"
        color = "#6ee7b7"
        icon  = "🟢"
        desc  = "Confluencia fuerte: múltiples factores técnicos y fundamentales alineados."
    elif score_pct >= 60 and heavy_ok >= heavy_total // 2 + 1:
        level = "ENTRADA POSIBLE"
        color = "#86efac"
        icon  = "🟡"
        desc  = "Buena confluencia, aunque no todos los factores clave están alineados."
    elif score_pct >= 40:
        level = "VIGILAR"
        color = "#fbbf24"
        icon  = "🟠"
        desc  = "Algunos factores positivos, pero faltan condiciones clave para una entrada óptima."
    else:
        level = "NO ES MOMENTO"
        color = "#fca5a5"
        icon  = "🔴"
        desc  = "Pocos factores alineados. Esperar mejor precio, menor RSI o mejores fundamentales."

    return {
        "level":   level,
        "color":   color,
        "icon":    icon,
        "desc":    desc,
        "score":   round(score_pct),
        "n_ok":    n_ok,
        "n_total": n_checks,
        "checks":  checks,   # lista de (nombre, cumplido, detalle, peso)
    }


# ─────────────────────────────────────────────────────────────────────────────
# TENDENCIA TRIMESTRAL (SEC EDGAR)
# ─────────────────────────────────────────────────────────────────────────────

def calc_trend(sec: dict | None) -> dict | None:
    """
    Analiza la tendencia de ingresos y beneficio neto trimestre a trimestre.
    Requiere al menos 4 trimestres de datos SEC.
    """
    if not sec:
        return None

    rev_q = sec.get("quarters", [])
    ni_q  = sec.get("ni_quarters", [])

    if len(rev_q) < 2:
        return None

    # Ordenar de más antiguo a más reciente
    rev_sorted = sorted(rev_q, key=lambda x: x.get("date", ""))
    ni_sorted  = sorted(ni_q,  key=lambda x: x.get("date", "")) if ni_q else []

    # Calcular variaciones QoQ
    def qoq_changes(series):
        changes = []
        for i in range(1, len(series)):
            prev = series[i-1].get("value") or 0
            curr = series[i].get("value") or 0
            if prev and prev != 0:
                pct = (curr - prev) / abs(prev) * 100
                changes.append({
                    "date":  series[i].get("date","")[:7],
                    "value": curr,
                    "prev":  prev,
                    "pct":   round(pct, 1),
                })
        return changes

    rev_changes = qoq_changes(rev_sorted)
    ni_changes  = qoq_changes(ni_sorted)

    # Tendencia: cuántos trimestres consecutivos al alza
    def streak(changes):
        if not changes:
            return 0, 0
        up = sum(1 for c in changes if c["pct"] > 0)
        down = sum(1 for c in changes if c["pct"] < 0)
        # Racha actual
        racha = 0
        for c in reversed(changes):
            if c["pct"] > 0:
                racha += 1
            else:
                break
        return up, racha

    rev_up, rev_streak  = streak(rev_changes)
    ni_up,  ni_streak   = streak(ni_changes)
    total_q = len(rev_changes)

    # Señal de tendencia
    if rev_streak >= 3 and ni_streak >= 3:
        trend_signal = ("ACELERACIÓN", "#6ee7b7")
    elif rev_streak >= 2 or ni_streak >= 2:
        trend_signal = ("MEJORANDO", "#86efac")
    elif rev_up > total_q // 2:
        trend_signal = ("ESTABLE", "#fbbf24")
    else:
        trend_signal = ("DETERIORANDO", "#fca5a5")

    return {
        "rev_quarters":  rev_sorted,
        "ni_quarters":   ni_sorted,
        "rev_changes":   rev_changes,
        "ni_changes":    ni_changes,
        "rev_streak":    rev_streak,
        "ni_streak":     ni_streak,
        "trend_signal":  trend_signal,
        "total_q":       total_q,
    }


# ─────────────────────────────────────────────────────────────────────────────
# COMPARATIVA DE COMPETIDORES
# ─────────────────────────────────────────────────────────────────────────────

def fetch_peer_data(peers: list[str]) -> list[dict]:
    """Obtiene métricas clave de los competidores."""
    results = []
    for ticker in peers:
        try:
            t    = yf.Ticker(ticker)
            info = t.info
            if not info:
                continue
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            if not price:
                continue
            results.append({
                "ticker":       ticker,
                "name":         (info.get("shortName") or ticker)[:22],
                "price":        price,
                "pe_forward":   info.get("forwardPE"),
                "pe_trailing":  info.get("trailingPE"),
                "peg":          info.get("pegRatio"),
                "ev_ebitda":    info.get("enterpriseToEbitda"),
                "price_sales":  info.get("priceToSalesTrailing12Months"),
                "profit_m":     (info.get("profitMargins") or 0) * 100,
                "roe":          (info.get("returnOnEquity") or 0) * 100,
                "rev_growth":   (info.get("revenueGrowth") or 0) * 100,
                "market_cap":   info.get("marketCap"),
                "52w_high":     info.get("fiftyTwoWeekHigh"),
                "52w_low":      info.get("fiftyTwoWeekLow"),
            })
        except Exception:
            continue
    return results


# ─────────────────────────────────────────────────────────────────────────────
# RENDER — SEÑAL DE CONFLUENCIA
# ─────────────────────────────────────────────────────────────────────────────

def render_entry_signal(signal: dict):
    _section = lambda t: st.markdown(
        f'<div class="section-header">{t}</div>', unsafe_allow_html=True)
    _section("H · SEÑAL DE ENTRADA")

    score   = signal["score"]
    level   = signal["level"]
    color   = signal["color"]
    icon    = signal["icon"]
    desc    = signal["desc"]
    n_ok    = signal["n_ok"]
    n_total = signal["n_total"]
    checks  = signal["checks"]

    # Barra de confluencia
    checks_html = ""
    for name, ok, detail, weight in checks:
        dot_color = color if ok else "#374151"
        dot       = "●" if ok else "○"
        w_label   = "●" * weight  # puntos de peso visual
        checks_html += f"""
        <div style="display:flex;align-items:flex-start;gap:0.6rem;padding:0.35rem 0;
                    border-bottom:1px solid #1a2540;font-size:0.82rem;">
          <span style="color:{dot_color};font-size:1rem;min-width:1rem;">{dot}</span>
          <div style="flex:1;">
            <span style="color:{'#f1f5f9' if ok else '#64748b'};">{name}</span>
            <span style="color:#64748b;font-size:0.74rem;margin-left:0.4rem;">({detail})</span>
          </div>
          <span style="color:#1e3a5f;font-size:0.65rem;min-width:2rem;text-align:right;">{w_label}</span>
        </div>"""

    st.markdown(f"""
    <div style="background:#0f172a;border:2px solid {color};border-radius:10px;
                padding:1.2rem 1.4rem;margin-bottom:1rem;">
      <div style="display:flex;align-items:center;gap:0.8rem;margin-bottom:0.8rem;">
        <span style="font-size:1.5rem;">{icon}</span>
        <div>
          <div style="font-family:'IBM Plex Mono',monospace;font-size:1.05rem;
                      font-weight:700;color:{color};">{level}</div>
          <div style="font-size:0.8rem;color:#94a3b8;margin-top:0.1rem;">{desc}</div>
        </div>
        <div style="margin-left:auto;text-align:right;">
          <div style="font-family:'IBM Plex Mono',monospace;font-size:1.8rem;
                      font-weight:700;color:{color};">{score}<span style="font-size:1rem;color:#64748b;">/100</span></div>
          <div style="font-size:0.72rem;color:#64748b;">{n_ok}/{n_total} criterios</div>
        </div>
      </div>
      <div style="background:#1e2d45;border-radius:4px;height:6px;margin-bottom:1rem;">
        <div style="height:6px;border-radius:4px;background:{color};width:{score}%;"></div>
      </div>
      <div style="font-size:0.68rem;color:#38bdf8;text-transform:uppercase;
                  letter-spacing:0.1em;margin-bottom:0.3rem;">
        DESGLOSE DE FACTORES &nbsp;·&nbsp;
        <span style="color:#64748b;">● peso alto &nbsp; ●● peso crítico</span>
      </div>
      {checks_html}
    </div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# RENDER — TENDENCIA TRIMESTRAL
# ─────────────────────────────────────────────────────────────────────────────

def render_trend(trend: dict | None):
    _section = lambda t: st.markdown(
        f'<div class="section-header">{t}</div>', unsafe_allow_html=True)
    _section("I · TENDENCIA TRIMESTRAL (SEC EDGAR)")

    if not trend:
        st.markdown('<div class="metric-card"><span style="color:#64748b;">Datos SEC insuficientes — se necesitan al menos 2 trimestres.</span></div>', unsafe_allow_html=True)
        return

    sig_label, sig_color = trend["trend_signal"]
    rev_changes = trend["rev_changes"]
    ni_changes  = trend["ni_changes"]

    def bar_chart_html(changes, label, color_pos="#6ee7b7", color_neg="#fca5a5"):
        if not changes:
            return ""
        max_abs = max(abs(c["pct"]) for c in changes) or 1
        bars = ""
        for c in changes:
            pct   = c["pct"]
            h_pct = min(abs(pct) / max_abs * 80, 80)  # altura máx 80%
            col   = color_pos if pct >= 0 else color_neg
            sign  = "+" if pct >= 0 else ""
            bars += f"""
            <div style="display:flex;flex-direction:column;align-items:center;gap:0.2rem;flex:1;">
              <div style="font-family:'IBM Plex Mono',monospace;font-size:0.68rem;
                          color:{col};font-weight:600;">{sign}{pct:.0f}%</div>
              <div style="height:80px;display:flex;align-items:flex-end;width:100%;">
                <div style="width:100%;height:{h_pct}px;background:{col};
                            border-radius:3px 3px 0 0;min-height:3px;"></div>
              </div>
              <div style="font-size:0.62rem;color:#64748b;transform:rotate(-30deg);
                          transform-origin:top left;white-space:nowrap;
                          margin-top:0.2rem;">{c['date']}</div>
            </div>"""
        return f"""
        <div style="margin-bottom:0.4rem;font-size:0.72rem;color:#94a3b8;
                    text-transform:uppercase;letter-spacing:0.08em;">{label}</div>
        <div style="display:flex;gap:0.3rem;align-items:flex-end;
                    padding-bottom:2rem;margin-bottom:0.5rem;">
          {bars}
        </div>"""

    rev_html = bar_chart_html(rev_changes, "Variación QoQ — Ingresos")
    ni_html  = bar_chart_html(ni_changes,  "Variación QoQ — Beneficio Neto",
                               color_pos="#6ee7b7", color_neg="#fca5a5")

    streak_rev = trend["rev_streak"]
    streak_ni  = trend["ni_streak"]

    st.markdown(f"""
    <div class="metric-card">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:1rem;">
        <div>
          <div style="font-family:'IBM Plex Mono',monospace;font-size:1rem;
                      font-weight:700;color:{sig_color};">{sig_label}</div>
          <div style="font-size:0.76rem;color:#64748b;margin-top:0.2rem;">
            Racha alcista: ingresos {streak_rev}Q · beneficio {streak_ni}Q consecutivos
          </div>
        </div>
        <div style="text-align:right;">
          <div style="font-size:0.7rem;color:#64748b;">Trimestres analizados</div>
          <div style="font-family:'IBM Plex Mono',monospace;font-size:1.2rem;
                      color:#f1f5f9;font-weight:600;">{trend['total_q']}</div>
        </div>
      </div>
      {rev_html}
      {ni_html}
    </div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# RENDER — COMPARATIVA DE COMPETIDORES
# ─────────────────────────────────────────────────────────────────────────────

def render_peers(main_ticker: str, main_data: dict, peers_data: list[dict],
                 fx_rate: float | None, ev: dict):
    _section = lambda t: st.markdown(
        f'<div class="section-header">{t}</div>', unsafe_allow_html=True)
    _section("J · COMPARATIVA CON COMPETIDORES")

    if not peers_data:
        st.markdown('<div class="metric-card"><span style="color:#64748b;">No se pudieron obtener datos de competidores.</span></div>', unsafe_allow_html=True)
        return

    # Construir fila para el ticker principal
    def make_row(ticker, name, d, is_main=False):
        def cell(val, suffix="", decimals=1, highlight=None):
            if val is None or val != val:
                return '<td style="color:#374151;text-align:right;">—</td>'
            color = "#f1f5f9"
            if highlight == "low_good" and val is not None:
                color = "#6ee7b7" if val < highlight_thresholds.get(highlight, 999) else "#fca5a5"
            fmt = f"{val:,.{decimals}f}{suffix}"
            return f'<td style="font-family:\'IBM Plex Mono\',monospace;color:{color};text-align:right;padding:0.3rem 0.5rem;">{fmt}</td>'

        bg  = "#1e3a5f" if is_main else "#111827"
        bdr = "border-left:3px solid #38bdf8;" if is_main else ""
        name_color = "#38bdf8" if is_main else "#e2e8f0"

        pe_f  = d.get("pe_forward")
        peg   = d.get("peg")
        ev_eb = d.get("ev_ebitda")
        pm    = d.get("profit_m")
        roe   = d.get("roe")
        rg    = d.get("rev_growth")
        mc    = d.get("market_cap")

        def colored(val, low_is_good=True, ref=None, suffix="×", dec=1):
            if val is None:
                return '<td style="color:#374151;text-align:right;padding:0.3rem 0.5rem;">—</td>'
            if ref is not None:
                col = "#6ee7b7" if (val < ref) == low_is_good else "#fca5a5"
            else:
                col = "#f1f5f9"
            return f'<td style="font-family:\'IBM Plex Mono\',monospace;color:{col};text-align:right;padding:0.3rem 0.5rem;">{val:,.{dec}f}{suffix}</td>'

        pe_ref  = ev.get("pe_ref", 20)
        peg_ref = ev.get("peg_ok", 1.5)
        ev_ref  = ev.get("ev_ebitda_fair", 14)

        # Market cap formateado
        mc_str = "—"
        if mc:
            if mc >= 1e12:   mc_str = f"${mc/1e12:.1f}T"
            elif mc >= 1e9:  mc_str = f"${mc/1e9:.1f}B"
            else:            mc_str = f"${mc/1e6:.0f}M"

        return f"""
        <tr style="background:{bg};{bdr}border-bottom:1px solid #1a2540;">
          <td style="padding:0.3rem 0.6rem;white-space:nowrap;">
            <span style="font-family:'IBM Plex Mono',monospace;font-weight:700;
                         color:{name_color};">{ticker}</span>
            <span style="font-size:0.72rem;color:#64748b;margin-left:0.3rem;">{name}</span>
            {'<span style="font-size:0.65rem;background:#1e3a5f;color:#38bdf8;padding:1px 5px;border-radius:3px;margin-left:0.3rem;">TÚ</span>' if is_main else ''}
          </td>
          {colored(pe_f,  low_is_good=True,  ref=pe_ref,  suffix="×")}
          {colored(peg,   low_is_good=True,  ref=peg_ref, suffix="")}
          {colored(ev_eb, low_is_good=True,  ref=ev_ref,  suffix="×")}
          {colored(pm,    low_is_good=False, ref=10,      suffix="%")}
          {colored(roe,   low_is_good=False, ref=12,      suffix="%")}
          {colored(rg,    low_is_good=False, ref=5,       suffix="%")}
          <td style="font-family:'IBM Plex Mono',monospace;color:#94a3b8;
                     text-align:right;padding:0.3rem 0.5rem;font-size:0.8rem;">{mc_str}</td>
        </tr>"""

    main_row  = make_row(main_ticker, main_data.get("company_name","")[:22], {
        "pe_forward":  main_data.get("pe_forward"),
        "peg":         main_data.get("peg_ratio"),
        "ev_ebitda":   main_data.get("ev_ebitda"),
        "profit_m":    (main_data.get("profit_margin") or 0) * 100,
        "roe":         (main_data.get("roe") or 0) * 100,
        "rev_growth":  main_data.get("revenue_yoy"),
        "market_cap":  main_data.get("market_cap"),
    }, is_main=True)

    peer_rows = "".join(
        make_row(p["ticker"], p["name"], p) for p in peers_data
    )

    header_style = "padding:0.4rem 0.5rem;font-size:0.68rem;color:#64748b;text-transform:uppercase;letter-spacing:0.06em;text-align:right;border-bottom:1px solid #1e2d45;"

    table = f"""
    <div style="overflow-x:auto;">
    <table style="width:100%;border-collapse:collapse;font-size:0.83rem;">
      <thead>
        <tr style="background:#0a0e1a;">
          <th style="{header_style}text-align:left;">Empresa</th>
          <th style="{header_style}">PER Fwd</th>
          <th style="{header_style}">PEG</th>
          <th style="{header_style}">EV/EBITDA</th>
          <th style="{header_style}">Margen</th>
          <th style="{header_style}">ROE</th>
          <th style="{header_style}">Crec.</th>
          <th style="{header_style}">Mkt Cap</th>
        </tr>
      </thead>
      <tbody>
        {main_row}
        {peer_rows}
      </tbody>
    </table>
    </div>
    <div style="font-size:0.7rem;color:#64748b;margin-top:0.5rem;">
      Verde = mejor que referencia sector · Rojo = peor · Referencia: PER {ev.get('pe_ref')}× · PEG {ev.get('peg_ok')} · EV/EBITDA {ev.get('ev_ebitda_fair')}×
    </div>"""

    st.markdown(f'<div class="metric-card" style="padding:0.8rem 0.5rem;">{table}</div>',
                unsafe_allow_html=True)
