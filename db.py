"""
db.py — v1.0
Cliente único de Supabase para toda la app + capa de caché persistente
(market_data_cache) con TTL por tipo de dato.

Todas las tablas están definidas en schema_supabase.sql:
  favorites, competitors, analyses_history, portfolio_positions,
  paper_trades, market_data_cache
"""

import streamlit as st
from datetime import datetime, timezone
from supabase import create_client, Client


# ─────────────────────────────────────────────────────────────────────────────
# CLIENTE (una sola instancia por sesión de servidor, vía st.cache_resource)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_resource(show_spinner=False)
def get_client() -> Client:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)


# ─────────────────────────────────────────────────────────────────────────────
# CACHÉ DE MERCADO — market_data_cache (ticker, data_type) -> payload jsonb
# ─────────────────────────────────────────────────────────────────────────────

# TTL en minutos por tipo de dato (acordado previamente)
CACHE_TTL_MINUTES = {
    "quote":             15,
    "technical":         60,
    "historical_prices": 24 * 60,
    "company_info":      24 * 60,
    "fundamentals":      48 * 60,
    "sec_data":          48 * 60,
    "short_interest":    24 * 60,
}
_DEFAULT_TTL = 60


def cache_get(ticker: str, data_type: str) -> dict | None:
    """
    Devuelve el payload cacheado si existe y no ha caducado según su TTL.
    Devuelve None si no hay dato o está caducado (el llamador debe
    entonces pedirlo a la API real y guardarlo con cache_set).
    """
    ticker = ticker.upper().strip()
    try:
        client = get_client()
        res = (
            client.table("market_data_cache")
            .select("payload, fetched_at")
            .eq("ticker", ticker)
            .eq("data_type", data_type)
            .limit(1)
            .execute()
        )
        if not res.data:
            return None

        row = res.data[0]
        fetched_at = datetime.fromisoformat(row["fetched_at"].replace("Z", "+00:00"))
        ttl_min = CACHE_TTL_MINUTES.get(data_type, _DEFAULT_TTL)
        age_min = (datetime.now(timezone.utc) - fetched_at).total_seconds() / 60

        if age_min > ttl_min:
            return None  # caducado

        return row["payload"]
    except Exception as e:
        print(f"[db.cache_get] Error ({ticker}/{data_type}): {e}")
        return None  # ante cualquier fallo, se comporta como "no hay caché"


def cache_set(ticker: str, data_type: str, payload: dict):
    """Guarda/actualiza (upsert) el payload en la caché."""
    ticker = ticker.upper().strip()
    try:
        client = get_client()
        client.table("market_data_cache").upsert({
            "ticker":     ticker,
            "data_type":  data_type,
            "payload":    payload,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        print(f"[db.cache_set] Error ({ticker}/{data_type}): {e}")


# ─────────────────────────────────────────────────────────────────────────────
# VERIFICACIÓN DE CONEXIÓN Y ESQUEMA
# ─────────────────────────────────────────────────────────────────────────────

_EXPECTED_TABLES = [
    "favorites",
    "competitors",
    "analyses_history",
    "portfolio_positions",
    "paper_trades",
    "market_data_cache",
]


def check_connection() -> dict:
    """
    Comprueba que las credenciales son válidas y que las 6 tablas
    esperadas existen y son consultables. Pensado para llamarse una vez
    de forma temporal (p.ej. desde un botón de debug en app.py) y quitarlo
    después.

    Devuelve: {"ok": bool, "tables": {nombre: "OK (N filas)" | "ERROR: ..."}}
    """
    result = {"ok": True, "tables": {}}
    try:
        client = get_client()
    except Exception as e:
        return {"ok": False, "tables": {}, "connection_error": str(e)}

    for table in _EXPECTED_TABLES:
        try:
            res = client.table(table).select("*", count="exact").limit(1).execute()
            n = res.count if res.count is not None else len(res.data)
            result["tables"][table] = f"OK ({n} filas)"
        except Exception as e:
            result["ok"] = False
            result["tables"][table] = f"ERROR: {e}"

    return result
