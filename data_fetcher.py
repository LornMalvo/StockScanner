"""
data_fetcher.py
Obtiene datos de Yahoo Finance (yfinance) y SEC EDGAR.
"""

import re
import requests
import yfinance as yf


# ─────────────────────────────────────────────────────────────
# YAHOO FINANCE
# ─────────────────────────────────────────────────────────────

def fetch_yahoo_data(ticker: str) -> dict | None:
    """Devuelve un dict con todos los datos de Yahoo Finance, o None si falla."""
    try:
        t = yf.Ticker(ticker)
        info = t.info

        # Validación mínima
        if not info or info.get("regularMarketPrice") is None and info.get("currentPrice") is None:
            return None

        price = info.get("currentPrice") or info.get("regularMarketPrice") or 0

        # TTM trimestral desde Yahoo
        financials = t.quarterly_financials
        ttm_quarters = []
        if financials is not None and not financials.empty:
            rev_row = None
            for label in ["Total Revenue", "Revenue"]:
                if label in financials.index:
                    rev_row = financials.loc[label]
                    break
            if rev_row is not None:
                for i, (date, val) in enumerate(rev_row.items()):
                    if i >= 4:
                        break
                    ttm_quarters.append({"date": str(date)[:10], "value": val})

        # Net Income TTM
        net_income_q = []
        income_stmt = t.quarterly_income_stmt
        if income_stmt is not None and not income_stmt.empty:
            ni_row = None
            for label in ["Net Income", "Net Income Common Stockholders"]:
                if label in income_stmt.index:
                    ni_row = income_stmt.loc[label]
                    break
            if ni_row is not None:
                for i, (date, val) in enumerate(ni_row.items()):
                    if i >= 4:
                        break
                    net_income_q.append({"date": str(date)[:10], "value": val})

        ttm_revenue = sum(q["value"] for q in ttm_quarters if q["value"] == q["value"])
        ttm_net_income = sum(q["value"] for q in net_income_q if q["value"] == q["value"])

        # Crecimiento YoY desde Yahoo
        rev_annual = t.financials
        revenue_yoy = None
        if rev_annual is not None and not rev_annual.empty:
            for label in ["Total Revenue", "Revenue"]:
                if label in rev_annual.index:
                    vals = rev_annual.loc[label].dropna().values
                    if len(vals) >= 2:
                        revenue_yoy = (vals[0] - vals[1]) / abs(vals[1]) * 100
                    break

        ni_annual = t.income_stmt
        earnings_yoy = None
        if ni_annual is not None and not ni_annual.empty:
            for label in ["Net Income", "Net Income Common Stockholders"]:
                if label in ni_annual.index:
                    vals = ni_annual.loc[label].dropna().values
                    if len(vals) >= 2:
                        earnings_yoy = (vals[0] - vals[1]) / abs(vals[1]) * 100
                    break

        return {
            # Identificación
            "company_name": info.get("longName") or info.get("shortName", ticker),
            "sector":        info.get("sector", "N/A"),
            "currency":      info.get("currency", "USD"),
            "exchange":      info.get("exchange", "N/A"),

            # Mercado y consenso
            "price":              price,
            "target_mean":        info.get("targetMeanPrice"),
            "target_low":         info.get("targetLowPrice"),
            "target_high":        info.get("targetHighPrice"),
            "recommendation":     info.get("recommendationKey", "N/A").upper(),
            "analyst_count":      info.get("numberOfAnalystOpinions"),

            # Valoración
            "pe_trailing":   info.get("trailingPE"),
            "pe_forward":    info.get("forwardPE"),
            "peg_ratio":     info.get("pegRatio"),
            "price_sales":   info.get("priceToSalesTrailing12Months"),
            "price_book":    info.get("priceToBook"),
            "ev_revenue":    info.get("enterpriseToRevenue"),
            "ev_ebitda":     info.get("enterpriseToEbitda"),

            # Rentabilidad
            "profit_margin":    info.get("profitMargins"),
            "operating_margin": info.get("operatingMargins"),
            "ebitda_margin":    (info.get("ebitda") / ttm_revenue) if ttm_revenue else None,
            "roe":              info.get("returnOnEquity"),
            "roa":              info.get("returnOnAssets"),

            # Balance
            "total_cash":     info.get("totalCash"),
            "total_debt":     info.get("totalDebt"),
            "debt_equity":    info.get("debtToEquity"),
            "current_ratio":  info.get("currentRatio"),
            "free_cash_flow": info.get("freeCashflow"),
            "operating_cf":   info.get("operatingCashflow"),

            # Crecimiento
            "revenue_yoy":   revenue_yoy if revenue_yoy is not None else (info.get("revenueGrowth", 0) * 100 if info.get("revenueGrowth") else None),
            "earnings_yoy":  earnings_yoy if earnings_yoy is not None else (info.get("earningsGrowth", 0) * 100 if info.get("earningsGrowth") else None),

            # Dividendos
            "dividend_yield": info.get("dividendYield"),
            "dividend_rate":  info.get("dividendRate"),

            # Short
            "short_ratio": info.get("shortRatio"),

            # EPS
            "eps_ttm":         info.get("trailingEps"),
            "eps_forward":     info.get("forwardEps"),
            "market_cap":      info.get("marketCap"),
            "enterprise_value":info.get("enterpriseValue"),
            "beta":            info.get("beta"),
            "52w_high":        info.get("fiftyTwoWeekHigh"),
            "52w_low":         info.get("fiftyTwoWeekLow"),

            # TTM trimestral
            "ttm_quarters":     ttm_quarters,
            "ttm_revenue":      ttm_revenue,
            "ttm_net_income":   ttm_net_income,
            "net_income_q":     net_income_q,

            # Raw
            "ebitda": info.get("ebitda"),
        }

    except Exception as e:
        print(f"[Yahoo] Error: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# SEC EDGAR
# ─────────────────────────────────────────────────────────────

SEC_HEADERS = {"User-Agent": "AnalisisFundamental contacto@ejemplo.com"}

def _get_cik(ticker: str) -> str | None:
    """Devuelve el CIK de SEC para un ticker."""
    url = "https://efts.sec.gov/LATEST/search-index?q=%22{}%22&dateRange=custom&startdt=2020-01-01&forms=10-K".format(ticker)
    # Método más fiable: ticker→CIK mapping
    map_url = "https://www.sec.gov/files/company_tickers.json"
    try:
        r = requests.get(map_url, headers=SEC_HEADERS, timeout=10)
        data = r.json()
        for entry in data.values():
            if entry.get("ticker", "").upper() == ticker.upper():
                return str(entry["cik_str"]).zfill(10)
    except Exception as e:
        print(f"[SEC CIK] Error: {e}")
    return None


def _get_concept(cik: str, concept: str, unit: str = "USD") -> list:
    """Obtiene una serie de datos del SEC EDGAR concept API."""
    url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{concept}.json"
    try:
        r = requests.get(url, headers=SEC_HEADERS, timeout=15)
        if r.status_code != 200:
            return []
        data = r.json()
        units = data.get("units", {}).get(unit, [])
        # Solo 10-Q y 10-K, forma instantánea o duración
        quarterly = [u for u in units if u.get("form") in ("10-Q", "10-K") and u.get("frame") is None]
        # Ordenar por fecha de fin
        quarterly.sort(key=lambda x: x.get("end", ""), reverse=True)
        return quarterly
    except Exception as e:
        print(f"[SEC concept {concept}] Error: {e}")
        return []


def _last_4_quarters(series: list) -> list:
    """
    De una serie SEC, extrae los 4 últimos trimestres estancos
    (reportes con exactamente ~91 días de duración, form 10-Q o 10-K).
    """
    quarterly = []
    seen_ends = set()
    for item in series:
        start = item.get("start", "")
        end   = item.get("end", "")
        if not start or not end:
            continue
        # Duración aprox de un trimestre (60-120 días)
        from datetime import datetime
        try:
            d_start = datetime.strptime(start, "%Y-%m-%d")
            d_end   = datetime.strptime(end,   "%Y-%m-%d")
            days    = (d_end - d_start).days
        except Exception:
            continue
        if 60 <= days <= 120 and end not in seen_ends:
            quarterly.append(item)
            seen_ends.add(end)
        if len(quarterly) == 4:
            break
    return quarterly


def fetch_sec_data(ticker: str) -> dict | None:
    """Obtiene ingresos y beneficio neto TTM desde SEC EDGAR."""
    cik = _get_cik(ticker)
    if not cik:
        return None

    # Revenue
    rev_series = _get_concept(cik, "Revenues") or _get_concept(cik, "RevenueFromContractWithCustomerExcludingAssessedTax")
    rev_q = _last_4_quarters(rev_series)

    # Net Income
    ni_series = _get_concept(cik, "NetIncomeLoss")
    ni_q = _last_4_quarters(ni_series)

    if not rev_q:
        return None

    ttm_revenue    = sum(q.get("val", 0) for q in rev_q)
    ttm_net_income = sum(q.get("val", 0) for q in ni_q) if ni_q else None

    quarters_formatted = [
        {"date": q["end"], "value": q["val"], "filed": q.get("filed", "")}
        for q in rev_q
    ]
    ni_formatted = [
        {"date": q["end"], "value": q["val"], "filed": q.get("filed", "")}
        for q in ni_q
    ] if ni_q else []

    return {
        "cik":           cik,
        "ttm_revenue":   ttm_revenue,
        "ttm_net_income":ttm_net_income,
        "quarters":      quarters_formatted,
        "ni_quarters":   ni_formatted,
        "currency":      "USD",
    }


# ─────────────────────────────────────────────────────────────
# VERIFICACIÓN CRUZADA
# ─────────────────────────────────────────────────────────────

def verify_cross_data(sec: dict, yahoo: dict) -> dict:
    """Compara TTM de SEC vs Yahoo y devuelve estado de auditoría."""
    if not sec or not yahoo:
        return {"status": "NO_DATA", "diff": None, "pct": None}

    sec_ttm   = sec.get("ttm_revenue", 0) or 0
    yahoo_ttm = yahoo.get("ttm_revenue", 0) or 0

    if sec_ttm == 0 and yahoo_ttm == 0:
        return {"status": "NO_DATA", "diff": None, "pct": None}

    diff = abs(sec_ttm - yahoo_ttm)
    base = max(sec_ttm, yahoo_ttm)
    pct  = (diff / base * 100) if base else 0

    if pct < 2:
        status = "OK"
    elif pct < 10:
        status = "WARN"
    else:
        status = "ERROR"

    return {
        "status":    status,
        "diff":      diff,
        "pct":       pct,
        "sec_ttm":   sec_ttm,
        "yahoo_ttm": yahoo_ttm,
    }
