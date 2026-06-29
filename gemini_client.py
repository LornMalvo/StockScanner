"""
gemini_client.py v1.2
Integracion con la API de Gemini (Google AI Studio).
Modelo: gemini-2.5-flash
"""

import requests
import streamlit as st
import os
import json
import re

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_BASE  = "https://generativelanguage.googleapis.com/v1beta/models"
TIMEOUT      = 40


def _get_key() -> str:
    try:
        return str(st.secrets["GEMINI_API_KEY"]).strip()
    except Exception:
        pass
    return os.environ.get("GEMINI_API_KEY", "").strip()


def _call(prompt: str, temperature: float = 0.3, max_tokens: int = 1500) -> str | None:
    key = _get_key()
    if not key:
        return None
    url  = f"{GEMINI_BASE}/{GEMINI_MODEL}:generateContent?key={key}"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature":     temperature,
            "maxOutputTokens": max_tokens,
        },
    }
    try:
        r = requests.post(url, json=body, timeout=TIMEOUT)
        if r.status_code == 200:
            candidates = r.json().get("candidates", [])
            if not candidates:
                return None
            parts = candidates[0].get("content", {}).get("parts", [])
            return parts[0].get("text", "").strip() if parts else None
        st.warning(f"[Gemini] HTTP {r.status_code}: {r.text[:200]}")
        return None
    except Exception as e:
        st.warning(f"[Gemini] Error de conexion: {e}")
        return None


def _extract_json(text: str) -> dict:
    """Extrae JSON de la respuesta aunque haya texto adicional antes/despues."""
    if not text:
        return {}
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if not match:
        st.warning(f"[Gemini] No se encontro JSON. Respuesta: {text[:300]}")
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        cleaned = match.group(0).replace('\n', ' ').replace('\r', ' ')
        try:
            return json.loads(cleaned)
        except Exception as e2:
            st.warning(f"[Gemini] Error JSON: {e2}. Texto: {match.group(0)[:200]}")
            return {}


def is_available() -> bool:
    return bool(_get_key())


