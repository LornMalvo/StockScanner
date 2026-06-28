"""
report.py
Renderiza el informe completo en Streamlit con el diseño oscuro.
"""

import streamlit as st


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


def _kv(label, value, color_class="row-val"):
    return f"""
    <div class="row-kv">
      <span class="row-key">{label}</span>
      <span class="{color_class}">{value}</span>
    </div>"""


def _section(title):
    st.markdown(f'<div class="section-header">{title}</div>', unsafe_allow_html=True)


# ─── Evaluación fundamental ───────────────────────────────────────────────────

def _evaluate(y: dict, sec: dict | None, use_sec: bool) -> dict:
    """Genera el diagnóstico final."""
    price        = y.get("price") or 0
    pe_forward   = y.get("pe_forward")
    pe_trailing  = y.get("pe_trailing")
    peg          = y.get("peg_ratio")
    target_mean  = y.get("target_mean")
    profit_m     = y.get("profit_margin") or 0
    roe          = y.get("roe") or 0
    rev_yoy      = y.get("revenue_yoy") or 0
    earn_yoy     = y.get("earnings_yoy") or 0
    short_ratio  = y.get("short_ratio") or 0
    week52_high  = y.get("52w_high") or price
    week52_low   = y.get("52w_low") or price

    # Salud fundamental (0-100)
    score = 0
    if profit_m > 0.15: score += 20
    elif profit_m > 0:  score += 10
    if roe > 0.15:      score += 15
    elif roe > 0:       score += 8
    if rev_yoy > 20:    score += 20
    elif rev_yoy > 5:   score += 12
    if earn_yoy > 20:   score += 20
    elif earn_yoy > 0:  score += 10
    if peg and peg < 1: score += 15
    elif peg and peg < 2: score += 8
    if short_ratio < 3: score += 10
    score = min(score, 100)

    # Valor objetivo fundamental (media ponderada)
    eps = y.get("eps_ttm") or y.get("eps_forward") or 0
    targets = []
    if pe_forward and eps:
        targets.append(pe_forward * eps * 1.05)
    if target_mean:
        targets.append(target_mean)
    if y.get("ev_ebitda") and y.get("ebitda"):
        mc = y.get("market_cap") or 1
        ev = y.get("enterprise_value") or 1
        adj = mc / ev if ev else 1
        targets.append(y["ev_ebitda"] * (y["ebitda"] / 1e9) * adj * 1e9 / (mc / price) if price else 0)

    fair_value = sum(targets) / len(targets) if targets else None

    # Descuento/prima sobre media 52w
    mid_52 = (week52_high + week52_low) / 2 if week52_high and week52_low else None
    vs_hist = ((price - mid_52) / mid_52 * 100) if mid_52 else None

    # Diagnóstico
    if fair_value:
        upside = (fair_value - price) / price * 100
    else:
        upside = None

    if upside is not None:
        if upside > 20:
            diag = "INFRAVALORADA — Potencial alcista significativo"
        elif upside > 5:
            diag = "LIGERAMENTE INFRAVALORADA"
        elif upside > -5:
            diag = "PRECIO JUSTO / RANGO OBJETIVO"
        elif upside > -20:
            diag = "EN OBSERVACIÓN (Precio Superior al Valor Objetivo)"
        else:
            diag = "SOBREVALORADA — Riesgo de corrección"
    else:
        diag = "DATOS INSUFICIENTES"

    # Riesgo técnico (basado en short ratio y distancia a máximos)
    risk = 0
    if short_ratio:
        risk += min(short_ratio * 1.5, 5)
    if week52_high and price:
        dist_high = (week52_high - price) / week52_high * 100
        risk += min(dist_high * 0.1, 5)
    risk = round(min(risk, 15), 1)

    # Valoración vs sector
    sector = y.get("sector", "")
    if pe_forward and pe_forward < 15 and peg and peg < 1:
        vs_sector = "Extremadamente infravalorada / GANGA"
    elif pe_forward and pe_forward < 20:
        vs_sector = "Infravalorada vs sector"
    elif pe_forward and pe_forward > 40:
        vs_sector = "Prima de valoración elevada"
    else:
        vs_sector = "En línea con el sector"

    return {
        "score":      score,
        "fair_value": fair_value,
        "upside":     upside,
        "diag":       diag,
        "vs_hist":    vs_hist,
        "vs_sector":  vs_sector,
        "risk":       risk,
    }


