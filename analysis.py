"""
analysis.py — v1.8
Módulos avanzados: señal de entrada, tendencia, competidores,
descripción empresa, noticias, análisis resultados, benchmarks sector.
"""

import yfinance as yf
import streamlit as st
import requests
import time
import json
import os
from datetime import datetime, timezone

# ─────────────────────────────────────────────────────────────────────────────
# BENCHMARKS DE SECTOR — medias de mercado por métrica
# ─────────────────────────────────────────────────────────────────────────────

SECTOR_BENCHMARKS = {
    "Technology":             {"pe_fwd":28, "peg":1.5, "ev_ebitda":22, "profit_m":18, "roe":22, "op_m":22, "price_sales":6.0, "price_book":8.0},
    "Communication Services": {"pe_fwd":22, "peg":1.3, "ev_ebitda":18, "profit_m":14, "roe":15, "op_m":18, "price_sales":3.5, "price_book":4.5},
    "Consumer Cyclical":      {"pe_fwd":20, "peg":1.2, "ev_ebitda":14, "profit_m": 7, "roe":14, "op_m":10, "price_sales":1.5, "price_book":3.5},
    "Consumer Defensive":     {"pe_fwd":22, "peg":2.0, "ev_ebitda":16, "profit_m": 9, "roe":18, "op_m":14, "price_sales":1.2, "price_book":4.0},
    "Healthcare":             {"pe_fwd":24, "peg":1.8, "ev_ebitda":18, "profit_m":13, "roe":15, "op_m":16, "price_sales":3.0, "price_book":4.0},
    "Financials":             {"pe_fwd":14, "peg":1.0, "ev_ebitda":10, "profit_m":20, "roe":11, "op_m":28, "price_sales":3.0, "price_book":1.3},
    "Industrials":            {"pe_fwd":20, "peg":1.5, "ev_ebitda":14, "profit_m": 9, "roe":14, "op_m":12, "price_sales":1.5, "price_book":3.5},
    "Energy":                 {"pe_fwd":14, "peg":1.0, "ev_ebitda": 6, "profit_m":10, "roe":12, "op_m":14, "price_sales":1.0, "price_book":1.8},
    "Basic Materials":        {"pe_fwd":16, "peg":1.2, "ev_ebitda": 8, "profit_m": 8, "roe":11, "op_m":12, "price_sales":1.2, "price_book":2.0},
    "Real Estate":            {"pe_fwd":30, "peg":2.5, "ev_ebitda":20, "profit_m":22, "roe": 8, "op_m":30, "price_sales":5.0, "price_book":2.0},
    "Utilities":              {"pe_fwd":18, "peg":2.0, "ev_ebitda":12, "profit_m":12, "roe": 9, "op_m":18, "price_sales":2.5, "price_book":1.5},
    "_default":               {"pe_fwd":20, "peg":1.5, "ev_ebitda":14, "profit_m":10, "roe":12, "op_m":14, "price_sales":2.5, "price_book":3.0},
}

def get_sector_benchmarks(sector: str) -> dict:
    for key in SECTOR_BENCHMARKS:
        if key != "_default" and key.lower() in (sector or "").lower():
            return SECTOR_BENCHMARKS[key]
    return SECTOR_BENCHMARKS["_default"]

# ─────────────────────────────────────────────────────────────────────────────
# TOOLTIPS PARA EL RASTREADOR DE GANGAS
# ─────────────────────────────────────────────────────────────────────────────

SCANNER_TOOLTIPS = {
    "F1 Valoración (PEG)":  "PEG = PER dividido entre tasa de crecimiento anual. PEG < 1 = pagas menos de lo que crece la empresa. El indicador más potente para detectar empresas baratas respecto a su crecimiento. Escala: <0.5 excepcional · <1.0 muy bueno · <1.5 aceptable · >2.0 caro.",
    "F2 Margen neto":       "Beneficio neto / ingresos totales. Indica cuánto dinero real queda tras TODOS los gastos. Escala: >20% excelente · >10% bueno · >5% aceptable · <0% pérdidas. Compara siempre dentro del mismo sector.",
    "F3 Crec. Ingresos":    "Crecimiento de ventas año sobre año (YoY). Demuestra demanda real y capacidad de expansión del negocio. Escala: >30% muy alto · >15% bueno · >5% aceptable · <0% preocupante.",
    "F4 ROE":               "Return on Equity = beneficio neto / patrimonio neto. Mide la eficiencia con que la empresa genera beneficios con el capital de los accionistas. Escala: >20% excelente · >12% bueno · >8% aceptable · <0% destruye valor.",
    "F5 Balance/FCF":       "Combina dos criterios: Free Cash Flow positivo (la empresa genera dinero real, no solo beneficio contable) y ratio Deuda/Equity bajo (<50% ideal). Ambos factores reducen el riesgo financiero.",
    "T1 Dist. máx. anual":  "% de caída desde el precio máximo de los últimos 12 meses. Las mejores oportunidades suelen encontrarse entre el 15-35% por debajo de máximos, si los fundamentales siguen intactos. >30% caída = posible oportunidad o problema real.",
    "T2 Corrección 3M":     "Caída desde el precio máximo de los últimos 3 meses. Una corrección reciente del 10-20% sobre una empresa con buenos fundamentales es la señal clásica de entrada que buscan los inversores value.",
    "T3 RSI":               "Índice de Fuerza Relativa (0-100). Mide si el precio ha subido/bajado demasiado rápido. RSI <30 = sobreventa extrema (posible rebote inminente) · RSI <40 = zona de compra · RSI 40-60 = neutral · RSI >70 = sobrecompra (evitar entrar).",
    "T4 Precio vs MMs":     "Si el precio cotiza por debajo de la Media Móvil de 50 o 200 sesiones, puede indicar una zona de soporte técnico relevante donde históricamente el precio ha rebotado. Señal técnica adicional, no definitiva.",
    "P1 RSI sobrecompra":   "PENALIZACIÓN: RSI > 70 significa que el precio ha subido demasiado rápido en poco tiempo y estadísticamente tiende a corregir. Entrar en sobrecompra implica asumir riesgo de corrección a corto plazo.",
    "P2 Short ratio alto":  "PENALIZACIÓN: Short Ratio > 5 días significa que muchos inversores institucionales apuestan activamente a la baja. Es una señal de desconfianza importante que merece investigación adicional antes de entrar.",
    "P3 En máximos":        "PENALIZACIÓN: Precio dentro del 3% de su máximo anual. Las mejores entradas son cuando la empresa está lejos de máximos con fundamentales sólidos. En máximos el riesgo/beneficio es menos favorable.",
}

# ─────────────────────────────────────────────────────────────────────────────
# COMPETIDORES POR SECTOR
# ─────────────────────────────────────────────────────────────────────────────

SECTOR_PEERS = {
    "Technology": {
        "Semiconductors":     ["NVDA","AMD","INTC","QCOM","AVGO","MU","AMAT","KLAC","LRCX","ASML"],
        "Software":           ["MSFT","ORCL","SAP","CRM","NOW","ADBE","WDAY","TEAM","SNOW","MDB"],
        "Hardware / Storage": ["AAPL","DELL","HPQ","WDC","STX","NTAP","PSTG","SMCI","ANET"],
        "General Technology": ["AAPL","MSFT","GOOGL","META","NVDA","AVGO","ORCL","CRM","ADBE","AMD"],
    },
    "Communication Services": {"General": ["GOOGL","META","NFLX","DIS","CMCSA","T","VZ","TMUS","SNAP","PINS"]},
    "Consumer Cyclical":      {"General": ["AMZN","TSLA","HD","MCD","NKE","LOW","SBUX","CMG","BKNG","TJX"]},
    "Consumer Defensive":     {"General": ["WMT","COST","PG","KO","PEP","MO","PM","MDLZ","GIS","K"]},
    "Healthcare": {
        "Pharma":             ["LLY","JNJ","PFE","MRK","ABBV","BMY","AZN","NVO","SNY","GSK"],
        "Biotech / Devices":  ["AMGN","GILD","REGN","VRTX","ISRG","MDT","ABT","BSX","EW","SYK"],
        "General Healthcare": ["LLY","JNJ","UNH","ABBV","MRK","TMO","ABT","DHR","BMY","AMGN"],
    },
    "Financials": {
        "Banks":              ["JPM","BAC","WFC","C","GS","MS","USB","TFC","PNC","COF"],
        "Insurance / Other":  ["BRK-B","V","MA","AXP","BLK","SCHW","CB","PRU","MET","ALL"],
        "General Financials": ["JPM","BAC","GS","MS","BLK","V","MA","AXP","SCHW","BRK-B"],
    },
    "Industrials":    {"General": ["HON","GE","CAT","DE","RTX","LMT","NOC","UNP","FDX","UPS"]},
    "Energy":         {"General": ["XOM","CVX","COP","EOG","OXY","SLB","MPC","VLO","PSX","HES"]},
    "Basic Materials":{"General": ["LIN","APD","SHW","FCX","NEM","NUE","STLD","ECL","PPG","ALB"]},
    "Real Estate":    {"General": ["PLD","AMT","EQIX","CCI","SPG","O","VICI","PSA","EQR","AVB"]},
    "Utilities":      {"General": ["NEE","SO","DUK","AEP","EXC","SRE","XEL","ES","D","PCG"]},
    "_default":       {"General": ["AAPL","MSFT","AMZN","GOOGL","META","NVDA","JPM","JNJ","V","XOM"]},
}

def get_peers(ticker: str, sector: str, company_name: str) -> list:
    """
    Obtiene competidores directos usando la lista curada por sector/subsector.
    Prioriza encontrar el subsector correcto buscando el ticker en las listas.
    """
    sector_map = None
    for key in SECTOR_PEERS:
        if key != "_default" and key.lower() in (sector or "").lower():
            sector_map = SECTOR_PEERS[key]
            break
    if not sector_map:
        sector_map = SECTOR_PEERS["_default"]

    if len(sector_map) == 1:
        peers = list(sector_map.values())[0]
    else:
        chosen = None
        # Primero: buscar el ticker directamente en las listas de subsector
        for subsector, tickers in sector_map.items():
            if ticker.upper() in [t.upper() for t in tickers]:
                chosen = tickers
                break
        # Segundo: buscar por palabras del nombre de empresa
        if not chosen:
            name_lower = (company_name or "").lower()
            for subsector, tickers in sector_map.items():
                if subsector in ("General Technology", "General"):
                    continue
                sub_words = subsector.lower().replace("/", " ").replace("-", " ").split()
                if any(w in name_lower for w in sub_words if len(w) > 3):
                    chosen = tickers
                    break
        # Fallback: primer subsector no genérico
        if not chosen:
            for subsector, tickers in sector_map.items():
                if subsector not in ("General Technology", "General", "_default"):
                    chosen = tickers
                    break
        peers = chosen or list(sector_map.values())[0]

    return [p for p in peers if p.upper() != ticker.upper()][:8]


# ─────────────────────────────────────────────────────────────────────────────
# DESCRIPCIÓN DE LA EMPRESA + INSIDERS + CALIDAD DEL BENEFICIO
# ─────────────────────────────────────────────────────────────────────────────

def fetch_company_description(ticker: str) -> dict:
    """
    Obtiene descripción + datos de insiders + calidad del beneficio (FCF/NI).
    """
    try:
        t    = yf.Ticker(ticker)
        info = t.info

        # Insider transactions
        insiders = []
        try:
            insider_df = t.insider_transactions
            if insider_df is not None and not insider_df.empty:
                for _, row in insider_df.head(12).iterrows():
                    try:
                        date_val = row.get("startDate") or row.get("Date","")
                        date_str = str(date_val)[:10] if date_val else "N/A"
                        text     = str(row.get("text","") or row.get("Transaction",""))
                        relation = str(row.get("relationship","") or row.get("Insider",""))
                        shares   = row.get("shares") or row.get("Shares") or 0
                        value    = row.get("value")  or row.get("Value")  or 0
                        is_buy   = any(w in text.lower() for w in
                                       ["purchase","buy","acquisition","bought"])
                        is_sell  = any(w in text.lower() for w in
                                       ["sale","sell","sold","disposition"])
                        if not text: continue
                        insiders.append({
                            "date":     date_str,
                            "text":     text[:70],
                            "relation": relation[:45],
                            "shares":   int(float(shares)) if shares else 0,
                            "value":    float(value) if value else 0,
                            "is_buy":   is_buy,
                            "is_sell":  is_sell,
                        })
                    except Exception:
                        continue
        except Exception:
            pass

        # Calidad del beneficio: FCF / Net Income
        fcf     = info.get("freeCashflow")
        net_inc = info.get("netIncomeToCommon") or info.get("netIncome")
        fcf_quality = None
        if fcf and net_inc and net_inc != 0:
            fcf_quality = round(fcf / abs(net_inc), 2)

        return {
            "description": info.get("longBusinessSummary",""),
            "sector":      info.get("sector",""),
            "industry":    info.get("industry",""),
            "employees":   info.get("fullTimeEmployees"),
            "website":     info.get("website",""),
            "country":     info.get("country",""),
            "insiders":    insiders,
            "fcf_quality": fcf_quality,
        }
    except Exception:
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# NOTICIAS RECIENTES  — compatible con yfinance >= 0.2.40
# ─────────────────────────────────────────────────────────────────────────────

