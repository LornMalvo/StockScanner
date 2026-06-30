"""
pdf_export.py — v1.0
Genera un PDF descargable con el resumen completo del análisis realizado,
incluyendo fecha y hora exactas del momento de la consulta.
"""

import io
from datetime import datetime, timezone
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER


# ─────────────────────────────────────────────────────────────────────────────
# ESTILOS
# ─────────────────────────────────────────────────────────────────────────────

def _build_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="ReportTitle", fontName="Helvetica-Bold", fontSize=18,
        textColor=colors.HexColor("#0a0e1a"), spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="ReportSubtitle", fontName="Helvetica", fontSize=10,
        textColor=colors.HexColor("#64748b"), spaceAfter=14,
    ))
    styles.add(ParagraphStyle(
        name="SectionHeader", fontName="Helvetica-Bold", fontSize=11,
        textColor=colors.HexColor("#1d4ed8"), spaceBefore=14, spaceAfter=6,
        borderColor=colors.HexColor("#1e2d45"), borderWidth=0,
    ))
    styles.add(ParagraphStyle(
        name="BodySmall", fontName="Helvetica", fontSize=9,
        textColor=colors.HexColor("#1f2937"), leading=13,
    ))
    styles.add(ParagraphStyle(
        name="BodyTiny", fontName="Helvetica", fontSize=7.5,
        textColor=colors.HexColor("#6b7280"), leading=10,
    ))
    styles.add(ParagraphStyle(
        name="DiagBig", fontName="Helvetica-Bold", fontSize=13,
        textColor=colors.HexColor("#0a0e1a"), spaceAfter=2,
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


def _table(data, col_widths=None, header=True):
    """Tabla con estilo consistente."""
    t = Table(data, colWidths=col_widths)
    style = [
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#1f2937")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#e5e7eb")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]
    if header:
        style += [
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1d4ed8")),
        ]
    t.setStyle(TableStyle(style))
    return t


# ─────────────────────────────────────────────────────────────────────────────
# GENERACIÓN DEL PDF
# ─────────────────────────────────────────────────────────────────────────────

def generate_analysis_pdf(
    ticker: str, company_name: str,
    y: dict, ev: dict, tech: dict | None,
    sq_data: dict | None, signal: dict | None,
    trend: dict | None, mult_data: dict | None,
    ea: dict | None,
    fx_rate: float | None = None,
) -> bytes:
    """
    Genera el PDF completo del análisis y devuelve los bytes para descarga.
    Incluye fecha y hora exactas de generación.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=1.8*cm, bottomMargin=1.8*cm,
        leftMargin=1.8*cm, rightMargin=1.8*cm,
    )
    styles = _build_styles()
    story  = []

    now_utc   = datetime.now(timezone.utc)
    date_str  = now_utc.strftime("%d/%m/%Y")
    time_str  = now_utc.strftime("%H:%M UTC")
    currency  = y.get("currency", "USD")

    # ── Cabecera ───────────────────────────────────────────────────────────
    story.append(Paragraph(f"Análisis Fundamental — {ticker}", styles["ReportTitle"]))
    story.append(Paragraph(company_name, styles["ReportSubtitle"]))
    story.append(Paragraph(
        f"<b>Fecha del análisis:</b> {date_str} &nbsp;&nbsp; "
        f"<b>Hora:</b> {time_str} &nbsp;&nbsp; "
        f"<b>Sector:</b> {y.get('sector','N/A')} &nbsp;&nbsp; "
        f"<b>Industria:</b> {y.get('industry','N/A')}",
        styles["BodySmall"]
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1e2d45"), spaceBefore=8, spaceAfter=10))

    # ── Diagnóstico general ───────────────────────────────────────────────
    price_now = y.get("price") or 0
    fair      = ev.get("fair_value")
    upside    = ev.get("upside")
    diag      = ev.get("diag", "N/A")

    story.append(Paragraph("DIAGNÓSTICO GENERAL", styles["SectionHeader"]))
    diag_data = [
        ["Precio actual", f"{currency} {price_now:,.2f}"],
        ["Valor objetivo estimado", f"{currency} {fair:,.2f}" if fair else "N/A"],
        ["Upside / Downside", f"{upside:+.2f}%" if upside is not None else "N/A"],
        ["Diagnóstico", diag],
        ["Salud fundamental (score)", f"{ev.get('health_score', 'N/A')}/100"],
        ["Riesgo técnico (short)", f"{ev.get('risk', 'N/A')}%"],
    ]
    story.append(_table(diag_data, col_widths=[7*cm, 8*cm], header=False))
    story.append(Spacer(1, 10))

    # ── Métricas fundamentales clave ──────────────────────────────────────
    story.append(Paragraph("MÉTRICAS FUNDAMENTALES", styles["SectionHeader"]))
    fund_data = [
        ["Métrica", "Valor"],
        ["Market Cap", _fmt_big(y.get("market_cap"))],
        ["PER Forward", _fmt_num(y.get("pe_forward"), 1, "x")],
        ["PEG Ratio", _fmt_num(y.get("peg_ratio"), 2)],
        ["EV/EBITDA", _fmt_num(y.get("ev_ebitda"), 1, "x")],
        ["Margen Neto", _fmt_num((y.get("profit_margin") or 0)*100, 1, "%")],
        ["Margen Operativo", _fmt_num((y.get("operating_margin") or 0)*100, 1, "%")],
        ["ROE", _fmt_num((y.get("roe") or 0)*100, 1, "%")],
        ["ROA", _fmt_num((y.get("roa") or 0)*100, 1, "%")],
        ["Revenue Growth YoY", _fmt_num(y.get("revenue_yoy"), 1, "%")],
        ["Earnings Growth YoY", _fmt_num(y.get("earnings_yoy"), 1, "%")],
        ["Free Cash Flow", _fmt_big(y.get("free_cash_flow"))],
        ["Deuda/Equity", _fmt_num(y.get("debt_equity"), 1, "%")],
        ["Current Ratio", _fmt_num(y.get("current_ratio"), 2, "x")],
        ["Dividend Yield", _fmt_num((y.get("dividend_yield") or 0)*100, 2, "%") if y.get("dividend_yield") else "N/A"],
        ["Beta", _fmt_num(y.get("beta"), 2)],
    ]
    story.append(_table(fund_data, col_widths=[7*cm, 8*cm]))
    story.append(Spacer(1, 10))

    # ── Análisis técnico ──────────────────────────────────────────────────
    if tech and not tech.get("error"):
        story.append(Paragraph("ANÁLISIS TÉCNICO", styles["SectionHeader"]))
        tech_data = [
            ["Indicador", "Valor"],
            ["RSI (14)", f"{tech.get('rsi', 'N/A'):.1f}" if tech.get("rsi") is not None else "N/A"],
            ["Señal RSI", tech.get("rsi_label", "N/A")],
            ["MM50", _fmt_num(tech.get("mm50"), 2)],
            ["MM200", _fmt_num(tech.get("mm200"), 2) if tech.get("mm200") else "N/A"],
            ["Señal MM50", tech.get("mm50_signal", "N/A")],
            ["Señal MM200", tech.get("mm200_signal", "N/A")],
        ]
        story.append(_table(tech_data, col_widths=[7*cm, 8*cm]))
        story.append(Spacer(1, 10))

    # ── Short squeeze ──────────────────────────────────────────────────────
    if sq_data and sq_data.get("short_ratio", 0) > 0:
        story.append(Paragraph("SHORT INTEREST &amp; SHORT SQUEEZE", styles["SectionHeader"]))
        sq_table = [
            ["Métrica", "Valor"],
            ["Probabilidad de squeeze", sq_data.get("level", "N/A")],
            ["Score", f"{sq_data.get('score', 0)}/100"],
            ["Short Ratio", f"{sq_data.get('short_ratio', 0):.1f} días"],
            ["Short % del Float", f"{sq_data.get('pct_float', 0):.1f}%"],
        ]
        story.append(_table(sq_table, col_widths=[7*cm, 8*cm]))
        story.append(Spacer(1, 10))

    # ── Señal de entrada ───────────────────────────────────────────────────
    if signal:
        story.append(Paragraph("SEÑAL DE ENTRADA", styles["SectionHeader"]))
        story.append(Paragraph(
            f"<b>{signal.get('level','N/A')}</b> — Score: {signal.get('score','N/A')}/100 "
            f"({signal.get('n_ok','?')}/{signal.get('n_total','?')} criterios cumplidos)",
            styles["BodySmall"]
        ))
        story.append(Paragraph(signal.get("desc", ""), styles["BodyTiny"]))
        story.append(Spacer(1, 10))

    # ── Histórico de múltiplos ─────────────────────────────────────────────
    if mult_data:
        story.append(Paragraph("HISTÓRICO DE MÚLTIPLOS PROPIOS (PER 5 años)", styles["SectionHeader"]))
        mult_table = [
            ["Métrica", "Valor"],
            ["PER actual", f"{mult_data.get('per_current', 0):.1f}x" if mult_data.get("per_current") else "N/A"],
            ["PER medio 5 años", f"{mult_data.get('per_mean', 0)}x"],
            ["Rango histórico", f"{mult_data.get('per_min','N/A')}x – {mult_data.get('per_max','N/A')}x"],
            ["Señal", mult_data.get("signal", ("N/A",""))[0]],
        ]
        story.append(_table(mult_table, col_widths=[7*cm, 8*cm]))
        story.append(Spacer(1, 10))

    # ── Análisis de últimos resultados ─────────────────────────────────────
    if ea and not ea.get("error"):
        story.append(Paragraph("ANÁLISIS DE ÚLTIMOS RESULTADOS", styles["SectionHeader"]))
        story.append(Paragraph(
            f"<b>Último trimestre:</b> {ea.get('last_q_date','N/A')} &nbsp;&nbsp; "
            f"<b>Próxima presentación:</b> {ea.get('next_q_date','N/A')}",
            styles["BodySmall"]
        ))
        positives = ea.get("positives", [])
        negatives = ea.get("negatives", [])
        if positives:
            story.append(Paragraph("<b>Puntos positivos:</b>", styles["BodySmall"]))
            for p in positives[:6]:
                story.append(Paragraph(f"• {p}", styles["BodyTiny"]))
        if negatives:
            story.append(Paragraph("<b>Puntos a vigilar:</b>", styles["BodySmall"]))
            for n in negatives[:5]:
                story.append(Paragraph(f"• {n}", styles["BodyTiny"]))
        story.append(Spacer(1, 10))

    # ── Pie de página / disclaimer ──────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#e5e7eb"), spaceBefore=14, spaceAfter=8))
    fx_note = f" · USD/EUR: {fx_rate:.4f}" if fx_rate else ""
    story.append(Paragraph(
        f"Documento generado automáticamente el {date_str} a las {time_str} mediante la app de "
        f"Análisis Fundamental. Fuente de datos: Yahoo Finance{fx_note}. "
        f"Este documento es una fotografía del análisis en el momento indicado y no se actualiza. "
        f"No constituye asesoramiento financiero ni recomendación de inversión.",
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
):
    """Botón de Streamlit para generar y descargar el PDF del análisis."""
    import streamlit as st

    try:
        pdf_bytes = generate_analysis_pdf(
            ticker, company_name, y, ev, tech,
            sq_data, signal, trend, mult_data, ea, fx_rate
        )
        now_str  = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
        filename = f"analisis_{ticker}_{now_str}.pdf"

        st.download_button(
            label="📄 Descargar análisis en PDF",
            data=pdf_bytes,
            file_name=filename,
            mime="application/pdf",
            use_container_width=False,
        )
    except Exception as e:
        st.warning(f"No se pudo generar el PDF: {e}")
