"""
pdf_export.py -- v2.0
Genera un PDF descargable con el resumen completo del analisis realizado,
incluyendo fecha y hora exactas del momento de la consulta. Ampliado para
incluir todas las metricas y calculos anadidos: salud fundamental detallada
con colores, metodologia de valoracion con cifras, contexto sectorial con
ajuste por tipos, indicadores tecnicos nuevos (MACD/ADX/OBV/Fibonacci/
soporte historico), senal de entrada con desglose completo, y comparativa
con competidores.
"""

import io
from datetime import datetime, timezone
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image
)
import matplotlib
matplotlib.use("Agg")   # backend sin GUI, necesario en servidor
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from reportlab.lib.enums import TA_LEFT, TA_CENTER


# ---------------------------------------------------------------------------
# ESTILOS
# ---------------------------------------------------------------------------

def _build_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="ReportTitle", fontName="Helvetica-Bold", fontSize=18,
        textColor=colors.HexColor("#0f172a"), spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="ReportSubtitle", fontName="Helvetica", fontSize=10,
        textColor=colors.HexColor("#64748b"), spaceAfter=14,
    ))
    styles.add(ParagraphStyle(
        name="SectionHeader", fontName="Helvetica-Bold", fontSize=11,
        textColor=colors.HexColor("#0284c7"), spaceBefore=14, spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="SubHeader", fontName="Helvetica-Bold", fontSize=9,
        textColor=colors.HexColor("#334155"), spaceBefore=8, spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="BodySmall", fontName="Helvetica", fontSize=9,
        textColor=colors.HexColor("#1e293b"), leading=13,
    ))
    styles.add(ParagraphStyle(
        name="BodyTiny", fontName="Helvetica", fontSize=7.5,
        textColor=colors.HexColor("#64748b"), leading=10,
    ))
    styles.add(ParagraphStyle(
        name="WarnBox", fontName="Helvetica", fontSize=8.5,
        textColor=colors.HexColor("#92400e"), leading=12,
        backColor=colors.HexColor("#fffbeb"), borderPadding=6,
    ))
    return styles


def _fmt_num(v, decimals=2, suffix="", prefix=""):
    if v is None:
        return "N/A"
    try:
        return f"{prefix}{v:,.{decimals}f}{suffix}"
    except Exception:
        return "N/A"


def _fmt_big(v, prefix="$"):
    if not v:
        return "N/A"
    v = float(v)
    if abs(v) >= 1e12: return f"{prefix}{v/1e12:.2f}T"
    if abs(v) >= 1e9:  return f"{prefix}{v/1e9:.2f}B"
    if abs(v) >= 1e6:  return f"{prefix}{v/1e6:.1f}M"
    return f"{prefix}{v:,.0f}"


