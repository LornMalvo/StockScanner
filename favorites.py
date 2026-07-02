"""
favorites.py — v1.0
Gestión de empresas favoritas con persistencia en archivo JSON local.
Mismo patrón de almacenamiento que competitors_store.json: persiste entre
recargas de página mientras el contenedor de Streamlit Cloud no se
redespliegue (no sobrevive a un nuevo deploy del código).
"""

import streamlit as st
import json
import os
from datetime import datetime, timezone

_FAVORITES_FILE = "/tmp/favorites_store.json"


def _load_favorites() -> dict:
    """Carga el diccionario completo de favoritos {ticker: {name, sector, added_date}}."""
    if os.path.exists(_FAVORITES_FILE):
        try:
            with open(_FAVORITES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_favorites(store: dict):
    try:
        with open(_FAVORITES_FILE, "w", encoding="utf-8") as f:
            json.dump(store, f, indent=2)
    except Exception as e:
        print(f"[Favorites] Error al guardar: {e}")


def is_favorite(ticker: str) -> bool:
    ticker = ticker.upper().strip()
    return ticker in _load_favorites()


def add_favorite(ticker: str, company_name: str = "", sector: str = ""):
    ticker = ticker.upper().strip()
    store = _load_favorites()
    store[ticker] = {
        "name":       company_name,
        "sector":     sector,
        "added_date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }
    _save_favorites(store)


def remove_favorite(ticker: str):
    ticker = ticker.upper().strip()
    store = _load_favorites()
    store.pop(ticker, None)
    _save_favorites(store)


def get_all_favorites() -> dict:
    return _load_favorites()


def render_favorite_star(ticker: str, company_name: str, sector: str):
    """
    Icono de estrella (sin texto) para marcar/desmarcar una empresa como
    favorita. Se rellena en amarillo cuando está marcada. Se coloca junto
    al ticker/nombre en la cabecera del análisis.

    El estilo (tamaño, color, sin fondo de botón) se aplica globalmente
    en app.py mediante selectores CSS `button[aria-label="★"]` /
    `button[aria-label="☆"]`, ya que Streamlit asigna el texto visible
    del botón como aria-label — mucho más fiable que intentar aislar un
    botón concreto con trucos de posición en el DOM.
    """
    ticker = ticker.upper().strip()
    fav = is_favorite(ticker)
    star_char = "★" if fav else "☆"

    if st.button(star_char, key=f"fav_btn_{ticker}",
                 help="Quitar de favoritos" if fav else "Añadir a favoritos"):
        if fav:
            remove_favorite(ticker)
            st.toast(f"{ticker} eliminado de favoritos", icon="⭐")
        else:
            add_favorite(ticker, company_name, sector)
            st.toast(f"{ticker} añadido a favoritos", icon="⭐")
        st.rerun()


def render_favorites_tab():
    """Pestaña completa de gestión de favoritos."""
    st.markdown("""
    <div style="font-size:0.82rem;color:#64748b;margin-bottom:1rem;">
    Empresas marcadas como favoritas. Guardadas de forma persistente para
    accederlas rápidamente sin tener que volver a escribir el ticker.
    </div>
    """, unsafe_allow_html=True)

    favorites = get_all_favorites()

    if not favorites:
        st.markdown(
            '<div style="text-align:center;padding:2.5rem;color:#64748b;">'
            '☆ Todavía no tienes empresas en favoritos.<br>'
            '<span style="font-size:0.8rem;">Pulsa la estrella junto al nombre de la empresa '
            'en la pestaña de Análisis para añadirla aquí.</span></div>',
            unsafe_allow_html=True
        )
        return

    st.markdown(
        f'<div style="font-size:0.7rem;color:#0284c7;text-transform:uppercase;'
        f'letter-spacing:0.1em;margin-bottom:0.8rem;">{len(favorites)} EMPRESAS EN FAVORITOS</div>',
        unsafe_allow_html=True
    )

    for ticker, info in sorted(favorites.items()):
        name    = info.get("name", "") or ""
        sector  = info.get("sector", "") or ""
        added   = info.get("added_date", "")

        col1, col2, col3 = st.columns([3, 2, 1])
        with col1:
            st.markdown(
                f'<div style="padding:0.6rem 0;">'
                f'<span style="font-family:\'IBM Plex Mono\',monospace;font-weight:700;'
                f'color:#0284c7;font-size:1rem;"><span style="color:#eab308;">★</span> {ticker}</span>'
                f'<span style="color:#1e293b;margin-left:0.6rem;">{name}</span>'
                f'<div style="font-size:0.72rem;color:#94a3b8;margin-top:0.1rem;">'
                f'{sector} · Añadido: {added}</div>'
                f'</div>',
                unsafe_allow_html=True
            )
        with col2:
            if st.button(f"📊 Analizar {ticker}", key=f"fav_analyze_{ticker}", use_container_width=True):
                st.session_state["_jump_to_analysis"] = ticker
                st.rerun()
        with col3:
            if st.button("✕", key=f"fav_remove_{ticker}", use_container_width=True):
                remove_favorite(ticker)
                st.rerun()

        st.markdown('<hr style="margin:0.3rem 0;border-color:#e2e8f0;">', unsafe_allow_html=True)
