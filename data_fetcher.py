"""
data_fetcher.py
Obtiene datos de Yahoo Finance (yfinance) y SEC EDGAR.
Incluye metadatos de frescura y nivel de fiabilidad por campo.
"""

import requests
import yfinance as yf
import pandas as pd
from datetime import datetime, timezone, timedelta


# ─────────────────────────────────────────────────────────────────────────────
# NIVELES DE FIABILIDAD
# ─────────────────────────────────────────────────────────────────────────────
#
#  🟢 OFICIAL   — Dato extraído directamente de un filing SEC (10-Q / 10-K)
#  🟡 AGREGADO  — Dato de Yahoo Finance (agrega múltiples fuentes, puede tener
#                 retraso o discrepancias menores)
#  🟠 CALCULADO — Calculado por la app a partir de datos brutos (ej. TTM, YoY)
#  🔴 ESTIMADO  — Estimación de analistas o dato no verificable oficialmente

TRUST = {
    "OFICIAL":   {"icon": "🟢", "label": "Oficial SEC",        "color": "#6ee7b7"},
    "AGREGADO":  {"icon": "🟡", "label": "Yahoo Finance",      "color": "#fbbf24"},
    "CALCULADO": {"icon": "🟠", "label": "Calculado por app",  "color": "#fb923c"},
    "ESTIMADO":  {"icon": "🔴", "label": "Estimación analistas","color": "#fca5a5"},
}

# Umbrales de frescura (días)
STALE_PRICE       =  1   # precio > 1 día = alerta
STALE_FUNDAMENTALS = 120  # fundamentales > 120 días = alerta (un trimestre)
STALE_SEC          = 100  # filing SEC > 100 días = alerta


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _days_since(date_str: str) -> int | None:
    """Días transcurridos desde una fecha ISO (YYYY-MM-DD o YYYY-MM-DDTHH:MM:SS)."""
    if not date_str:
        return None
    try:
        d = date_str[:10]
        dt = datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return (_now() - dt).days
    except Exception:
        return None


def _freshness_status(days: int | None, threshold: int) -> dict:
    """Devuelve estado de frescura para un dato."""
    if days is None:
        return {"ok": None, "label": "Fecha desconocida", "color": "#64748b", "icon": "⚪"}
    if days <= threshold:
        return {"ok": True,  "label": f"Actualizado hace {days}d", "color": "#6ee7b7", "icon": "✅"}
    elif days <= threshold * 1.5:
        return {"ok": False, "label": f"⚠ Hace {days}d (puede estar desfasado)", "color": "#fbbf24", "icon": "⚠️"}
    else:
        return {"ok": False, "label": f"🚨 Hace {days}d — DATO DESFASADO", "color": "#fca5a5", "icon": "🚨"}


# ─────────────────────────────────────────────────────────────────────────────
# TIPO DE CAMBIO USD → EUR
# ─────────────────────────────────────────────────────────────────────────────

