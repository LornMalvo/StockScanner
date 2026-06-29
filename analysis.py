"""
analysis.py — v1.8
Módulos avanzados: señal de entrada, tendencia, competidores,
descripción empresa, noticias, análisis resultados, benchmarks sector.
"""

import yfinance as yf
import streamlit as st
import time
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

def fetch_earnings_analysis(ticker: str, y: dict) -> dict:
    try:
        t    = yf.Ticker(ticker)
        info = t.info

        last_q_ts = info.get("mostRecentQuarter")
        next_q_ts = info.get("earningsTimestamp") or info.get("earningsTimestampStart")

        last_q_date = datetime.fromtimestamp(last_q_ts, tz=timezone.utc).strftime("%Y-%m-%d") if last_q_ts else "N/A"
        next_q_date = datetime.fromtimestamp(next_q_ts, tz=timezone.utc).strftime("%Y-%m-%d") if next_q_ts else "N/A"

        eps_actual   = info.get("trailingEps")
        eps_estimate = info.get("epsCurrentYear") or info.get("epsForward")
        eps_surprise = None
        if eps_actual and eps_estimate and eps_estimate != 0:
            eps_surprise = (eps_actual - eps_estimate) / abs(eps_estimate) * 100

        q_data   = y.get("ttm_quarters", [])
        q_growth = None
        if len(q_data) >= 2:
            v0 = q_data[0].get("value") or 0
            v1 = q_data[1].get("value") or 0
            if v1 and v1 != 0:
                q_growth = (v0 - v1) / abs(v1) * 100

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

        beat_eps = None
        if eps_surprise is not None:
            if eps_surprise > 5:
                positives.append(f"Batió expectativas de EPS en +{eps_surprise:.1f}%")
                beat_eps = True
            elif eps_surprise < -5:
                negatives.append(f"Decepcionó expectativas de EPS en {eps_surprise:.1f}%")
                beat_eps = False

        return {
            "last_q_date":     last_q_date,
            "next_q_date":     next_q_date,
            "eps_surprise":    eps_surprise,
            "beat_eps":        beat_eps,
            "q_growth":        q_growth,
            "positives":       positives[:6],
            "negatives":       negatives[:5],
            "warnings":        warnings,
            "is_growth_stage": is_growth_stage,
        }
    except Exception as e:
        return {"error": str(e)}

# ─────────────────────────────────────────────────────────────────────────────
# SEÑAL DE CONFLUENCIA DE ENTRADA
# ─────────────────────────────────────────────────────────────────────────────

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

    total_w    = sum(c[3] for c in checks)
    achieved_w = sum(c[3] for c in checks if c[1])
    n_ok       = sum(1 for c in checks if c[1])
    score_pct  = (achieved_w / total_w * 100) if total_w else 0

    heavy_ok    = sum(1 for c in checks if c[1] and c[3] >= 2)
    heavy_total = sum(1 for c in checks if c[3] >= 2)

    if score_pct >= 80 and heavy_ok >= heavy_total - 1:
        level, color, icon = "ENTRADA IDEAL",   "#6ee7b7", "🟢"
        desc = "Confluencia fuerte: múltiples factores técnicos y fundamentales alineados."
    elif score_pct >= 60 and heavy_ok >= heavy_total // 2 + 1:
        level, color, icon = "ENTRADA POSIBLE", "#86efac", "🟡"
        desc = "Buena confluencia, aunque no todos los factores clave están alineados."
    elif score_pct >= 40:
        level, color, icon = "VIGILAR",         "#fbbf24", "🟠"
        desc = "Algunos factores positivos, pero faltan condiciones clave para una entrada óptima."
    else:
        level, color, icon = "NO ES MOMENTO",   "#fca5a5", "🔴"
        desc = "Pocos factores alineados. Esperar mejor precio, menor RSI o mejores fundamentales."

    return {
        "level": level, "color": color, "icon": icon, "desc": desc,
        "score": round(score_pct), "n_ok": n_ok,
        "n_total": len(checks), "checks": checks,
    }