def _extract_news_url(item: dict) -> str:
    """Extrae la URL de una noticia independientemente de la versión de yfinance."""
    # yfinance >= 0.2.40: estructura anidada en 'content'
    content = item.get("content", {})
    if content:
        # canonicalUrl es el más fiable
        canon = content.get("canonicalUrl", {})
        if isinstance(canon, dict):
            url = canon.get("url", "")
            if url:
                return url
        # clickThroughUrl como alternativa
        click = content.get("clickThroughUrl", {})
        if isinstance(click, dict):
            url = click.get("url", "")
            if url:
                return url
    # Versiones antiguas
    return item.get("link","") or item.get("url","") or ""


def _extract_news_title(item: dict) -> str:
    """Extrae el título de una noticia."""
    content = item.get("content", {})
    if content:
        return content.get("title","") or item.get("title","")
    return item.get("title","")


def _extract_news_publisher(item: dict) -> str:
    """Extrae el publisher de una noticia."""
    content = item.get("content", {})
    if content:
        provider = content.get("provider", {})
        if isinstance(provider, dict):
            return provider.get("displayName","") or provider.get("name","")
    return item.get("publisher","") or item.get("source","")


def _extract_news_timestamp(item: dict) -> int:
    """Extrae el timestamp de publicación."""
    content = item.get("content", {})
    if content:
        pub_date = content.get("pubDate","") or content.get("publishedAt","")
        if pub_date:
            try:
                from datetime import datetime, timezone
                # Formato ISO: "2024-01-15T10:30:00Z"
                dt = datetime.fromisoformat(pub_date.replace("Z","+00:00"))
                return int(dt.timestamp())
            except Exception:
                pass
    # Versiones antiguas: timestamp unix directo
    return item.get("providerPublishTime", 0) or item.get("publishTime", 0) or 0


def fetch_recent_news(ticker: str, max_items: int = 8) -> list:
    """
    Obtiene noticias recientes de yfinance.
    Compatible con versiones antiguas y nuevas de la API.
    """
    try:
        t    = yf.Ticker(ticker)
        raw  = t.news or []

        if not raw:
            print(f"[News] Sin noticias para {ticker}")
            return []

        print(f"[News] {ticker}: {len(raw)} noticias raw, keys ejemplo: {list(raw[0].keys()) if raw else []}")

        now    = datetime.now(timezone.utc).timestamp()
        cutoff = now - (90 * 24 * 3600)  # 90 días
        items  = []

        for n in raw:
            ts        = _extract_news_timestamp(n)
            title     = _extract_news_title(n)
            url       = _extract_news_url(n)
            publisher = _extract_news_publisher(n)

            if not title:
                continue
            # Si no hay timestamp fiable, incluir igualmente (últimas noticias)
            if ts and ts < cutoff:
                continue

            date_str = ""
            if ts:
                try:
                    date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
                except Exception:
                    date_str = ""

            items.append({
                "title":     title[:150],
                "publisher": publisher,
                "url":       url,
                "ts":        ts or 0,
                "date":      date_str,
            })

        items.sort(key=lambda x: x["ts"], reverse=True)
        result = items[:max_items]
        print(f"[News] {ticker}: {len(result)} noticias válidas tras filtrado")
        return result

    except Exception as e:
        print(f"[News] Error para {ticker}: {e}")
        return []

# ─────────────────────────────────────────────────────────────────────────────
# ANÁLISIS DE ÚLTIMOS RESULTADOS
# ─────────────────────────────────────────────────────────────────────────────

_MESES_ES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
    7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}


def _fmt_fecha_es(dt: datetime) -> str:
    """Formatea una fecha como '31 de marzo de 2026'."""
    return f"{dt.day} de {_MESES_ES[dt.month]} de {dt.year}"


def _tiempo_transcurrido(dt_pasado: datetime, dt_ahora: datetime) -> str:
    """Calcula meses y días transcurridos entre dos fechas, en texto legible."""
    if dt_pasado > dt_ahora:
        return ""
    delta_days = (dt_ahora - dt_pasado).days
    meses = delta_days // 30
    dias  = delta_days % 30
    partes = []
    if meses > 0:
        partes.append(f"{meses} mes{'es' if meses != 1 else ''}")
    if dias > 0 or not partes:
        partes.append(f"{dias} día{'s' if dias != 1 else ''}")
    return " y ".join(partes)


def _tiempo_restante(dt_futuro: datetime, dt_ahora: datetime) -> str:
    """Calcula meses y días restantes hasta una fecha futura, en texto legible."""
    if dt_futuro < dt_ahora:
        return ""
    delta_days = (dt_futuro - dt_ahora).days
    meses = delta_days // 30
    dias  = delta_days % 30
    partes = []
    if meses > 0:
        partes.append(f"{meses} mes{'es' if meses != 1 else ''}")
    if dias > 0 or not partes:
        partes.append(f"{dias} día{'s' if dias != 1 else ''}")
    return " y ".join(partes)


def _safe_float(v) -> float | None:
    """Convierte un valor de pandas a float, manejando NaN/None de forma segura."""
    if v is None:
        return None
    try:
        import math
        fv = float(v)
        if math.isnan(fv):
            return None
        return fv
    except (TypeError, ValueError):
        return None


# ─────────────────────────────────────────────────────────────────────────────
# EARNINGS — FUENTE: FINNHUB (primaria) + yfinance fallback
# ─────────────────────────────────────────────────────────────────────────────
# Finnhub proporciona EPS estimado/real y Revenue estimado/real por trimestre
# con la fecha real de la conference call, separados correctamente del cierre
# del periodo fiscal. Endpoint: GET /stock/earnings?symbol=TICKER&limit=8
# Documentación: https://finnhub.io/docs/api/company-earnings

FINNHUB_BASE = "https://finnhub.io/api/v1"


def _get_finnhub_key() -> str:
    try:
        return str(st.secrets["FINNHUB_API_KEY"]).strip()
    except Exception:
        pass
    return os.environ.get("FINNHUB_API_KEY", "").strip()


def _fetch_earnings_finnhub(ticker: str, limit: int = 8) -> list:
    """
    Obtiene el histórico de earnings desde Finnhub.
    Endpoint correcto: /calendar/earnings con rango de fechas.
    Devuelve epsActual, epsEstimate, revenueActual, revenueEstimate, fecha real de presentación.
    """
    key = _get_finnhub_key()
    if not key:
        print("[Finnhub] Sin FINNHUB_API_KEY configurada en Secrets")
        return []
    try:
        from datetime import date, timedelta
        # Consultar los últimos 3 años para tener historial suficiente
        today     = date.today()
        date_to   = today.strftime("%Y-%m-%d")
        date_from = (today - timedelta(days=3*365)).strftime("%Y-%m-%d")

        r = requests.get(
            f"{FINNHUB_BASE}/calendar/earnings",
            params={
                "symbol": ticker.upper(),
                "from":   date_from,
                "to":     date_to,
                "token":  key,
            },
            timeout=12,
        )
        if r.status_code != 200:
            print(f"[Finnhub] HTTP {r.status_code} para {ticker}: {r.text[:200]}")
            return []

        data = r.json()
        items = data.get("earningsCalendar", [])
        if not items:
            print(f"[Finnhub] earningsCalendar vacío para {ticker}")
            return []

        out = []
        for item in items:
            try:
                date_str = item.get("date", "")
                year     = item.get("year")
                quarter  = item.get("quarter")
                eps_est  = item.get("epsEstimate")
                eps_act  = item.get("epsActual")
                rev_est  = item.get("revenueEstimate")
                rev_act  = item.get("revenueActual")
                hour     = item.get("hour", "")

                if not date_str:
                    continue

                # Etiqueta fiscal
                if year and quarter:
                    fiscal_label = f"Q{quarter} '{str(year)[2:]}"
                else:
                    try:
                        dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
                        q  = (dt.month - 1) // 3 + 1
                        fiscal_label = f"Q{q} '{str(dt.year)[2:]}"
                    except Exception:
                        fiscal_label = date_str[:7]

                # Sorpresa EPS
                eps_surprise = None
                if eps_act is not None and eps_est is not None and eps_est != 0:
                    eps_surprise = (float(eps_act) - float(eps_est)) / abs(float(eps_est)) * 100

                # Sorpresa Revenue
                rev_surprise = None
                if rev_act is not None and rev_est is not None and rev_est != 0:
                    rev_surprise = (float(rev_act) - float(rev_est)) / abs(float(rev_est)) * 100

                # Resultado — solo si hay datos reales reportados
                if eps_act is None and rev_act is None:
                    result = "N/A"
                elif eps_surprise is not None:
                    result = "BEAT" if eps_surprise > 0.5 else ("MISSED" if eps_surprise < -0.5 else "MET")
                else:
                    result = "N/A"

                out.append({
                    "fiscal_label": fiscal_label,
                    "date":         date_str[:10],
                    "eps_estimate": float(eps_est) if eps_est is not None else None,
                    "eps_reported": float(eps_act) if eps_act is not None else None,
                    "surprise_pct": round(eps_surprise, 2) if eps_surprise is not None else None,
                    "rev_estimate": float(rev_est) if rev_est is not None else None,
                    "rev_actual":   float(rev_act) if rev_act is not None else None,
                    "rev_surprise": round(rev_surprise, 2) if rev_surprise is not None else None,
                    "result":       result,
                    "hour":         hour,
                })
            except Exception as e:
                print(f"[Finnhub] Error parseando fila: {e} — item: {item}")
                continue

        # Ordenar de más reciente a más antiguo
        out.sort(key=lambda x: x["date"], reverse=True)

        # Filtrar solo trimestres ya presentados (eps_reported o rev_actual no nulos)
        # y limitar al número pedido
        reported = [h for h in out if h["eps_reported"] is not None or h["rev_actual"] is not None]
        pending  = [h for h in out if h["eps_reported"] is None and h["rev_actual"] is None]

        # Incluir el próximo pendiente al principio si existe
        result_list = (pending[:1] + reported)[:limit]

        print(f"[Finnhub] {ticker}: {len(reported)} trimestres con datos + {len(pending)} pendientes")
        return result_list

    except Exception as e:
        print(f"[Finnhub] Excepción de red para {ticker}: {e}")
        return []


def _fetch_earnings_yf_fallback(ticker: str, max_items: int = 8) -> list:
    """Fallback a yfinance si Finnhub no está configurado o falla."""
    try:
        t = yf.Ticker(ticker)
        edates = t.earnings_dates
        if edates is None or edates.empty:
            return []

        col_est  = "EPS Estimate" if "EPS Estimate" in edates.columns else None
        col_rep  = "Reported EPS" if "Reported EPS" in edates.columns else None
        col_surp = "Surprise(%)"  if "Surprise(%)"  in edates.columns else None
        if not col_rep:
            return []

        edates_sorted = edates.sort_index(ascending=False)
        history = []
        for date_idx, row in edates_sorted.iterrows():
            dt = date_idx.to_pydatetime() if hasattr(date_idx, "to_pydatetime") else date_idx
            q  = (dt.month - 1) // 3 + 1
            fiscal_label = f"Q{q} '{str(dt.year)[2:]}"

            eps_est = _safe_float(row.get(col_est)) if col_est else None
            eps_rep = _safe_float(row.get(col_rep)) if col_rep else None
            surp    = _safe_float(row.get(col_surp)) if col_surp else None

            if eps_rep is None:
                history.append({
                    "fiscal_label": fiscal_label, "date": dt.strftime("%Y-%m-%d"),
                    "eps_estimate": eps_est, "eps_reported": None,
                    "surprise_pct": None, "rev_estimate": None,
                    "rev_actual": None, "rev_surprise": None,
                    "result": "N/A", "hour": "",
                })
                continue

            surprise_pct = (surp * 100) if surp is not None else (
                (eps_rep - eps_est) / abs(eps_est) * 100
                if eps_est and eps_est != 0 else None
            )
            result = ("BEAT" if (surprise_pct or 0) > 0.5
                      else "MISSED" if (surprise_pct or 0) < -0.5 else "MET")

            history.append({
                "fiscal_label": fiscal_label, "date": dt.strftime("%Y-%m-%d"),
                "eps_estimate": eps_est, "eps_reported": eps_rep,
                "surprise_pct": round(surprise_pct, 2) if surprise_pct is not None else None,
                "rev_estimate": None, "rev_actual": None, "rev_surprise": None,
                "result": result, "hour": "",
            })
            if len(history) >= max_items:
                break
        return history
    except Exception as e:
        print(f"[EarningsYF] {ticker}: {e}")
        return []


def _get_earnings_history_cached(ticker: str, max_items: int = 8) -> list:
    """Punto de entrada único con caché en session_state."""
    cache_key = f"_earnings_hist_cache_{ticker.upper()}"
    if cache_key in st.session_state:
        return st.session_state[cache_key]

    # Finnhub primero (más fiable para earnings trimestrales)
    history = _fetch_earnings_finnhub(ticker, limit=max_items)
    if not history:
        print(f"[Earnings] Finnhub vacío para {ticker}, probando yfinance...")
        history = _fetch_earnings_yf_fallback(ticker, max_items)

    result = history[:max_items]
    st.session_state[cache_key] = result
    return result


def fetch_earnings_history(ticker: str, max_items: int = 8) -> list:
    """
    Histórico de resultados con EPS estimado/real, Revenue estimado/real
    y porcentaje de sorpresa. Fuente primaria: Finnhub.
    """
    return _get_earnings_history_cached(ticker, max_items)