# ─── Render principal ─────────────────────────────────────────────────────────

def render_report(ticker, company_name, y: dict, sec: dict | None, cross: dict | None, use_sec: bool, fx_rate: float | None = None, tech: dict | None = None):
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
    source_data = sec if (use_sec and sec) else None
    quarters_to_show = source_data["quarters"] if source_data and source_data.get("quarters") else y.get("ttm_quarters", [])
    source_label = "SEC EDGAR" if (use_sec and sec) else "Yahoo Finance"

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
    ev = _evaluate(y, sec, use_sec)

    _section("EVALUACIÓN FINAL")

    score     = ev["score"]
    fair      = ev["fair_value"]
    upside    = ev["upside"]
    vs_hist   = ev["vs_hist"]
    price_now = y.get("price") or 0

    # Barra de salud
    bar_w = score
    st.markdown(f"""
    <div class="metric-card">
      <div class="metric-label">SALUD FUNDAMENTAL</div>
      <div class="metric-value">{score:.0f} / 100</div>
      <div class="progress-bar-bg">
        <div class="progress-bar-fill" style="width:{bar_w}%;"></div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Veredicto
    upside_str = f"{upside:+.2f}%" if upside is not None else "N/A"
    fair_usd   = f"{currency_y} {fair:,.2f}" if fair else "N/A"
    fair_eur   = f" (€{fair*fx_rate:,.2f})" if (fair and fx_rate and currency_y == "USD") else ""
    fair_str   = f"{fair_usd}{fair_eur}" if fair else "N/A"
    hist_str   = f"{vs_hist:+.2f}% vs media 52W" if vs_hist is not None else "N/A"
    price_eur  = f" (€{price_now*fx_rate:,.2f})" if (fx_rate and currency_y == "USD") else ""

    color_upside = "#6ee7b7" if (upside or 0) > 0 else "#fca5a5"

    st.markdown(f"""
    <div class="verdict-box">
      <div class="verdict-title">DIAGNÓSTICO GENERAL</div>
      <div class="verdict-main">{ev['diag']}</div>
      <div class="verdict-sub" style="margin-top:0.6rem;">
        <span style="color:#94a3b8;">Precio actual:</span>
        <span style="font-family:'IBM Plex Mono',monospace;font-weight:600;color:#f1f5f9;"> {currency_y} {price_now:,.2f}{price_eur}</span>
        &nbsp;·&nbsp;
        <span style="color:#94a3b8;">Valor objetivo:</span>
        <span style="font-family:'IBM Plex Mono',monospace;font-weight:600;color:#f1f5f9;"> {fair_str}</span>
        <span style="font-family:'IBM Plex Mono',monospace;font-weight:600;color:{color_upside};"> ({upside_str})</span>
      </div>
      <div class="verdict-sub">
        <span style="color:#94a3b8;">Vs. media 52W:</span>
        <span style="font-family:'IBM Plex Mono',monospace;font-weight:600;color:#fbbf24;"> {hist_str}</span>
      </div>
      <div class="verdict-sub" style="margin-top:0.4rem;">
        <span style="color:#94a3b8;">Valoración vs sector:</span>
        <span style="color:#e2e8f0;"> {ev['vs_sector']}</span>
      </div>
      <div class="verdict-sub">
        <span style="color:#94a3b8;">Riesgo técnico (short):</span>
        <span style="color:#e2e8f0;"> {ev['risk']}%</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.caption(f"Datos: {'SEC EDGAR + ' if sec else ''}Yahoo Finance · {ticker} · Tipo de cambio USD/EUR: {fx_rate:.4f} · Los datos no constituyen asesoramiento financiero.")
