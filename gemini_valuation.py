"""
gemini_valuation.py — v1.0
Consulta simple a Gemini Pro: un prompt fijo con ticker y precio
interpolados, y el texto de respuesta se muestra tal cual en la app.
Sin parsing de JSON — solo texto libre de entrada y salida.

Requiere GEMINI_API_KEY en Streamlit Secrets (Settings → Secrets):
    GEMINI_API_KEY = "tu-key-de-aistudio.google.com"
"""

import requests
import streamlit as st
import os

GEMINI_MODEL = "gemini-3.5-flash"
GEMINI_URL   = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
TIMEOUT      = 40


def _get_gemini_key() -> str:
    try:
        return str(st.secrets["GEMINI_API_KEY"]).strip()
    except Exception:
        pass
    return os.environ.get("GEMINI_API_KEY", "").strip()


def is_available() -> bool:
    return bool(_get_gemini_key())


# ─────────────────────────────────────────────────────────────────────────────
# PROMPT FIJO — edita este texto para cambiar lo que se le pide a Gemini.
# {ticker} y {price} se sustituyen automáticamente por los datos reales.
# ─────────────────────────────────────────────────────────────────────────────

PROMPT_TEMPLATE = """Actúa como un analista financiero senior. Analiza la empresa con ticker {ticker}, que cotiza actualmente a {price}.

Con base en tu conocimiento general de esta empresa (modelo de negocio, posición competitiva, situación financiera aproximada y perspectivas del sector), ofrece una valoración cualitativa breve que responda a:

1. ¿Cuál es tu opinión general sobre la empresa a este precio?
2. ¿Cuáles son sus principales fortalezas?
3. ¿Cuáles son sus principales riesgos o debilidades?
4. ¿Qué deberían vigilar los inversores en los próximos trimestres?

Responde en español, en un máximo de 5 párrafos cortos, en prosa (sin listas ni encabezados). Sé directo y evita generalidades vacías."""


def fetch_ai_valuation(ticker: str, price: float, currency: str = "USD") -> str | None:
    """
    Llama a Gemini con el prompt fijo (ticker y precio interpolados) y
    devuelve el texto de respuesta tal cual. None si falla o no hay key.
    """
    key = _get_gemini_key()
    if not key:
        return None

    price_str = f"{currency} {price:,.2f}" if price else "precio no disponible"
    prompt = PROMPT_TEMPLATE.format(ticker=ticker.upper(), price=price_str)

    try:
        r = requests.post(
            f"{GEMINI_URL}?key={key}",
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.4, "maxOutputTokens": 1200},
            },
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            st.warning(f"Gemini devolvió un error (HTTP {r.status_code}). Revisa la API key en Secrets.")
            print(f"[Gemini] HTTP {r.status_code}: {r.text[:300]}")
            return None

        data       = r.json()
        candidates = data.get("candidates", [])
        if not candidates:
            st.warning("Gemini no devolvió respuesta (posible bloqueo de seguridad o prompt vacío).")
            return None

        parts = candidates[0].get("content", {}).get("parts", [])
        text  = parts[0].get("text", "").strip() if parts else ""
        return text or None

    except Exception as e:
        st.warning(f"No se pudo conectar con Gemini: {e}")
        return None


def render_ai_valuation(ticker: str, price: float, currency: str = "USD"):
    """Sección 'Valoración por IA — Gemini Pro' con botón de generación bajo demanda."""
    st.markdown(
        '<div class="section-header">VALORACIÓN POR IA — GEMINI PRO</div>',
        unsafe_allow_html=True
    )

    if not is_available():
        st.markdown(
            '<div class="metric-card"><span style="color:#64748b;">'
            'Añade tu GEMINI_API_KEY en Streamlit → Settings → Secrets para activar esta sección.'
            '</span></div>',
            unsafe_allow_html=True
        )
        return

    cache_key = f"_gemini_valuation_{ticker.upper()}"
    cached    = st.session_state.get(cache_key)

    col1, col2 = st.columns([3, 1])
    with col1:
        label = "🔄 Regenerar valoración" if cached else "✨ Generar valoración con IA"
    with col2:
        pass
    generate = st.button(label, key=f"gemini_btn_{ticker}")

    if generate:
        with st.spinner("Consultando a Gemini…"):
            result = fetch_ai_valuation(ticker, price, currency)
        if result:
            st.session_state[cache_key] = result
            cached = result
        else:
            st.error("No se pudo generar la valoración. Revisa la API key o inténtalo de nuevo.")

    if cached:
        paragraphs = [p.strip() for p in cached.split("\n") if p.strip()]
        html_body  = "".join(
            f'<p style="margin:0 0 0.75rem 0;font-size:0.85rem;color:#1e293b;line-height:1.8;">{p}</p>'
            for p in paragraphs
        )
        st.markdown(
            '<div class="metric-card" style="border-left:4px solid #0284c7;">'
            f'{html_body}'
            '<div style="font-size:0.67rem;color:#94a3b8;margin-top:0.4rem;">'
            f'Generado por Gemini ({GEMINI_MODEL}) a partir de su conocimiento general — '
            'no consulta datos de mercado en tiempo real más allá del precio indicado. '
            'No constituye asesoramiento financiero.</div>'
            '</div>',
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            '<div style="font-size:0.78rem;color:#94a3b8;padding:0.4rem 0;">'
            'Pulsa el botón para generar una valoración cualitativa con IA de esta empresa.</div>',
            unsafe_allow_html=True
        )