def fetch_usd_eur_rate() -> tuple[float, dict]:
    """
    Obtiene el tipo de cambio USD/EUR en tiempo real.
    Devuelve (rate, metadata).
    """
    fetch_time = _now().strftime("%Y-%m-%d %H:%M UTC")
    try:
        fx   = yf.Ticker("EURUSD=X")
        info = fx.info
        rate = info.get("regularMarketPrice") or info.get("currentPrice")
        if rate:
            # Hora de mercado
            ts = info.get("regularMarketTime")
            if ts:
                mkt_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                market_time = mkt_dt.strftime("%Y-%m-%d %H:%M UTC")
                days_old = (_now() - mkt_dt).days
            else:
                market_time = fetch_time
                days_old = 0
            freshness = _freshness_status(days_old, STALE_PRICE)
            return round(1 / rate, 6), {
                "fetch_time":   fetch_time,
                "market_time":  market_time,
                "days_old":     days_old,
                "freshness":    freshness,
                "source":       "Yahoo Finance (EURUSD=X)",
                "trust":        TRUST["AGREGADO"],
            }
    except Exception:
        pass
    # Fallback
    return round(1 / 1.139, 6), {
        "fetch_time":  fetch_time,
        "market_time": "N/A",
        "days_old":    None,
        "freshness":   {"ok": None, "label": "Tipo de cambio aproximado (fallback)", "color": "#fbbf24", "icon": "⚠️"},
        "source":      "Fallback estático",
        "trust":       TRUST["ESTIMADO"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# ANÁLISIS TÉCNICO: RSI, MM50, MM200
# ─────────────────────────────────────────────────────────────────────────────

def _calc_rsi(closes: pd.Series, period: int = 14) -> float | None:
    try:
        delta    = closes.diff()
        gain     = delta.clip(lower=0)
        loss     = (-delta).clip(lower=0)
        avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
        avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
        rs  = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return round(float(rsi.iloc[-1]), 2)
    except Exception:
        return None


def _rsi_label(rsi: float | None) -> tuple[str, str]:
    if rsi is None:
        return "N/A", ""
    if rsi >= 70:   return "SOBRECOMPRA", "red"
    if rsi >= 60:   return "ZONA ALCISTA", "yellow"
    if rsi <= 30:   return "SOBREVENTA", "green"
    if rsi <= 40:   return "ZONA BAJISTA", "yellow"
    return "NEUTRAL", ""


def fetch_technical_data(ticker: str) -> dict:
    """RSI(14), MM50, MM200 con metadatos de frescura."""
    try:
        t    = yf.Ticker(ticker)
        hist = t.history(period="1y", interval="1d")

        if hist.empty or len(hist) < 50:
            return {"error": "Histórico insuficiente"}

        closes = hist["Close"]
        price  = float(closes.iloc[-1])

        # Fecha del último dato
        last_date = hist.index[-1]
        if hasattr(last_date, "strftime"):
            last_date_str = last_date.strftime("%Y-%m-%d")
        else:
            last_date_str = str(last_date)[:10]
        days_old  = _days_since(last_date_str)
        freshness = _freshness_status(days_old, STALE_PRICE)

        rsi   = _calc_rsi(closes)
        mm50  = round(float(closes.tail(50).mean()), 4)
        mm200 = round(float(closes.tail(200).mean()), 4) if len(closes) >= 200 else None

        rsi_lbl, rsi_cls = _rsi_label(rsi)

        mm50_signal,  mm50_cls  = ("Por encima ↑ (alcista)", "green") if price > mm50  else ("Por debajo ↓ (bajista)", "red")
        if mm200 is None:
            mm200_signal, mm200_cls = "Datos insuficientes", ""
        elif price > mm200:
            mm200_signal, mm200_cls = "Por encima ↑ (alcista)", "green"
        else:
            mm200_signal, mm200_cls = "Por debajo ↓ (bajista)", "red"

        cross_signal = None
        if mm200 is not None:
            cross_signal = ("GOLDEN CROSS", "green") if mm50 > mm200 else ("DEATH CROSS", "red")

        dist_mm50  = round((price - mm50)  / mm50  * 100, 2)
        dist_mm200 = round((price - mm200) / mm200 * 100, 2) if mm200 else None

        return {
            "price":        price,
            "rsi":          rsi,
            "rsi_label":    rsi_lbl,
            "rsi_css":      rsi_cls,
            "mm50":         mm50,
            "mm50_signal":  mm50_signal,
            "mm50_css":     mm50_cls,
            "dist_mm50":    dist_mm50,
            "mm200":        mm200,
            "mm200_signal": mm200_signal,
            "mm200_css":    mm200_cls,
            "dist_mm200":   dist_mm200,
            "cross_signal": cross_signal,
            # Metadatos
            "last_date":    last_date_str,
            "days_old":     days_old,
            "freshness":    freshness,
            "trust":        TRUST["AGREGADO"],
            "source":       f"Yahoo Finance — precios diarios (último: {last_date_str})",
        }
    except Exception as e:
        return {"error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# YAHOO FINANCE
# ─────────────────────────────────────────────────────────────────────────────

def fetch_yahoo_data(ticker: str) -> dict | None:
    """Datos fundamentales de Yahoo Finance con metadatos de frescura y fiabilidad."""
    try:
        t    = yf.Ticker(ticker)
        info = t.info

        if not info or (info.get("regularMarketPrice") is None and info.get("currentPrice") is None):
            return None

        price = info.get("currentPrice") or info.get("regularMarketPrice") or 0

        # ── Fecha del precio ──────────────────────────────────────────────
        price_ts = info.get("regularMarketTime")
        if price_ts:
            price_dt      = datetime.fromtimestamp(price_ts, tz=timezone.utc)
            price_date    = price_dt.strftime("%Y-%m-%d %H:%M UTC")
            price_days    = (_now() - price_dt).days
        else:
            price_date    = "N/A"
            price_days    = None
        price_freshness = _freshness_status(price_days, STALE_PRICE)

        # ── Fecha del último earnings (fundamentales) ─────────────────────
        earnings_ts = info.get("mostRecentQuarter") or info.get("lastFiscalYearEnd")
        if earnings_ts:
            earnings_dt   = datetime.fromtimestamp(earnings_ts, tz=timezone.utc)
            earnings_date = earnings_dt.strftime("%Y-%m-%d")
            earnings_days = (_now() - earnings_dt).days
        else:
            earnings_date = "N/A"
            earnings_days = None
        fund_freshness = _freshness_status(earnings_days, STALE_FUNDAMENTALS)

        # ── Fecha objetivo analistas ──────────────────────────────────────
        analyst_ts = info.get("recommendationMean")  # no es fecha, pero usamos otro campo
        # Yahoo no expone fecha del consenso directamente; marcamos como ESTIMADO

        # ── TTM trimestral ────────────────────────────────────────────────
        financials   = t.quarterly_financials
        ttm_quarters = []
        if financials is not None and not financials.empty:
            for label in ["Total Revenue", "Revenue"]:
                if label in financials.index:
                    rev_row = financials.loc[label]
                    for i, (date, val) in enumerate(rev_row.items()):
                        if i >= 4: break
                        ttm_quarters.append({"date": str(date)[:10], "value": val})
                    break

        net_income_q = []
        income_stmt  = t.quarterly_income_stmt
        if income_stmt is not None and not income_stmt.empty:
            for label in ["Net Income", "Net Income Common Stockholders"]:
                if label in income_stmt.index:
                    ni_row = income_stmt.loc[label]
                    for i, (date, val) in enumerate(ni_row.items()):
                        if i >= 4: break
                        net_income_q.append({"date": str(date)[:10], "value": val})
                    break

        ttm_revenue    = sum(q["value"] for q in ttm_quarters if q["value"] == q["value"])
        ttm_net_income = sum(q["value"] for q in net_income_q if q["value"] == q["value"])

        # ── Crecimiento YoY ───────────────────────────────────────────────
        revenue_yoy  = None
        earnings_yoy = None
        rev_annual = t.financials
        if rev_annual is not None and not rev_annual.empty:
            for label in ["Total Revenue", "Revenue"]:
                if label in rev_annual.index:
                    vals = rev_annual.loc[label].dropna().values
                    if len(vals) >= 2:
                        revenue_yoy = (vals[0] - vals[1]) / abs(vals[1]) * 100
                    break
        ni_annual = t.income_stmt
        if ni_annual is not None and not ni_annual.empty:
            for label in ["Net Income", "Net Income Common Stockholders"]:
                if label in ni_annual.index:
                    vals = ni_annual.loc[label].dropna().values
                    if len(vals) >= 2:
                        earnings_yoy = (vals[0] - vals[1]) / abs(vals[1]) * 100
                    break

        return {
            # Identificación
            "company_name":  info.get("longName") or info.get("shortName", ticker),
            "sector":        info.get("sector", "N/A"),
            "currency":      info.get("currency", "USD"),
            "exchange":      info.get("exchange", "N/A"),

            # Mercado
            "price":         price,
            "target_mean":   info.get("targetMeanPrice"),
            "target_low":    info.get("targetLowPrice"),
            "target_high":   info.get("targetHighPrice"),
            "recommendation":info.get("recommendationKey", "N/A").upper(),
            "analyst_count": info.get("numberOfAnalystOpinions"),

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
            "revenue_yoy":  revenue_yoy  if revenue_yoy  is not None else (info.get("revenueGrowth",  0) * 100 if info.get("revenueGrowth")  else None),
            "earnings_yoy": earnings_yoy if earnings_yoy is not None else (info.get("earningsGrowth", 0) * 100 if info.get("earningsGrowth") else None),

            # Dividendos
            "dividend_yield": info.get("dividendYield"),
            "dividend_rate":  info.get("dividendRate"),

            # Otros
            "short_ratio":      info.get("shortRatio"),
            "eps_ttm":          info.get("trailingEps"),
            "eps_forward":      info.get("forwardEps"),
            "market_cap":       info.get("marketCap"),
            "enterprise_value": info.get("enterpriseValue"),
            "beta":             info.get("beta"),
            "52w_high":         info.get("fiftyTwoWeekHigh"),
            "52w_low":          info.get("fiftyTwoWeekLow"),

            # TTM
            "ttm_quarters":    ttm_quarters,
            "ttm_revenue":     ttm_revenue,
            "ttm_net_income":  ttm_net_income,
            "net_income_q":    net_income_q,
            "ebitda":          info.get("ebitda"),

            # ── Metadatos de fiabilidad ───────────────────────────────────
            "meta": {
                "fetch_time":      _now().strftime("%Y-%m-%d %H:%M UTC"),
                "price_date":      price_date,
                "price_days_old":  price_days,
                "price_freshness": price_freshness,
                "earnings_date":   earnings_date,
                "earnings_days":   earnings_days,
                "fund_freshness":  fund_freshness,
                # Fiabilidad por grupo de métricas
                "trust_price":       TRUST["AGREGADO"],   # precio Yahoo = agregado
                "trust_fundamentals":TRUST["AGREGADO"],   # márgenes, ROE, etc.
                "trust_consensus":   TRUST["ESTIMADO"],   # targets analistas = estimación
                "trust_growth":      TRUST["CALCULADO"],  # YoY calculado por la app
                "trust_ttm":         TRUST["CALCULADO"],  # TTM calculado por la app
            },
        }

    except Exception as e:
        print(f"[Yahoo] Error: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# SEC EDGAR
# ─────────────────────────────────────────────────────────────────────────────

SEC_HEADERS = {"User-Agent": "AnalisisFundamental contacto@ejemplo.com"}


def _get_cik(ticker: str) -> str | None:
    try:
        r    = requests.get("https://www.sec.gov/files/company_tickers.json",
                            headers=SEC_HEADERS, timeout=10)
        data = r.json()
        for entry in data.values():
            if entry.get("ticker", "").upper() == ticker.upper():
                return str(entry["cik_str"]).zfill(10)
    except Exception as e:
        print(f"[SEC CIK] Error: {e}")
    return None


def _get_concept(cik: str, concept: str, unit: str = "USD") -> list:
    url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{concept}.json"
    try:
        r = requests.get(url, headers=SEC_HEADERS, timeout=15)
        if r.status_code != 200:
            return []
        data     = r.json()
        units    = data.get("units", {}).get(unit, [])
        quarterly = [u for u in units if u.get("form") in ("10-Q", "10-K") and u.get("frame") is None]
        quarterly.sort(key=lambda x: x.get("end", ""), reverse=True)
        return quarterly
    except Exception as e:
        print(f"[SEC concept {concept}] Error: {e}")
        return []


def _last_4_quarters(series: list) -> list:
    from datetime import datetime as dt
    quarterly  = []
    seen_ends  = set()
    for item in series:
        start = item.get("start", "")
        end   = item.get("end", "")
        if not start or not end:
            continue
        try:
            days = (dt.strptime(end, "%Y-%m-%d") - dt.strptime(start, "%Y-%m-%d")).days
        except Exception:
            continue
        if 60 <= days <= 120 and end not in seen_ends:
            quarterly.append(item)
            seen_ends.add(end)
        if len(quarterly) == 4:
            break
    return quarterly


def fetch_sec_data(ticker: str) -> dict | None:
    """Ingresos y beneficio neto TTM desde SEC EDGAR con metadatos de frescura."""
    cik = _get_cik(ticker)
    if not cik:
        return None

    rev_series = _get_concept(cik, "Revenues") or _get_concept(cik, "RevenueFromContractWithCustomerExcludingAssessedTax")
    rev_q      = _last_4_quarters(rev_series)
    ni_series  = _get_concept(cik, "NetIncomeLoss")
    ni_q       = _last_4_quarters(ni_series)

    if not rev_q:
        return None

    ttm_revenue    = sum(q.get("val", 0) for q in rev_q)
    ttm_net_income = sum(q.get("val", 0) for q in ni_q) if ni_q else None

    quarters_fmt = [{"date": q["end"], "value": q["val"], "filed": q.get("filed", "")} for q in rev_q]
    ni_fmt       = [{"date": q["end"], "value": q["val"], "filed": q.get("filed", "")} for q in ni_q] if ni_q else []

    # Frescura: fecha del último filing presentado
    latest_filed = rev_q[0].get("filed", "") if rev_q else ""
    latest_end   = rev_q[0].get("end",   "") if rev_q else ""
    days_filed   = _days_since(latest_filed)
    days_end     = _days_since(latest_end)
    # Usamos días desde el final del trimestre (más relevante para el inversor)
    sec_freshness = _freshness_status(days_end, STALE_SEC)

    return {
        "cik":            cik,
        "ttm_revenue":    ttm_revenue,
        "ttm_net_income": ttm_net_income,
        "quarters":       quarters_fmt,
        "ni_quarters":    ni_fmt,
        "currency":       "USD",
        # Metadatos
        "meta": {
            "fetch_time":    _now().strftime("%Y-%m-%d %H:%M UTC"),
            "latest_end":    latest_end,
            "latest_filed":  latest_filed,
            "days_since_end":    days_end,
            "days_since_filed":  days_filed,
            "freshness":     sec_freshness,
            "trust":         TRUST["OFICIAL"],
            "source":        f"SEC EDGAR (CIK {cik}) — último trimestre: {latest_end}",
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# VERIFICACIÓN CRUZADA
# ─────────────────────────────────────────────────────────────────────────────

def verify_cross_data(sec: dict, yahoo: dict) -> dict:
    if not sec or not yahoo:
        return {"status": "NO_DATA", "diff": None, "pct": None}

    sec_ttm   = sec.get("ttm_revenue",   0) or 0
    yahoo_ttm = yahoo.get("ttm_revenue", 0) or 0

    if sec_ttm == 0 and yahoo_ttm == 0:
        return {"status": "NO_DATA", "diff": None, "pct": None}

    diff = abs(sec_ttm - yahoo_ttm)
    base = max(sec_ttm, yahoo_ttm)
    pct  = (diff / base * 100) if base else 0

    if pct < 2:   status = "OK"
    elif pct < 10: status = "WARN"
    else:          status = "ERROR"

    return {
        "status":    status,
        "diff":      diff,
        "pct":       pct,
        "sec_ttm":   sec_ttm,
        "yahoo_ttm": yahoo_ttm,
    }
