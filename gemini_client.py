"""
gemini_client.py — v1.0
Integración con la API de Gemini (Google AI Studio).
Modelo: gemini-2.5-flash (tier gratuito: 250 req/día)
Endpoint: https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent

Funcionalidades:
  1. Identificación de competidores reales por subsector específico
  2. Análisis de fortalezas y debilidades vs competidores
  3. Resumen ejecutivo del análisis completo
  4. Q&A interactivo sobre la empresa
"""

import requests
import streamlit as st
import os
import json


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────────────────────────────────────

GEMINI_MODEL   = "gemini-2.5-flash"
GEMINI_BASE    = "https://generativelanguage.googleapis.com/v1beta/models"
TIMEOUT        = 30


def _get_key() -> str:
    try:
        return str(st.secrets["GEMINI_API_KEY"]).strip()
    except Exception:
        pass
    return os.environ.get("GEMINI_API_KEY", "").strip()


def _call(prompt: str, temperature: float = 0.3, max_tokens: int = 1024) -> str | None:
    """Llamada directa a la API REST de Gemini."""
    key = _get_key()
    if not key:
        return None
    url = f"{GEMINI_BASE}/{GEMINI_MODEL}:generateContent?key={key}"
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
            data = r.json()
            parts = (data.get("candidates", [{}])[0]
                        .get("content", {})
                        .get("parts", [{}]))
            return parts[0].get("text", "").strip() if parts else None
        else:
            print(f"[Gemini] HTTP {r.status_code}: {r.text[:300]}")
            return None
    except Exception as e:
        print(f"[Gemini] Error: {e}")
        return None


def is_available() -> bool:
    return bool(_get_key())


# ─────────────────────────────────────────────────────────────────────────────
# 1. IDENTIFICACIÓN DE COMPETIDORES REALES
# ─────────────────────────────────────────────────────────────────────────────

def identify_competitors(ticker: str, company_name: str,
                          sector: str, industry: str,
                          description: str) -> dict:
    """
    Usa Gemini para identificar los competidores directos reales
    del subsegmento exacto de negocio de la empresa.
    Devuelve lista de tickers y nombre del subsector.
    """
    desc_short = (description or "")[:600]
    prompt = f"""Eres un analista financiero experto. Analiza esta empresa y devuelve sus competidores directos reales.

EMPRESA: {company_name} ({ticker})
SECTOR: {sector} / {industry}
DESCRIPCIÓN: {desc_short}

TAREA: Identifica los 6-8 competidores que compiten DIRECTAMENTE con {company_name} en su subsegmento específico de negocio.
NO uses empresas del sector genérico — usa competidores del nicho exacto.

Responde ÚNICAMENTE con este JSON (sin texto adicional, sin markdown):
{{
  "subsector": "nombre del subsector específico en 3-5 palabras",
  "competitors": [
    {{"ticker": "XXXX", "name": "Nombre empresa", "reason": "Por qué compite directamente"}},
    ...
  ],
  "moat_factors": ["factor competitivo 1", "factor competitivo 2", "factor competitivo 3"]
}}

Solo incluye empresas que cotizan en bolsa con ticker real. Si no sabes el ticker exacto, omite la empresa."""

    raw = _call(prompt, temperature=0.1, max_tokens=800)
    if not raw:
        return {}

    # Limpiar posibles bloques markdown
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip().rstrip("```").strip()

    try:
        data = json.loads(raw)
        return {
            "subsector":   data.get("subsector", ""),
            "competitors": data.get("competitors", []),
            "moat_factors":data.get("moat_factors", []),
        }
    except Exception as e:
        print(f"[Gemini competitors] JSON parse error: {e} — raw: {raw[:200]}")
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# 2. ANÁLISIS DE FORTALEZAS Y DEBILIDADES
# ─────────────────────────────────────────────────────────────────────────────