# ─────────────────────────────────────────────────────────────────────────────
# TENDENCIA TRIMESTRAL
# ─────────────────────────────────────────────────────────────────────────────

def calc_trend(y: dict | None) -> dict | None:
    """
    Analiza la tendencia trimestral de ingresos y beneficio neto.
    Usa ttm_quarters y net_income_q de Yahoo Finance.
    Calcula variación QoQ (trimestre vs trimestre anterior del año pasado)
    para evitar estacionalidad — compara Q1-2025 vs Q1-2024, etc.
    """
    if not y:
        return None

    rev_q = y.get("ttm_quarters", []) or []
    ni_q  = y.get("net_income_q",  []) or []

    # Necesitamos al menos 2 puntos para calcular variación
    if len(rev_q) < 2:
        return None

    # Ordenar de más antiguo a más reciente
    rev_sorted = sorted(rev_q, key=lambda x: x.get("date",""))
    ni_sorted  = sorted(ni_q,  key=lambda x: x.get("date","")) if ni_q else []

    def qoq(series):
        """Variación trimestral: cada Q vs el Q anterior disponible."""
        out = []
        for i in range(1, len(series)):
            prev = series[i-1].get("value") or 0
            curr = series[i].get("value")   or 0
            if prev and prev != 0:
                pct = (curr - prev) / abs(prev) * 100
                # Usar solo el mes/año del trimestre como etiqueta
                date_lbl = series[i].get("date","")[:7]  # YYYY-MM
                out.append({
                    "date":  date_lbl,
                    "value": curr,
                    "prev":  prev,
                    "pct":   round(pct, 1),
                })
        return out

    rev_ch = qoq(rev_sorted)
    ni_ch  = qoq(ni_sorted)

    if not rev_ch:
        return None

    def streak(changes):
        if not changes: return 0, 0
        up    = sum(1 for c in changes if c["pct"] > 0)
        racha = 0
        for c in reversed(changes):
            if c["pct"] > 0: racha += 1
            else: break
        return up, racha

    rev_up, rev_s = streak(rev_ch)
    ni_up,  ni_s  = streak(ni_ch)
    total = len(rev_ch)

    if rev_s >= 2 and ni_s >= 2:   sig = ("ACELERACIÓN",  "#6ee7b7")
    elif rev_s >= 1 or ni_s >= 1:  sig = ("MEJORANDO",    "#86efac")
    elif rev_up > total // 2:       sig = ("ESTABLE",      "#fbbf24")
    else:                           sig = ("DETERIORANDO", "#fca5a5")

    return {
        "rev_changes":  rev_ch,
        "ni_changes":   ni_ch,
        "rev_streak":   rev_s,
        "ni_streak":    ni_s,
        "trend_signal": sig,
        "total_q":      total,
        "source":       "Yahoo Finance (trimestral)",
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
                return {"date": hist.index[i].strftime("%Y-%m-%d"), "type": "GOLDEN CROSS"}
            elif diff.iloc[i] < 0 and diff.iloc[i-1] >= 0:
                return {"date": hist.index[i].strftime("%Y-%m-%d"), "type": "DEATH CROSS"}
        return {}
    except Exception:
        return {}

# ─────────────────────────────────────────────────────────────────────────────
# COMPETIDORES
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
    st.markdown('<div class="section-header">B · DESCRIPCIÓN DE LA EMPRESA</div>', unsafe_allow_html=True)
    if not company_info or not company_info.get("description"):
        st.markdown('<div class="metric-card"><span style="color:#64748b;">Descripción no disponible.</span></div>', unsafe_allow_html=True)
        return

    desc      = company_info.get("description","")
    industry  = company_info.get("industry","")
    country   = company_info.get("country","")
    employees = company_info.get("employees")
    website   = company_info.get("website","")
    emp_str   = f"{employees:,}" if employees else "N/A"
    web_html  = f'<a href="{website}" target="_blank" style="color:#38bdf8;">{website}</a>' if website else "N/A"
    desc_short = desc if len(desc) <= 1000 else desc[:1000] + "…"
    insiders   = company_info.get("insiders", [])
    fcf_q      = company_info.get("fcf_quality")

    tags = ""
    if industry:  tags += f'<span style="background:#1e2d45;color:#94a3b8;padding:2px 9px;border-radius:4px;font-size:0.75rem;margin-right:0.4rem;">{industry}</span>'
    if country:   tags += f'<span style="background:#1e2d45;color:#94a3b8;padding:2px 9px;border-radius:4px;font-size:0.75rem;margin-right:0.4rem;">🌍 {country}</span>'
    if employees: tags += f'<span style="background:#1e2d45;color:#94a3b8;padding:2px 9px;border-radius:4px;font-size:0.75rem;">👥 {emp_str} empleados</span>'

    # Calidad del beneficio
    fcf_html = ""
    if fcf_q is not None:
        if fcf_q >= 0.9:
            fcf_col = "#6ee7b7"
            fcf_lbl = "Beneficio de alta calidad — se convierte en caja real"
        elif fcf_q >= 0.5:
            fcf_col = "#fbbf24"
            fcf_lbl = "Calidad moderada — parte del beneficio no es caja"
        elif fcf_q >= 0:
            fcf_col = "#fb923c"
            fcf_lbl = "Calidad baja — beneficio contable supera al FCF"
        else:
            fcf_col = "#fca5a5"
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
            f'font-size:0.6rem;color:#334155;border:1px solid #334155;'
            f'border-radius:50%;padding:0 3px;font-family:monospace;'
            f'vertical-align:middle;">?</span>'
        )
        fcf_html = (
            f'<div style="margin-top:0.7rem;padding:0.5rem 0.7rem;background:#0f172a;border-radius:6px;'
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
        f'<div style="font-size:0.85rem;color:#cbd5e1;line-height:1.75;">{desc_short}</div>'
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
            net_signal = '<span style="color:#6ee7b7;font-weight:700;">🟢 SEÑAL ALCISTA — más compras que ventas de insiders</span>'
        elif len(sells) > len(buys) * 2:
            net_signal = '<span style="color:#fca5a5;font-weight:700;">🔴 SEÑAL BAJISTA — ventas significativas de insiders</span>'
        else:
            net_signal = '<span style="color:#64748b;">Actividad mixta de insiders</span>'

        rows_ins = ""
        for ins in insiders[:8]:
            col  = "#6ee7b7" if ins["is_buy"] else "#fca5a5" if ins["is_sell"] else "#94a3b8"
            icon = "▲" if ins["is_buy"] else "▼" if ins["is_sell"] else "—"
            val_str = f"${ins['value']/1e6:.1f}M" if ins["value"] > 1e6 else (f"${ins['value']:,.0f}" if ins["value"] else "")
            rows_ins += (
                f'<div style="display:grid;grid-template-columns:0.8fr 2fr 2fr 1fr;gap:0.3rem;'
                f'padding:0.3rem 0;border-bottom:1px solid #1a2540;font-size:0.76rem;">'
                f'<span style="color:{col};font-weight:700;">{icon} {ins["date"]}</span>'
                f'<span style="color:#94a3b8;">{ins["relation"]}</span>'
                f'<span style="color:#e2e8f0;">{ins["text"]}</span>'
                f'<span style="font-family:\'IBM Plex Mono\',monospace;color:{col};text-align:right;">{val_str}</span>'
                f'</div>'
            )

        st.markdown(
            '<div class="metric-card" style="border-left:3px solid #334155;">'
            '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.6rem;">'
            '<span style="font-size:0.7rem;color:#38bdf8;text-transform:uppercase;letter-spacing:0.1em;">Transacciones de Insiders (últimas)</span>'
            f'<span style="font-size:0.78rem;">{net_signal}</span>'
            '</div>'
            f'{rows_ins}'
            '<div style="font-size:0.68rem;color:#475569;margin-top:0.4rem;">Fuente: Yahoo Finance · Las compras de insiders son señal alcista frecuente</div>'
            '</div>',
            unsafe_allow_html=True
        )

# ─────────────────────────────────────────────────────────────────────────────
# RENDER — NOTICIAS RECIENTES
# ─────────────────────────────────────────────────────────────────────────────

def render_news(news_items: list):
    st.markdown('<div class="section-header">C · NOTICIAS Y ANUNCIOS RECIENTES (últimos 3 meses)</div>', unsafe_allow_html=True)
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
            '<div style="padding:0.55rem 0;border-bottom:1px solid #1a2540;">'
            '<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:0.6rem;">'
            f'<div style="flex:1;">{link_open}'
            f'<span style="font-size:0.83rem;color:#e2e8f0;line-height:1.55;">{title}</span>'
            f'{link_close}</div>'
            f'<span style="font-family:\'IBM Plex Mono\',monospace;font-size:0.72rem;color:#38bdf8;white-space:nowrap;margin-top:2px;">{date}</span>'
            '</div>'
            f'<div style="font-size:0.72rem;color:#475569;margin-top:0.15rem;">{publisher}</div>'
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

    last_q  = ea.get("last_q_date","N/A")
    next_q  = ea.get("next_q_date","N/A")
    pos     = ea.get("positives",[])
    neg     = ea.get("negatives",[])
    warns   = ea.get("warnings",[])
    beat    = ea.get("beat_eps")
    eps_s   = ea.get("eps_surprise")

    # Aviso empresa en crecimiento
    warn_html = ""
    for w in warns:
        warn_html += (
            '<div style="background:#1a1000;border:1px solid #f59e0b;border-left:4px solid #f59e0b;'
            'border-radius:6px;padding:0.7rem 0.9rem;margin-bottom:0.8rem;">'
            '<div style="color:#fbbf24;font-weight:700;font-size:0.8rem;margin-bottom:0.3rem;">'
            '⚡ EMPRESA EN FASE DE CRECIMIENTO / EXPANSIÓN</div>'
            f'<div style="color:#fcd34d;font-size:0.78rem;line-height:1.6;">{w}</div>'
            '</div>'
        )

    # Fechas
    beat_html = ""
    if beat is True:
        beat_html = '<span style="background:#064e3b;color:#6ee7b7;padding:2px 8px;border-radius:4px;font-size:0.75rem;margin-left:0.5rem;">✔ Batió expectativas EPS</span>'
    elif beat is False:
        beat_html = '<span style="background:#4c0519;color:#fca5a5;padding:2px 8px;border-radius:4px;font-size:0.75rem;margin-left:0.5rem;">✘ No cumplió expectativas EPS</span>'

    dates_html = (
        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:0.5rem;margin-bottom:0.8rem;">'
        '<div style="background:#0f172a;border-radius:6px;padding:0.5rem 0.7rem;">'
        '<div style="font-size:0.68rem;color:#64748b;text-transform:uppercase;">Último resultado presentado</div>'
        f'<div style="font-family:\'IBM Plex Mono\',monospace;color:#f1f5f9;font-weight:600;">{last_q}</div>'
        f'{beat_html}'
        '</div>'
        '<div style="background:#0f172a;border-radius:6px;padding:0.5rem 0.7rem;">'
        '<div style="font-size:0.68rem;color:#64748b;text-transform:uppercase;">Próxima presentación estimada</div>'
        f'<div style="font-family:\'IBM Plex Mono\',monospace;color:#38bdf8;font-weight:600;">{next_q}</div>'
        '</div>'
        '</div>'
    )

    # Puntos positivos
    pos_html = ""
    if pos:
        items = "".join(
            f'<div style="display:flex;gap:0.5rem;padding:0.3rem 0;border-bottom:1px solid #1a2540;font-size:0.8rem;">'
            f'<span style="color:#6ee7b7;min-width:1rem;">✔</span>'
            f'<span style="color:#e2e8f0;">{p}</span></div>'
            for p in pos
        )
        pos_html = (
            '<div style="margin-bottom:0.6rem;">'
            '<div style="font-size:0.7rem;color:#6ee7b7;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:0.3rem;">Puntos positivos</div>'
            f'{items}</div>'
        )

    # Puntos negativos
    neg_html = ""
    if neg:
        items = "".join(
            f'<div style="display:flex;gap:0.5rem;padding:0.3rem 0;border-bottom:1px solid #1a2540;font-size:0.8rem;">'
            f'<span style="color:#fca5a5;min-width:1rem;">✘</span>'
            f'<span style="color:#e2e8f0;">{n}</span></div>'
            for n in neg
        )
        neg_html = (
            '<div style="margin-bottom:0.6rem;">'
            '<div style="font-size:0.7rem;color:#fca5a5;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:0.3rem;">Puntos a vigilar</div>'
            f'{items}</div>'
        )

    st.markdown(
        '<div class="metric-card">'
        f'{warn_html}{dates_html}{pos_html}{neg_html}'
        '</div>',
        unsafe_allow_html=True
    )

# ─────────────────────────────────────────────────────────────────────────────
# RENDER — SEÑAL DE CONFLUENCIA
# ─────────────────────────────────────────────────────────────────────────────

def render_entry_signal(signal: dict):
    st.markdown('<div class="section-header">H · SEÑAL DE ENTRADA</div>', unsafe_allow_html=True)

    score   = signal["score"]
    level   = signal["level"]
    color   = signal["color"]
    icon    = signal["icon"]
    desc    = signal["desc"]
    n_ok    = signal["n_ok"]
    n_total = signal["n_total"]
    checks  = signal["checks"]

    rows = ""
    for name, ok, detail, weight in checks:
        dot_color = color if ok else "#374151"
        dot       = "●" if ok else "○"
        w_dots    = "●" * weight
        rows += (
            '<div style="display:flex;align-items:flex-start;gap:0.6rem;padding:0.35rem 0;'
            'border-bottom:1px solid #1a2540;font-size:0.82rem;">'
            f'<span style="color:{dot_color};font-size:1rem;min-width:1rem;">{dot}</span>'
            '<div style="flex:1;">'
            f'<span style="color:{"#f1f5f9" if ok else "#64748b"};">{name}</span>'
            f'<span style="color:#64748b;font-size:0.74rem;margin-left:0.4rem;">({detail})</span>'
            '</div>'
            f'<span style="color:#1e3a5f;font-size:0.65rem;min-width:2rem;text-align:right;">{w_dots}</span>'
            '</div>'
        )

    st.markdown(
        f'<div style="background:#0f172a;border:2px solid {color};border-radius:10px;padding:1.2rem 1.4rem;margin-bottom:1rem;">'
        '<div style="display:flex;align-items:center;gap:0.8rem;margin-bottom:0.8rem;">'
        f'<span style="font-size:1.5rem;">{icon}</span>'
        '<div>'
        f'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:1.05rem;font-weight:700;color:{color};">{level}</div>'
        f'<div style="font-size:0.8rem;color:#94a3b8;margin-top:0.1rem;">{desc}</div>'
        '</div>'
        '<div style="margin-left:auto;text-align:right;">'
        f'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:1.8rem;font-weight:700;color:{color};">'
        f'{score}<span style="font-size:1rem;color:#64748b;">/100</span></div>'
        f'<div style="font-size:0.72rem;color:#64748b;">{n_ok}/{n_total} criterios</div>'
        '</div></div>'
        f'<div style="background:#1e2d45;border-radius:4px;height:6px;margin-bottom:1rem;">'
        f'<div style="height:6px;border-radius:4px;background:{color};width:{score}%;"></div></div>'
        '<div style="font-size:0.68rem;color:#38bdf8;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:0.3rem;">'
        'DESGLOSE DE FACTORES</div>'
        f'{rows}</div>',
        unsafe_allow_html=True
    )

# ─────────────────────────────────────────────────────────────────────────────
# RENDER — TENDENCIA TRIMESTRAL
# ─────────────────────────────────────────────────────────────────────────────

def render_trend(trend: dict | None, yahoo_quarters: list | None = None):
    """Renderiza la tendencia de ingresos usando datos de Yahoo Finance TTM."""
    st.markdown('<div class="section-header">I · TENDENCIA TRIMESTRAL</div>', unsafe_allow_html=True)

    if not trend and not yahoo_quarters:
        st.markdown('<div class="metric-card"><span style="color:#64748b;">Datos insuficientes para calcular tendencia.</span></div>', unsafe_allow_html=True)
        return

    sig_label, sig_color = trend["trend_signal"]
    rev_ch = trend.get("rev_changes", [])
    ni_ch  = trend.get("ni_changes",  [])

    def bar_html(changes, label, c_pos="#6ee7b7", c_neg="#fca5a5"):
        if not changes: return ""
        max_abs = max(abs(c["pct"]) for c in changes) or 1
        bars = ""
        for c in changes:
            pct  = c["pct"]
            h    = min(abs(pct) / max_abs * 70, 70)
            col  = c_pos if pct >= 0 else c_neg
            sign = "+" if pct >= 0 else ""
            bars += (
                '<div style="display:flex;flex-direction:column;align-items:center;gap:0.15rem;flex:1;">' +
                f'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:0.68rem;color:{col};font-weight:600;">{sign}{pct:.0f}%</div>' +
                '<div style="height:70px;display:flex;align-items:flex-end;width:100%;">' +
                f'<div style="width:100%;height:{h}px;background:{col};border-radius:3px 3px 0 0;min-height:3px;"></div>' +
                '</div>' +
                f'<div style="font-size:0.65rem;color:#64748b;white-space:nowrap;">{c["date"]}</div>' +
                '</div>'
            )
        return (
            f'<div style="font-size:0.7rem;color:#94a3b8;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:0.3rem;">{label}</div>' +
            '<div style="display:flex;gap:0.25rem;align-items:flex-end;padding-bottom:1.2rem;margin-bottom:0.8rem;">' +
            f'{bars}</div>'
        )

    rev_bars = bar_html(rev_ch, "🟡 Crecimiento YoY — Revenue (Yahoo)")
    ni_bars  = bar_html(ni_ch,  "🟡 Crecimiento YoY — Beneficio Neto (Yahoo)")

    header = (
        '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:1rem;">' +
        '<div>' +
        f'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:1rem;font-weight:700;color:{sig_color};">{sig_label}</div>' +
        f'<div style="font-size:0.76rem;color:#64748b;margin-top:0.2rem;">' +
        f'Racha alcista: ingresos {trend["rev_streak"]}Q · beneficio {trend["ni_streak"]}Q consecutivos</div>' +
        '</div>' +
        f'<div style="text-align:right;"><div style="font-size:0.7rem;color:#64748b;">Trimestres</div>' +
        f'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:1.2rem;color:#f1f5f9;font-weight:600;">{trend["total_q"]}</div>' +
        '</div></div>'
    )
    source_note = '<div style="font-size:0.7rem;color:#475569;margin-top:0.3rem;">Fuente: Yahoo Finance · Variaciones QoQ (trimestre sobre trimestre anterior)</div>'
    content = header + rev_bars + ni_bars + source_note

    st.markdown(f'<div class="metric-card">{content}</div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# RENDER — COMPARATIVA CON COMPETIDORES
# ─────────────────────────────────────────────────────────────────────────────

def render_peers(main_ticker: str, main_data: dict, peers_data: list,
                 fx_rate: float | None, ev: dict):
    st.markdown('<div class="section-header">J · COMPARATIVA FRENTE A COMPETENCIA</div>', unsafe_allow_html=True)
    if not peers_data:
        st.markdown('<div class="metric-card"><span style="color:#64748b;">No se pudieron obtener datos de competidores.</span></div>', unsafe_allow_html=True)
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
            return '<td style="color:#374151;text-align:right;padding:0.3rem 0.5rem;">—</td>'
        col = "#f1f5f9"
        if ref is not None:
            col = "#6ee7b7" if (val < ref) == low_good else "#fca5a5"
        return f'<td style="font-family:\'IBM Plex Mono\',monospace;color:{col};text-align:right;padding:0.3rem 0.5rem;">{val:,.{dec}f}{sfx}</td>'

    def make_row(ticker, name, d, is_main=False):
        bg    = "#1e3a5f" if is_main else "#111827"
        bdr   = "border-left:3px solid #38bdf8;" if is_main else ""
        nc    = "#38bdf8" if is_main else "#e2e8f0"
        badge = '<span style="font-size:0.65rem;background:#1e3a5f;color:#38bdf8;padding:1px 5px;border-radius:3px;margin-left:0.3rem;">TÚ</span>' if is_main else ""
        return (
            f'<tr style="background:{bg};{bdr}border-bottom:1px solid #1a2540;">'
            f'<td style="padding:0.3rem 0.6rem;white-space:nowrap;">'
            f'<span style="font-family:\'IBM Plex Mono\',monospace;font-weight:700;color:{nc};">{ticker}</span>'
            f'<span style="font-size:0.72rem;color:#64748b;margin-left:0.3rem;">{name}</span>{badge}</td>'
            + td_col(d.get("pe_forward"), low_good=True,  ref=pe_ref,  sfx="x")
            + td_col(d.get("peg"),        low_good=True,  ref=peg_ref, sfx="")
            + td_col(d.get("ev_ebitda"),  low_good=True,  ref=ev_ref,  sfx="x")
            + td_col(d.get("profit_m"),   low_good=False, ref=10,      sfx="%")
            + td_col(d.get("roe"),        low_good=False, ref=12,      sfx="%")
            + td_col(d.get("rev_growth"), low_good=False, ref=5,       sfx="%")
            + f'<td style="font-family:\'IBM Plex Mono\',monospace;color:#94a3b8;text-align:right;padding:0.3rem 0.5rem;font-size:0.8rem;">{mc_fmt(d.get("market_cap"))}</td>'
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
    hs = "padding:0.4rem 0.5rem;font-size:0.68rem;color:#64748b;text-transform:uppercase;letter-spacing:0.06em;text-align:right;border-bottom:1px solid #1e2d45;"

    # Tooltips en cabeceras de columna
    # IMPORTANTE: dentro de tablas los tooltips necesitan position:fixed
    # para escapar del contexto de overflow:hidden del contenedor
    def th(label, tip, align="right"):
        tip_safe = tip.replace('"','&quot;')
        return (
            f'<th style="{hs}text-align:{align};">'
            f'{label}'
            f'<span style="margin-left:0.3rem;position:relative;cursor:help;display:inline-block;">'
            f'<span style="font-size:0.6rem;color:#1e3a5f;border:1px solid #1e3a5f;'
            f'border-radius:50%;padding:0 3px;font-family:\'IBM Plex Mono\',monospace;" '
            f'title="{tip_safe}">?</span>'
            f'</span></th>'
        )

    table = (
        '<div style="overflow-x:auto;">'
        '<table style="width:100%;border-collapse:collapse;font-size:0.83rem;">'
        '<thead><tr style="background:#0a0e1a;">'
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
        color   = "#fca5a5"
        icon    = "🔥"
        summary = ("Confluencia de factores bajistas extremos. El potencial de squeeze es muy elevado "
                   "si llega un catalizador alcista (buenos resultados, noticia positiva, upgrade de analista). "
                   "Alto riesgo/oportunidad: movimientos de +20/30% en días no son inusuales en estos casos.")
    elif score >= 45:
        level   = "MODERADA-ALTA"
        color   = "#fb923c"
        icon    = "⚡"
        summary = ("Presión bajista significativa. Un catalizador positivo podría desencadenar coberturas "
                   "forzadas y amplificar el movimiento alcista más allá de lo que justificarían los fundamentales.")
    elif score >= 25:
        level   = "MODERADA"
        color   = "#fbbf24"
        icon    = "⚠️"
        summary = ("Short interest notable pero no en niveles de squeeze inminente. "
                   "Vigilar si continúa aumentando en los próximos meses.")
    elif score >= 10:
        level   = "BAJA"
        color   = "#6ee7b7"
        icon    = "✓"
        summary = "Presión bajista limitada. Poco riesgo de squeeze pero también poca presión compradora forzada."
    else:
        level   = "MUY BAJA"
        color   = "#38bdf8"
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
        '<div class="section-header">ANÁLISIS SHORT INTEREST &amp; SHORT SQUEEZE</div>',
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
            f'font-size:0.6rem;color:#334155;border:1px solid #334155;'
            f'border-radius:50%;padding:0 3px;font-family:monospace;'
            f'vertical-align:middle;">?</span>'
        )

    # Desglose de factores
    factor_rows = ""
    for fname, pts, max_pts, flbl in factors:
        pct_bar = (pts / max_pts * 100) if max_pts else 0
        bar_col = color if pts > 0 else "#1e2d45"
        factor_rows += (
            f'<div style="margin-bottom:0.5rem;">'
            f'<div style="display:flex;justify-content:space-between;font-size:0.78rem;margin-bottom:0.2rem;">'
            f'<span style="color:#94a3b8;">{fname}</span>'
            f'<span style="font-family:\'IBM Plex Mono\',monospace;color:{color if pts>0 else "#64748b"};">'
            f'{pts}/{max_pts}</span>'
            f'</div>'
            f'<div style="background:#1e2d45;border-radius:3px;height:6px;">'
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
        f'<div style="background:#1e2d45;border-radius:4px;height:8px;margin-bottom:1rem;">'
        f'<div style="height:8px;border-radius:4px;background:{color};width:{score}%;"></div>'
        f'</div>'
        # Métricas clave en grid
        f'<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:0.5rem;margin-bottom:1rem;">'
        f'<div style="background:#0f172a;border-radius:6px;padding:0.45rem 0.6rem;">'
        f'<div style="font-size:0.67rem;color:#64748b;">Short Ratio{tip_sr}</div>'
        f'<div style="font-family:\'IBM Plex Mono\',monospace;color:{color};font-weight:700;">'
        f'{sq["short_ratio"]:.1f} días</div></div>'
        f'<div style="background:#0f172a;border-radius:6px;padding:0.45rem 0.6rem;">'
        f'<div style="font-size:0.67rem;color:#64748b;">Short % del Float{tip_pf}</div>'
        f'<div style="font-family:\'IBM Plex Mono\',monospace;color:{color};font-weight:700;">'
        f'{sq["pct_float"]:.1f}%</div></div>'
        f'<div style="background:#0f172a;border-radius:6px;padding:0.45rem 0.6rem;">'
        f'<div style="font-size:0.67rem;color:#64748b;">Acciones en corto</div>'
        f'<div style="font-family:\'IBM Plex Mono\',monospace;color:#f1f5f9;font-weight:600;">'
        f'{fmt_shares(sq["shares_short"])}</div></div>'
        f'</div>'
        # Desglose por factor
        f'<div style="font-size:0.7rem;color:#38bdf8;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:0.5rem;">'
        f'Desglose de factores</div>'
        f'{factor_rows}'
        # Resumen
        f'<div style="background:#0f172a;border-radius:6px;padding:0.6rem 0.8rem;margin-top:0.5rem;">'
        f'<div style="font-size:0.78rem;color:#cbd5e1;line-height:1.6;">{summary}</div>'
        f'</div>'
        f'<div style="font-size:0.68rem;color:#475569;margin-top:0.5rem;">'
        f'Fuente: Yahoo Finance · El short squeeze no es predecible con certeza — requiere un catalizador externo.'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True
    )