def _fmt(y: dict) -> dict:
    def pct(v):  return f"{(v or 0)*100:.1f}%" if v is not None else "N/D"
    def num(v, s=""): return f"{v:.1f}{s}" if v is not None else "N/D"
    def big(v):
        if not v: return "N/D"
        v = float(v)
        if abs(v) >= 1e12: return f"${v/1e12:.1f}T"
        if abs(v) >= 1e9:  return f"${v/1e9:.1f}B"
        return f"${v/1e6:.0f}M"
    return {
        "rev_yoy":   num(y.get("revenue_yoy"),  "%"),
        "earn_yoy":  num(y.get("earnings_yoy"), "%"),
        "margin":    pct(y.get("profit_margin")),
        "op_margin": pct(y.get("operating_margin")),
        "roe":       pct(y.get("roe")),
        "roa":       pct(y.get("roa")),
        "pe":        num(y.get("pe_forward"),   "x"),
        "peg":       num(y.get("peg_ratio")),
        "ev_ebitda": num(y.get("ev_ebitda"),    "x"),
        "de":        num(y.get("debt_equity"),  "%"),
        "fcf":       "positivo" if (y.get("free_cash_flow") or 0) > 0 else "negativo",
        "mcap":      big(y.get("market_cap")),
        "price":     f"${y.get('price', 0):,.2f}",
        "eps_ttm":   num(y.get("eps_ttm")),
        "beta":      num(y.get("beta")),
        "short":     num(y.get("short_ratio"),  "d"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. IDENTIFICACION DE COMPETIDORES REALES
# ─────────────────────────────────────────────────────────────────────────────

def identify_competitors(ticker: str, company_name: str,
                          sector: str, industry: str,
                          description: str) -> dict:
    desc_short = (description or "")[:600]
    prompt = (
        f"Analiza esta empresa e identifica sus competidores directos reales.\n\n"
        f"EMPRESA: {company_name} ({ticker})\n"
        f"SECTOR: {sector} | INDUSTRIA: {industry}\n"
        f"NEGOCIO: {desc_short}\n\n"
        f"Identifica 5-7 empresas que compitan DIRECTAMENTE en el mismo nicho especifico.\n"
        f"NO uses el sector generico, usa el subsegmento exacto de negocio.\n\n"
        f"Devuelve este JSON exacto (sin texto adicional antes ni despues):\n"
        f'{{\n'
        f'  "subsector": "nombre del subsector especifico (3-5 palabras)",\n'
        f'  "competitors": [\n'
        f'    {{"ticker": "XXXX", "name": "Nombre empresa", "reason": "razon de competencia directa"}},\n'
        f'    {{"ticker": "YYYY", "name": "Nombre empresa", "reason": "razon de competencia directa"}}\n'
        f'  ],\n'
        f'  "moat_factors": ["ventaja 1", "ventaja 2", "ventaja 3"]\n'
        f'}}\n'
    )
    raw  = _call(prompt, temperature=0.1, max_tokens=900)
    data = _extract_json(raw or "")
    return {
        "subsector":    data.get("subsector", ""),
        "competitors":  data.get("competitors", []),
        "moat_factors": data.get("moat_factors", []),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. FORTALEZAS, DEBILIDADES Y MOAT
# ─────────────────────────────────────────────────────────────────────────────

def analyze_strengths_weaknesses(ticker: str, company_name: str,
                                  y: dict, peers_data: list,
                                  subsector: str,
                                  moat_factors: list) -> dict:
    m = _fmt(y)
    peers_text = "\n".join(
        f"  {p['ticker']} ({p['name'][:20]}): "
        f"RevYoY {p.get('rev_growth') or 0:.0f}% | "
        f"Margen {p.get('profit_m') or 0:.1f}% | "
        f"ROE {p.get('roe') or 0:.1f}% | "
        f"PER {p.get('pe_forward') or 0:.1f}x"
        for p in peers_data[:6]
    ) or "  Sin datos de competidores"
    moat_hint = f"Posibles ventajas: {', '.join(moat_factors)}" if moat_factors else ""

    prompt = (
        f"Analiza la posicion competitiva de {company_name} ({ticker}) en {subsector}.\n\n"
        f"METRICAS DE {company_name}:\n"
        f"  Revenue YoY: {m['rev_yoy']} | Beneficio YoY: {m['earn_yoy']}\n"
        f"  Margen neto: {m['margin']} | Margen op: {m['op_margin']}\n"
        f"  ROE: {m['roe']} | PER: {m['pe']} | EV/EBITDA: {m['ev_ebitda']}\n"
        f"  FCF: {m['fcf']} | Deuda/Equity: {m['de']} | Cap: {m['mcap']}\n\n"
        f"COMPETIDORES DIRECTOS:\n{peers_text}\n\n"
        f"{moat_hint}\n\n"
        f"Devuelve este JSON exacto (sin texto adicional):\n"
        f'{{\n'
        f'  "strengths": ["fortaleza especifica 1", "fortaleza especifica 2", "fortaleza especifica 3"],\n'
        f'  "weaknesses": ["debilidad especifica 1", "debilidad especifica 2"],\n'
        f'  "moat": "descripcion del moat en 2-3 frases con datos concretos",\n'
        f'  "position": "una frase sobre posicion competitiva actual"\n'
        f'}}\n'
    )
    raw  = _call(prompt, temperature=0.2, max_tokens=900)
    data = _extract_json(raw or "")
    return {
        "strengths":  data.get("strengths", []),
        "weaknesses": data.get("weaknesses", []),
        "moat":       data.get("moat", ""),
        "position":   data.get("position", ""),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. ANALISIS DE ULTIMOS RESULTADOS CON IA
# ─────────────────────────────────────────────────────────────────────────────

def analyze_earnings_with_ai(ticker: str, company_name: str,
                              y: dict, ea: dict) -> str:
    m          = _fmt(y)
    last_q     = ea.get("last_q_date",  "N/D")
    next_q     = ea.get("next_q_date",  "N/D")
    eps_s      = ea.get("eps_surprise")
    beat_eps   = ea.get("beat_eps")
    positives  = ea.get("positives",  [])
    negatives  = ea.get("negatives",  [])
    is_growth  = ea.get("is_growth_stage", False)

    beat_str  = ("SUPERO expectativas de EPS" if beat_eps
                 else ("NO alcanzo expectativas" if beat_eps is False
                       else "Sin dato de expectativas"))
    eps_s_str = f"{eps_s:+.1f}% vs consenso" if eps_s is not None else ""
    pos_str   = "\n".join(f"  + {p}" for p in positives) or "  Sin datos positivos"
    neg_str   = "\n".join(f"  - {n}" for n in negatives) or "  Sin datos negativos"
    growth_note = ("IMPORTANTE: empresa en fase de crecimiento/expansion — "
                   "las perdidas pueden ser estrategicas.") if is_growth else ""

    prompt = (
        f"Eres un analista financiero senior. Analiza los ultimos resultados de {company_name} ({ticker}).\n\n"
        f"ULTIMO TRIMESTRE: {last_q} | PROXIMA PRESENTACION: {next_q}\n"
        f"VS EXPECTATIVAS: {beat_str} {eps_s_str}\n\n"
        f"METRICAS ACTUALES:\n"
        f"  Revenue YoY: {m['rev_yoy']} | Beneficio YoY: {m['earn_yoy']}\n"
        f"  Margen neto: {m['margin']} | Margen op: {m['op_margin']}\n"
        f"  FCF: {m['fcf']} | ROE: {m['roe']} | EPS TTM: {m['eps_ttm']}\n\n"
        f"PUNTOS DESTACADOS:\n"
        f"Positivos:\n{pos_str}\n"
        f"Negativos:\n{neg_str}\n"
        f"{growth_note}\n\n"
        f"Escribe un analisis cualitativo de 3-4 parrafos en espanol que responda:\n"
        f"1. Como fueron los ultimos resultados y que nos dicen sobre el estado del negocio\n"
        f"2. Que senales dan para el proximo trimestre ({next_q})\n"
        f"3. Que vigilar especialmente en la proxima presentacion\n"
        f"4. Valoracion global: refuerzan o debilitan la tesis de inversion\n\n"
        f"Se especifico y usa los datos. No uses listas, escribe en prosa fluida."
    )
    return _call(prompt, temperature=0.4, max_tokens=1000) or ""


# ─────────────────────────────────────────────────────────────────────────────
# 4. RESUMEN EJECUTIVO
# ─────────────────────────────────────────────────────────────────────────────

def generate_executive_summary(ticker: str, company_name: str,
                                y: dict, ev: dict, sq: dict,
                                tech: dict | None,
                                strengths_data: dict,
                                subsector: str) -> str:
    m      = _fmt(y)
    rsi_v  = tech.get("rsi") if tech and not tech.get("error") else None
    rsi_s  = f"{rsi_v:.1f}" if rsi_v is not None else "N/D"
    mm_pos = ""
    if tech and not tech.get("error"):
        p = y.get("price") or 0
        if tech.get("mm50"):
            mm_pos += f"{"sobre" if p > tech["mm50"] else "bajo"} MM50"
        if tech.get("mm200"):
            mm_pos += f" | {"sobre" if p > tech["mm200"] else "bajo"} MM200"

    diag   = ev.get("diag", "")
    fair   = f"${ev.get('fair_value', 0):,.2f}" if ev.get("fair_value") else "N/D"
    upside = f"{ev.get('upside', 0):+.1f}%" if ev.get("upside") is not None else "N/D"
    sq_lvl = sq.get("level","") if sq else ""
    sq_scr = sq.get("score",  0) if sq else 0
    sq_pct = sq.get("pct_float", 0) if sq else 0
    sq_sr  = sq.get("short_ratio", 0) if sq else 0

    str_txt = " | ".join(strengths_data.get("strengths",  [])) or "No analizadas"
    wk_txt  = " | ".join(strengths_data.get("weaknesses", [])) or "No analizadas"
    moat    = strengths_data.get("moat",     "") or "No determinado"
    pos_txt = strengths_data.get("position", "") or ""

    prompt = (
        f"Eres un analista financiero senior. Escribe un resumen ejecutivo DETALLADO de {company_name} ({ticker}).\n\n"
        f"=== DATOS DEL ANALISIS ===\n\n"
        f"EMPRESA: {company_name} ({ticker}) | Subsector: {subsector}\n"
        f"Precio: {m['price']} | Market Cap: {m['mcap']}\n\n"
        f"DIAGNOSTICO: {diag}\n"
        f"Valor objetivo: {fair} | Upside: {upside}\n"
        f"PER: {m['pe']} | PEG: {m['peg']} | EV/EBITDA: {m['ev_ebitda']}\n\n"
        f"FUNDAMENTOS:\n"
        f"  Revenue YoY: {m['rev_yoy']} | Beneficio YoY: {m['earn_yoy']}\n"
        f"  Margen neto: {m['margin']} | Margen op: {m['op_margin']}\n"
        f"  ROE: {m['roe']} | FCF: {m['fcf']} | D/E: {m['de']}\n\n"
        f"TECNICO: RSI {rsi_s} | {mm_pos} | Beta: {m['beta']}\n\n"
        f"SHORT INTEREST: {sq_lvl} (score {sq_scr}/100, {sq_pct:.1f}% float, ratio {sq_sr:.1f}d)\n\n"
        f"COMPETITIVO:\n"
        f"  Fortalezas: {str_txt}\n"
        f"  Debilidades: {wk_txt}\n"
        f"  Moat: {moat}\n"
        f"  Posicion: {pos_txt}\n\n"
        f"=== INSTRUCCIONES ===\n\n"
        f"Escribe exactamente 5 parrafos en espanol, separados por linea en blanco:\n"
        f"P1: Estado del negocio y calidad del crecimiento actual\n"
        f"P2: Rentabilidad, generacion de caja y salud del balance\n"
        f"P3: Valoracion — si el precio es atractivo, justo o caro y por que\n"
        f"P4: Posicion competitiva, riesgos principales y relevancia del short interest\n"
        f"P5: Conclusion accionable clara — entrar, mantener o esperar, con condicion o precio ideal\n\n"
        f"Prosa fluida sin listas ni titulos. Cada parrafo 3-4 frases."
    )
    return _call(prompt, temperature=0.35, max_tokens=1400) or ""


# ─────────────────────────────────────────────────────────────────────────────
# RENDERS
# ─────────────────────────────────────────────────────────────────────────────

def render_ai_strengths_in_description(strengths_data: dict, subsector: str):
    if not strengths_data:
        return
    strengths  = strengths_data.get("strengths", [])
    weaknesses = strengths_data.get("weaknesses", [])
    moat       = strengths_data.get("moat", "")
    position   = strengths_data.get("position", "")
    if not strengths and not weaknesses and not moat:
        return

    rows_s = "".join(
        f'<div style="display:flex;gap:0.5rem;padding:0.28rem 0;'
        f'border-bottom:1px solid #1a2540;font-size:0.8rem;">'
        f'<span style="color:#6ee7b7;min-width:1rem;flex-shrink:0;">checkmark</span>'
        f'<span style="color:#e2e8f0;">{s}</span></div>'
        for s in strengths
    )
    rows_s = rows_s.replace("checkmark", "&#10004;")

    rows_w = "".join(
        f'<div style="display:flex;gap:0.5rem;padding:0.28rem 0;'
        f'border-bottom:1px solid #1a2540;font-size:0.8rem;">'
        f'<span style="color:#fca5a5;min-width:1rem;flex-shrink:0;">&#10008;</span>'
        f'<span style="color:#e2e8f0;">{w}</span></div>'
        for w in weaknesses
    )
    moat_html = (
        f'<div style="background:#0a1628;border-left:3px solid #38bdf8;'
        f'border-radius:4px;padding:0.55rem 0.75rem;margin-top:0.6rem;">'
        f'<div style="font-size:0.68rem;color:#38bdf8;text-transform:uppercase;'
        f'letter-spacing:0.08em;margin-bottom:0.2rem;">Ventaja competitiva (Moat)</div>'
        f'<div style="font-size:0.8rem;color:#cbd5e1;line-height:1.65;">{moat}</div>'
        f'</div>'
    ) if moat else ""
    pos_html = (
        f'<div style="font-size:0.78rem;color:#fbbf24;margin-top:0.5rem;'
        f'padding:0.3rem 0;border-top:1px solid #1a2540;">&#9658; {position}</div>'
    ) if position else ""
    badge = (
        f'<span style="background:#0f2d1a;color:#6ee7b7;padding:2px 8px;'
        f'border-radius:4px;font-size:0.7rem;margin-left:0.5rem;font-weight:600;">'
        f'Gemini &#183; {subsector}</span>'
    ) if subsector else '<span style="background:#0f2d1a;color:#6ee7b7;padding:2px 8px;border-radius:4px;font-size:0.7rem;margin-left:0.5rem;">Gemini</span>'

    st.markdown(
        f'<div class="metric-card" style="border-left:3px solid #1e3a5f;margin-top:0.5rem;">'
        f'<div style="font-size:0.7rem;color:#94a3b8;text-transform:uppercase;'
        f'letter-spacing:0.08em;margin-bottom:0.6rem;">Analisis competitivo {badge}</div>'
        f'<div style="margin-bottom:0.5rem;">'
        f'<div style="font-size:0.68rem;color:#6ee7b7;text-transform:uppercase;'
        f'letter-spacing:0.06em;margin-bottom:0.25rem;">Puntos fuertes</div>'
        f'{rows_s or "<span style=\'color:#475569;font-size:0.78rem;\'>Sin datos</span>"}'
        f'</div>'
        f'<div style="margin-top:0.4rem;">'
        f'<div style="font-size:0.68rem;color:#fca5a5;text-transform:uppercase;'
        f'letter-spacing:0.06em;margin-bottom:0.25rem;">Puntos debiles / riesgos</div>'
        f'{rows_w or "<span style=\'color:#475569;font-size:0.78rem;\'>Sin datos</span>"}'
        f'</div>'
        f'{moat_html}{pos_html}</div>',
        unsafe_allow_html=True
    )


def render_ai_earnings_analysis(ai_earnings: str):
    if not ai_earnings:
        return
    st.markdown(
        '<div class="section-header">ANALISIS IA DE ULTIMOS RESULTADOS</div>',
        unsafe_allow_html=True
    )
    paragraphs = [p.strip() for p in ai_earnings.split("\n") if p.strip()]
    html_body  = "".join(
        f'<p style="margin:0 0 0.75rem 0;font-size:0.84rem;color:#e2e8f0;line-height:1.8;">{p}</p>'
        for p in paragraphs
    )
    st.markdown(
        '<div class="metric-card" style="border-left:3px solid #1e3a5f;">'
        '<div style="font-size:0.68rem;color:#38bdf8;text-transform:uppercase;'
        'letter-spacing:0.08em;margin-bottom:0.6rem;">Gemini 2.5 Flash</div>'
        f'{html_body}'
        '<div style="font-size:0.67rem;color:#334155;margin-top:0.3rem;">'
        'Generado por Gemini · No constituye asesoramiento financiero.</div>'
        '</div>',
        unsafe_allow_html=True
    )


def render_executive_summary(summary: str):
    if not summary:
        return
    paragraphs = [p.strip() for p in summary.split("\n") if p.strip()]
    html_body  = "".join(
        f'<p style="margin:0 0 0.8rem 0;font-size:0.85rem;color:#e2e8f0;line-height:1.85;">{p}</p>'
        for p in paragraphs
    )
    st.markdown(
        '<div class="section-header">RESUMEN EJECUTIVO · GEMINI AI</div>',
        unsafe_allow_html=True
    )
    st.markdown(
        '<div class="metric-card" style="border-left:4px solid #38bdf8;">'
        f'{html_body}'
        '<div style="font-size:0.67rem;color:#334155;margin-top:0.3rem;">'
        'Generado por Gemini 2.5 Flash · Yahoo Finance · No constituye asesoramiento financiero.</div>'
        '</div>',
        unsafe_allow_html=True
    )