def analyze_strengths_weaknesses(ticker: str, company_name: str,
                                  y: dict, peers_data: list,
                                  subsector: str) -> dict:
    """
    Compara métricas de la empresa vs sus competidores reales
    y genera análisis cualitativo de fortalezas y debilidades.
    """
    def pct(v): return f"{(v or 0)*100:.1f}%" if v is not None else "N/D"
    def num(v, sfx=""): return f"{v:.1f}{sfx}" if v is not None else "N/D"

    # Datos de la empresa analizada
    main_metrics = (
        f"  - Revenue YoY: {num(y.get('revenue_yoy'), '%')}\n"
        f"  - Margen neto: {pct(y.get('profit_margin'))}\n"
        f"  - Margen operativo: {pct(y.get('operating_margin'))}\n"
        f"  - ROE: {pct(y.get('roe'))}\n"
        f"  - PER Forward: {num(y.get('pe_forward'), 'x')}\n"
        f"  - EV/EBITDA: {num(y.get('ev_ebitda'), 'x')}\n"
        f"  - Deuda/Equity: {num(y.get('debt_equity'), '%')}\n"
        f"  - FCF: {'positivo' if (y.get('free_cash_flow') or 0) > 0 else 'negativo'}"
    )

    # Datos de competidores
    peers_text = ""
    for p in peers_data[:5]:
        peers_text += (
            f"  {p['ticker']} ({p['name']}): "
            f"Rev YoY {num(p.get('rev_growth'),'%')} | "
            f"Margen {num(p.get('profit_m'),'%')} | "
            f"ROE {num(p.get('roe'),'%')} | "
            f"PER {num(p.get('pe_forward'),'x')}\n"
        )

    prompt = f"""Eres un analista financiero experto en el sector {subsector}.

EMPRESA ANALIZADA: {company_name} ({ticker})
MÉTRICAS:
{main_metrics}

COMPETIDORES DIRECTOS:
{peers_text if peers_text else "  Sin datos de competidores disponibles"}

TAREA: Basándote en los datos numéricos anteriores y tu conocimiento del sector {subsector}, analiza:
1. Los 3-4 puntos FUERTES más relevantes de {company_name} frente a sus competidores
2. Los 2-3 puntos DÉBILES o riesgos más importantes
3. Lo que hace ESPECIAL o diferente a esta empresa (su moat o ventaja competitiva)

Responde en español, de forma concisa y directa. Máximo 3 líneas por punto.
Responde ÚNICAMENTE con este JSON (sin texto adicional):
{{
  "strengths": ["fortaleza 1", "fortaleza 2", "fortaleza 3"],
  "weaknesses": ["debilidad 1", "debilidad 2"],
  "differentiator": "qué hace especial a esta empresa en 2-3 frases"
}}"""

    raw = _call(prompt, temperature=0.2, max_tokens=700)
    if not raw:
        return {}

    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip().rstrip("```").strip()

    try:
        data = json.loads(raw)
        return {
            "strengths":      data.get("strengths", []),
            "weaknesses":     data.get("weaknesses", []),
            "differentiator": data.get("differentiator", ""),
        }
    except Exception as e:
        print(f"[Gemini strengths] JSON parse error: {e}")
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# 3. RESUMEN EJECUTIVO
# ─────────────────────────────────────────────────────────────────────────────

def generate_executive_summary(ticker: str, company_name: str,
                                y: dict, ev: dict, sq: dict,
                                tech: dict | None) -> str:
    """
    Genera un resumen ejecutivo accionable del análisis completo.
    Sintetiza todos los datos en 4-5 frases directas.
    """
    def pct(v): return f"{(v or 0)*100:.1f}%" if v is not None else "N/D"
    def num(v, sfx=""): return f"{v:.1f}{sfx}" if v is not None else "N/D"
    def big(v):
        if not v: return "N/D"
        v = float(v)
        if abs(v) >= 1e12: return f"${v/1e12:.1f}T"
        if abs(v) >= 1e9:  return f"${v/1e9:.1f}B"
        return f"${v/1e6:.0f}M"

    rsi   = num(tech.get("rsi") if tech and not tech.get("error") else None)
    mm50  = "por encima" if tech and not tech.get("error") and (y.get("price") or 0) > (tech.get("mm50") or 0) else "por debajo"
    diag  = ev.get("diag", "")
    fair  = f"${ev.get('fair_value', 0):,.2f}" if ev.get("fair_value") else "N/D"
    upside= f"{ev.get('upside', 0):+.1f}%" if ev.get("upside") is not None else "N/D"
    sq_lvl= sq.get("level","") if sq else ""

    prompt = f"""Eres un analista financiero senior. Genera un resumen ejecutivo CONCISO y ACCIONABLE.

EMPRESA: {company_name} ({ticker})
DATOS CLAVE:
- Precio: ${y.get('price', 0):,.2f} | Market Cap: {big(y.get('market_cap'))}
- Diagnóstico app: {diag} | Valor objetivo: {fair} ({upside} upside)
- Revenue YoY: {num(y.get('revenue_yoy'),'%')} | Beneficio YoY: {num(y.get('earnings_yoy'),'%')}
- Margen neto: {pct(y.get('profit_margin'))} | ROE: {pct(y.get('roe'))}
- PER Forward: {num(y.get('pe_forward'),'x')} | EV/EBITDA: {num(y.get('ev_ebitda'),'x')}
- FCF: {'positivo ✓' if (y.get('free_cash_flow') or 0) > 0 else 'negativo ✗'}
- RSI: {rsi} | Precio {mm50} de MM50
- Short squeeze: {sq_lvl}
- Deuda/Equity: {num(y.get('debt_equity'),'%')}

INSTRUCCIONES:
- Escribe exactamente 4-5 frases en español
- Sé directo y accionable — qué está bien, qué preocupa, qué haría un inversor
- No uses bullet points, escribe en prosa fluida
- La última frase debe ser una conclusión clara sobre si el momento es bueno o no para entrar
- No repitas los números exactos ya mostrados en la app — interprétalos"""

    result = _call(prompt, temperature=0.4, max_tokens=400)
    return result or ""