def fetch_earnings_analysis(ticker: str, y: dict) -> dict:
    """
    Análisis del último trimestre reportado. Usa Finnhub como fuente
    primaria para EPS y fecha real de presentación.
    """
    try:
        t    = yf.Ticker(ticker)
        info = t.info
        now_utc = datetime.now(timezone.utc)

        history = _get_earnings_history_cached(ticker, max_items=8)

        last_q_dt    = None
        next_q_dt    = None
        eps_estimate = None
        eps_actual   = None
        eps_surprise = None
        beat_eps     = None
        rev_actual   = None
        rev_estimate = None
        rev_surprise = None

        if history:
            # Primer registro con eps_reported es el último trimestre presentado
            for h in history:
                if h.get("eps_reported") is not None:
                    try:
                        last_q_dt    = datetime.strptime(h["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    except Exception:
                        pass
                    eps_actual   = h.get("eps_reported")
                    eps_estimate = h.get("eps_estimate")
                    eps_surprise = h.get("surprise_pct")
                    rev_actual   = h.get("rev_actual")
                    rev_estimate = h.get("rev_estimate")
                    rev_surprise = h.get("rev_surprise")
                    break

        # Próxima presentación desde info de Yahoo (fiable para fechas futuras)
        next_q_ts = info.get("earningsTimestamp") or info.get("earningsTimestampStart")
        if next_q_ts:
            candidate = datetime.fromtimestamp(next_q_ts, tz=timezone.utc)
            if candidate > now_utc:
                next_q_dt = candidate
        # Fallback: buscar en historial una fila futura sin reportar
        if next_q_dt is None and history:
            for h in history:
                if h.get("eps_reported") is None:
                    try:
                        c = datetime.strptime(h["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                        if c > now_utc:
                            next_q_dt = c
                            break
                    except Exception:
                        continue

        # Fallback final de EPS si Finnhub y yfinance fallaron
        if eps_actual is None:
            print(f"[Earnings] {ticker} — sin histórico, usando trailingEps de Yahoo como último recurso")
            eps_actual   = _safe_float(info.get("trailingEps"))
            eps_estimate = _safe_float(info.get("epsCurrentYear")) or _safe_float(info.get("epsForward"))
            if eps_actual and eps_estimate and eps_estimate != 0:
                eps_surprise = (eps_actual - eps_estimate) / abs(eps_estimate) * 100

        if eps_surprise is not None:
            beat_eps = eps_surprise > 0

        last_q_date_fmt = _fmt_fecha_es(last_q_dt) if last_q_dt else "N/A"
        next_q_date_fmt = _fmt_fecha_es(next_q_dt) if next_q_dt else "N/A"
        last_q_date     = last_q_dt.strftime("%Y-%m-%d") if last_q_dt else "N/A"
        next_q_date     = next_q_dt.strftime("%Y-%m-%d") if next_q_dt else "N/A"
        tiempo_desde    = _tiempo_transcurrido(last_q_dt, now_utc) if last_q_dt else ""
        tiempo_hasta    = _tiempo_restante(next_q_dt, now_utc)     if next_q_dt else ""

        q_data   = y.get("ttm_quarters", [])
        q_growth = None
        if len(q_data) >= 2:
            v0 = q_data[0].get("value") or 0
            v1 = q_data[1].get("value") or 0
            if v1 and v1 != 0:
                q_growth = (v0 - v1) / abs(v1) * 100

        rev_actual_last = q_data[0].get("value") if q_data else None

        positives = []
        negatives = []
        warnings  = []

        profit_m   = (y.get("profit_margin") or 0) * 100
        roe        = (y.get("roe") or 0) * 100
        rev_yoy    = y.get("revenue_yoy") or 0
        earn_yoy   = y.get("earnings_yoy") or 0
        fcf        = y.get("free_cash_flow") or 0
        debt_eq    = y.get("debt_equity") or 0
        curr_ratio = y.get("current_ratio") or 0
        op_m       = (y.get("operating_margin") or 0) * 100
        rev_growth = (info.get("revenueGrowth") or 0) * 100

        is_growth_stage = (profit_m < 0 and rev_yoy > 15)
        if is_growth_stage:
            warnings.append(
                "EMPRESA EN FASE DE CRECIMIENTO/EXPANSIÓN: Las pérdidas actuales son "
                "consecuencia de la inversión agresiva en crecimiento (R&D, infraestructura, "
                "captación de clientes). En este estadio, evaluar por crecimiento de ingresos, "
                "posición de mercado y trayectoria hacia la rentabilidad, no por PER o márgenes."
            )

        if rev_yoy > 20:    positives.append(f"Crecimiento de ingresos excepcional: +{rev_yoy:.1f}% YoY")
        elif rev_yoy > 10:  positives.append(f"Crecimiento de ingresos sólido: +{rev_yoy:.1f}% YoY")
        if earn_yoy > 30:   positives.append(f"Beneficios creciendo a ritmo fuerte: +{earn_yoy:.1f}% YoY")
        elif earn_yoy > 0:  positives.append(f"Beneficios en crecimiento: +{earn_yoy:.1f}% YoY")
        if profit_m > 20:   positives.append(f"Margen neto excelente: {profit_m:.1f}%")
        elif profit_m > 10: positives.append(f"Margen neto saludable: {profit_m:.1f}%")
        if roe > 20:        positives.append(f"ROE muy elevado ({roe:.1f}%): alta eficiencia del capital")
        if fcf > 0:         positives.append("Free Cash Flow positivo: genera caja real")
        if op_m > 20:       positives.append(f"Margen operativo destacado: {op_m:.1f}%")
        if curr_ratio > 2:  positives.append(f"Balance muy líquido (Current Ratio: {curr_ratio:.1f}×)")
        if q_growth and q_growth > 10:
            positives.append(f"Aceleración QoQ: +{q_growth:.1f}% respecto al trimestre anterior")

        if profit_m < 0 and not is_growth_stage:
            negatives.append(f"Empresa con pérdidas netas ({profit_m:.1f}% margen)")
        if earn_yoy < -10:  negatives.append(f"Caída significativa de beneficios: {earn_yoy:.1f}% YoY")
        if rev_yoy < 0:     negatives.append(f"Contracción de ingresos: {rev_yoy:.1f}% YoY")
        if debt_eq > 200:   negatives.append(f"Deuda elevada: D/E {debt_eq:.0f}%")
        if curr_ratio < 1:  negatives.append(f"Liquidez ajustada (Current Ratio: {curr_ratio:.1f}×)")
        if fcf < 0:         negatives.append("Free Cash Flow negativo: consumiendo caja")
        if q_growth and q_growth < -10:
            negatives.append(f"Desaceleración QoQ: {q_growth:.1f}% vs trimestre anterior")

        if eps_surprise is not None:
            if eps_surprise > 5:
                positives.append(f"Batió expectativas de EPS en +{eps_surprise:.1f}%")
            elif eps_surprise < -5:
                negatives.append(f"Decepcionó expectativas de EPS en {eps_surprise:.1f}%")

        if rev_surprise is not None:
            if rev_surprise > 2:
                positives.append(f"Superó estimaciones de Revenue en +{rev_surprise:.1f}%")
            elif rev_surprise < -2:
                negatives.append(f"Revenue por debajo de estimaciones en {rev_surprise:.1f}%")

        beat_revenue = (rev_surprise > 0) if rev_surprise is not None else (rev_growth > 0 if rev_growth else None)

        return {
            "last_q_date":      last_q_date,
            "next_q_date":      next_q_date,
            "last_q_date_fmt":  last_q_date_fmt,
            "next_q_date_fmt":  next_q_date_fmt,
            "tiempo_desde":     tiempo_desde,
            "tiempo_hasta":     tiempo_hasta,
            "eps_estimate":     eps_estimate,
            "eps_actual":       eps_actual,
            "eps_surprise":     eps_surprise,
            "beat_eps":         beat_eps,
            "rev_estimate":     rev_estimate,
            "rev_actual":       rev_actual,
            "rev_surprise":     rev_surprise,
            "beat_revenue":     beat_revenue,
            "revenue_growth":   rev_growth,
            "q_growth":         q_growth,
            "positives":        positives[:6],
            "negatives":        negatives[:5],
            "warnings":         warnings,
            "is_growth_stage":  is_growth_stage,
        }
    except Exception as e:
        return {"error": str(e)}

# ─────────────────────────────────────────────────────────────────────────────
# SEÑAL DE CONFLUENCIA DE ENTRADA
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# MOMENTUM DE REVISIONES DE ANALISTAS
# ─────────────────────────────────────────────────────────────────────────────
# Cuando los analistas revisan al alza sus estimaciones de EPS para el
# trimestre en curso, suele preceder a subidas de precio (es uno de los
# factores con mejor track record histórico en estudios de factor investing —
# incorpora información no capturada por los múltiplos estáticos: guidance
# reciente de la empresa, cambios de expectativas sectoriales, etc.).
# Fuente: módulo earningsTrend de Yahoo Finance (quoteSummary).

_YAHOO_HEADERS_REV = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


def fetch_analyst_revisions(ticker: str) -> dict | None:
    """
    Obtiene el número de revisiones de EPS al alza vs a la baja en los
    últimos 30 días para el trimestre fiscal actual. Devuelve None si el
    dato no está disponible (no se penaliza al ticker por ello — el check
    correspondiente en la señal de entrada simplemente se omite).
    """
    cache_key = f"_analyst_revisions_cache_{ticker.upper()}"
    if cache_key in st.session_state:
        return st.session_state[cache_key]

    result = None
    try:
        url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker.upper()}"
        r = requests.get(url, params={"modules": "earningsTrend"},
                          headers=_YAHOO_HEADERS_REV, timeout=10)
        if r.status_code == 200:
            data      = r.json()
            qs_result = data.get("quoteSummary", {}).get("result", [])
            if qs_result:
                trends = qs_result[0].get("earningsTrend", {}).get("trend", [])
                # period "0q" = trimestre fiscal actual en curso
                current_q = next((t for t in trends if t.get("period") == "0q"), None)
                if current_q:
                    revisions = current_q.get("epsRevisions", {})
                    up_30   = (revisions.get("upLast30days")   or {}).get("raw")
                    down_30 = (revisions.get("downLast30days") or {}).get("raw")
                    if up_30 is not None or down_30 is not None:
                        result = {
                            "up_30d":   up_30 or 0,
                            "down_30d": down_30 or 0,
                        }
        else:
            print(f"[AnalystRevisions] {ticker}: HTTP {r.status_code}")
    except Exception as e:
        print(f"[AnalystRevisions] {ticker}: {e}")

    st.session_state[cache_key] = result
    return result


def calc_entry_signal(y: dict, tech: dict | None, ev: dict) -> dict:
    price       = y.get("price") or 0
    week52_high = y.get("52w_high") or price
    upside      = ev.get("upside")
    health      = ev.get("health_score", 0)

    rsi   = tech.get("rsi")   if tech and not tech.get("error") else None
    mm50  = tech.get("mm50")  if tech and not tech.get("error") else None
    mm200 = tech.get("mm200") if tech and not tech.get("error") else None

    checks = []

    if upside is not None:
        checks.append(("Margen de seguridad (upside > 10%)", upside >= 10,
            f"Upside estimado: {upside:+.1f}%", 3))

    if week52_high and price:
        dist = (week52_high - price) / week52_high * 100
        checks.append(("Alejado de máximos anuales (>10%)", dist >= 10,
            f"{dist:.1f}% por debajo del máximo 52W", 2))

    if rsi is not None:
        ok    = rsi < 50
        ideal = rsi < 40
        checks.append(("RSI en zona de compra (< 50)", ok,
            f"RSI = {rsi:.1f} ({'óptimo' if ideal else 'aceptable' if ok else 'elevado'})", 2))

    if mm200 is not None and price:
        ok = price < mm200
        checks.append(("Precio bajo MM200 (posible rebote)", ok,
            f"Precio {'bajo' if ok else 'sobre'} MM200 ({mm200:,.2f})", 2))

    checks.append(("Salud fundamental sólida (>55/100)", health >= 55,
        f"Score fundamental: {health}/100", 3))

    peg     = y.get("peg_ratio")
    peg_ref = ev.get("peg_ok", 1.5)
    if peg is not None:
        checks.append((f"PEG atractivo (< {peg_ref})", peg < peg_ref,
            f"PEG actual: {peg:.2f}", 2))

    fcf = y.get("free_cash_flow") or 0
    checks.append(("Free Cash Flow positivo", fcf > 0,
        "FCF positivo" if fcf > 0 else "FCF negativo", 1))

    if mm50 is not None and price:
        ok = price < mm50
        checks.append(("Corrección reciente (precio < MM50)", ok,
            f"Precio {'bajo' if ok else 'sobre'} MM50 ({mm50:,.2f})", 1))

    # Momentum de revisiones de analistas (30 días)
    revisions = y.get("analyst_revisions")
    if revisions:
        up   = revisions.get("up_30d", 0)
        down = revisions.get("down_30d", 0)
        if (up + down) > 0:
            ok = up > down
            checks.append(("Momentum revisiones analistas (30d)", ok,
                f"{up} al alza / {down} a la baja (EPS trimestre actual)", 2))

    total_w    = sum(c[3] for c in checks)
    achieved_w = sum(c[3] for c in checks if c[1])
    n_ok       = sum(1 for c in checks if c[1])
    score_pct  = (achieved_w / total_w * 100) if total_w else 0

    heavy_ok    = sum(1 for c in checks if c[1] and c[3] >= 2)
    heavy_total = sum(1 for c in checks if c[3] >= 2)

    if score_pct >= 80 and heavy_ok >= heavy_total - 1:
        level, color, icon = "ENTRADA IDEAL",   "#059669", "🟢"
        desc = "Confluencia fuerte: múltiples factores técnicos y fundamentales alineados."
    elif score_pct >= 60 and heavy_ok >= heavy_total // 2 + 1:
        level, color, icon = "ENTRADA POSIBLE", "#16a34a", "🟡"
        desc = "Buena confluencia, aunque no todos los factores clave están alineados."
    elif score_pct >= 40:
        level, color, icon = "VIGILAR",         "#d97706", "🟠"
        desc = "Algunos factores positivos, pero faltan condiciones clave para una entrada óptima."
    else:
        level, color, icon = "NO ES MOMENTO",   "#dc2626", "🔴"
        desc = "Pocos factores alineados. Esperar mejor precio, menor RSI o mejores fundamentales."

    MAX_POSSIBLE_CHECKS = 9   # margen, health, dist_max, RSI, MM50, MM200, PEG, FCF, corrección, revisiones (9 max)
    missing_checks = MAX_POSSIBLE_CHECKS - len(checks)
    reliability_ok = missing_checks <= 1   # tolerable perder 1 check (p.ej. PEG no aplicable)

    return {
        "level": level, "color": color, "icon": icon, "desc": desc,
        "score": round(score_pct), "n_ok": n_ok,
        "n_total": len(checks), "checks": checks,
        "missing_checks": missing_checks,
        "reliability_ok": reliability_ok,
    }

# ─────────────────────────────────────────────────────────────────────────────
# TENDENCIA TRIMESTRAL
# ─────────────────────────────────────────────────────────────────────────────

def calc_trend(y: dict | None) -> dict | None:
    """
    Prepara los datos para el apartado de TENDENCIA Y EVOLUCIÓN TRIMESTRAL.
    Muestra los valores ABSOLUTOS de Revenue y EPS de los últimos 4 trimestres
    (no variaciones YoY) para ver la trayectoria real trimestre a trimestre.
    """
    if not y:
        return None

    rev_q = y.get("ttm_quarters", []) or []
    eps_q = y.get("eps_q",         []) or []

    if len(rev_q) < 2:
        return None

    # Ordenar de más antiguo a más reciente y tomar últimos 4
    rev_sorted = sorted(rev_q, key=lambda x: x.get("date",""))[-4:]
    eps_sorted = sorted(eps_q, key=lambda x: x.get("date",""))[-4:] if eps_q else []

    # Calcular variación QoQ (para el semáforo de señal)
    def qoq_pct(series):
        out = []
        for i in range(1, len(series)):
            prev = series[i-1].get("value") or 0
            curr = series[i].get("value") or 0
            if prev and prev != 0:
                out.append(round((curr - prev) / abs(prev) * 100, 1))
        return out

    rev_changes = qoq_pct(rev_sorted)
    eps_changes = qoq_pct(eps_sorted)

    # Señal global basada en la tendencia reciente
    def streak_up(changes):
        if not changes: return 0
        s = 0
        for c in reversed(changes):
            if c > 0: s += 1
            else: break
        return s

    rev_streak = streak_up(rev_changes)
    eps_streak = streak_up(eps_changes)

    if rev_streak >= 2 and eps_streak >= 2:   sig = ("ACELERACIÓN",  "#059669")
    elif rev_streak >= 1 or eps_streak >= 1:  sig = ("MEJORANDO",    "#16a34a")
    elif sum(1 for c in rev_changes if c > 0) >= len(rev_changes) // 2:
        sig = ("ESTABLE", "#d97706")
    else:
        sig = ("DETERIORANDO", "#dc2626")

    return {
        "rev_quarters":  rev_sorted,
        "eps_quarters":  eps_sorted,
        "rev_changes":   rev_changes,
        "eps_changes":   eps_changes,
        "rev_streak":    rev_streak,
        "eps_streak":    eps_streak,
        "trend_signal":  sig,
        "total_q":       len(rev_sorted),
        "source":        "Yahoo Finance (trimestral)",
    }

# ─────────────────────────────────────────────────────────────────────────────
# ÚLTIMO CRUCE MM50/MM200
# ─────────────────────────────────────────────────────────────────────────────

def fetch_last_cross_date(ticker: str) -> dict:
    try:
        t    = yf.Ticker(ticker)
        hist = t.history(period="2y", interval="1d")
        if hist.empty or len(hist) < 200:
            return {}
        closes = hist["Close"]
        mm50   = closes.rolling(50).mean()
        mm200  = closes.rolling(200).mean()
        diff   = mm50 - mm200
        for i in range(len(diff)-1, 0, -1):
            if diff.iloc[i] > 0 and diff.iloc[i-1] <= 0:
                return {"date": _fmt_fecha_es(hist.index[i]), "type": "GOLDEN CROSS"}
            elif diff.iloc[i] < 0 and diff.iloc[i-1] >= 0:
                return {"date": _fmt_fecha_es(hist.index[i]), "type": "DEATH CROSS"}
        return {}
    except Exception:
        return {}

# ─────────────────────────────────────────────────────────────────────────────
# COMPETIDORES MANUALES — gestión y persistencia por ticker
# ─────────────────────────────────────────────────────────────────────────────
# La tabla de comparativa NO se rellena automáticamente: el usuario añade
# manualmente los tickers que considera competencia directa de la empresa
# analizada. Se guardan en un archivo JSON local que persiste mientras el
# contenedor de Streamlit Cloud no se redespliegue (sobrevive a recargas
# de página y a cierres de sesión del navegador, pero no a un nuevo deploy
# del código ni a un redeploy manual de la app).

_COMPETITORS_FILE = "/tmp/competitors_store.json"


def _load_competitors_store() -> dict:
    """Carga el almacén completo de competidores manuales desde disco."""
    if os.path.exists(_COMPETITORS_FILE):
        try:
            with open(_COMPETITORS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_competitors_store(store: dict):
    """Guarda el almacén completo de competidores manuales a disco."""
    try:
        with open(_COMPETITORS_FILE, "w", encoding="utf-8") as f:
            json.dump(store, f, indent=2)
    except Exception as e:
        print(f"[Competitors] Error al guardar: {e}")


def get_manual_competitors(ticker: str) -> list:
    """Devuelve la lista de tickers competidores guardados para esta empresa."""
    ticker = ticker.upper().strip()
    store = _load_competitors_store()
    return store.get(ticker, [])


def add_manual_competitor(ticker: str, competitor_ticker: str) -> bool:
    """
    Añade un competidor a la lista guardada para 'ticker'.
    Devuelve True si se añadió, False si ya existía o si es el mismo ticker.
    """
    ticker            = ticker.upper().strip()
    competitor_ticker = competitor_ticker.upper().strip()

    if not competitor_ticker or competitor_ticker == ticker:
        return False

    store = _load_competitors_store()
    current = store.get(ticker, [])
    if competitor_ticker in current:
        return False

    current.append(competitor_ticker)
    store[ticker] = current
    _save_competitors_store(store)
    return True


def remove_manual_competitor(ticker: str, competitor_ticker: str):
    """Elimina un competidor de la lista guardada para 'ticker'."""
    ticker            = ticker.upper().strip()
    competitor_ticker = competitor_ticker.upper().strip()

    store   = _load_competitors_store()
    current = store.get(ticker, [])
    if competitor_ticker in current:
        current.remove(competitor_ticker)
        store[ticker] = current
        _save_competitors_store(store)


def validate_ticker_exists(ticker: str) -> dict | None:
    """
    Verifica que un ticker existe en Yahoo Finance antes de añadirlo.
    Devuelve un dict básico con nombre si es válido, None si no existe.
    """
    try:
        t    = yf.Ticker(ticker.upper().strip())
        info = t.info
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        if not price:
            return None
        return {
            "ticker": ticker.upper().strip(),
            "name":   info.get("shortName") or info.get("longName") or ticker,
        }
    except Exception:
        return None


def render_competitor_manager(ticker: str):
    """
    Widget para añadir/eliminar competidores manuales de la empresa analizada.
    Se muestra dentro del apartado COMPARATIVA FRENTE A COMPETENCIA.
    """
    current = get_manual_competitors(ticker)

    with st.expander(
        f"➕ Gestionar competidores ({len(current)} añadidos)",
        expanded=(len(current) == 0)
    ):
        st.markdown(
            '<div style="font-size:0.78rem;color:#64748b;margin-bottom:0.6rem;">'
            'Añade los tickers que consideres competencia directa de esta empresa. '
            'Se guardan para futuras consultas de este mismo ticker.</div>',
            unsafe_allow_html=True
        )

        col1, col2 = st.columns([3, 1])
        with col1:
            new_comp = st.text_input(
                "Ticker del competidor",
                placeholder="ej. AMD, ASML, SNOW...",
                label_visibility="collapsed",
                key=f"new_comp_{ticker}"
            )
        with col2:
            add_clicked = st.button("Añadir", key=f"add_comp_{ticker}", use_container_width=True)

        if add_clicked and new_comp.strip():
            comp_clean = new_comp.strip().upper()
            if comp_clean == ticker.upper():
                st.warning("No puedes añadir la misma empresa como su propia competencia.")
            elif comp_clean in current:
                st.info(f"{comp_clean} ya está en la lista.")
            else:
                with st.spinner(f"Verificando {comp_clean}…"):
                    valid = validate_ticker_exists(comp_clean)
                if valid:
                    add_manual_competitor(ticker, comp_clean)
                    st.success(f"{comp_clean} ({valid['name']}) añadido como competidor.")
                    st.rerun()
                else:
                    st.error(f"No se encontró el ticker {comp_clean} en Yahoo Finance.")
        elif add_clicked:
            st.warning("Introduce un ticker.")

        if current:
            st.markdown(
                '<div style="font-size:0.7rem;color:#64748b;margin-top:0.6rem;margin-bottom:0.3rem;">'
                'Competidores guardados — pulsa para eliminar:</div>',
                unsafe_allow_html=True
            )
            del_cols = st.columns(min(len(current), 5))
            for i, comp in enumerate(current):
                with del_cols[i % len(del_cols)]:
                    if st.button(f"✕ {comp}", key=f"del_comp_{ticker}_{comp}", use_container_width=True):
                        remove_manual_competitor(ticker, comp)
                        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# COMPETIDORES — descarga de datos
# ─────────────────────────────────────────────────────────────────────────────

def fetch_peer_data(peers: list) -> list:
    results = []
    for ticker in peers:
        try:
            t    = yf.Ticker(ticker)
            info = t.info
            if not info: continue
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            if not price: continue
            results.append({
                "ticker":    ticker,
                "name":      (info.get("shortName") or ticker)[:22],
                "price":     price,
                "pe_forward":info.get("forwardPE"),
                "peg":       info.get("pegRatio"),
                "ev_ebitda": info.get("enterpriseToEbitda"),
                "profit_m":  (info.get("profitMargins") or 0) * 100,
                "roe":       (info.get("returnOnEquity") or 0) * 100,
                "rev_growth":(info.get("revenueGrowth") or 0) * 100,
                "market_cap":info.get("marketCap"),
            })
            time.sleep(0.1)
        except Exception:
            continue
    return results

# ─────────────────────────────────────────────────────────────────────────────
# RENDER — DESCRIPCIÓN DE LA EMPRESA
# ─────────────────────────────────────────────────────────────────────────────

def render_company_description(company_info: dict, company_name: str):
    st.markdown('<div class="section-header">DESCRIPCIÓN DE LA EMPRESA</div>', unsafe_allow_html=True)
    if not company_info or not company_info.get("description"):
        st.markdown('<div class="metric-card"><span style="color:#64748b;">Descripción no disponible.</span></div>', unsafe_allow_html=True)
        return

    desc      = company_info.get("description","")
    industry  = company_info.get("industry","")
    country   = company_info.get("country","")
    employees = company_info.get("employees")
    website   = company_info.get("website","")
    emp_str   = f"{employees:,}" if employees else "N/A"
    web_html  = f'<a href="{website}" target="_blank" style="color:#0284c7;">{website}</a>' if website else "N/A"
    desc_short = desc if len(desc) <= 1000 else desc[:1000] + "…"
    insiders   = company_info.get("insiders", [])
    fcf_q      = company_info.get("fcf_quality")

    tags = ""
    if industry:  tags += f'<span style="background:#334155;color:#64748b;padding:2px 9px;border-radius:4px;font-size:0.75rem;margin-right:0.4rem;">{industry}</span>'
    if country:   tags += f'<span style="background:#334155;color:#64748b;padding:2px 9px;border-radius:4px;font-size:0.75rem;margin-right:0.4rem;">🌍 {country}</span>'
    if employees: tags += f'<span style="background:#334155;color:#64748b;padding:2px 9px;border-radius:4px;font-size:0.75rem;">👥 {emp_str} empleados</span>'

    # Calidad del beneficio
    fcf_html = ""
    if fcf_q is not None:
        if fcf_q >= 0.9:
            fcf_col = "#059669"
            fcf_lbl = "Beneficio de alta calidad — se convierte en caja real"
        elif fcf_q >= 0.5:
            fcf_col = "#d97706"
            fcf_lbl = "Calidad moderada — parte del beneficio no es caja"
        elif fcf_q >= 0:
            fcf_col = "#ea580c"
            fcf_lbl = "Calidad baja — beneficio contable supera al FCF"
        else:
            fcf_col = "#dc2626"
            fcf_lbl = "FCF negativo — cuidado con la calidad del beneficio"
        tip_fcf_q = (
            'Calidad del beneficio = FCF / Beneficio Neto. '
            'Mide cuánto del beneficio contable se convierte en caja real. '
            'Valores: >0.9 = alta calidad (el beneficio es real y cobrable). '
            '0.5-0.9 = calidad moderada. '
            '<0.5 = calidad baja (ajustes contables inflan el beneficio). '
            '<0 = FCF negativo (la empresa consume más caja de la que genera). '
            'Un ratio persistentemente bajo puede indicar contabilidad agresiva.'
        )
        tip_html = (
            f'<span title="{tip_fcf_q}" style="margin-left:0.3rem;cursor:help;'
            f'font-size:0.6rem;color:#94a3b8;border:1px solid #cbd5e1;'
            f'border-radius:50%;padding:0 3px;font-family:monospace;'
            f'vertical-align:middle;">?</span>'
        )
        fcf_html = (
            f'<div style="margin-top:0.7rem;padding:0.5rem 0.7rem;background:#f4f6f9;border-radius:6px;'
            f'border-left:3px solid {fcf_col};">'
            f'<span style="font-size:0.7rem;color:#64748b;text-transform:uppercase;letter-spacing:0.06em;">'
            f'Calidad del beneficio (FCF/Net Income){tip_html}</span><br>'
            f'<span style="font-family:\'IBM Plex Mono\',monospace;color:{fcf_col};font-weight:700;">{fcf_q:.2f}×</span>'
            f'<span style="font-size:0.78rem;color:{fcf_col};margin-left:0.5rem;">{fcf_lbl}</span>'
            f'</div>'
        )

    st.markdown(
        '<div class="metric-card">'
        f'<div style="margin-bottom:0.7rem;">{tags}</div>'
        f'<div style="font-size:0.85rem;color:#94a3b8;line-height:1.75;">{desc_short}</div>'
        f'{fcf_html}'
        f'<div style="margin-top:0.6rem;font-size:0.75rem;color:#64748b;">🌐 {web_html}</div>'
        '</div>',
        unsafe_allow_html=True
    )

    # Insider transactions
    if insiders:
        buys  = [i for i in insiders if i["is_buy"]]
        sells = [i for i in insiders if i["is_sell"]]
        net_signal = ""
        if len(buys) > len(sells) * 1.5:
            net_signal = '<span style="color:#059669;font-weight:700;">🟢 SEÑAL ALCISTA — más compras que ventas de insiders</span>'
        elif len(sells) > len(buys) * 2:
            net_signal = '<span style="color:#dc2626;font-weight:700;">🔴 SEÑAL BAJISTA — ventas significativas de insiders</span>'
        else:
            net_signal = '<span style="color:#64748b;">Actividad mixta de insiders</span>'

        rows_ins = ""
        for ins in insiders[:8]:
            col  = "#059669" if ins["is_buy"] else "#dc2626" if ins["is_sell"] else "#64748b"
            icon = "▲" if ins["is_buy"] else "▼" if ins["is_sell"] else "—"
            val_str = f"${ins['value']/1e6:.1f}M" if ins["value"] > 1e6 else (f"${ins['value']:,.0f}" if ins["value"] else "")
            rows_ins += (
                f'<div style="display:grid;grid-template-columns:0.8fr 2fr 2fr 1fr;gap:0.3rem;'
                f'padding:0.3rem 0;border-bottom:1px solid #eef1f5;font-size:0.76rem;">'
                f'<span style="color:{col};font-weight:700;">{icon} {ins["date"]}</span>'
                f'<span style="color:#64748b;">{ins["relation"]}</span>'
                f'<span style="color:#1e293b;">{ins["text"]}</span>'
                f'<span style="font-family:\'IBM Plex Mono\',monospace;color:{col};text-align:right;">{val_str}</span>'
                f'</div>'
            )

        st.markdown(
            '<div class="metric-card" style="border-left:3px solid #cbd5e1;">'
            '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.6rem;">'
            '<span style="font-size:0.7rem;color:#0284c7;text-transform:uppercase;letter-spacing:0.1em;">Transacciones de Insiders (últimas)</span>'
            f'<span style="font-size:0.78rem;">{net_signal}</span>'
            '</div>'
            f'{rows_ins}'
            '<div style="font-size:0.68rem;color:#94a3b8;margin-top:0.4rem;">Fuente: Yahoo Finance · Las compras de insiders son señal alcista frecuente</div>'
            '</div>',
            unsafe_allow_html=True
        )

# ─────────────────────────────────────────────────────────────────────────────
# RENDER — NOTICIAS RECIENTES
# ─────────────────────────────────────────────────────────────────────────────

def render_news(news_items: list):
    st.markdown('<div class="section-header">NOTICIAS Y ANUNCIOS RECIENTES (últimos 3 meses)</div>', unsafe_allow_html=True)
    if not news_items:
        st.markdown('<div class="metric-card"><span style="color:#64748b;">No se encontraron noticias recientes.</span></div>', unsafe_allow_html=True)
        return

    rows = ""
    for n in news_items:
        title     = n.get("title","")[:130]
        publisher = n.get("publisher","")
        date      = n.get("date","")
        url       = n.get("url","")
        link_open = f'<a href="{url}" target="_blank" style="text-decoration:none;color:inherit;">' if url else ""
        link_close= "</a>" if url else ""
        rows += (
            '<div style="padding:0.55rem 0;border-bottom:1px solid #eef1f5;">'
            '<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:0.6rem;">'
            f'<div style="flex:1;">{link_open}'
            f'<span style="font-size:0.83rem;color:#1e293b;line-height:1.55;">{title}</span>'
            f'{link_close}</div>'
            f'<span style="font-family:\'IBM Plex Mono\',monospace;font-size:0.72rem;color:#0284c7;white-space:nowrap;margin-top:2px;">{date}</span>'
            '</div>'
            f'<div style="font-size:0.72rem;color:#94a3b8;margin-top:0.15rem;">{publisher}</div>'
            '</div>'
        )

    st.markdown(f'<div class="metric-card">{rows}</div>', unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# RENDER — ANÁLISIS DE RESULTADOS
# ─────────────────────────────────────────────────────────────────────────────

def render_earnings_analysis(ea: dict):
    st.markdown('<div class="section-header">ANÁLISIS DE ÚLTIMOS RESULTADOS</div>', unsafe_allow_html=True)
    if not ea or ea.get("error"):
        st.markdown('<div class="metric-card"><span style="color:#64748b;">Datos de resultados no disponibles.</span></div>', unsafe_allow_html=True)
        return

    last_q_fmt   = ea.get("last_q_date_fmt","N/A")
    next_q_fmt   = ea.get("next_q_date_fmt","N/A")
    tiempo_desde = ea.get("tiempo_desde","")
    tiempo_hasta = ea.get("tiempo_hasta","")
    pos          = ea.get("positives",[])
    neg          = ea.get("negatives",[])
    warns        = ea.get("warnings",[])
    beat_eps     = ea.get("beat_eps")
    eps_est      = ea.get("eps_estimate")
    eps_act      = ea.get("eps_actual")
    eps_surprise = ea.get("eps_surprise")
    beat_revenue = ea.get("beat_revenue")
    rev_growth   = ea.get("revenue_growth")

    # Aviso empresa en crecimiento
    warn_html = ""
    for w in warns:
        warn_html += (
            '<div style="background:#fffbeb;border:1px solid #d97706;border-left:4px solid #d97706;'
            'border-radius:6px;padding:0.7rem 0.9rem;margin-bottom:0.8rem;">'
            '<div style="color:#d97706;font-weight:700;font-size:0.8rem;margin-bottom:0.3rem;">'
            '⚡ EMPRESA EN FASE DE CRECIMIENTO / EXPANSIÓN</div>'
            f'<div style="color:#92400e;font-size:0.78rem;line-height:1.6;">{w}</div>'
            '</div>'
        )

    # Fechas con formato español y tiempo transcurrido/restante
    desde_str = f' <span style="color:#94a3b8;">(hace {tiempo_desde})</span>' if tiempo_desde else ""
    hasta_str = f' <span style="color:#94a3b8;">(en {tiempo_hasta})</span>' if tiempo_hasta else ""

    dates_html = (
        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:0.5rem;margin-bottom:0.8rem;">'
        '<div style="background:#f4f6f9;border-radius:6px;padding:0.6rem 0.8rem;">'
        '<div style="font-size:0.68rem;color:#64748b;text-transform:uppercase;">Última presentación</div>'
        f'<div style="font-size:0.92rem;color:#0f172a;font-weight:600;">{last_q_fmt}</div>'
        f'<div style="font-size:0.74rem;margin-top:0.15rem;">{desde_str}</div>'
        '</div>'
        '<div style="background:#f4f6f9;border-radius:6px;padding:0.6rem 0.8rem;">'
        '<div style="font-size:0.68rem;color:#64748b;text-transform:uppercase;">Próxima presentación</div>'
        f'<div style="font-size:0.92rem;color:#0284c7;font-weight:600;">{next_q_fmt}</div>'
        f'<div style="font-size:0.74rem;margin-top:0.15rem;">{hasta_str}</div>'
        '</div>'
        '</div>'
    )

    # Tabla de expectativas EPS y Revenue vs reportado
    def _beat_badge(beat):
        if beat is True:
            return '<span style="background:#d1fae5;color:#059669;padding:2px 9px;border-radius:4px;font-size:0.72rem;font-weight:700;">✔ SUPERÓ</span>'
        elif beat is False:
            return '<span style="background:#fee2e2;color:#dc2626;padding:2px 9px;border-radius:4px;font-size:0.72rem;font-weight:700;">✘ NO ALCANZÓ</span>'
        return '<span style="background:#334155;color:#64748b;padding:2px 9px;border-radius:4px;font-size:0.72rem;">N/A</span>'

    def _fmt_rev(v):
        if v is None: return "N/A"
        v = float(v)
        if abs(v) >= 1e12: return f"${v/1e12:.2f}T"
        if abs(v) >= 1e9:  return f"${v/1e9:.2f}B"
        if abs(v) >= 1e6:  return f"${v/1e6:.1f}M"
        return f"${v:,.0f}"

    eps_est_str  = f"${eps_est:.2f}"     if eps_est is not None     else "N/A"
    eps_act_str  = f"${eps_act:.2f}"     if eps_act is not None     else "N/A"
    eps_surp_str = f"{eps_surprise:+.2f}%" if eps_surprise is not None else "N/A"
    surp_color   = "#059669" if (eps_surprise or 0) >= 0 else "#dc2626"

    # Revenue: si Finnhub dio estimado y real, los mostramos en valor absoluto
    rev_est      = ea.get("rev_estimate")
    rev_act      = ea.get("rev_actual")
    rev_surp     = ea.get("rev_surprise")

    if rev_act is not None:
        # Datos de Finnhub — estimado y real absolutos
        rev_est_str  = _fmt_rev(rev_est)
        rev_act_str  = _fmt_rev(rev_act)
        rev_surp_str = f"{rev_surp:+.2f}%" if rev_surp is not None else "N/A"
        rev_color    = "#059669" if (rev_surp or 0) >= 0 else "#dc2626"
        rev_source   = "Fuente: Finnhub · Estimado = consenso de analistas previo a la presentación"
    else:
        # Fallback — solo crecimiento YoY
        rev_growth   = ea.get("revenue_growth")
        rev_est_str  = "—"
        rev_act_str  = f"{rev_growth:+.1f}% YoY" if rev_growth is not None else "N/A"
        rev_surp_str = "—"
        rev_color    = "#059669" if (rev_growth or 0) >= 0 else "#dc2626"
        rev_source   = "Revenue: estimado de consenso no disponible · Se muestra variación YoY"

    expect_html = (
        '<div style="margin-bottom:0.8rem;">'
        '<div style="font-size:0.7rem;color:#0284c7;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:0.4rem;">'
        'Expectativas del mercado vs resultado real</div>'
        '<table style="width:100%;border-collapse:collapse;">'
        '<thead><tr style="border-bottom:1px solid #e2e8f0;">'
        '<th style="text-align:left;padding:0.3rem 0.5rem;font-size:0.68rem;color:#64748b;text-transform:uppercase;">Métrica</th>'
        '<th style="text-align:right;padding:0.3rem 0.5rem;font-size:0.68rem;color:#64748b;text-transform:uppercase;">Estimado</th>'
        '<th style="text-align:right;padding:0.3rem 0.5rem;font-size:0.68rem;color:#64748b;text-transform:uppercase;">Reportado</th>'
        '<th style="text-align:right;padding:0.3rem 0.5rem;font-size:0.68rem;color:#64748b;text-transform:uppercase;">Sorpresa</th>'
        '<th style="text-align:center;padding:0.3rem 0.5rem;font-size:0.68rem;color:#64748b;text-transform:uppercase;">Resultado</th>'
        '</tr></thead><tbody>'
        '<tr style="border-bottom:1px solid #eef1f5;">'
        '<td style="padding:0.4rem 0.5rem;font-size:0.82rem;color:#1e293b;">EPS</td>'
        f'<td style="padding:0.4rem 0.5rem;text-align:right;font-family:\'IBM Plex Mono\',monospace;color:#64748b;">{eps_est_str}</td>'
        f'<td style="padding:0.4rem 0.5rem;text-align:right;font-family:\'IBM Plex Mono\',monospace;color:#0f172a;font-weight:600;">{eps_act_str}</td>'
        f'<td style="padding:0.4rem 0.5rem;text-align:right;font-family:\'IBM Plex Mono\',monospace;color:{surp_color};font-weight:600;">{eps_surp_str}</td>'
        f'<td style="padding:0.4rem 0.5rem;text-align:center;">{_beat_badge(beat_eps)}</td>'
        '</tr>'
        '<tr>'
        '<td style="padding:0.4rem 0.5rem;font-size:0.82rem;color:#1e293b;">Revenue</td>'
        f'<td style="padding:0.4rem 0.5rem;text-align:right;font-family:\'IBM Plex Mono\',monospace;color:#64748b;">{rev_est_str}</td>'
        f'<td style="padding:0.4rem 0.5rem;text-align:right;font-family:\'IBM Plex Mono\',monospace;color:{rev_color};font-weight:600;">{rev_act_str}</td>'
        f'<td style="padding:0.4rem 0.5rem;text-align:right;font-family:\'IBM Plex Mono\',monospace;color:{rev_color};font-weight:600;">{rev_surp_str}</td>'
        f'<td style="padding:0.4rem 0.5rem;text-align:center;">{_beat_badge(beat_revenue)}</td>'
        '</tr>'
        '</tbody></table>'
        f'<div style="font-size:0.68rem;color:#94a3b8;margin-top:0.4rem;">{rev_source}</div>'
        '</div>'

    )

    # Puntos positivos
    pos_html = ""
    if pos:
        items = "".join(
            f'<div style="display:flex;gap:0.5rem;padding:0.3rem 0;border-bottom:1px solid #eef1f5;font-size:0.8rem;">'
            f'<span style="color:#059669;min-width:1rem;">✔</span>'
            f'<span style="color:#1e293b;">{p}</span></div>'
            for p in pos
        )
        pos_html = (
            '<div style="margin-bottom:0.6rem;">'
            '<div style="font-size:0.7rem;color:#059669;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:0.3rem;">Puntos positivos</div>'
            f'{items}</div>'
        )

    # Puntos negativos
    neg_html = ""
    if neg:
        items = "".join(
            f'<div style="display:flex;gap:0.5rem;padding:0.3rem 0;border-bottom:1px solid #eef1f5;font-size:0.8rem;">'
            f'<span style="color:#dc2626;min-width:1rem;">✘</span>'
            f'<span style="color:#1e293b;">{n}</span></div>'
            for n in neg
        )
        neg_html = (
            '<div style="margin-bottom:0.6rem;">'
            '<div style="font-size:0.7rem;color:#dc2626;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:0.3rem;">Puntos a vigilar</div>'
            f'{items}</div>'
        )

    st.markdown(
        '<div class="metric-card">'
        f'{warn_html}{dates_html}{expect_html}{pos_html}{neg_html}'
        '</div>',
        unsafe_allow_html=True
    )


# ─────────────────────────────────────────────────────────────────────────────
# RENDER — HISTÓRICO DE RESULTADOS (estilo StockTwits)
# ─────────────────────────────────────────────────────────────────────────────

def render_earnings_history(history: list):
    st.markdown(
        '<div class="section-header">HISTÓRICO DE RESULTADOS</div>',
        unsafe_allow_html=True
    )

    if not history:
        st.markdown(
            '<div class="metric-card"><span style="color:#64748b;">'
            'Histórico de resultados no disponible para este ticker.</span></div>',
            unsafe_allow_html=True
        )
        return

    # Detectar si tenemos datos de Revenue (Finnhub los proporciona)
    has_revenue = any(h.get("rev_actual") is not None for h in history)

    def badge(result):
        if result == "BEAT":
            return '<span style="background:#d1fae5;color:#059669;padding:3px 10px;border-radius:4px;font-size:0.7rem;font-weight:700;">BEAT</span>'
        elif result == "MISSED":
            return '<span style="background:#fee2e2;color:#dc2626;padding:3px 10px;border-radius:4px;font-size:0.7rem;font-weight:700;">MISSED</span>'
        elif result == "MET":
            return '<span style="background:#334155;color:#d97706;padding:3px 10px;border-radius:4px;font-size:0.7rem;font-weight:700;">MET</span>'
        return '<span style="background:#334155;color:#64748b;padding:3px 10px;border-radius:4px;font-size:0.7rem;">N/A</span>'

    def fmt_rev(v):
        if v is None: return "--"
        v = float(v)
        if abs(v) >= 1e12: return f"${v/1e12:.2f}T"
        if abs(v) >= 1e9:  return f"${v/1e9:.2f}B"
        if abs(v) >= 1e6:  return f"${v/1e6:.1f}M"
        return f"${v:,.0f}"

    if has_revenue:
        # Tabla expandida con EPS + Revenue
        grid  = "0.7fr 0.9fr 0.9fr 0.7fr 1fr 1fr 0.7fr 0.8fr"
        hdr = (
            '<div style="display:grid;grid-template-columns:{g};gap:0.3rem;'
            'padding:0.3rem 0;border-bottom:1px solid #e2e8f0;margin-bottom:0.2rem;">'.format(g=grid)
            + '<span style="font-size:0.62rem;color:#94a3b8;text-transform:uppercase;">Periodo</span>'
            + '<span style="font-size:0.62rem;color:#94a3b8;text-transform:uppercase;text-align:right;">EPS Est.</span>'
            + '<span style="font-size:0.62rem;color:#94a3b8;text-transform:uppercase;text-align:right;">EPS Real</span>'
            + '<span style="font-size:0.62rem;color:#94a3b8;text-transform:uppercase;text-align:right;">EPS %</span>'
            + '<span style="font-size:0.62rem;color:#94a3b8;text-transform:uppercase;text-align:right;">Rev. Est.</span>'
            + '<span style="font-size:0.62rem;color:#94a3b8;text-transform:uppercase;text-align:right;">Rev. Real</span>'
            + '<span style="font-size:0.62rem;color:#94a3b8;text-transform:uppercase;text-align:right;">Rev. %</span>'
            + '<span style="font-size:0.62rem;color:#94a3b8;text-transform:uppercase;text-align:center;">Resultado</span>'
            + '</div>'
        )
        rows = ""
        for h in history:
            eps_est = f"${h['eps_estimate']:.2f}" if h.get("eps_estimate") is not None else "--"
            eps_rep = f"${h['eps_reported']:.2f}" if h.get("eps_reported") is not None else "--"
            eps_s   = f"{h['surprise_pct']:+.1f}%" if h.get("surprise_pct") is not None else "--"
            eps_c   = "#059669" if (h.get("surprise_pct") or 0) >= 0 else "#dc2626"
            r_est   = fmt_rev(h.get("rev_estimate"))
            r_act   = fmt_rev(h.get("rev_actual"))
            r_s     = f"{h['rev_surprise']:+.1f}%" if h.get("rev_surprise") is not None else "--"
            r_c     = "#059669" if (h.get("rev_surprise") or 0) >= 0 else "#dc2626"
            rows += (
                f'<div style="display:grid;grid-template-columns:{grid};gap:0.3rem;'
                f'padding:0.45rem 0;border-bottom:1px solid #eef1f5;align-items:center;">'
                f'<span style="font-family:\'IBM Plex Mono\',monospace;font-size:0.82rem;color:#0f172a;font-weight:600;">{h["fiscal_label"]}</span>'
                f'<span style="font-family:\'IBM Plex Mono\',monospace;font-size:0.78rem;color:#64748b;text-align:right;">{eps_est}</span>'
                f'<span style="font-family:\'IBM Plex Mono\',monospace;font-size:0.78rem;color:#1e293b;text-align:right;">{eps_rep}</span>'
                f'<span style="font-family:\'IBM Plex Mono\',monospace;font-size:0.78rem;color:{eps_c};text-align:right;font-weight:600;">{eps_s}</span>'
                f'<span style="font-family:\'IBM Plex Mono\',monospace;font-size:0.78rem;color:#64748b;text-align:right;">{r_est}</span>'
                f'<span style="font-family:\'IBM Plex Mono\',monospace;font-size:0.78rem;color:#1e293b;text-align:right;">{r_act}</span>'
                f'<span style="font-family:\'IBM Plex Mono\',monospace;font-size:0.78rem;color:{r_c};text-align:right;font-weight:600;">{r_s}</span>'
                f'<span style="text-align:center;">{badge(h.get("result","N/A"))}</span>'
                f'</div>'
            )
        source = "Fuente: Finnhub · Estimado = consenso de analistas previo a la presentación · Sorpresa: % diferencia estimado/real"
    else:
        # Tabla simple solo EPS
        grid = "1fr 1.2fr 1.2fr 1fr 0.9fr"
        hdr = (
            '<div style="display:grid;grid-template-columns:{g};gap:0.4rem;'
            'padding:0.3rem 0;border-bottom:1px solid #e2e8f0;margin-bottom:0.2rem;">'.format(g=grid)
            + '<span style="font-size:0.66rem;color:#94a3b8;text-transform:uppercase;">Periodo</span>'
            + '<span style="font-size:0.66rem;color:#94a3b8;text-transform:uppercase;text-align:right;">EPS Est.</span>'
            + '<span style="font-size:0.66rem;color:#94a3b8;text-transform:uppercase;text-align:right;">EPS Real</span>'
            + '<span style="font-size:0.66rem;color:#94a3b8;text-transform:uppercase;text-align:right;">Sorpresa</span>'
            + '<span style="font-size:0.66rem;color:#94a3b8;text-transform:uppercase;text-align:center;">Resultado</span>'
            + '</div>'
        )
        rows = ""
        for h in history:
            est   = f"${h['eps_estimate']:.2f}" if h.get("eps_estimate") is not None else "--"
            rep   = f"${h['eps_reported']:.2f}" if h.get("eps_reported") is not None else "--"
            surp  = f"{h['surprise_pct']:+.2f}%" if h.get("surprise_pct") is not None else "--"
            surp_c = "#059669" if (h.get("surprise_pct") or 0) >= 0 else "#dc2626"
            rows += (
                f'<div style="display:grid;grid-template-columns:{grid};gap:0.4rem;'
                f'padding:0.5rem 0;border-bottom:1px solid #eef1f5;align-items:center;">'
                f'<span style="font-family:\'IBM Plex Mono\',monospace;font-size:0.85rem;color:#0f172a;font-weight:600;">{h["fiscal_label"]}</span>'
                f'<span style="font-family:\'IBM Plex Mono\',monospace;font-size:0.82rem;color:#64748b;text-align:right;">{est}</span>'
                f'<span style="font-family:\'IBM Plex Mono\',monospace;font-size:0.82rem;color:#1e293b;text-align:right;">{rep}</span>'
                f'<span style="font-family:\'IBM Plex Mono\',monospace;font-size:0.82rem;color:{surp_c};text-align:right;font-weight:600;">{surp}</span>'
                f'<span style="text-align:center;">{badge(h.get("result","N/A"))}</span>'
                f'</div>'
            )
        source = "Fuente: yfinance · Estimado = consenso de analistas · Revenue no disponible en esta fuente"

    st.markdown(
        f'<div class="metric-card">{hdr}{rows}'
        f'<div style="font-size:0.68rem;color:#94a3b8;margin-top:0.5rem;">{source}</div>'
        f'</div>',
        unsafe_allow_html=True
    )

# ─────────────────────────────────────────────────────────────────────────────
# RENDER — SEÑAL DE CONFLUENCIA
# ─────────────────────────────────────────────────────────────────────────────

def render_entry_signal(signal: dict):
    st.markdown('<div class="section-header">SEÑAL DE ENTRADA</div>', unsafe_allow_html=True)

    score   = signal["score"]
    level   = signal["level"]
    color   = signal["color"]
    icon    = signal["icon"]
    desc    = signal["desc"]
    n_ok    = signal["n_ok"]
    n_total = signal["n_total"]
    checks  = signal["checks"]
    missing = signal.get("missing_checks", 0)
    rel_ok  = signal.get("reliability_ok", True)

    if not rel_ok:
        st.markdown(
            f'<div style="background:#f4f6f9;border:1px solid #d97706;border-left:4px solid #d97706;'
            f'border-radius:6px;padding:0.6rem 0.9rem;margin-bottom:0.6rem;font-size:0.78rem;'
            f'color:#d97706;line-height:1.6;">'
            f'⚠ FIABILIDAD REDUCIDA: solo se pudieron evaluar {n_total} de 9 criterios posibles '
            f'por falta de datos (técnico, valoración o fundamentales). El score puede no ser '
            f'representativo — interpreta esta señal con cautela adicional.</div>',
            unsafe_allow_html=True
        )

    rows = ""
    for name, ok, detail, weight in checks:
        dot_color = color if ok else "#d1d9e0"
        dot       = "●" if ok else "○"
        w_dots    = "●" * weight
        rows += (
            '<div style="display:flex;align-items:flex-start;gap:0.6rem;padding:0.35rem 0;'
            'border-bottom:1px solid #eef1f5;font-size:0.82rem;">'
            f'<span style="color:{dot_color};font-size:1rem;min-width:1rem;">{dot}</span>'
            '<div style="flex:1;">'
            f'<span style="color:{"#0f172a" if ok else "#64748b"};">{name}</span>'
            f'<span style="color:#64748b;font-size:0.74rem;margin-left:0.4rem;">({detail})</span>'
            '</div>'
            f'<span style="color:#0ea5e9;font-size:0.65rem;min-width:2rem;text-align:right;">{w_dots}</span>'
            '</div>'
        )

    st.markdown(
        f'<div style="background:#f4f6f9;border:2px solid {color};border-radius:10px;padding:1.2rem 1.4rem;margin-bottom:1rem;">'
        '<div style="display:flex;align-items:center;gap:0.8rem;margin-bottom:0.8rem;">'
        f'<span style="font-size:1.5rem;">{icon}</span>'
        '<div>'
        f'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:1.05rem;font-weight:700;color:{color};">{level}</div>'
        f'<div style="font-size:0.8rem;color:#64748b;margin-top:0.1rem;">{desc}</div>'
        '</div>'
        '<div style="margin-left:auto;text-align:right;">'
        f'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:1.8rem;font-weight:700;color:{color};">'
        f'{score}<span style="font-size:1rem;color:#64748b;">/100</span></div>'
        f'<div style="font-size:0.72rem;color:#64748b;">{n_ok}/{n_total} criterios</div>'
        '</div></div>'
        f'<div style="background:#334155;border-radius:4px;height:6px;margin-bottom:1rem;">'
        f'<div style="height:6px;border-radius:4px;background:{color};width:{score}%;"></div></div>'
        '<div style="font-size:0.68rem;color:#0284c7;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:0.3rem;">'
        'DESGLOSE DE FACTORES</div>'
        f'{rows}</div>',
        unsafe_allow_html=True
    )

# ─────────────────────────────────────────────────────────────────────────────
# RENDER — TENDENCIA TRIMESTRAL
# ─────────────────────────────────────────────────────────────────────────────

def render_trend(trend: dict | None, yahoo_quarters: list | None = None):
    """
    Renderiza TENDENCIA Y EVOLUCIÓN TRIMESTRAL.
    Muestra barras con valores absolutos de Revenue y EPS por trimestre,
    coloreando cada barra según si sube o baja respecto al trimestre anterior.
    """
    st.markdown(
        '<div class="section-header">TENDENCIA Y EVOLUCIÓN TRIMESTRAL</div>',
        unsafe_allow_html=True
    )

    if not trend:
        st.markdown(
            '<div class="metric-card"><span style="color:#64748b;">'
            'Datos insuficientes para calcular tendencia trimestral.</span></div>',
            unsafe_allow_html=True
        )
        return

    sig_label, sig_color = trend["trend_signal"]
    rev_q = trend.get("rev_quarters", [])
    eps_q = trend.get("eps_quarters", [])

    def fmt_val(v, is_eps=False):
        """Formatea valores para etiquetas de barra."""
        if v is None: return "—"
        if is_eps:
            return f"${v:.2f}"
        v = float(v)
        if abs(v) >= 1e12: return f"${v/1e12:.2f}T"
        if abs(v) >= 1e9:  return f"${v/1e9:.1f}B"
        if abs(v) >= 1e6:  return f"${v/1e6:.0f}M"
        return f"${v:,.0f}"

    def abs_bars(quarters: list, label: str, is_eps: bool = False,
                 c_up: str = "#059669", c_down: str = "#dc2626",
                 c_neutral: str = "#0284c7") -> str:
        """
        Genera barras verticales con valores absolutos.
        La altura es proporcional al valor. El color indica si subió/bajó vs trimestre anterior.
        """
        if not quarters:
            return ""

        values = [q.get("value") for q in quarters]
        # Filtrar None y calcular max para escala
        valid = [abs(v) for v in values if v is not None]
        if not valid:
            return ""
        max_v = max(valid) or 1

        bars = ""
        for i, q in enumerate(quarters):
            v    = q.get("value")
            date = q.get("date","")[:7]
            if v is None:
                bars += (
                    '<div style="display:flex;flex-direction:column;align-items:center;'
                    'gap:0.15rem;flex:1;">'
                    '<div style="font-size:0.68rem;color:#d1d9e0;">—</div>'
                    '<div style="height:80px;"></div>'
                    f'<div style="font-size:0.62rem;color:#64748b;">{date}</div>'
                    '</div>'
                )
                continue

            h   = max(int(abs(v) / max_v * 80), 4)
            # Color: verde si sube vs anterior, rojo si baja, azul para el primero
            if i == 0:
                col = c_neutral
            elif values[i-1] is not None:
                col = c_up if v >= values[i-1] else c_down
            else:
                col = c_neutral

            # Mostrar variación QoQ como texto pequeño sobre la barra
            qoq_str = ""
            if i > 0 and values[i-1] is not None and values[i-1] != 0:
                qoq = (v - values[i-1]) / abs(values[i-1]) * 100
                sign = "+" if qoq >= 0 else ""
                qoq_str = f'<div style="font-size:0.6rem;color:{col};margin-bottom:0.1rem;">{sign}{qoq:.0f}%</div>'

            bars += (
                '<div style="display:flex;flex-direction:column;align-items:center;'
                'gap:0.1rem;flex:1;">'
                f'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:0.68rem;'
                f'color:{col};font-weight:600;">{fmt_val(v, is_eps)}</div>'
                f'{qoq_str}'
                '<div style="height:80px;display:flex;align-items:flex-end;width:100%;">'
                f'<div style="width:100%;height:{h}px;background:{col};'
                f'border-radius:3px 3px 0 0;min-height:4px;"></div>'
                '</div>'
                f'<div style="font-size:0.62rem;color:#64748b;white-space:nowrap;">{date}</div>'
                '</div>'
            )

        return (
            f'<div style="font-size:0.7rem;color:#64748b;text-transform:uppercase;'
            f'letter-spacing:0.08em;margin-bottom:0.4rem;">{label}</div>'
            '<div style="display:flex;gap:0.4rem;align-items:flex-end;'
            'padding-bottom:1rem;margin-bottom:0.6rem;border-bottom:1px solid #eef1f5;">'
            f'{bars}</div>'
        )

    rev_bars = abs_bars(rev_q, "🟡 Revenue por trimestre (Yahoo Finance)")
    eps_bars = abs_bars(eps_q, "🟡 EPS por trimestre (Yahoo Finance)", is_eps=True)

    header = (
        '<div style="display:flex;align-items:center;justify-content:space-between;'
        'margin-bottom:1rem;">'
        '<div>'
        f'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:1rem;'
        f'font-weight:700;color:{sig_color};">{sig_label}</div>'
        f'<div style="font-size:0.76rem;color:#64748b;margin-top:0.2rem;">'
        f'Trimestres en alza: Revenue {trend["rev_streak"]}Q · EPS {trend["eps_streak"]}Q consecutivos</div>'
        '</div>'
        f'<div style="text-align:right;">'
        f'<div style="font-size:0.7rem;color:#64748b;">Trimestres</div>'
        f'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:1.2rem;'
        f'color:#0f172a;font-weight:600;">{trend["total_q"]}</div>'
        '</div></div>'
    )
    legend = (
        '<div style="font-size:0.68rem;color:#94a3b8;margin-top:0.2rem;">'
        '<span style="color:#059669;">■</span> Sube vs trimestre anterior &nbsp;'
        '<span style="color:#dc2626;">■</span> Baja vs trimestre anterior &nbsp;'
        '<span style="color:#0284c7;">■</span> Primer dato disponible &nbsp;·&nbsp;'
        'El % sobre cada barra indica la variación QoQ</div>'
    )

    no_eps_note = (
        '<div style="font-size:0.75rem;color:#64748b;padding:0.4rem 0;">'
        'EPS trimestral no disponible para este ticker en Yahoo Finance.</div>'
    ) if not eps_q else ""

    content = header + rev_bars + (eps_bars or no_eps_note) + legend
    st.markdown(f'<div class="metric-card">{content}</div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# RENDER — COMPARATIVA CON COMPETIDORES
# ─────────────────────────────────────────────────────────────────────────────

def render_peers(main_ticker: str, main_data: dict, peers_data: list,
                 fx_rate: float | None, ev: dict):
    st.markdown('<div class="section-header">COMPARATIVA FRENTE A COMPETENCIA</div>', unsafe_allow_html=True)

    # Widget de gestión de competidores manuales (siempre visible)
    render_competitor_manager(main_ticker)

    if not peers_data:
        st.markdown(
            '<div class="metric-card">'
            '<span style="color:#64748b;">Todavía no has añadido competidores para esta empresa. '
            'Usa el panel de arriba para añadirlos.</span>'
            '</div>',
            unsafe_allow_html=True
        )
        return

    pe_ref  = ev.get("pe_ref", 20)
    peg_ref = ev.get("peg_ok", 1.5)
    ev_ref  = ev.get("ev_ebitda_fair", 14)

    def mc_fmt(mc):
        if not mc: return "—"
        if mc >= 1e12: return f"${mc/1e12:.1f}T"
        if mc >= 1e9:  return f"${mc/1e9:.1f}B"
        return f"${mc/1e6:.0f}M"

    def td_col(val, low_good=True, ref=None, sfx="x", dec=1):
        if val is None:
            return '<td style="color:#d1d9e0;text-align:right;padding:0.3rem 0.5rem;">—</td>'
        col = "#0f172a"
        if ref is not None:
            col = "#059669" if (val < ref) == low_good else "#dc2626"
        return f'<td style="font-family:\'IBM Plex Mono\',monospace;color:{col};text-align:right;padding:0.3rem 0.5rem;">{val:,.{dec}f}{sfx}</td>'

    def make_row(ticker, name, d, is_main=False):
        bg    = "#dbeafe" if is_main else "#ffffff"
        bdr   = "border-left:3px solid #0284c7;" if is_main else ""
        nc    = "#0284c7" if is_main else "#334155"
        badge = '<span style="font-size:0.65rem;background:#dbeafe;color:#0284c7;padding:1px 5px;border-radius:3px;margin-left:0.3rem;">TÚ</span>' if is_main else ""
        return (
            f'<tr style="background:{bg};{bdr}border-bottom:1px solid #eef1f5;">'
            f'<td style="padding:0.3rem 0.6rem;white-space:nowrap;">'
            f'<span style="font-family:\'IBM Plex Mono\',monospace;font-weight:700;color:{nc};">{ticker}</span>'
            f'<span style="font-size:0.72rem;color:#64748b;margin-left:0.3rem;">{name}</span>{badge}</td>'
            + td_col(d.get("pe_forward"), low_good=True,  ref=pe_ref,  sfx="x")
            + td_col(d.get("peg"),        low_good=True,  ref=peg_ref, sfx="")
            + td_col(d.get("ev_ebitda"),  low_good=True,  ref=ev_ref,  sfx="x")
            + td_col(d.get("profit_m"),   low_good=False, ref=10,      sfx="%")
            + td_col(d.get("roe"),        low_good=False, ref=12,      sfx="%")
            + td_col(d.get("rev_growth"), low_good=False, ref=5,       sfx="%")
            + f'<td style="font-family:\'IBM Plex Mono\',monospace;color:#64748b;text-align:right;padding:0.3rem 0.5rem;font-size:0.8rem;">{mc_fmt(d.get("market_cap"))}</td>'
            + '</tr>'
        )

    main_row  = make_row(main_ticker, (main_data.get("company_name","") or "")[:22], {
        "pe_forward": main_data.get("pe_forward"),
        "peg":        main_data.get("peg_ratio"),
        "ev_ebitda":  main_data.get("ev_ebitda"),
        "profit_m":   (main_data.get("profit_margin") or 0) * 100,
        "roe":        (main_data.get("roe") or 0) * 100,
        "rev_growth": main_data.get("revenue_yoy"),
        "market_cap": main_data.get("market_cap"),
    }, is_main=True)

    peer_rows = "".join(make_row(p["ticker"], p["name"], p) for p in peers_data)
    hs = "padding:0.4rem 0.5rem;font-size:0.68rem;color:#64748b;text-transform:uppercase;letter-spacing:0.06em;text-align:right;border-bottom:1px solid #e2e8f0;"

    # Tooltips en cabeceras de columna
    # IMPORTANTE: dentro de tablas los tooltips necesitan position:fixed
    # para escapar del contexto de overflow:hidden del contenedor
    def th(label, tip, align="right"):
        tip_safe = tip.replace('"','&quot;')
        return (
            f'<th style="{hs}text-align:{align};">'
            f'{label}'
            f'<span style="margin-left:0.3rem;position:relative;cursor:help;display:inline-block;">'
            f'<span style="font-size:0.6rem;color:#0284c7;border:1px solid #0284c7;'
            f'border-radius:50%;padding:0 3px;font-family:\'IBM Plex Mono\',monospace;" '
            f'title="{tip_safe}">?</span>'
            f'</span></th>'
        )

    table = (
        '<div style="overflow-x:auto;">'
        '<table style="width:100%;border-collapse:collapse;font-size:0.83rem;">'
        '<thead><tr style="background:#f8fafc;">'
        f'<th style="{hs}text-align:left;">Empresa</th>'
        + th("PER Fwd",   f"PER Forward: precio / beneficio estimado próximos 12 meses. Referencia sector: {pe_ref}×. Verde si está por debajo.")
        + th("PEG",       f"PEG = PER / crecimiento anual. <1 = empresa barata respecto a su crecimiento. Referencia sector: <{peg_ref}.")
        + th("EV/EBITDA", f"Valor empresa / EBITDA. Métrica universal de valoración. Referencia sector: {ev_ref}×. Verde si está por debajo.")
        + th("Margen",    "Margen de beneficio neto (%). Verde si supera el 10%. Cuanto más alto, más rentable el negocio.")
        + th("ROE",       "Return on Equity: beneficio / patrimonio neto (%). Verde si supera el 12%. Mide eficiencia del capital.")
        + th("Crec.",     "Crecimiento de ingresos YoY (%). Verde si supera el 5%. Indica capacidad de expansión del negocio.")
        + th("Mkt Cap",   "Capitalización bursátil total. T = billones, B = miles de millones, M = millones.")
        + '</tr></thead>'
        f'<tbody>{main_row}{peer_rows}</tbody>'
        '</table></div>'
        f'<div style="font-size:0.7rem;color:#64748b;margin-top:0.5rem;">'
        f'Verde = mejor que referencia sector · Rojo = peor · Ref: PER {pe_ref}× · PEG {peg_ref} · EV/EBITDA {ev_ref}×</div>'
    )

    st.markdown(f'<div class="metric-card" style="padding:0.8rem 0.5rem;">{table}</div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# ANÁLISIS DE SHORT INTEREST Y PROBABILIDAD DE SHORT SQUEEZE
# ─────────────────────────────────────────────────────────────────────────────

def calc_short_squeeze(y: dict) -> dict:
    """
    Calcula la probabilidad de short squeeze basándose en:
      1. Short Ratio (días para cubrir): días que tardarían los bajistas en
         cerrar sus posiciones al volumen medio. >5 días = presión relevante.
      2. Short % of Float: porcentaje del float en posiciones cortas.
         >10% = significativo, >20% = muy elevado, >30% = extremo.
      3. Variación mensual del short interest: si sube agresivamente
         puede indicar acumulación bajista o anticipación de malas noticias.
      4. RSI bajo + short alto = condiciones clásicas de squeeze potencial.

    El squeeze ocurre cuando los bajistas se ven forzados a comprar para cubrir
    sus posiciones, acelerando la subida del precio.
    """
    short_ratio    = y.get("short_ratio") or 0
    pct_float      = (y.get("short_percent_of_float") or 0) * 100
    shares_short   = y.get("shares_short") or 0
    shares_prior   = y.get("shares_short_prior") or 0
    float_shares   = y.get("float_shares") or 0
    date_si        = y.get("date_short_interest")

    # Variación mensual del short interest
    monthly_change = None
    monthly_change_pct = None
    if shares_short and shares_prior and shares_prior > 0:
        monthly_change     = shares_short - shares_prior
        monthly_change_pct = (monthly_change / shares_prior) * 100

    # ── Puntuación por factor (0-100 total) ──────────────────────────────
    score = 0
    factors = []

    # Factor 1: Short Ratio (0-35 pts)
    if short_ratio >= 10:
        f1, f1_lbl = 35, f"Ratio extremo: {short_ratio:.1f} días para cubrir"
    elif short_ratio >= 7:
        f1, f1_lbl = 25, f"Ratio muy alto: {short_ratio:.1f} días para cubrir"
    elif short_ratio >= 5:
        f1, f1_lbl = 15, f"Ratio relevante: {short_ratio:.1f} días para cubrir"
    elif short_ratio >= 3:
        f1, f1_lbl = 7,  f"Ratio moderado: {short_ratio:.1f} días para cubrir"
    else:
        f1, f1_lbl = 0,  f"Ratio bajo: {short_ratio:.1f} días — presión bajista mínima"
    score += f1
    factors.append(("Short Ratio", f1, 35, f1_lbl))

    # Factor 2: % del Float (0-40 pts)
    if pct_float >= 30:
        f2, f2_lbl = 40, f"{pct_float:.1f}% del float vendido en corto — nivel extremo"
    elif pct_float >= 20:
        f2, f2_lbl = 28, f"{pct_float:.1f}% del float vendido en corto — muy elevado"
    elif pct_float >= 10:
        f2, f2_lbl = 16, f"{pct_float:.1f}% del float vendido en corto — significativo"
    elif pct_float >= 5:
        f2, f2_lbl = 6,  f"{pct_float:.1f}% del float vendido en corto — moderado"
    else:
        f2, f2_lbl = 0,  f"{pct_float:.1f}% del float vendido en corto — bajo"
    score += f2
    factors.append(("Short % del Float", f2, 40, f2_lbl))

    # Factor 3: Cambio mensual (0-25 pts)
    if monthly_change_pct is not None:
        if monthly_change_pct >= 25:
            f3, f3_lbl = 25, f"Short interest subió +{monthly_change_pct:.0f}% en el último mes — acumulación bajista agresiva"
        elif monthly_change_pct >= 10:
            f3, f3_lbl = 12, f"Short interest subió +{monthly_change_pct:.0f}% en el último mes"
        elif monthly_change_pct <= -20:
            f3, f3_lbl = -5, f"Short interest bajó {monthly_change_pct:.0f}% — bajistas cerrando posiciones (señal positiva)"
        else:
            f3, f3_lbl = 0, f"Short interest estable ({monthly_change_pct:+.0f}% vs mes anterior)"
        score += f3
        factors.append(("Variación mensual", max(f3,0), 25, f3_lbl))
    else:
        factors.append(("Variación mensual", 0, 25, "Sin dato de mes anterior"))

    score = max(0, min(100, score))

    # ── Clasificación de probabilidad ─────────────────────────────────────
    if score >= 70:
        level   = "MUY ALTA"
        color   = "#dc2626"
        icon    = "🔥"
        summary = ("Confluencia de factores bajistas extremos. El potencial de squeeze es muy elevado "
                   "si llega un catalizador alcista (buenos resultados, noticia positiva, upgrade de analista). "
                   "Alto riesgo/oportunidad: movimientos de +20/30% en días no son inusuales en estos casos.")
    elif score >= 45:
        level   = "MODERADA-ALTA"
        color   = "#ea580c"
        icon    = "⚡"
        summary = ("Presión bajista significativa. Un catalizador positivo podría desencadenar coberturas "
                   "forzadas y amplificar el movimiento alcista más allá de lo que justificarían los fundamentales.")
    elif score >= 25:
        level   = "MODERADA"
        color   = "#d97706"
        icon    = "⚠️"
        summary = ("Short interest notable pero no en niveles de squeeze inminente. "
                   "Vigilar si continúa aumentando en los próximos meses.")
    elif score >= 10:
        level   = "BAJA"
        color   = "#059669"
        icon    = "✓"
        summary = "Presión bajista limitada. Poco riesgo de squeeze pero también poca presión compradora forzada."
    else:
        level   = "MUY BAJA"
        color   = "#0284c7"
        icon    = "○"
        summary = "Posiciones cortas mínimas. El mercado no muestra desconfianza bajista significativa."

    # Fecha del último reporte de short interest
    date_str = "N/A"
    if date_si:
        try:
            from datetime import datetime, timezone
            if isinstance(date_si, (int, float)):
                date_str = datetime.fromtimestamp(date_si, tz=timezone.utc).strftime("%Y-%m-%d")
            else:
                date_str = str(date_si)[:10]
        except Exception:
            date_str = str(date_si)[:10]

    return {
        "score":              score,
        "level":              level,
        "color":              color,
        "icon":               icon,
        "summary":            summary,
        "short_ratio":        short_ratio,
        "pct_float":          pct_float,
        "shares_short":       shares_short,
        "float_shares":       float_shares,
        "monthly_change_pct": monthly_change_pct,
        "date_si":            date_str,
        "factors":            factors,
    }


def render_short_squeeze(sq: dict):
    """Renderiza el análisis de short interest y probabilidad de short squeeze."""
    st.markdown(
        '<div class="section-header">SHORT INTEREST &amp; SHORT SQUEEZE</div>',
        unsafe_allow_html=True
    )

    if not sq or sq.get("short_ratio", 0) == 0:
        st.markdown(
            '<div class="metric-card"><span style="color:#64748b;">'
            'Datos de short interest no disponibles para este ticker.</span></div>',
            unsafe_allow_html=True
        )
        return

    score    = sq["score"]
    level    = sq["level"]
    color    = sq["color"]
    icon     = sq["icon"]
    summary  = sq["summary"]
    factors  = sq["factors"]

    def fmt_shares(v):
        if not v: return "N/A"
        if v >= 1e9:  return f"{v/1e9:.2f}B"
        if v >= 1e6:  return f"{v/1e6:.1f}M"
        if v >= 1e3:  return f"{v/1e3:.0f}K"
        return str(int(v))

    def tip(text):
        safe = text.replace('"','&quot;')
        return (
            f'<span title="{safe}" style="margin-left:0.3rem;cursor:help;'
            f'font-size:0.6rem;color:#94a3b8;border:1px solid #cbd5e1;'
            f'border-radius:50%;padding:0 3px;font-family:monospace;'
            f'vertical-align:middle;">?</span>'
        )

    # Desglose de factores
    factor_rows = ""
    for fname, pts, max_pts, flbl in factors:
        pct_bar = (pts / max_pts * 100) if max_pts else 0
        bar_col = color if pts > 0 else "#334155"
        factor_rows += (
            f'<div style="margin-bottom:0.5rem;">'
            f'<div style="display:flex;justify-content:space-between;font-size:0.78rem;margin-bottom:0.2rem;">'
            f'<span style="color:#64748b;">{fname}</span>'
            f'<span style="font-family:\'IBM Plex Mono\',monospace;color:{color if pts>0 else "#64748b"};">'
            f'{pts}/{max_pts}</span>'
            f'</div>'
            f'<div style="background:#334155;border-radius:3px;height:6px;">'
            f'<div style="width:{pct_bar:.0f}%;height:6px;border-radius:3px;background:{bar_col};"></div>'
            f'</div>'
            f'<div style="font-size:0.72rem;color:#64748b;margin-top:0.15rem;">{flbl}</div>'
            f'</div>'
        )

    # Métricas numéricas
    tip_sr  = tip("Días que necesitarían todos los bajistas para cerrar sus posiciones al volumen medio diario. >5d = presión relevante, >10d = muy alta.")
    tip_pf  = tip("Porcentaje del float (acciones en circulación real) vendido en corto. >10% significativo, >20% muy alto, >30% extremo y propenso a squeeze.")
    tip_sq  = tip("El short squeeze ocurre cuando una subida del precio fuerza a los bajistas a comprar para cubrir pérdidas, acelerando aún más la subida. Requiere catalizador + alto short interest + bajo float.")

    date_note = f'Último reporte: {sq["date_si"]}' if sq["date_si"] != "N/A" else ""

    st.markdown(
        f'<div class="metric-card">'
        # Cabecera con probabilidad
        f'<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:1rem;">'
        f'<div>'
        f'<div style="font-size:0.7rem;color:#64748b;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:0.2rem;">'
        f'Probabilidad de Short Squeeze{tip_sq}</div>'
        f'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:1.2rem;font-weight:700;color:{color};">'
        f'{icon} {level}</div>'
        f'</div>'
        f'<div style="text-align:right;">'
        f'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:2rem;font-weight:700;color:{color};">'
        f'{score}<span style="font-size:1rem;color:#64748b;">/100</span></div>'
        f'<div style="font-size:0.68rem;color:#64748b;">{date_note}</div>'
        f'</div>'
        f'</div>'
        # Barra de score
        f'<div style="background:#334155;border-radius:4px;height:8px;margin-bottom:1rem;">'
        f'<div style="height:8px;border-radius:4px;background:{color};width:{score}%;"></div>'
        f'</div>'
        # Métricas clave en grid
        f'<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:0.5rem;margin-bottom:1rem;">'
        f'<div style="background:#f4f6f9;border-radius:6px;padding:0.45rem 0.6rem;">'
        f'<div style="font-size:0.67rem;color:#64748b;">Short Ratio{tip_sr}</div>'
        f'<div style="font-family:\'IBM Plex Mono\',monospace;color:{color};font-weight:700;">'
        f'{sq["short_ratio"]:.1f} días</div></div>'
        f'<div style="background:#f4f6f9;border-radius:6px;padding:0.45rem 0.6rem;">'
        f'<div style="font-size:0.67rem;color:#64748b;">Short % del Float{tip_pf}</div>'
        f'<div style="font-family:\'IBM Plex Mono\',monospace;color:{color};font-weight:700;">'
        f'{sq["pct_float"]:.1f}%</div></div>'
        f'<div style="background:#f4f6f9;border-radius:6px;padding:0.45rem 0.6rem;">'
        f'<div style="font-size:0.67rem;color:#64748b;">Acciones en corto</div>'
        f'<div style="font-family:\'IBM Plex Mono\',monospace;color:#0f172a;font-weight:600;">'
        f'{fmt_shares(sq["shares_short"])}</div></div>'
        f'</div>'
        # Desglose por factor
        f'<div style="font-size:0.7rem;color:#0284c7;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:0.5rem;">'
        f'Desglose de factores</div>'
        f'{factor_rows}'
        # Resumen
        f'<div style="background:#f4f6f9;border-radius:6px;padding:0.6rem 0.8rem;margin-top:0.5rem;">'
        f'<div style="font-size:0.78rem;color:#94a3b8;line-height:1.6;">{summary}</div>'
        f'</div>'
        f'<div style="font-size:0.68rem;color:#94a3b8;margin-top:0.5rem;">'
        f'Fuente: Yahoo Finance · El short squeeze no es predecible con certeza — requiere un catalizador externo.'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True
    )
