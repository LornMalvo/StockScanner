"""
gemini_client.py — v1.1
Integración con la API de Gemini (Google AI Studio).
Modelo: gemini-2.5-flash
Endpoint: https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent

Funcionalidades:
  1. Identificación de competidores reales por subsector específico
  2. Análisis de fortalezas, debilidades y moat frente a competidores
  3. Resumen ejecutivo del análisis completo
  4. Q&A interactivo sobre la empresa
"""

import requests
import streamlit as st
import os
import json

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_BASE  = "https://generativelanguage.googleapis.com/v1beta/models"
TIMEOUT      = 35


def _get_key() -> str:
    try:
        return str(st.secrets["GEMINI_API_KEY"]).strip()
    except Exception:
        pass
    return os.environ.get("GEMINI_API_KEY", "").strip()


def _call(prompt: str, temperature: float = 0.3, max_tokens: int = 1200) -> str | None:
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
            parts = (r.json().get("candidates", [{}])[0]
                              .get("content", {})
                              .get("parts", [{}]))
            return parts[0].get("text", "").strip() if parts else None
        print(f"[Gemini] HTTP {r.status_code}: {r.text[:300]}")
        return None
    except Exception as e:
        print(f"[Gemini] Error: {e}")
        return None


def _parse_json(raw: str) -> dict:
    """Limpia y parsea JSON de la respuesta de Gemini."""
    if not raw:
        return {}
    raw = raw.strip()
    # Eliminar bloques markdown ```json ... ```
    if "```" in raw:
        parts = raw.split("```")
        for p in parts:
            p = p.strip()
            if p.startswith("json"):
                p = p[4:].strip()
            if p.startswith("{"):
                raw = p
                break
    raw = raw.strip()
    try:
        return json.loads(raw)
    except Exception as e:
        print(f"[Gemini JSON] parse error: {e} — raw[:200]: {raw[:200]}")
        return {}


def is_available() -> bool:
    return bool(_get_key())


# ─────────────────────────────────────────────────────────────────────────────
# 1. IDENTIFICACIÓN DE COMPETIDORES REALES
# ─────────────────────────────────────────────────────────────────────────────

