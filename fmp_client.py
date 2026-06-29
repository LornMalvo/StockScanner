"""
fmp_client.py — v2.1
Cliente para la API Stable de Financial Modeling Prep (FMP).
Base URL: https://financialmodelingprep.com/stable/
Documentación: https://site.financialmodelingprep.com/developer/docs

Fuente primaria de fundamentales: sustituye SEC EDGAR directa.
Yahoo Finance se mantiene para: precio, ratios de mercado, técnico, TTM trimestral.
"""

import requests
import streamlit as st
import os
from datetime import datetime, timezone

FMP_BASE  = "https://financialmodelingprep.com/stable"
TIMEOUT   = 20
STALE_FMP = 100   # días antes de marcar como desfasado


# ─────────────────────────────────────────────────────────────────────────────
# API KEY
# ─────────────────────────────────────────────────────────────────────────────

def _get_fmp_key() -> str:
    """
    Lee la FMP API key desde st.secrets o variable de entorno.
    Streamlit secrets se accede con st.secrets["KEY"], no con .get().
    """
    # Método 1: Streamlit secrets (Streamlit Cloud)
    try:
        return str(st.secrets["FMP_API_KEY"]).strip()
    except Exception:
        pass
    # Método 2: Variable de entorno (ejecución local)
    key = os.environ.get("FMP_API_KEY", "").strip()
    if key:
        return key
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# HTTP helper
# ─────────────────────────────────────────────────────────────────────────────

