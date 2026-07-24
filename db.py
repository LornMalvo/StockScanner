"""
db.py — v1.0
Cliente único de Supabase para toda la app + capa de caché persistente
(market_data_cache) con TTL por tipo de dato.

Todas las tablas están definidas en schema_supabase.sql:
  favorites, competitors, analyses_history, portfolio_positions,
  paper_trades, market_data_cache
"""

import streamlit as st
import math
from datetime import datetime, timezone, date, timedelta
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

# TTL en minutos por tipo de dato, uno por cada función pesada de
# data_fetcher.py que engancha la caché. "yahoo_data" incluye precio en
# vivo mezclado con fundamentales, así que su TTL es corto pese a cargar
# datos pesados — es el compromiso de cachear la función tal cual está
# estructurada hoy, en vez de trocearla en piezas más finas.
CACHE_TTL_MINUTES = {
    "yahoo_data":     24 * 60,   # fundamentales — el precio ya no depende de este TTL, se sirve siempre en vivo
    "technical":       60,
    "balance_sheet":  48 * 60,
    "sec_data":       48 * 60,
}
_DEFAULT_TTL = 60


def _json_safe(obj):
    """
    Convierte recursivamente tipos no serializables en JSON estándar
    (numpy.float64/int64, NaN, pandas Timestamp, date/datetime) a tipos
    nativos de Python. Necesario porque yfinance devuelve objetos numpy/
    pandas dentro de los diccionarios que queremos guardar como jsonb.
    """
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, (str, int, bool)):
        return obj
    # numpy escalares, pandas Timestamp, Decimal, etc. — todos exponen
    # .item() o son convertibles a través de str()/float() de forma segura
    if hasattr(obj, "item"):
        try:
            return _json_safe(obj.item())
        except Exception:
            pass
    if hasattr(obj, "isoformat"):
        try:
            return obj.isoformat()
        except Exception:
            pass
    try:
        return float(obj) if "." in str(obj) else str(obj)
    except Exception:
        return str(obj)


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
            "payload":    _json_safe(payload),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        print(f"[db.cache_set] Error ({ticker}/{data_type}): {e}")


# ─────────────────────────────────────────────────────────────────────────────
# FAVORITOS — tabla favorites (ticker PK)
# ─────────────────────────────────────────────────────────────────────────────

def favorites_get_all() -> dict:
    """Devuelve {ticker: {name, sector, added_date}}, mismo shape que el JSON anterior."""
    try:
        client = get_client()
        res = client.table("favorites").select("*").execute()
        return {
            row["ticker"]: {
                "name":       row.get("name") or "",
                "sector":     row.get("sector") or "",
                "added_date": (row.get("added_at") or "")[:16].replace("T", " ") + " UTC" if row.get("added_at") else "",
            }
            for row in (res.data or [])
        }
    except Exception as e:
        print(f"[db.favorites_get_all] Error: {e}")
        return {}


def favorites_is_favorite(ticker: str) -> bool:
    ticker = ticker.upper().strip()
    try:
        client = get_client()
        res = client.table("favorites").select("ticker").eq("ticker", ticker).limit(1).execute()
        return bool(res.data)
    except Exception as e:
        print(f"[db.favorites_is_favorite] Error: {e}")
        return False


def favorites_add(ticker: str, name: str = "", sector: str = ""):
    ticker = ticker.upper().strip()
    try:
        client = get_client()
        client.table("favorites").upsert({
            "ticker": ticker,
            "name":   name,
            "sector": sector,
        }).execute()
    except Exception as e:
        print(f"[db.favorites_add] Error: {e}")


def favorites_remove(ticker: str):
    ticker = ticker.upper().strip()
    try:
        client = get_client()
        client.table("favorites").delete().eq("ticker", ticker).execute()
    except Exception as e:
        print(f"[db.favorites_remove] Error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# COMPETIDORES — tabla competitors, bidireccional (ticker_a < ticker_b, par único)
# ─────────────────────────────────────────────────────────────────────────────

def competitors_get_for(ticker: str) -> list:
    """
    Devuelve la lista de tickers competidores de 'ticker', combinando ambos
    lados del par (ticker_a y ticker_b) — así AVGO→MRVL también hace que
    MRVL vea a AVGO como competidor, sin tener que añadirlo dos veces.
    """
    ticker = ticker.upper().strip()
    try:
        client = get_client()
        res_a = client.table("competitors").select("ticker_b").eq("ticker_a", ticker).execute()
        res_b = client.table("competitors").select("ticker_a").eq("ticker_b", ticker).execute()
        out = [r["ticker_b"] for r in (res_a.data or [])] + [r["ticker_a"] for r in (res_b.data or [])]
        return sorted(set(out))
    except Exception as e:
        print(f"[db.competitors_get_for] Error: {e}")
        return []


def competitors_add(ticker: str, competitor: str) -> bool:
    """Añade el par (orden alfabético forzado). Devuelve False si ya existía o es inválido."""
    ticker     = ticker.upper().strip()
    competitor = competitor.upper().strip()
    if not competitor or competitor == ticker:
        return False
    a, b = sorted([ticker, competitor])
    try:
        client = get_client()
        existing = (
            client.table("competitors").select("id")
            .eq("ticker_a", a).eq("ticker_b", b).limit(1).execute()
        )
        if existing.data:
            return False
        client.table("competitors").insert({"ticker_a": a, "ticker_b": b}).execute()
        return True
    except Exception as e:
        print(f"[db.competitors_add] Error: {e}")
        return False


def competitors_remove(ticker: str, competitor: str):
    """Elimina el par, sea cual sea el orden en que se pasen los tickers."""
    ticker     = ticker.upper().strip()
    competitor = competitor.upper().strip()
    a, b = sorted([ticker, competitor])
    try:
        client = get_client()
        client.table("competitors").delete().eq("ticker_a", a).eq("ticker_b", b).execute()
    except Exception as e:
        print(f"[db.competitors_remove] Error: {e}")


def cache_clear_expired(max_age_hours: int = 72):
    """
    Borra de market_data_cache filas más viejas que max_age_hours.
    No es estrictamente necesario (cache_get ya ignora lo caducado), pero
    evita que la tabla crezca indefinidamente. Llamar ocasionalmente
    (p.ej. desde un botón manual), no en cada carga de página.
    """
    try:
        client = get_client()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        client.table("market_data_cache").delete().lt("fetched_at", cutoff.isoformat()).execute()
    except Exception as e:
        print(f"[db.cache_clear_expired] Error: {e}")


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