def identify_competitors(ticker: str, company_name: str,
                          sector: str, industry: str,
                          description: str) -> dict:
    """
    Identifica los competidores directos reales en el subsegmento exacto.
    """
    desc_short = (description or "")[:700]
    prompt = f"""Eres un analista financiero experto en mercados de capitales.

EMPRESA A ANALIZAR: {company_name} (ticker: {ticker})
SECTOR: {sector}
INDUSTRIA: {industry}
DESCRIPCIÓN DEL NEGOCIO: {desc_short}

TAREA CRÍTICA: Identifica los 6-8 competidores que compiten DIRECTAMENTE con {company_name} en su subsegmento ESPECÍFICO de negocio. No uses el sector genérico.

Ejemplos de lo que se espera:
- Si la empresa es Palantir (análisis de datos gubernamental/empresarial), los competidores son C3.ai, Alteryx, Verint, Snowflake — NO Microsoft ni Oracle.
- Si la empresa es Capricor Therapeutics (terapia génica para Duchenne), los competidores son Solid Biosciences, Sarepta Therapeutics, NS Pharma — NO Pfizer ni Johnson & Johnson.
- Si la empresa es Netflix (streaming de entretenimiento), los competidores son Disney+, Max, Paramount+, Apple TV+ — NO Comcast genérico.

Devuelve ÚNICAMENTE este JSON válido, sin texto adicional ni markdown:
{{
  "subsector": "nombre preciso del subsector en 3-6 palabras",
  "competitors": [
    {{"ticker": "XXXX", "name": "Nombre de la empresa", "reason": "por qué compite directamente con {company_name}"}},
    {{"ticker": "YYYY", "name": "Nombre de la empresa", "reason": "por qué compite directamente con {company_name}"}}
  ],
  "moat_factors": ["posible ventaja competitiva 1 de {company_name}", "posible ventaja competitiva 2", "posible ventaja competitiva 3"]
}}

IMPORTANTE: Solo incluye empresas que cotizan en bolsa con ticker real y verificado. Máximo 8 competidores."""

    data = _parse_json(_call(prompt, temperature=0.1, max_tokens=900))
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
    """
    Analiza fortalezas, debilidades y moat comparando métricas reales
    contra los competidores identificados por IA.
    """
    def pct(v):  return f"{(v or 0)*100:.1f}%" if v is not None else "N/D"
    def num(v, s=""): return f"{v:.1f}{s}" if v is not None else "N/D"
    def big(v):
        if not v: return "N/D"
        v = float(v)
        if abs(v) >= 1e12: return f"${v/1e12:.1f}T"
        if abs(v) >= 1e9:  return f"${v/1e9:.1f}B"
        return f"${v/1e6:.0f}M"

    main = (
        f"  Revenue YoY: {num(y.get('revenue_yoy'),'%')} | "
        f"Margen neto: {pct(y.get('profit_margin'))} | "
        f"Margen op: {pct(y.get('operating_margin'))} | "
        f"ROE: {pct(y.get('roe'))} | "
        f"PER fwd: {num(y.get('pe_forward'),'x')} | "
        f"EV/EBITDA: {num(y.get('ev_ebitda'),'x')} | "
        f"D/E: {num(y.get('debt_equity'),'%')} | "
        f"FCF: {'✓ positivo' if (y.get('free_cash_flow') or 0) > 0 else '✗ negativo'} | "
        f"Market Cap: {big(y.get('market_cap'))}"
    )

    peers_text = ""
    for p in peers_data[:6]:
        peers_text += (
            f"  {p['ticker']} ({p['name'][:20]}): "
            f"Rev YoY {num(p.get('rev_growth'),'%')} | "
            f"Margen {num(p.get('profit_m'),'%')} | "
            f"ROE {num(p.get('roe'),'%')} | "
            f"PER {num(p.get('pe_forward'),'x')} | "
            f"Cap {big(p.get('market_cap'))}\n"
        )

    moat_hint = f"\nPosibles ventajas competitivas identificadas: {', '.join(moat_factors)}" if moat_factors else ""

    prompt = f"""Eres un analista financiero senior especializado en el sector {subsector}.

EMPRESA: {company_name} ({ticker}) — subsector: {subsector}
MÉTRICAS CLAVE:
{main}

COMPETIDORES DIRECTOS Y SUS MÉTRICAS:
{peers_text if peers_text else "  Sin datos de competidores disponibles"}
{moat_hint}

TAREA: Basándote en los datos numéricos anteriores y tu conocimiento profundo del sector {subsector}:

1. Identifica los 3-4 PUNTOS FUERTES más relevantes de {company_name} frente a sus competidores directos. Sé específico: menciona en qué métricas supera y por qué importa en este sector.

2. Identifica los 2-3 PUNTOS DÉBILES o riesgos más importantes. Sé específico y objetivo.

3. Describe el MOAT o ventaja competitiva diferencial de {company_name} — qué la hace difícil de replicar. Si no tiene moat claro, dilo.

4. Una frase de CONCLUSIÓN sobre la posición competitiva actual (líder, seguidor, nicho, en riesgo...).

Responde en español. Máximo 2 líneas por punto. Sé directo y concreto.
Devuelve ÚNICAMENTE este JSON válido, sin texto adicional:
{{
  "strengths": ["punto fuerte 1 específico", "punto fuerte 2 específico", "punto fuerte 3 específico"],
  "weaknesses": ["punto débil 1 específico", "punto débil 2 específico"],
  "moat": "descripción del moat en 2-3 frases. Qué la hace especial o difícil de replicar.",
  "position": "frase de conclusión sobre posición competitiva"
}}"""

    data = _parse_json(_call(prompt, temperature=0.2, max_tokens=900))
    return {
        "strengths":  data.get("strengths", []),
        "weaknesses": data.get("weaknesses", []),
        "moat":       data.get("moat", ""),
        "position":   data.get("position", ""),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. RESUMEN EJECUTIVO
# ─────────────────────────────────────────────────────────────────────────────

def generate_executive_summary(ticker: str, company_name: str,
                                y: dict, ev: dict, sq: dict,
                                tech: dict | None,
                                strengths_data: dict,
                                subsector: str) -> str:
    """
    Genera un resumen ejecutivo completo y accionable.
    """
    def pct(v):   return f"{(v or 0)*100:.1f}%" if v is not None else "N/D"
    def num(v, s=""): return f"{v:.1f}{s}" if v is not None else "N/D"
    def big(v):
        if not v: return "N/D"
        v = float(v)
        if abs(v) >= 1e12: return f"${v/1e12:.1f}T"
        if abs(v) >= 1e9:  return f"${v/1e9:.1f}B"
        return f"${v/1e6:.0f}M"

    rsi  = num(tech.get("rsi")) if tech and not tech.get("error") else "N/D"
    mm_pos = ""
    if tech and not tech.get("error"):
        p = y.get("price") or 0
        if tech.get("mm50"):
            mm_pos += f"{'▲' if p > tech['mm50'] else '▼'} MM50 "
        if tech.get("mm200"):
            mm_pos += f"{'▲' if p > tech['mm200'] else '▼'} MM200"

    diag   = ev.get("diag", "")
    fair   = f"${ev.get('fair_value', 0):,.2f}" if ev.get("fair_value") else "N/D"
    upside = f"{ev.get('upside', 0):+.1f}%" if ev.get("upside") is not None else "N/D"
    sq_lvl = sq.get("level","") if sq else ""
    sq_scr = sq.get("score", 0) if sq else 0

    strengths_txt  = "; ".join(strengths_data.get("strengths",[])) or "No analizadas"
    weaknesses_txt = "; ".join(strengths_data.get("weaknesses",[])) or "No analizadas"
    moat_txt       = strengths_data.get("moat","") or "No determinado"
    position_txt   = strengths_data.get("position","") or ""

    prompt = f"""Eres un analista financiero senior con 20 años de experiencia. Escribe un resumen ejecutivo COMPLETO de la siguiente empresa.

EMPRESA: {company_name} ({ticker}) — subsector: {subsector}

DATOS FUNDAMENTALES:
- Precio: ${y.get('price', 0):,.2f} | Market Cap: {big(y.get('market_cap'))}
- Diagnóstico: {diag} | Valor objetivo: {fair} (upside: {upside})
- Revenue YoY: {num(y.get('revenue_yoy'),'%')} | Beneficio YoY: {num(y.get('earnings_yoy'),'%')}
- Margen neto: {pct(y.get('profit_margin'))} | Margen operativo: {pct(y.get('operating_margin'))}
- ROE: {pct(y.get('roe'))} | PER Forward: {num(y.get('pe_forward'),'x')} | EV/EBITDA: {num(y.get('ev_ebitda'),'x')}
- FCF: {'positivo' if (y.get('free_cash_flow') or 0) > 0 else 'negativo'} | Deuda/Equity: {num(y.get('debt_equity'),'%')}
- RSI: {rsi} | Posición vs medias: {mm_pos}
- Short squeeze: {sq_lvl} (score: {sq_scr}/100)

ANÁLISIS COMPETITIVO:
- Fortalezas: {strengths_txt}
- Debilidades: {weaknesses_txt}
- Moat/Ventaja: {moat_txt}
- Posición: {position_txt}

INSTRUCCIONES ESTRICTAS:
- Escribe exactamente 5 párrafos cortos en español (2-3 frases cada uno)
- Párrafo 1: situación del negocio y crecimiento
- Párrafo 2: rentabilidad y calidad financiera
- Párrafo 3: valoración actual y comparativa con el sector
- Párrafo 4: posición competitiva y riesgos principales
- Párrafo 5: conclusión clara — si es buen momento para entrar, qué esperar
- No uses bullet points ni listas — solo prosa fluida
- No repitas los datos en bruto — interprétalos y dales contexto"""

    result = _call(prompt, temperature=0.4, max_tokens=1000)
    return result or ""


# ─────────────────────────────────────────────────────────────────────────────
# 4. Q&A INTERACTIVO
# ─────────────────────────────────────────────────────────────────────────────

def answer_question(question: str, ticker: str, company_name: str,
                    y: dict, ev: dict) -> str:
    def pct(v):   return f"{(v or 0)*100:.1f}%" if v is not None else "N/D"
    def num(v, s=""): return f"{v:.1f}{s}" if v is not None else "N/D"

    context = f"""EMPRESA: {company_name} ({ticker})
Sector: {y.get('sector','')} / {y.get('industry','')}
Precio: ${y.get('price', 0):,.2f} | Market Cap: {(y.get('market_cap',0) or 0)/1e9:.1f}B
PER Forward: {num(y.get('pe_forward'),'x')} | PEG: {num(y.get('peg_ratio'))} | EV/EBITDA: {num(y.get('ev_ebitda'),'x')}
Margen neto: {pct(y.get('profit_margin'))} | Margen op: {pct(y.get('operating_margin'))}
ROE: {pct(y.get('roe'))} | ROA: {pct(y.get('roa'))}
Revenue YoY: {num(y.get('revenue_yoy'),'%')} | Earnings YoY: {num(y.get('earnings_yoy'),'%')}
FCF: {'positivo' if (y.get('free_cash_flow') or 0) > 0 else 'negativo'} | D/E: {num(y.get('debt_equity'),'%')}
Short Ratio: {num(y.get('short_ratio'),'d')} | Beta: {num(y.get('beta'))}
Diagnóstico: {ev.get('diag','')} | Valor objetivo: ${(ev.get('fair_value') or 0):,.2f} ({(ev.get('upside') or 0):+.1f}% upside)"""

    prompt = f"""Eres un analista financiero experto. Responde esta pregunta sobre {company_name} ({ticker}).

DATOS DEL ANÁLISIS:
{context}

PREGUNTA: {question}

Responde en español. Sé directo y específico. Máximo 200 palabras. Sin listas — prosa natural."""

    return _call(prompt, temperature=0.5, max_tokens=400) or "No se pudo generar respuesta."


# ─────────────────────────────────────────────────────────────────────────────
# RENDERS
# ─────────────────────────────────────────────────────────────────────────────

def render_ai_strengths_in_description(strengths_data: dict, subsector: str):
    """
    Renderiza fortalezas, debilidades y moat DENTRO del apartado de descripción.
    Se llama desde render_company_description en analysis.py.
    """
    if not strengths_data or (
        not strengths_data.get("strengths") and
        not strengths_data.get("weaknesses") and
        not strengths_data.get("moat")
    ):
        return

    strengths  = strengths_data.get("strengths", [])
    weaknesses = strengths_data.get("weaknesses", [])
    moat       = strengths_data.get("moat", "")
    position   = strengths_data.get("position", "")

    rows_s = "".join(
        f'<div style="display:flex;gap:0.5rem;padding:0.28rem 0;'
        f'border-bottom:1px solid #1a2540;font-size:0.8rem;">'
        f'<span style="color:#6ee7b7;min-width:1rem;">✔</span>'
        f'<span style="color:#e2e8f0;">{s}</span></div>'
        for s in strengths
    )
    rows_w = "".join(
        f'<div style="display:flex;gap:0.5rem;padding:0.28rem 0;'
        f'border-bottom:1px solid #1a2540;font-size:0.8rem;">'
        f'<span style="color:#fca5a5;min-width:1rem;">✘</span>'
        f'<span style="color:#e2e8f0;">{w}</span></div>'
        for w in weaknesses
    )
    moat_html = (
        f'<div style="background:#0a1628;border-left:3px solid #38bdf8;border-radius:4px;'
        f'padding:0.55rem 0.75rem;margin-top:0.6rem;">'
        f'<div style="font-size:0.68rem;color:#38bdf8;text-transform:uppercase;'
        f'letter-spacing:0.08em;margin-bottom:0.2rem;">Ventaja competitiva (Moat)</div>'
        f'<div style="font-size:0.8rem;color:#cbd5e1;line-height:1.65;">{moat}</div>'
        f'</div>'
    ) if moat else ""
    pos_html = (
        f'<div style="font-size:0.78rem;color:#fbbf24;margin-top:0.5rem;'
        f'padding:0.3rem 0;border-top:1px solid #1a2540;">'
        f'▸ {position}</div>'
    ) if position else ""

    badge = (
        f'<span style="background:#0f2d1a;color:#6ee7b7;padding:2px 8px;border-radius:4px;'
        f'font-size:0.7rem;margin-left:0.5rem;font-weight:600;">✨ Gemini · {subsector}</span>'
        if subsector else
        '<span style="background:#0f2d1a;color:#6ee7b7;padding:2px 8px;border-radius:4px;font-size:0.7rem;margin-left:0.5rem;">✨ Gemini IA</span>'
    )

    st.markdown(
        f'<div class="metric-card" style="border-left:3px solid #1e3a5f;margin-top:0.5rem;">'
        f'<div style="font-size:0.7rem;color:#94a3b8;text-transform:uppercase;'
        f'letter-spacing:0.08em;margin-bottom:0.6rem;">'
        f'Análisis competitivo{badge}</div>'
        f'<div style="margin-bottom:0.5rem;">'
        f'<div style="font-size:0.68rem;color:#6ee7b7;text-transform:uppercase;'
        f'letter-spacing:0.06em;margin-bottom:0.25rem;">Puntos fuertes</div>'
        f'{rows_s if rows_s else "<span style=\'color:#475569;font-size:0.78rem;\'>Sin datos</span>"}'
        f'</div>'
        f'<div style="margin-top:0.4rem;">'
        f'<div style="font-size:0.68rem;color:#fca5a5;text-transform:uppercase;'
        f'letter-spacing:0.06em;margin-bottom:0.25rem;">Puntos débiles / riesgos</div>'
        f'{rows_w if rows_w else "<span style=\'color:#475569;font-size:0.78rem;\'>Sin datos</span>"}'
        f'</div>'
        f'{moat_html}{pos_html}'
        f'</div>',
        unsafe_allow_html=True
    )


def render_executive_summary(summary: str):
    """Resumen ejecutivo completo al final del análisis."""
    if not summary:
        return
    # Convertir saltos de línea en párrafos HTML
    paragraphs = [p.strip() for p in summary.split("\n") if p.strip()]
    html_body  = "".join(
        f'<p style="margin:0 0 0.7rem 0;font-size:0.86rem;color:#e2e8f0;line-height:1.8;">{p}</p>'
        for p in paragraphs
    )
    st.markdown(
        '<div style="background:#0f172a;border:1px solid #1e3a5f;border-left:4px solid #38bdf8;'
        'border-radius:8px;padding:1.1rem 1.3rem;margin-bottom:1rem;">'
        '<div style="font-size:0.7rem;color:#38bdf8;text-transform:uppercase;'
        'letter-spacing:0.1em;margin-bottom:0.7rem;">✨ Resumen ejecutivo · Gemini AI</div>'
        f'{html_body}'
        '</div>',
        unsafe_allow_html=True
    )


def render_qa_widget(ticker: str, company_name: str, y: dict, ev: dict):
    """
    Widget Q&A. Usa st.form para evitar que los botones reinicien el análisis.
    """
    st.markdown(
        '<div class="section-header">✨ CONSULTA A GEMINI SOBRE ESTA EMPRESA</div>',
        unsafe_allow_html=True
    )

    suggestions = [
        f"¿Cuál es el mayor riesgo de invertir en {company_name} ahora mismo?",
        f"¿Por qué cotiza {ticker} con esa valoración respecto al sector?",
        f"¿Qué debería vigilar en el próximo informe de resultados?",
        f"¿Es sostenible el crecimiento actual de {company_name}?",
    ]

    st.markdown(
        '<div style="font-size:0.78rem;color:#64748b;margin-bottom:0.4rem;">'
        'Preguntas sugeridas (cópiala en el campo de texto):</div>',
        unsafe_allow_html=True
    )
    # Mostrar sugerencias como texto, no como botones, para no disparar reruns
    sug_html = "".join(
        f'<div style="padding:0.3rem 0.5rem;margin-bottom:0.25rem;background:#0f172a;'
        f'border:1px solid #1e2d45;border-radius:4px;font-size:0.78rem;color:#94a3b8;'
        f'cursor:default;">{s}</div>'
        for s in suggestions
    )
    st.markdown(f'<div style="margin-bottom:0.6rem;">{sug_html}</div>',
                unsafe_allow_html=True)

    # Usar st.form para que el botón Enviar no provoque rerun completo de la app
    with st.form(key=f"qa_form_{ticker}", clear_on_submit=False):
        question = st.text_input(
            "Tu pregunta",
            placeholder=f"Escribe cualquier pregunta sobre {company_name}…",
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button("Preguntar a Gemini →")

    if submitted and question.strip():
        with st.spinner("Gemini está analizando…"):
            answer = answer_question(question, ticker, company_name, y, ev)
        st.markdown(
            '<div style="background:#111827;border:1px solid #1e2d45;'
            'border-left:3px solid #38bdf8;border-radius:6px;padding:0.85rem 1rem;margin-top:0.4rem;">'
            f'<div style="font-size:0.75rem;color:#475569;margin-bottom:0.35rem;">'
            f'Pregunta: {question}</div>'
            f'<div style="font-size:0.85rem;color:#e2e8f0;line-height:1.75;">{answer}</div>'
            '<div style="font-size:0.67rem;color:#334155;margin-top:0.4rem;">'
            'Generado por Gemini 2.5 Flash · Basado en datos de Yahoo Finance · '
            'No constituye asesoramiento financiero.</div>'
            '</div>',
            unsafe_allow_html=True
        )
    elif submitted:
        st.warning("Escribe una pregunta primero.")