def _table(data, col_widths=None, header=True, row_colors=None):
    """
    Tabla con estilo consistente. row_colors: lista opcional de colores hex
    (uno por fila de datos, sin contar cabecera) para pintar el texto de
    la segunda columna -- usado en Salud Fundamental para el semaforo
    rojo/ambar/verde.
    """
    t = Table(data, colWidths=col_widths)
    style = [
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#1e293b")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]
    if header:
        style += [
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0284c7")),
        ]
    if row_colors:
        offset = 1 if header else 0
        for i, c in enumerate(row_colors):
            if c:
                style.append(("TEXTCOLOR", (0, i+offset), (0, i+offset), colors.HexColor(c)))
    t.setStyle(TableStyle(style))
    return t


# ---------------------------------------------------------------------------
# GENERACION DEL PDF
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# GRAFICO DE COTIZACION (imagen estatica para el PDF)
# ---------------------------------------------------------------------------

def _generate_price_chart_image(tech: dict, ticker: str, currency: str = "USD") -> io.BytesIO | None:
    """
    Genera el grafico de cotizacion a 1 ano con MM50/MM200 como imagen PNG
    (via matplotlib) para insertar en el PDF. La version interactiva de la
    app usa Plotly, pero Plotly requiere el paquete kaleido (no siempre
    disponible/instalable de forma fiable) para exportar a imagen estatica;
    matplotlib es la opcion mas ligera y sin dependencias extra para este caso.
    Devuelve None si no hay datos de historico de precios disponibles.
    """
    history = tech.get("price_history") if tech else None
    if not history:
        return None

    try:
        dates  = [datetime.strptime(h["date"], "%Y-%m-%d") for h in history]
        closes = [h["close"] for h in history]
        mm50s  = [h["mm50"]  for h in history]
        mm200s = [h["mm200"] for h in history]

        fig, ax = plt.subplots(figsize=(9.2, 3.6), dpi=150)

        ax.plot(dates, closes, color="#0284c7", linewidth=1.4, label="Precio")
        ax.plot(dates, mm50s,  color="#d97706", linewidth=1.0, label="MM50")
        if any(v is not None for v in mm200s):
            ax.plot(dates, mm200s, color="#dc2626", linewidth=1.0, label="MM200")

        ax.set_facecolor("#ffffff")
        fig.patch.set_facecolor("#ffffff")
        ax.grid(True, color="#f1f5f9", linewidth=0.6)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#e2e8f0")
        ax.spines["bottom"].set_color("#e2e8f0")
        ax.tick_params(colors="#64748b", labelsize=8)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        ax.set_ylabel(f"Precio ({currency})", fontsize=8, color="#475569")
        ax.legend(loc="upper left", fontsize=8, frameon=False)
        fig.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png", facecolor="#ffffff", bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return buf
    except Exception as e:
        print(f"[PDF Chart] Error generando gráfico para {ticker}: {e}")
        return None


def generate_analysis_pdf(
    ticker: str, company_name: str,
    y: dict, ev: dict, tech: dict | None,
    sq_data: dict | None, signal: dict | None,
    trend: dict | None, mult_data: dict | None,
    ea: dict | None,
    fx_rate: float | None = None,
    peers_data: list | None = None,
    vf: dict | None = None,
) -> bytes:
    """Genera el PDF completo del analisis y devuelve los bytes para descarga."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=1.6*cm, bottomMargin=1.6*cm,
        leftMargin=1.8*cm, rightMargin=1.8*cm,
    )
    styles = _build_styles()
    story  = []

    now_utc   = datetime.now(timezone.utc)
    date_str  = now_utc.strftime("%d/%m/%Y")
    time_str  = now_utc.strftime("%H:%M UTC")
    currency  = y.get("currency", "USD")

    def big(v): return _fmt_big(v)
    def num(v, d=2, s=""): return _fmt_num(v, d, s)

    # -- Cabecera --------------------------------------------------------
    story.append(Paragraph(f"Analisis Fundamental -- {ticker}", styles["ReportTitle"]))
    story.append(Paragraph(company_name, styles["ReportSubtitle"]))
    story.append(Paragraph(
        f"<b>Fecha del analisis:</b> {date_str} &nbsp;&nbsp; "
        f"<b>Hora:</b> {time_str} &nbsp;&nbsp; "
        f"<b>Sector:</b> {y.get('sector','N/A')} &nbsp;&nbsp; "
        f"<b>Industria:</b> {y.get('industry','N/A')}",
        styles["BodySmall"]
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0"), spaceBefore=8, spaceAfter=10))

    # -- Diagnostico general ----------------------------------------------
    price_now   = y.get("price") or 0
    fair        = ev.get("fair_value")
    upside      = ev.get("upside")
    diag        = ev.get("diag", "N/A")
    target_mean = y.get("target_mean")
    analyst_n   = y.get("analyst_count")

    story.append(Paragraph("DIAGNOSTICO GENERAL", styles["SectionHeader"]))
    diag_data = [
        ["Precio actual", f"{currency} {price_now:,.2f}"],
        ["Valor objetivo (mediana, consenso peso doble)", f"{currency} {fair:,.2f}" if fair else "N/A"],
    ]
    fair_single = ev.get("fair_value_single")
    if fair_single and fair and fair != fair_single:
        diff_pct = (fair - fair_single) / fair_single * 100
        diag_data.append([
            "Valor objetivo (mediana, consenso peso simple)",
            f"{currency} {fair_single:,.2f} ({diff_pct:+.1f}% vs peso doble)"
        ])
    diag_data.append(["Upside / Downside", f"{upside:+.2f}%" if upside is not None else "N/A"])
    if target_mean:
        an_upside = (target_mean - price_now) / price_now * 100 if price_now else None
        diag_data.append([
            f"Objetivo analistas ({analyst_n or '?'} analistas)",
            f"{currency} {target_mean:,.2f} ({an_upside:+.1f}%)" if an_upside is not None else f"{currency} {target_mean:,.2f}"
        ])
    targets_range = ev.get("targets_range")
    if targets_range:
        rmin, rmax = targets_range
        diag_data.append(["Rango entre metodos", f"{currency} {rmin:,.2f} -- {rmax:,.2f}"])
    diag_data += [
        ["Diagnostico", diag],
        ["Salud fundamental (score)", f"{ev.get('health_score', 'N/A')}/100"],
        ["Riesgo tecnico (short)", f"{ev.get('risk', 'N/A')}%"],
    ]
    story.append(_table(diag_data, col_widths=[7*cm, 8.2*cm], header=False))

    if ev.get("health_modifier_applied"):
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            f"<b>Aviso:</b> el diagnostico base por upside sugeriria \"{ev.get('diag_base','')}\", "
            f"pero se ha matizado por la Salud Fundamental ({ev.get('health_score')}/100) -- "
            f"ver seccion de Salud Fundamental para el detalle.",
            styles["WarnBox"]
        ))
    story.append(Spacer(1, 10))

    # -- Contexto sectorial -------------------------------------------------
    story.append(Paragraph("CONTEXTO SECTORIAL", styles["SectionHeader"]))
    sector_data = [
        ["Sector de referencia", ev.get("sector_label", "N/A")],
        ["PER justo del sector", f"{ev.get('pe_ref','N/A')}x"],
        ["PEG aceptable", f"< {ev.get('peg_ok','N/A')}"],
        ["EV/EBITDA justo", f"{ev.get('ev_ebitda_fair','N/A')}x"],
    ]
    rate_adj = ev.get("rate_adjustment")
    if rate_adj:
        sector_data.append(["Bono 10Y USA (ajuste tipos)",
                             f"{rate_adj['rf_current']*100:.2f}% (ref. {rate_adj['rf_baseline']*100:.1f}%, factor x{rate_adj['factor']:.2f})"])
    story.append(_table(sector_data, col_widths=[7*cm, 8.2*cm], header=False))
    story.append(Spacer(1, 10))

    # -- Metodologia de valoracion -------------------------------------------
    methods_used = ev.get("methods_used", [])
    if methods_used:
        story.append(Paragraph("METODOLOGIA DE VALORACION", styles["SectionHeader"]))
        for m in methods_used:
            story.append(Paragraph(f"&#8226; {m}", styles["BodyTiny"]))

        rule40 = ev.get("rule_of_40")
        if rule40:
            r40_verdict = "CUMPLE" if rule40["passes"] else "NO CUMPLE"
            story.append(Paragraph(
                f"<b>Regla del 40</b> (auditoria de crecimiento hyper-growth): "
                f"Crec. ingresos {rule40['rev_growth']:+.1f}% + Margen FCF {rule40['fcf_margin']:+.1f}% "
                f"= {rule40['total']:+.1f}% (umbral 40%) -- {r40_verdict}",
                styles["WarnBox"] if not rule40["passes"] else styles["BodySmall"]
            ))
        story.append(Spacer(1, 10))

    # -- Salud fundamental detallada -----------------------------------------
    health_breakdown = ev.get("health_breakdown", [])
    if health_breakdown:
        story.append(Paragraph(f"SALUD FUNDAMENTAL -- {ev.get('health_score','N/A')}/100", styles["SectionHeader"]))
        hs_rows = []
        hs_colors = []
        for item in health_breakdown:
            if isinstance(item, tuple):
                text, color = item
            else:
                text, color = item, None
            hs_rows.append([text])
            hs_colors.append(color)
        hs_table = Table(hs_rows, colWidths=[15.2*cm])
        hs_style = [
            ("FONTSIZE", (0,0), (-1,-1), 8),
            ("FONTNAME", (0,0), (-1,-1), "Helvetica"),
            ("BOTTOMPADDING", (0,0), (-1,-1), 4),
            ("TOPPADDING", (0,0), (-1,-1), 4),
            ("LINEBELOW", (0,0), (-1,-1), 0.3, colors.HexColor("#eef1f5")),
            ("LEFTPADDING", (0,0), (-1,-1), 4),
        ]
        for i, c in enumerate(hs_colors):
            if c and c.startswith("#"):
                hs_style.append(("TEXTCOLOR", (0,i), (0,i), colors.HexColor(c)))
        hs_table.setStyle(TableStyle(hs_style))
        story.append(hs_table)
        story.append(Paragraph(
            "Colores: rojo = dato debil, ambar = normal, verde = bueno/destacable.",
            styles["BodyTiny"]
        ))
        story.append(Spacer(1, 10))

    # -- Piotroski F-Score (herramienta independiente) -----------------------
    pio = ev.get("piotroski", {})
    if pio.get("n_evaluable", 0) > 0:
        story.append(Paragraph(
            f"PIOTROSKI F-SCORE -- {pio['score']}/{pio['n_evaluable']} evaluado ({pio['level']})",
            styles["SectionHeader"]
        ))
        story.append(Paragraph(
            "Sistema de 9 criterios binarios (rentabilidad, apalancamiento/liquidez, eficiencia "
            "operativa) para detectar deterioro financiero. Herramienta independiente, no se "
            f"mezcla con el score de Salud Fundamental. {9 - pio['n_evaluable']} criterio(s) no "
            "evaluable(s) por falta de balance historico para este ticker.",
            styles["BodySmall"]
        ))
        pio_rows = [["Criterio", "Estado", "Detalle"]]
        pio_colors = []
        for name, status, detail in pio["criteria"]:
            if status is None:
                status_txt, color = "No evaluable", "#94a3b8"
            elif status:
                status_txt, color = "Cumple", "#059669"
            else:
                status_txt, color = "No cumple", "#dc2626"
            pio_rows.append([name, status_txt, detail])
            pio_colors.append(color)
        pio_table = Table(pio_rows, colWidths=[4.5*cm, 2.3*cm, 8.4*cm])
        pio_style = [
            ("FONTSIZE", (0,0), (-1,-1), 7.6),
            ("FONTNAME", (0,0), (-1,-1), "Helvetica"),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#0284c7")),
            ("BOTTOMPADDING", (0,0), (-1,-1), 4),
            ("TOPPADDING", (0,0), (-1,-1), 4),
            ("LINEBELOW", (0,0), (-1,-1), 0.3, colors.HexColor("#e2e8f0")),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
        ]
        for i, c in enumerate(pio_colors):
            pio_style.append(("TEXTCOLOR", (1, i+1), (1, i+1), colors.HexColor(c)))
        pio_table.setStyle(TableStyle(pio_style))
        story.append(pio_table)
        story.append(Spacer(1, 10))

    # -- Metricas fundamentales clave -----------------------------------------
    story.append(Paragraph("METRICAS FUNDAMENTALES", styles["SectionHeader"]))
    net_debt_ebitda = None
    total_debt, total_cash, ebitda = y.get("total_debt"), y.get("total_cash"), y.get("ebitda")
    if total_debt is not None and ebitda:
        net_debt_ebitda = (total_debt - (total_cash or 0)) / ebitda if ebitda else None
    fund_data = [
        ["Metrica", "Valor"],
        ["Market Cap", big(y.get("market_cap"))],
        ["PER Forward", num(y.get("pe_forward"), 1, "x")],
        ["PEG Ratio", num(y.get("peg_ratio"), 2)],
        ["EV/EBITDA", num(y.get("ev_ebitda"), 1, "x")],
        ["Margen Neto", num((y.get("profit_margin") or 0)*100, 1, "%")],
        ["Margen Operativo", num((y.get("operating_margin") or 0)*100, 1, "%")],
        ["ROE", num((y.get("roe") or 0)*100, 1, "%")],
        ["ROA", num((y.get("roa") or 0)*100, 1, "%")],
        ["Revenue Growth YoY", num(y.get("revenue_yoy"), 1, "%")],
        ["Earnings Growth YoY", num(y.get("earnings_yoy"), 1, "%")],
        ["Free Cash Flow", big(y.get("free_cash_flow"))],
        ["Deuda/Equity", num(y.get("debt_equity"), 1, "%")],
        ["Current Ratio", num(y.get("current_ratio"), 2, "x")],
        ["Quick Ratio", num(y.get("quick_ratio"), 2, "x")],
        ["Net Debt / EBITDA", num(net_debt_ebitda, 2, "x") if net_debt_ebitda is not None else "N/A"],
        ["Dividend Yield", num((y.get("dividend_yield") or 0)*100, 2, "%") if y.get("dividend_yield") else "N/A"],
        ["Beta", num(y.get("beta"), 2)],
    ]
    story.append(_table(fund_data, col_widths=[7*cm, 8.2*cm]))
    story.append(Spacer(1, 10))

    # -- Analisis tecnico -----------------------------------------------------
    if tech and not tech.get("error"):
        story.append(Paragraph("ANALISIS TECNICO", styles["SectionHeader"]))

        chart_buf = _generate_price_chart_image(tech, ticker, currency)
        if chart_buf:
            img = Image(chart_buf, width=15.5*cm, height=6.07*cm)
            story.append(img)
            story.append(Paragraph(
                "Cotizacion a 1 ano con medias moviles MM50 (naranja) y MM200 (roja).",
                styles["BodyTiny"]
            ))
            story.append(Spacer(1, 6))

        tech_data = [
            ["Indicador", "Valor"],
            ["RSI (14)", f"{tech.get('rsi'):.1f}" if tech.get("rsi") is not None else "N/A"],
            ["Senal RSI", tech.get("rsi_label", "N/A")],
            ["MM50", num(tech.get("mm50"), 2)],
            ["MM200", num(tech.get("mm200"), 2) if tech.get("mm200") else "N/A"],
            ["Senal MM50", tech.get("mm50_signal", "N/A")],
            ["Senal MM200", tech.get("mm200_signal", "N/A")],
        ]
        cross_sig = tech.get("cross_signal")
        if cross_sig:
            tech_data.append(["Cruce MM50/MM200", cross_sig[0]])

        macd_d = tech.get("macd")
        if macd_d:
            macd_sig = ("Cruce alcista" if macd_d.get("bullish_cross") else
                        "Divergencia alcista" if macd_d.get("bullish_divergence") else
                        "Cruce bajista" if macd_d.get("bearish_cross") else "Sin senal de giro")
            tech_data.append(["MACD", f"{macd_d.get('macd',0):.3f} (hist. {macd_d.get('histogram',0):+.3f})"])
            tech_data.append(["Senal MACD", macd_sig])

        adx_v = tech.get("adx")
        if adx_v is not None:
            tech_data.append(["ADX (14)", f"{adx_v:.1f} ({'Tendencia fuerte' if adx_v>25 else 'Tendencia debil/lateral'})"])

        obv_d = tech.get("obv")
        if obv_d:
            obv_lbl = ("Posible acumulacion" if obv_d.get("accumulation") else
                       "Posible distribucion" if obv_d.get("distribution") else
                       "Alcista" if obv_d.get("obv_trend_up") else "Bajista")
            tech_data.append(["OBV (volumen)", obv_lbl])

        fib_d = tech.get("fibonacci")
        if fib_d:
            near = fib_d.get("near_support")
            tech_data.append(["Fibonacci 52 semanas", f"En soporte {near}" if near else "Sin soporte Fibonacci cercano"])

        sup_d = tech.get("historical_support")
        if sup_d:
            tech_data.append(["Soporte historico mas fuerte",
                               f"{currency} {sup_d['level']:,.2f} (-{sup_d['distance_pct']:.1f}%, {sup_d['touches']} rebotes)"])

        story.append(_table(tech_data, col_widths=[7*cm, 8.2*cm]))
        story.append(Spacer(1, 10))

    # -- Short squeeze ---------------------------------------------------------
    if sq_data and sq_data.get("short_ratio", 0) > 0:
        story.append(Paragraph("SHORT INTEREST &amp; SHORT SQUEEZE", styles["SectionHeader"]))
        sq_table = [
            ["Metrica", "Valor"],
            ["Probabilidad de squeeze", sq_data.get("level", "N/A")],
            ["Score", f"{sq_data.get('score', 0)}/100"],
            ["Short Ratio", f"{sq_data.get('short_ratio', 0):.1f} dias"],
            ["Short % del Float", f"{sq_data.get('pct_float', 0):.1f}%"],
        ]
        story.append(_table(sq_table, col_widths=[7*cm, 8.2*cm]))
        story.append(Spacer(1, 10))

    # -- Senal de entrada --------------------------------------------------------
    if signal:
        story.append(Paragraph("SENAL DE ENTRADA", styles["SectionHeader"]))
        story.append(Paragraph(
            f"<b>{signal.get('level','N/A')}</b> -- Score: {signal.get('score','N/A')}/100 "
            f"({signal.get('n_ok','?')}/{signal.get('n_total','?')} criterios cumplidos)",
            styles["BodySmall"]
        ))
        if signal.get("adx_veto_applied"):
            story.append(Paragraph(
                f"VETO ADX: {signal.get('adx_veto_detail','')}", styles["WarnBox"]
            ))
        else:
            story.append(Paragraph(signal.get("desc", ""), styles["BodyTiny"]))

        checks = signal.get("checks", [])
        if checks:
            story.append(Spacer(1, 4))
            chk_rows = [["Criterio", "Cumple", "Detalle", "Peso"]]
            for name, ok, detail, weight in checks:
                chk_rows.append([name, "Si" if ok else "No", detail, str(weight)])
            chk_table = Table(chk_rows, colWidths=[4.8*cm, 1.3*cm, 7.3*cm, 1.4*cm])
            chk_style = [
                ("FONTSIZE", (0,0), (-1,-1), 7.5),
                ("FONTNAME", (0,0), (-1,-1), "Helvetica"),
                ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
                ("TEXTCOLOR", (0,0), (-1,0), colors.white),
                ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#0284c7")),
                ("BOTTOMPADDING", (0,0), (-1,-1), 3),
                ("TOPPADDING", (0,0), (-1,-1), 3),
                ("LINEBELOW", (0,0), (-1,-1), 0.3, colors.HexColor("#eef1f5")),
            ]
            for i, (name, ok, detail, weight) in enumerate(checks):
                color = "#059669" if ok else "#dc2626"
                chk_style.append(("TEXTCOLOR", (1, i+1), (1, i+1), colors.HexColor(color)))
            chk_table.setStyle(TableStyle(chk_style))
            story.append(chk_table)
        story.append(Spacer(1, 10))

    # -- Valoracion Final (sintesis de los 4 sistemas) -------------------------
    if vf:
        story.append(Paragraph("VALORACION FINAL", styles["SectionHeader"]))
        story.append(Paragraph(
            f"<b>{vf.get('icon','')} {vf.get('level','N/A')}</b>",
            ParagraphStyle(name="VFLevel", fontName="Helvetica-Bold", fontSize=12,
                            textColor=colors.HexColor(vf.get("color", "#0f172a")), spaceAfter=4)
        ))
        story.append(Paragraph(vf.get("message", ""), styles["BodySmall"]))

        labels_calidad = {"alta": "Alta", "media": "Media", "baja": "Baja"}
        labels_precio  = {"barata": "Barata", "justa": "Precio justo", "cara": "Cara", "sin_datos": "Sin datos"}
        labels_timing  = {"bueno": "Buen timing", "neutro": "Timing neutro", "malo": "Mal timing", "sin_datos": "Sin datos"}

        if not vf.get("reliability_ok", True):
            story.append(Paragraph(
                "FIABILIDAD REDUCIDA: falta el Valor Objetivo o la Senal de Entrada no se pudo "
                "calcular con suficientes datos -- el veredicto puede no ser representativo.",
                styles["WarnBox"]
            ))

        vf_table = [
            ["Dimension", "Clasificacion", "Base"],
            ["Calidad", labels_calidad.get(vf.get("calidad"), "N/A"),
             f"Score compuesto: {vf.get('calidad_score','N/A')}/100"],
            ["Precio", labels_precio.get(vf.get("precio"), "N/A"),
             f"Diagnostico: {ev.get('diag_base','N/A')}"],
            ["Timing", labels_timing.get(vf.get("timing"), "N/A"),
             f"Senal: {signal.get('level','N/A') if signal else 'N/A'}"],
        ]
        story.append(_table(vf_table, col_widths=[3.5*cm, 4.5*cm, 7.2*cm]))
        story.append(Paragraph(
            "Calidad = combinacion de Salud Fundamental y Piotroski F-Score (60%/40% si Piotroski "
            "tiene 5 o mas criterios evaluables, si no solo Salud Fundamental) -- Precio = Diagnostico "
            "General -- Timing = Senal de Entrada. Nunca es una media directa de los 4 sistemas, para "
            "evitar contar dos veces el mismo dato subyacente.",
            styles["BodyTiny"]
        ))
        story.append(Spacer(1, 10))

    # -- Historico de multiplos ------------------------------------------------
    if mult_data:
        story.append(Paragraph("HISTORICO DE MULTIPLOS PROPIOS (PER 5 anos)", styles["SectionHeader"]))
        mult_table = [
            ["Metrica", "Valor"],
            ["PER actual", f"{mult_data.get('per_current', 0):.1f}x" if mult_data.get("per_current") else "N/A"],
            ["PER medio 5 anos", f"{mult_data.get('per_mean', 0)}x"],
            ["Rango historico", f"{mult_data.get('per_min','N/A')}x -- {mult_data.get('per_max','N/A')}x"],
            ["Senal", mult_data.get("signal", ("N/A",""))[0]],
        ]
        story.append(_table(mult_table, col_widths=[7*cm, 8.2*cm]))
        story.append(Spacer(1, 10))

    # -- Analisis de ultimos resultados -----------------------------------------
    if ea and not ea.get("error"):
        story.append(Paragraph("ANALISIS DE ULTIMOS RESULTADOS", styles["SectionHeader"]))
        _last_q = ea.get("last_q_date")
        _next_q = ea.get("next_q_date")
        _last_q_txt = _last_q if _last_q and _last_q != "N/A" else "No disponible"
        _next_q_txt = _next_q if _next_q and _next_q != "N/A" else "No disponible"
        story.append(Paragraph(
            f"<b>Ultimo trimestre:</b> {_last_q_txt} &nbsp;&nbsp; "
            f"<b>Proxima presentacion:</b> {_next_q_txt}",
            styles["BodySmall"]
        ))
        positives = ea.get("positives", [])
        negatives = ea.get("negatives", [])
        if positives:
            story.append(Paragraph("<b>Puntos positivos:</b>", styles["BodySmall"]))
            for p in positives[:6]:
                story.append(Paragraph(f"&#8226; {p}", styles["BodyTiny"]))
        if negatives:
            story.append(Paragraph("<b>Puntos a vigilar:</b>", styles["BodySmall"]))
            for n in negatives[:5]:
                story.append(Paragraph(f"&#8226; {n}", styles["BodyTiny"]))
        story.append(Spacer(1, 10))

    # -- Comparativa con competidores --------------------------------------------
    if peers_data:
        story.append(Paragraph("COMPARATIVA FRENTE A COMPETENCIA", styles["SectionHeader"]))
        peer_rows = [["Ticker", "PER Fwd", "PEG", "Margen", "ROE", "Crec. Rev"]]
        peer_rows.append([
            ticker, num(y.get("pe_forward"),1,"x"), num(y.get("peg_ratio"),2),
            num((y.get("profit_margin") or 0)*100,1,"%"), num((y.get("roe") or 0)*100,1,"%"),
            num(y.get("revenue_yoy"),1,"%")
        ])
        for p in peers_data[:6]:
            peer_rows.append([
                p.get("ticker","N/A"), num(p.get("pe_forward"),1,"x"), num(p.get("peg"),2),
                num(p.get("profit_m"),1,"%"), num(p.get("roe"),1,"%"), num(p.get("rev_growth"),1,"%")
            ])
        peer_table = Table(peer_rows, colWidths=[2.5*cm]*6)
        peer_style = [
            ("FONTSIZE", (0,0), (-1,-1), 8),
            ("FONTNAME", (0,0), (-1,-1), "Helvetica"),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#0284c7")),
            ("BACKGROUND", (0,1), (-1,1), colors.HexColor("#dbeafe")),
            ("FONTNAME", (0,1), (-1,1), "Helvetica-Bold"),
            ("ALIGN", (1,0), (-1,-1), "RIGHT"),
            ("BOTTOMPADDING", (0,0), (-1,-1), 4),
            ("TOPPADDING", (0,0), (-1,-1), 4),
            ("LINEBELOW", (0,0), (-1,-1), 0.3, colors.HexColor("#eef1f5")),
        ]
        peer_table.setStyle(TableStyle(peer_style))
        story.append(peer_table)
        story.append(Paragraph(f"Fila resaltada = {ticker} (empresa analizada).", styles["BodyTiny"]))
        story.append(Spacer(1, 10))

    # -- Pie de pagina / disclaimer -----------------------------------------------
    story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#e2e8f0"), spaceBefore=14, spaceAfter=8))
    fx_note = f" · USD/EUR: {fx_rate:.4f}" if fx_rate else ""
    story.append(Paragraph(
        f"Documento generado automaticamente el {date_str} a las {time_str} mediante Stock Scanner. "
        f"Fuente de datos: Yahoo Finance{fx_note}. "
        f"Este documento es una fotografia del analisis en el momento indicado y no se actualiza. "
        f"No constituye asesoramiento financiero ni recomendacion de inversion.",
        styles["BodyTiny"]
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def render_pdf_download_button(
    ticker: str, company_name: str,
    y: dict, ev: dict, tech: dict | None,
    sq_data: dict | None, signal: dict | None,
    trend: dict | None, mult_data: dict | None,
    ea: dict | None,
    fx_rate: float | None = None,
    peers_data: list | None = None,
    vf: dict | None = None,
):
    """Boton de Streamlit para generar y descargar el PDF del analisis."""
    import streamlit as st

    try:
        pdf_bytes = generate_analysis_pdf(
            ticker, company_name, y, ev, tech,
            sq_data, signal, trend, mult_data, ea, fx_rate, peers_data, vf
        )
        now_str  = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
        filename = f"analisis_{ticker}_{now_str}.pdf"

        st.download_button(
            label="Descargar analisis en PDF",
            data=pdf_bytes,
            file_name=filename,
            mime="application/pdf",
            use_container_width=False,
        )
    except Exception as e:
        st.warning(f"No se pudo generar el PDF: {e}")