# ─────────────────────────────────────────────────────────────────────────────
# 4. Q&A INTERACTIVO
# ─────────────────────────────────────────────────────────────────────────────

def answer_question(question: str, ticker: str, company_name: str,
                    y: dict, ev: dict, context_extra: str = "") -> str:
    """
    Responde preguntas del usuario sobre la empresa analizada.
    Usa los datos del análisis como contexto.
    """
    def pct(v): return f"{(v or 0)*100:.1f}%" if v is not None else "N/D"
    def num(v, sfx=""): return f"{v:.1f}{sfx}" if v is not None else "N/D"

    context = f"""EMPRESA: {company_name} ({ticker})
Sector: {y.get('sector','')} / {y.get('industry','')}
Precio: ${y.get('price', 0):,.2f} | Market Cap: {y.get('market_cap', 0)/1e9:.1f}B
PER Forward: {num(y.get('pe_forward'),'x')} | PEG: {num(y.get('peg_ratio'))}
EV/EBITDA: {num(y.get('ev_ebitda'),'x')} | Price/Sales: {num(y.get('price_sales'),'x')}
Margen neto: {pct(y.get('profit_margin'))} | Margen operativo: {pct(y.get('operating_margin'))}
ROE: {pct(y.get('roe'))} | ROA: {pct(y.get('roa'))}
Revenue YoY: {num(y.get('revenue_yoy'),'%')} | Earnings YoY: {num(y.get('earnings_yoy'),'%')}
FCF: {y.get('free_cash_flow', 0)/1e9:.2f}B | Deuda/Equity: {num(y.get('debt_equity'),'%')}
Short Ratio: {num(y.get('short_ratio'),'d')} | Beta: {num(y.get('beta'))}
Diagnóstico: {ev.get('diag','')} | Valor objetivo: ${ev.get('fair_value', 0):,.2f} ({ev.get('upside', 0):+.1f}% upside)
{context_extra}"""

    prompt = f"""Eres un analista financiero experto. Responde esta pregunta sobre {company_name} ({ticker}).

DATOS DEL ANÁLISIS:
{context}

PREGUNTA DEL USUARIO: {question}

INSTRUCCIONES:
- Responde en español de forma clara y directa
- Basa tu respuesta principalmente en los datos proporcionados
- Si la pregunta requiere información que no está en los datos, indícalo claramente
- Máximo 150 palabras
- No uses listas largas — responde en prosa natural"""

    result = _call(prompt, temperature=0.5, max_tokens=300)
    return result or "No se pudo generar una respuesta. Comprueba la API key de Gemini."


# ─────────────────────────────────────────────────────────────────────────────
# RENDERS
# ─────────────────────────────────────────────────────────────────────────────