def _get(endpoint: str, params: dict | None = None) -> list | dict | None:
    """
    Llamada GET a la API Stable de FMP.
    Devuelve el JSON parseado o None si hay error.
    """
    key = _get_fmp_key()
    if not key:
        print("[FMP] Sin API key — configura FMP_API_KEY en Streamlit Secrets")
        return None

    url    = f"{FMP_BASE}/{endpoint}"
    params = params or {}
    params["apikey"] = key

    try:
        r = requests.get(url, params=params, timeout=TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            # FMP devuelve lista vacía o dict con error
            if isinstance(data, dict) and "Error Message" in data:
                print(f"[FMP] Error en {endpoint}: {data['Error Message']}")
                return None
            return data
        elif r.status_code == 401:
            print(f"[FMP] API key inválida o sin permisos para {endpoint}")
        elif r.status_code == 429:
            print(f"[FMP] Límite de llamadas alcanzado ({endpoint})")
        else:
            print(f"[FMP] HTTP {r.status_code} en {endpoint}")
        return None
    except Exception as e:
        print(f"[FMP] Excepción en {endpoint}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de fecha
# ─────────────────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)

def _days_since(date_str: str) -> int | None:
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return (_now() - dt).days
    except Exception:
        return None

def _freshness(days: int | None) -> dict:
    if days is None:
        return {"ok": None, "label": "Fecha desconocida", "color": "#64748b", "icon": "⚪"}
    if days <= STALE_FMP:
        return {"ok": True,  "label": f"Actualizado hace {days}d",            "color": "#6ee7b7", "icon": "✅"}
    elif days <= STALE_FMP * 1.5:
        return {"ok": False, "label": f"⚠ Hace {days}d (puede estar desfasado)", "color": "#fbbf24", "icon": "⚠️"}
    else:
        return {"ok": False, "label": f"🚨 Hace {days}d — DATO DESFASADO",    "color": "#fca5a5", "icon": "🚨"}

def _fmt_date(date_str: str) -> str:
    return date_str[:10] if date_str else "N/A"


# ─────────────────────────────────────────────────────────────────────────────
# 1. PERFIL DE EMPRESA
# ─────────────────────────────────────────────────────────────────────────────

def diagnose_fmp_connection() -> dict:
    """
    Diagnóstico completo de la conexión FMP.
    Devuelve estado de la key y un test real a la API.
    """
    result = {
        "key_found":     False,
        "key_source":    "ninguna",
        "key_preview":   "",
        "api_reachable": False,
        "api_status":    "",
        "error":         "",
    }

    key = _get_fmp_key()
    if not key:
        try:
            available = list(st.secrets.keys()) if hasattr(st, 'secrets') else []
            result["error"] = f"FMP_API_KEY no encontrada. Secrets disponibles: {available}"
        except Exception as e:
            result["error"] = f"FMP_API_KEY no encontrada. Error al leer secrets: {e}"
        return result

    result["key_found"]   = True
    result["key_preview"] = key[:6] + "..." + key[-4:] if len(key) > 10 else "***"

    try:
        st.secrets["FMP_API_KEY"]
        result["key_source"] = "Streamlit Secrets"
    except Exception:
        result["key_source"] = "Variable de entorno"

    # Test real
    try:
        r = requests.get(
            f"{FMP_BASE}/profile",
            params={"symbol": "AAPL", "apikey": key},
            timeout=10
        )
        result["api_status"] = f"HTTP {r.status_code}"
        if r.status_code == 200:
            data = r.json()
            if data and isinstance(data, list) and data[0].get("companyName"):
                result["api_reachable"] = True
            else:
                result["error"] = f"Respuesta inesperada: {str(data)[:200]}"
        elif r.status_code == 401:
            result["error"] = "API key inválida (HTTP 401)"
        elif r.status_code == 403:
            result["error"] = "Acceso denegado — endpoint no disponible en tu plan (HTTP 403)"
        else:
            result["error"] = f"Error HTTP {r.status_code}: {r.text[:200]}"
    except Exception as e:
        result["error"] = f"No se pudo conectar: {e}"

    return result


def fetch_fmp_profile(ticker: str) -> dict | None:
    """
    Perfil completo: nombre, sector, descripción, CEO, empleados, imagen.
    Endpoint: /stable/profile?symbol=TICKER
    """
    data = _get("profile", {"symbol": ticker})
    if not data or not isinstance(data, list) or not data[0]:
        return None

    p = data[0]
    return {
        "name":        p.get("companyName", ticker),
        "sector":      p.get("sector", ""),
        "industry":    p.get("industry", ""),
        "description": p.get("description", ""),
        "ceo":         p.get("ceo", ""),
        "employees":   p.get("fullTimeEmployees"),
        "website":     p.get("website", ""),
        "country":     p.get("country", ""),
        "image":       p.get("image", ""),
        "ipo_date":    p.get("ipoDate", ""),
        "exchange":    p.get("exchangeFullName", ""),
        "currency":    p.get("currency", "USD"),
        "cik":         p.get("cik", ""),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. INCOME STATEMENT ANUAL (últimos 5 años)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_fmp_income(ticker: str, limit: int = 5) -> dict | None:
    """
    Income statements anuales normalizados desde filings SEC (10-K).
    Endpoint: /stable/income-statement?symbol=TICKER&period=FY&limit=5

    Devuelve:
      - latest:        datos del último año fiscal
      - history:       lista de todos los años para tendencia
      - yoy_revenue:   crecimiento YoY de ingresos (%)
      - yoy_netincome: crecimiento YoY de beneficio neto (%)
      - filing_date:   fecha de presentación del último 10-K
      - meta:          metadatos de frescura
    """
    data = _get("income-statement", {"symbol": ticker, "period": "FY", "limit": limit})
    if not data or not isinstance(data, list) or not data[0]:
        return None

    latest = data[0]

    # YoY (último año vs anterior)
    yoy_rev = yoy_ni = None
    if len(data) >= 2:
        prev = data[1]
        rev0 = latest.get("revenue") or 0
        rev1 = prev.get("revenue")   or 0
        ni0  = latest.get("netIncome") or 0
        ni1  = prev.get("netIncome")   or 0
        if rev1:  yoy_rev = (rev0 - rev1) / abs(rev1) * 100
        if ni1:   yoy_ni  = (ni0  - ni1)  / abs(ni1)  * 100

    # Historial para gráfico de tendencia (orden cronológico)
    history = list(reversed(data))

    # Metadatos de frescura
    filing_date   = latest.get("filingDate", "")
    accepted_date = latest.get("acceptedDate", "")
    fiscal_date   = latest.get("date", "")
    days_filing   = _days_since(filing_date)
    fresh         = _freshness(days_filing)

    return {
        # Datos del último año fiscal
        "fiscal_date":    _fmt_date(fiscal_date),
        "fiscal_year":    latest.get("fiscalYear", ""),
        "filing_date":    _fmt_date(filing_date),
        "accepted_date":  _fmt_date(accepted_date),
        "currency":       latest.get("reportedCurrency", "USD"),
        "cik":            latest.get("cik", ""),

        # P&L
        "revenue":            latest.get("revenue"),
        "gross_profit":       latest.get("grossProfit"),
        "operating_income":   latest.get("operatingIncome"),
        "ebitda":             latest.get("ebitda"),
        "net_income":         latest.get("netIncome"),
        "eps":                latest.get("eps"),
        "eps_diluted":        latest.get("epsDiluted"),

        # Márgenes calculados
        "gross_margin":   (latest.get("grossProfit",0) / latest["revenue"] * 100)
                          if latest.get("revenue") else None,
        "op_margin":      (latest.get("operatingIncome",0) / latest["revenue"] * 100)
                          if latest.get("revenue") else None,
        "net_margin":     (latest.get("netIncome",0) / latest["revenue"] * 100)
                          if latest.get("revenue") else None,
        "ebitda_margin":  (latest.get("ebitda",0) / latest["revenue"] * 100)
                          if latest.get("revenue") else None,

        # Gastos relevantes
        "rd_expenses":    latest.get("researchAndDevelopmentExpenses"),
        "sga_expenses":   latest.get("sellingGeneralAndAdministrativeExpenses"),
        "da":             latest.get("depreciationAndAmortization"),

        # Crecimiento YoY (FMP oficial, no calculado por app)
        "yoy_revenue":    yoy_rev,
        "yoy_net_income": yoy_ni,

        # Historial completo
        "history": [
            {
                "date":       h.get("date","")[:10],
                "fiscal_year":h.get("fiscalYear",""),
                "revenue":    h.get("revenue"),
                "net_income": h.get("netIncome"),
                "ebitda":     h.get("ebitda"),
                "op_income":  h.get("operatingIncome"),
                "eps":        h.get("eps"),
            }
            for h in history
        ],

        # Metadatos
        "meta": {
            "source":       f"FMP — Income Statement (10-K) · Filing: {_fmt_date(filing_date)}",
            "filing_date":  _fmt_date(filing_date),
            "fiscal_date":  _fmt_date(fiscal_date),
            "days_old":     days_filing,
            "freshness":    fresh,
            "trust":        {"icon":"🟢","label":"FMP / SEC 10-K","color":"#6ee7b7"},
            "n_years":      len(data),
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. KEY METRICS TTM
# ─────────────────────────────────────────────────────────────────────────────

def fetch_fmp_key_metrics(ticker: str) -> dict | None:
    """
    Métricas clave TTM calculadas por FMP a partir de filings reales.
    Incluye Graham Number, ROIC, FCF yield, EV ratios, etc.
    Endpoint: /stable/key-metrics-ttm?symbol=TICKER
    """
    data = _get("key-metrics-ttm", {"symbol": ticker})
    if not data or not isinstance(data, list) or not data[0]:
        return None

    m = data[0]
    return {
        # Valoración
        "market_cap":         m.get("marketCap"),
        "ev":                 m.get("enterpriseValueTTM"),
        "ev_to_sales":        m.get("evToSalesTTM"),
        "ev_to_ebitda":       m.get("evToEBITDATTM"),
        "ev_to_fcf":          m.get("evToFreeCashFlowTTM"),
        "ev_to_op_cf":        m.get("evToOperatingCashFlowTTM"),
        "earnings_yield":     (m.get("earningsYieldTTM") or 0) * 100,
        "fcf_yield":          (m.get("freeCashFlowYieldTTM") or 0) * 100,

        # Calidad
        "graham_number":      m.get("grahamNumberTTM"),
        "income_quality":     m.get("incomeQualityTTM"),  # FCF/NetIncome, >1 = buena calidad
        "net_debt_to_ebitda": m.get("netDebtToEBITDATTM"),

        # Rentabilidad
        "roe":                (m.get("returnOnEquityTTM") or 0) * 100,
        "roa":                (m.get("returnOnAssetsTTM") or 0) * 100,
        "roic":               (m.get("returnOnInvestedCapitalTTM") or 0) * 100,
        "roce":               (m.get("returnOnCapitalEmployedTTM") or 0) * 100,

        # Balance / liquidez
        "current_ratio":      m.get("currentRatioTTM"),
        "working_capital":    m.get("workingCapitalTTM"),

        # Capex
        "capex_to_revenue":   (m.get("capexToRevenueTTM") or 0) * 100,
        "capex_to_ocf":       (m.get("capexToOperatingCashFlowTTM") or 0) * 100,
        "rd_to_revenue":      (m.get("researchAndDevelopementToRevenueTTM") or 0) * 100,

        # Cash conversion
        "days_receivable":    m.get("daysOfSalesOutstandingTTM"),
        "days_payable":       m.get("daysOfPayablesOutstandingTTM"),
        "days_inventory":     m.get("daysOfInventoryOutstandingTTM"),
        "cash_conv_cycle":    m.get("cashConversionCycleTTM"),

        # FCF absoluto
        "fcf_to_equity":      m.get("freeCashFlowToEquityTTM"),
        "fcf_to_firm":        m.get("freeCashFlowToFirmTTM"),

        "meta": {
            "source": "FMP Key Metrics TTM",
            "trust":  {"icon":"🟢","label":"FMP / SEC filing","color":"#6ee7b7"},
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. FUNCIÓN PRINCIPAL: fetch_fmp_data
# ─────────────────────────────────────────────────────────────────────────────

def fetch_fmp_data(ticker: str) -> dict | None:
    """
    Obtiene todos los datos de FMP para un ticker:
      - Perfil (sector, descripción, CEO, empleados)
      - Income statement anual (últimos 5 años)
      - Key metrics TTM

    Devuelve un dict unificado o None si FMP no está disponible.
    """
    key = _get_fmp_key()
    if not key:
        return None

    profile    = fetch_fmp_profile(ticker)
    income     = fetch_fmp_income(ticker)
    key_metrics= fetch_fmp_key_metrics(ticker)

    if not profile and not income:
        return None

    return {
        "available":   True,
        "ticker":      ticker.upper(),
        "profile":     profile     or {},
        "income":      income      or {},
        "key_metrics": key_metrics or {},
        "fetch_time":  _now().strftime("%Y-%m-%d %H:%M UTC"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5. VERIFICACIÓN CRUZADA FMP vs Yahoo
# ─────────────────────────────────────────────────────────────────────────────

def verify_fmp_vs_yahoo(fmp: dict, yahoo: dict) -> dict:
    """
    Compara ingresos TTM de FMP (anual) vs Yahoo Finance.
    Nota: FMP da datos anuales (FY), Yahoo da TTM trimestral.
    La diferencia esperada puede ser de hasta un 5% por desfase temporal.
    """
    if not fmp or not yahoo:
        return {"status": "NO_DATA"}

    fmp_rev   = (fmp.get("income") or {}).get("revenue")
    yahoo_rev = yahoo.get("ttm_revenue") or yahoo.get("market_cap")

    if not fmp_rev or not yahoo_rev:
        return {"status": "NO_DATA"}

    # Comparar ingresos anuales FMP vs TTM Yahoo
    fmp_rev   = float(fmp_rev)
    yahoo_rev = float(yahoo_rev)
    diff      = abs(fmp_rev - yahoo_rev)
    base      = max(fmp_rev, yahoo_rev)
    pct       = (diff / base * 100) if base else 0

    # FMP es anual (FY), Yahoo es TTM → diferencia de hasta 5% es normal
    if pct < 5:    status = "OK"
    elif pct < 15: status = "WARN"
    else:          status = "ERROR"

    return {
        "status":    status,
        "fmp_rev":   fmp_rev,
        "yahoo_rev": yahoo_rev,
        "diff":      diff,
        "pct":       round(pct, 2),
        "note":      "FMP = ingresos anuales (10-K) · Yahoo = TTM trimestral. Diferencia de hasta 5% es normal.",
    }