def render_ai_description(strengths_data: dict, subsector: str):
    """Renderiza el bloque de fortalezas/debilidades en la descripción."""
    if not strengths_data:
        return

    strengths    = strengths_data.get("strengths", [])
    weaknesses   = strengths_data.get("weaknesses", [])
    differentiator = strengths_data.get("differentiator", "")

    if not strengths and not weaknesses:
        return

    rows_s = "".join(
        f'<div style="display:flex;gap:0.5rem;padding:0.3rem 0;border-bottom:1px solid #1a2540;font-size:0.8rem;">'
        f'<span style="color:#6ee7b7;font-size:0.9rem;">✔</span>'
        f'<span style="color:#e2e8f0;">{s}</span></div>'
        for s in strengths
    )
    rows_w = "".join(
        f'<div style="display:flex;gap:0.5rem;padding:0.3rem 0;border-bottom:1px solid #1a2540;font-size:0.8rem;">'
        f'<span style="color:#fca5a5;font-size:0.9rem;">✘</span>'
        f'<span style="color:#e2e8f0;">{w}</span></div>'
        for w in weaknesses
    )
    diff_html = (
        f'<div style="background:#0f172a;border-left:3px solid #38bdf8;border-radius:4px;'
        f'padding:0.5rem 0.7rem;margin-top:0.5rem;font-size:0.8rem;color:#94a3b8;line-height:1.6;">'
        f'<span style="font-size:0.68rem;color:#38bdf8;text-transform:uppercase;letter-spacing:0.08em;">'
        f'Ventaja competitiva</span><br>{differentiator}</div>'
    ) if differentiator else ""

    badge = (
        f'<span style="background:#064e3b;color:#6ee7b7;padding:2px 8px;border-radius:4px;'
        f'font-size:0.72rem;margin-left:0.5rem;">✨ IA · {subsector}</span>'
        if subsector else
        '<span style="background:#064e3b;color:#6ee7b7;padding:2px 8px;border-radius:4px;font-size:0.72rem;margin-left:0.5rem;">✨ Análisis IA</span>'
    )

    st.markdown(
        f'<div class="metric-card" style="border-left:3px solid #1e3a5f;">'
        f'<div style="font-size:0.7rem;color:#38bdf8;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:0.5rem;">'
        f'Fortalezas y debilidades frente a la competencia{badge}</div>'
        f'<div style="margin-bottom:0.4rem;">'
        f'<div style="font-size:0.68rem;color:#6ee7b7;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.2rem;">Puntos fuertes</div>'
        f'{rows_s}</div>'
        f'<div style="margin-top:0.4rem;">'
        f'<div style="font-size:0.68rem;color:#fca5a5;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.2rem;">Puntos débiles / riesgos</div>'
        f'{rows_w}</div>'
        f'{diff_html}'
        f'</div>',
        unsafe_allow_html=True
    )


def render_executive_summary(summary: str):
    """Renderiza el resumen ejecutivo al inicio del informe."""
    if not summary:
        return
    st.markdown(
        '<div style="background:#0f172a;border:1px solid #1e3a5f;border-left:4px solid #38bdf8;'
        'border-radius:8px;padding:1rem 1.2rem;margin-bottom:1rem;">'
        '<div style="font-size:0.7rem;color:#38bdf8;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:0.5rem;">'
        '✨ Resumen ejecutivo · Gemini AI</div>'
        f'<div style="font-size:0.86rem;color:#e2e8f0;line-height:1.8;">{summary}</div>'
        '</div>',
        unsafe_allow_html=True
    )


def render_qa_widget(ticker: str, company_name: str, y: dict, ev: dict):
    """Renderiza el widget de Q&A interactivo."""
    st.markdown(
        '<div class="section-header">✨ PREGUNTAS SOBRE ESTA EMPRESA · GEMINI AI</div>',
        unsafe_allow_html=True
    )

    # Sugerencias rápidas
    suggestions = [
        f"¿Cuál es el mayor riesgo de invertir en {company_name} ahora mismo?",
        f"¿Por qué cotiza {ticker} con esa valoración respecto al sector?",
        f"¿Qué debería vigilar en el próximo informe de resultados?",
        f"¿Es sostenible el crecimiento actual de {company_name}?",
    ]

    st.markdown(
        '<div style="font-size:0.78rem;color:#64748b;margin-bottom:0.5rem;">Sugerencias:</div>',
        unsafe_allow_html=True
    )
    cols = st.columns(2)
    for i, sug in enumerate(suggestions):
        with cols[i % 2]:
            if st.button(sug[:55] + "…" if len(sug) > 55 else sug,
                         key=f"qa_sug_{i}",
                         use_container_width=True):
                st.session_state[f"qa_input_{ticker}"] = sug

    question = st.text_input(
        "Escribe tu pregunta",
        value=st.session_state.get(f"qa_input_{ticker}", ""),
        placeholder=f"Pregunta lo que quieras sobre {company_name}…",
        key=f"qa_field_{ticker}",
        label_visibility="collapsed",
    )

    if st.button("Preguntar →", key=f"qa_btn_{ticker}"):
        if question.strip():
            with st.spinner("Gemini está analizando…"):
                answer = answer_question(question, ticker, company_name, y, ev)
            if answer:
                st.markdown(
                    '<div style="background:#111827;border:1px solid #1e2d45;border-left:3px solid #38bdf8;'
                    'border-radius:6px;padding:0.8rem 1rem;margin-top:0.5rem;">'
                    f'<div style="font-size:0.8rem;color:#64748b;margin-bottom:0.3rem;">Pregunta: {question}</div>'
                    f'<div style="font-size:0.85rem;color:#e2e8f0;line-height:1.75;">{answer}</div>'
                    '<div style="font-size:0.68rem;color:#334155;margin-top:0.4rem;">'
                    'Generado por Gemini 2.5 Flash · Basado en datos de Yahoo Finance · No constituye asesoramiento financiero.</div>'
                    '</div>',
                    unsafe_allow_html=True
                )
        else:
            st.warning("Escribe una pregunta primero.")
