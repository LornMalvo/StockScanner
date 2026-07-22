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


def _calc_macd(closes: pd.Series) -> dict | None:
    """
    MACD estándar: EMA(12) - EMA(26), línea de señal = EMA(9) del MACD.

    Detecta además una divergencia alcista: si el precio marca un mínimo
    más bajo que el mínimo anterior, pero el histograma MACD en ese punto
    es más alto que en el mínimo anterior, el impulso bajista se está
    debilitando aunque el precio siga cayendo.

    MEJORA vs versión anterior: la detección original solo exigía que un
    punto fuese el más bajo en una ventana de ±5 sesiones, lo que en
    mercados de alta volatilidad podía marcar como "mínimo local" simple
    ruido de 1-2 días y disparar divergencias falsas que activaban
    prematuramente la Señal de Entrada. Ahora se exige además:
      1. Separación mínima de 10 sesiones entre los dos mínimos comparados
         (evita comparar dos dientes de sierra del mismo movimiento).
      2. Profundidad mínima: cada mínimo debe estar al menos un 3% por
         debajo de los máximos que lo rodean (±10 sesiones), para que
         cuente como un swing low real y no ruido intradía.
    """
    try:
        ema12  = closes.ewm(span=12, adjust=False).mean()
        ema26  = closes.ewm(span=26, adjust=False).mean()
        macd   = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        hist   = macd - signal

        macd_now, signal_now, hist_now = float(macd.iloc[-1]), float(signal.iloc[-1]), float(hist.iloc[-1])
        macd_prev, signal_prev = float(macd.iloc[-2]), float(signal.iloc[-2])

        bullish_cross = (macd_prev <= signal_prev) and (macd_now > signal_now)
        bearish_cross = (macd_prev >= signal_prev) and (macd_now < signal_now)

        MIN_SEPARATION = 10    # sesiones mínimas entre los dos mínimos comparados
        MIN_DEPTH_PCT  = 0.03  # profundidad mínima (3%) respecto a los máximos circundantes

        divergence = False
        window = min(90, len(closes) - 1)   # ventana algo más amplia para dar margen a la separación mínima
        recent_closes = closes.tail(window)
        recent_hist   = hist.tail(window)
        vals = recent_closes.values

        def _is_real_swing_low(i, vals, min_depth_pct):
            """Exige que el mínimo esté MIN_DEPTH_PCT por debajo de los máximos ±10 sesiones."""
            lo = max(0, i - 10)
            hi = min(len(vals), i + 11)
            surrounding_max = vals[lo:hi].max()
            if surrounding_max <= 0:
                return False
            depth = (surrounding_max - vals[i]) / surrounding_max
            return depth >= min_depth_pct

        local_min_idx = []
        for i in range(5, len(vals) - 5):
            seg = vals[i-5:i+6]
            if vals[i] == seg.min() and _is_real_swing_low(i, vals, MIN_DEPTH_PCT):
                local_min_idx.append(i)

        if len(local_min_idx) >= 2:
            i2 = local_min_idx[-1]
            # Buscar el mínimo anterior más reciente que cumpla la separación mínima
            i1_candidates = [idx for idx in local_min_idx[:-1] if (i2 - idx) >= MIN_SEPARATION]
            if i1_candidates:
                i1 = i1_candidates[-1]
                price_lower_low = vals[i2] < vals[i1]
                hist_higher_low = recent_hist.iloc[i2] > recent_hist.iloc[i1]
                divergence = price_lower_low and hist_higher_low

        return {
            "macd": round(macd_now, 4), "signal": round(signal_now, 4),
            "histogram": round(hist_now, 4),
            "bullish_cross": bullish_cross, "bearish_cross": bearish_cross,
            "bullish_divergence": divergence,
            # Series completas (misma longitud que "closes", sin NaN iniciales
            # porque ewm con adjust=False arranca en el primer valor) — se
            # usan para dibujar el panel de histograma MACD bajo el gráfico
            # de cotización, no solo el último valor puntual.
            "macd_series":      [round(float(v), 4) for v in macd.tolist()],
            "signal_series":    [round(float(v), 4) for v in signal.tolist()],
            "histogram_series": [round(float(v), 4) for v in hist.tolist()],
        }
    except Exception:
        return None


def _calc_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> float | None:
    """
    ADX (Average Directional Index) de 14 periodos — mide la FUERZA de la
    tendencia, no su dirección. Un ADX > 25 indica tendencia fuerte
    (alcista o bajista); < 20 indica mercado sin tendencia clara/lateral.
    Se usa como filtro de seguridad: una tendencia bajista fuerte (ADX>25
    con precio bajo MM200) bloquea la calificación "Entrada Ideal", evitando
    recomendar comprar en plena caída estructural ("cuchillo cayendo").
    """
    try:
        up_move   = high.diff()
        down_move = -low.diff()
        plus_dm   = ((up_move > down_move) & (up_move > 0)) * up_move
        minus_dm  = ((down_move > up_move) & (down_move > 0)) * down_move

        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low  - close.shift()).abs()
        tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        atr       = tr.ewm(alpha=1/period, adjust=False).mean()
        plus_di   = 100 * (plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr)
        minus_di  = 100 * (minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr)
        dx        = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
        adx       = dx.ewm(alpha=1/period, adjust=False).mean()

        val = float(adx.iloc[-1])
        return round(val, 2) if val == val else None   # descarta NaN
    except Exception:
        return None


def _calc_obv_signal(close: pd.Series, volume: pd.Series) -> dict | None:
    """
    On-Balance Volume — acumula volumen en días de subida, lo resta en días
    de bajada. Compara la tendencia del OBV contra la tendencia del precio
    en los últimos 20 días: si el precio cae o está plano pero el OBV sube,
    sugiere ACUMULACIÓN silenciosa (entradas de dinero fuerte pese al precio
    débil); si el precio sube pero el OBV cae, sugiere DISTRIBUCIÓN (el
    volumen no respalda la subida — posible rally débil).
    """
    try:
        direction = close.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
        obv = (direction * volume).fillna(0).cumsum()

        window = min(20, len(close) - 1)
        price_change = float(close.iloc[-1] - close.iloc[-window])
        obv_change   = float(obv.iloc[-1] - obv.iloc[-window])

        price_pct = price_change / float(close.iloc[-window]) * 100 if close.iloc[-window] else 0

        accumulation = price_pct <= 1 and obv_change > 0     # precio plano/bajista + OBV subiendo
        distribution = price_pct > 1 and obv_change < 0      # precio subiendo + OBV cayendo

        return {
            "obv_trend_up": obv_change > 0,
            "price_pct_20d": round(price_pct, 1),
            "accumulation": accumulation,
            "distribution": distribution,
        }
    except Exception:
        return None


def _calc_fibonacci_zone(price: float, week52_high: float | None, week52_low: float | None) -> dict | None:
    """
    Niveles de retroceso de Fibonacci entre el máximo y mínimo de 52 semanas
    (estructura estática de mercado — a diferencia de las medias móviles,
    que son soportes dinámicos, estos niveles no se mueven con el tiempo).
    Se considera "zona de soporte" si el precio está dentro de una banda de
    ±3% alrededor del retroceso del 61.8% o 78.6% — las zonas de rebote más
    vigiladas técnicamente tras una corrección.
    """
    if not price or not week52_high or not week52_low or week52_high <= week52_low:
        return None
    try:
        rango = week52_high - week52_low
        levels = {
            "23.6%": week52_high - rango * 0.236,
            "38.2%": week52_high - rango * 0.382,
            "50.0%": week52_high - rango * 0.500,
            "61.8%": week52_high - rango * 0.618,
            "78.6%": week52_high - rango * 0.786,
        }
        near_support = None
        for label, level in levels.items():
            if label in ("61.8%", "78.6%") and level > 0:
                if abs(price - level) / level <= 0.03:
                    near_support = label
                    break
        return {"levels": levels, "near_support": near_support}
    except Exception:
        return None


def _calc_historical_support(closes: pd.Series, dates: list, price: float) -> dict | None:
    """
    Encuentra el soporte histórico estructural más fuerte por debajo del
    precio actual, usando los 2 años de histórico ya disponibles.

    Método: se localizan los mínimos locales de la serie (puntos que son el
    valor más bajo dentro de una ventana de ±5 sesiones), se agrupan en
    "clusters" los que están a menos del 2.5% entre sí (niveles de precio
    donde el mercado ha rebotado varias veces), y se identifica el cluster
    con más toques (más veces que el precio ha rebotado ahí) que esté por
    debajo del precio actual y dentro de un rango razonable (hasta un 40%
    por debajo), para que sea relevante como referencia práctica y no un
    mínimo histórico demasiado lejano para importar en el corto plazo.

    A diferencia de las medias móviles (soportes dinámicos que se mueven
    con el tiempo) o Fibonacci (niveles proporcionales fijos), esto son
    niveles de precio REALES donde el mercado ya ha demostrado interés
    comprador de forma repetida.

    Además del cluster más fuerte (compatibilidad con el resto de la app,
    p.ej. Señal de Entrada, que solo necesita "el mejor soporte"), se
    devuelven también los 3 clusters más relevantes bajo la clave
    "clusters" — los usa el Motor de Confluencia (Capa A) para construir
    el Mapa de Suelos Proyectados con varios niveles, no solo uno.
    """
    try:
        vals = closes.values
        n    = len(vals)
        if n < 30:
            return None

        # Mínimos locales (ventana ±5 sesiones)
        local_mins = []
        for i in range(5, n - 5):
            seg = vals[i-5:i+6]
            if vals[i] == seg.min():
                local_mins.append((i, float(vals[i])))

        # Solo mínimos por debajo del precio actual y dentro de un -40% razonable
        candidates = [(i, v) for i, v in local_mins if v < price and v >= price * 0.60]
        if not candidates:
            return None

        # Clustering simple: agrupar niveles a menos del 2.5% entre sí
        candidates.sort(key=lambda x: x[1])
        clusters = []
        for i, v in candidates:
            placed = False
            for cl in clusters:
                if abs(v - cl["avg"]) / cl["avg"] <= 0.025:
                    cl["touches"].append((i, v))
                    cl["avg"] = sum(t[1] for t in cl["touches"]) / len(cl["touches"])
                    placed = True
                    break
            if not placed:
                clusters.append({"avg": v, "touches": [(i, v)]})

        # Exigir al menos 2 toques para considerarlo "soporte" real
        valid_clusters = [cl for cl in clusters if len(cl["touches"]) >= 2]
        if not valid_clusters:
            return None

        def _cluster_dict(cl):
            touch_idxs = [t[0] for t in cl["touches"]]
            last_touch_idx = max(touch_idxs)
            last_touch_date = dates[last_touch_idx] if last_touch_idx < len(dates) else None
            distance_pct = (price - cl["avg"]) / price * 100
            return {
                "level":        round(cl["avg"], 2),
                "touches":      len(cl["touches"]),
                "distance_pct": round(distance_pct, 1),
                "last_touch_date": last_touch_date,
            }

        # Los 3 clusters más relevantes: primero por nº de toques (más
        # fiable), y a igualdad de toques, el más cercano al precio actual
        # (más útil como referencia práctica que un mínimo muy lejano)
        valid_clusters.sort(key=lambda c: (-len(c["touches"]), price - c["avg"]))
        top_clusters = [_cluster_dict(cl) for cl in valid_clusters[:3]]

        # Para el Motor de Confluencia interesa el orden por cercanía al
        # precio (de más cercano a más profundo), no por nº de toques
        clusters_by_proximity = sorted(top_clusters, key=lambda c: c["level"], reverse=True)

        best = top_clusters[0]  # compatibilidad: cluster más fuerte por toques
        return {
            **best,
            "clusters": clusters_by_proximity,
        }
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# BALANCE HISTÓRICO (2 años) — para Piotroski F-Score, ROIC y Dilución
# ─────────────────────────────────────────────────────────────────────────────
# Yahoo cambia los nombres de fila del balance/income statement entre tickers
# sin previo aviso (ya nos ha pasado con EPS y Dividend Yield). Por eso cada
# campo se busca probando varios nombres candidatos y se descarta con None
# si ninguno aparece, en vez de asumir un valor — así cada criterio que
# dependa de este dato puede marcarse como "no evaluable" en vez de dar un
# resultado silenciosamente incorrecto.

def _find_row(df: pd.DataFrame, candidates: list):
    """Devuelve la primera fila (Serie) cuyo nombre coincide con algún candidato."""
    if df is None or df.empty:
        return None
    for name in candidates:
        if name in df.index:
            return df.loc[name]
    return None


def fetch_balance_sheet_history(ticker: str) -> dict:
    """
    Extrae del balance e income statement ANUAL (hasta 4 años disponibles,
    lo que Yahoo exponga) todos los campos necesarios para Piotroski
    F-Score, ROIC, el chequeo de dilución, y el crecimiento de beneficios
    suavizado (CAGR multi-año) usado en el Valor Objetivo. Cada campo puede
    venir como None si Yahoo no lo expone para ese ticker concreto — los
    consumidores de este dict deben tratarlo así, nunca asumir 0.
    """
    result = {
        "total_assets_cur": None, "total_assets_prior": None,
        "current_assets_cur": None, "current_liab_cur": None,
        "current_ratio_prior": None,
        "long_term_debt_cur": None, "long_term_debt_prior": None,
        "gross_margin_cur": None, "gross_margin_prior": None,
        "shares_out_cur": None, "shares_out_prior": None,
        "total_equity_cur": None,
        "operating_income_cur": None,
        "net_income_prior": None,
        "net_income_series": [],   # más reciente primero, hasta ~4 años
        "revenue_prior_for_turnover": None,
    }
    try:
        t  = yf.Ticker(ticker)
        bs = t.balance_sheet     # anual, columnas = años, más reciente primero
        inc = t.income_stmt

        if bs is not None and not bs.empty and len(bs.columns) >= 1:
            ta_row = _find_row(bs, ["Total Assets"])
            if ta_row is not None:
                vals = ta_row.dropna()
                if len(vals) >= 1: result["total_assets_cur"]   = float(vals.iloc[0])
                if len(vals) >= 2: result["total_assets_prior"] = float(vals.iloc[1])

            ca_row = _find_row(bs, ["Current Assets"])
            cl_row = _find_row(bs, ["Current Liabilities"])
            if ca_row is not None and cl_row is not None:
                ca_vals, cl_vals = ca_row.dropna(), cl_row.dropna()
                if len(ca_vals) >= 1 and len(cl_vals) >= 1:
                    result["current_assets_cur"] = float(ca_vals.iloc[0])
                    result["current_liab_cur"]   = float(cl_vals.iloc[0])
                if len(ca_vals) >= 2 and len(cl_vals) >= 2 and cl_vals.iloc[1]:
                    result["current_ratio_prior"] = float(ca_vals.iloc[1]) / float(cl_vals.iloc[1])

            ltd_row = _find_row(bs, ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"])
            if ltd_row is not None:
                vals = ltd_row.dropna()
                if len(vals) >= 1: result["long_term_debt_cur"]   = float(vals.iloc[0])
                if len(vals) >= 2: result["long_term_debt_prior"] = float(vals.iloc[1])

            shares_row = _find_row(bs, ["Ordinary Shares Number", "Share Issued"])
            if shares_row is not None:
                vals = shares_row.dropna()
                if len(vals) >= 1: result["shares_out_cur"]   = float(vals.iloc[0])
                if len(vals) >= 2: result["shares_out_prior"] = float(vals.iloc[1])

            eq_row = _find_row(bs, ["Common Stock Equity", "Stockholders Equity",
                                     "Total Equity Gross Minority Interest"])
            if eq_row is not None:
                vals = eq_row.dropna()
                if len(vals) >= 1: result["total_equity_cur"] = float(vals.iloc[0])

        if inc is not None and not inc.empty and len(inc.columns) >= 1:
            rev_row  = _find_row(inc, ["Total Revenue"])
            cogs_row = _find_row(inc, ["Cost Of Revenue", "Reconciled Cost Of Revenue"])
            gp_row   = _find_row(inc, ["Gross Profit"])
            if rev_row is not None:
                rev_vals = rev_row.dropna()
                if len(rev_vals) >= 2:
                    result["revenue_prior_for_turnover"] = float(rev_vals.iloc[1])
                if gp_row is not None:
                    gp_vals = gp_row.dropna()
                    if len(rev_vals) >= 1 and len(gp_vals) >= 1 and rev_vals.iloc[0]:
                        result["gross_margin_cur"] = float(gp_vals.iloc[0]) / float(rev_vals.iloc[0])
                    if len(rev_vals) >= 2 and len(gp_vals) >= 2 and rev_vals.iloc[1]:
                        result["gross_margin_prior"] = float(gp_vals.iloc[1]) / float(rev_vals.iloc[1])
                elif cogs_row is not None:
                    cogs_vals = cogs_row.dropna()
                    if len(rev_vals) >= 1 and len(cogs_vals) >= 1 and rev_vals.iloc[0]:
                        result["gross_margin_cur"] = (float(rev_vals.iloc[0]) - float(cogs_vals.iloc[0])) / float(rev_vals.iloc[0])
                    if len(rev_vals) >= 2 and len(cogs_vals) >= 2 and rev_vals.iloc[1]:
                        result["gross_margin_prior"] = (float(rev_vals.iloc[1]) - float(cogs_vals.iloc[1])) / float(rev_vals.iloc[1])

            op_row = _find_row(inc, ["Operating Income", "EBIT"])
            if op_row is not None:
                vals = op_row.dropna()
                if len(vals) >= 1: result["operating_income_cur"] = float(vals.iloc[0])

            ni_row = _find_row(inc, ["Net Income", "Net Income Common Stockholders"])
            if ni_row is not None:
                vals = ni_row.dropna()
                if len(vals) >= 2: result["net_income_prior"] = float(vals.iloc[1])
                # Serie completa disponible (más reciente primero), para CAGR multi-año
                result["net_income_series"] = [float(v) for v in vals.tolist()]

    except Exception as e:
        print(f"[BalanceHistory] {ticker}: {e}")

    return result


# ─────────────────────────────────────────────────────────────────────────────
# FUERZA RELATIVA VS MERCADO (SPY) Y LIQUIDEZ
# ─────────────────────────────────────────────────────────────────────────────

def fetch_relative_strength(closes: pd.Series, period_days: int = 63) -> dict | None:
    """
    Compara el rendimiento de la acción contra el S&P 500 (SPY) en la misma
    ventana temporal (~63 sesiones = 3 meses). Una caída del 15% en un mes en
    que el mercado cae un 20% es en realidad fuerza relativa, no debilidad —
    el sistema técnico actual evalúa la acción aislada sin este contexto.
    """
    try:
        if len(closes) < period_days + 1:
            period_days = len(closes) - 1
        if period_days < 10:
            return None

        stock_ret = float(closes.iloc[-1] / closes.iloc[-period_days-1] - 1) * 100

        spy = yf.Ticker("SPY").history(period="6mo", interval="1d")["Close"]
        if spy.empty or len(spy) < period_days + 1:
            return None
        spy_ret = float(spy.iloc[-1] / spy.iloc[-period_days-1] - 1) * 100

        rel_strength = stock_ret - spy_ret
        return {
            "stock_return_pct": round(stock_ret, 1),
            "spy_return_pct":   round(spy_ret, 1),
            "relative_strength_pct": round(rel_strength, 1),
            "period_days": period_days,
            "outperforming": rel_strength > 0,
        }
    except Exception as e:
        print(f"[RelativeStrength] Error: {e}")
        return None


def _calc_ma_cross_recency(closes: pd.Series, dates_str: list) -> dict | None:
    """
    Fecha del último Golden/Death Cross (MM50 cruza MM200) y su antigüedad
    en sesiones. Sustituye a fetch_last_cross_date() (analysis.py), que
    hacía su propia llamada de red duplicada al histórico de 2 años —
    aquí se reutiliza el histórico que fetch_technical_data() ya descargó.

    Es un indicador REZAGADO por naturaleza (una media de 200 sesiones
    tarda en reaccionar): confirma una tendencia ya en marcha, no la
    predice. Por eso en la Señal de Entrada se pondera de forma moderada,
    igual que MACD u OBV, no como un factor fundamental.
    """
    try:
        n = len(closes)
        if n < 200:
            return None
        mm50  = closes.rolling(50).mean()
        mm200 = closes.rolling(200).mean()
        diff  = mm50 - mm200
        for i in range(n - 1, 0, -1):
            d_i, d_im1 = diff.iloc[i], diff.iloc[i-1]
            if pd.isna(d_i) or pd.isna(d_im1):
                continue
            if d_i > 0 and d_im1 <= 0:
                return {"date": dates_str[i], "type": "GOLDEN CROSS", "days_ago": (n - 1) - i}
            if d_i < 0 and d_im1 >= 0:
                return {"date": dates_str[i], "type": "DEATH CROSS", "days_ago": (n - 1) - i}
        return None
    except Exception:
        return None


def _calc_price_ma_cross(closes: pd.Series, ma_series: pd.Series, volumes: pd.Series,
                          dates_str: list, ma_label: str) -> dict | None:
    """
    Última vez que el PRECIO (no las medias entre sí) cruzó una media
    móvil concreta, con el volumen de esa sesión comparado a la media de
    volumen de las 20 sesiones previas. Un cruce con volumen significativo
    (≥1.5×) tiene más peso como ruptura real que uno con volumen normal
    (más probable que sea un "falso cruce" que se revierte enseguida).
    """
    try:
        n = len(closes)
        if n < 25 or ma_series is None:
            return None
        diff = closes - ma_series
        for i in range(n - 1, 0, -1):
            d_i, d_im1 = diff.iloc[i], diff.iloc[i-1]
            if pd.isna(d_i) or pd.isna(d_im1):
                continue
            crossed_up   = d_i > 0 and d_im1 <= 0
            crossed_down = d_i < 0 and d_im1 >= 0
            if crossed_up or crossed_down:
                vol_window   = volumes.iloc[max(0, i - 20):i]
                avg_vol      = float(vol_window.mean()) if len(vol_window) > 0 else None
                vol_that_day = float(volumes.iloc[i])
                vol_ratio    = (vol_that_day / avg_vol) if avg_vol and avg_vol > 0 else None
                return {
                    "ma":                 ma_label,
                    "direction":          "up" if crossed_up else "down",
                    "date":               dates_str[i],
                    "days_ago":           (n - 1) - i,
                    "volume_ratio":       round(vol_ratio, 2) if vol_ratio is not None else None,
                    "significant_volume": bool(vol_ratio is not None and vol_ratio >= 1.5),
                }
        return None
    except Exception:
        return None


def _calc_cross_proximity(mm50: float | None, mm200: float | None, price: float | None) -> dict | None:
    """
    Alerta de PROXIMIDAD — no una predicción. Señala cuándo la MM50 y la
    MM200 están muy próximas entre sí (posible Golden/Death Cross cercano
    si la tendencia actual continúa) o cuándo el precio está muy cerca de
    tocar una de las medias. Es puramente informativa: extrapolar CUÁNDO
    se producirá un cruce a partir de la pendiente reciente no tiene
    respaldo estadístico real (las tendencias revierten constantemente,
    sobre todo en mercados laterales) — por eso este dato NO puntúa en la
    Señal de Entrada, solo se muestra como aviso a vigilar.
    """
    if not mm50 or not mm200 or not price:
        return None
    NEAR_THRESHOLD = 2.0  # % de margen para considerar "cerca"
    notes = []
    gap_ma_pct = abs(mm50 - mm200) / price * 100
    if gap_ma_pct <= NEAR_THRESHOLD:
        notes.append(f"MM50 y MM200 muy próximas ({gap_ma_pct:.1f}% de separación) — posible cruce cercano si continúa la tendencia")
    dist_mm50_pct = abs(price - mm50) / price * 100
    if dist_mm50_pct <= NEAR_THRESHOLD:
        notes.append(f"Precio a {dist_mm50_pct:.1f}% de la MM50")
    dist_mm200_pct = abs(price - mm200) / price * 100
    if dist_mm200_pct <= NEAR_THRESHOLD:
        notes.append(f"Precio a {dist_mm200_pct:.1f}% de la MM200")
    return {"notes": notes} if notes else None


# ─────────────────────────────────────────────────────────────────────────────
# MOTOR DE CONFLUENCIA — zonas de soporte por combinación de métodos
# ─────────────────────────────────────────────────────────────────────────────
# Vive aquí (no en report.py, donde se usa para el Plan de Entrada/Salida, ni
# en analysis.py, donde se usa para la Señal de Entrada) porque ambos módulos
# necesitan importarla y report.py ya importa de analysis.py — así se evita
# el import circular manteniendo una única implementación compartida.

CONFLUENCE_MARGIN = 0.015

# Nº de capas independientes coincidiendo en una zona -> etiqueta de fiabilidad
_RELIABILITY_LABELS = {
    1: "Media (1 indicador)",
    2: "Alta (2 indicadores)",
}
_RELIABILITY_LABEL_3PLUS = "Extrema (3+ indicadores)"


def build_confluence_supports(price: float, tech: dict) -> list:
    """
    Motor de Confluencia (Fase 1 — Capas A, C y D; la Capa B de Volume
    Profile/HVN queda para la Fase 2).

    Combina 3 métodos técnicos independientes que la app ya calcula por
    separado:
      Capa A: clusters de soporte histórico (mínimos locales con rebotes reales)
      Capa C: medias móviles dinámicas (MM50, MM100, MM200)
      Capa D: retrocesos de Fibonacci (38.2/50/61.8/78.6% del rango 52 semanas)

    y agrupa los niveles que caen dentro de ±1.5% entre sí en una misma
    "zona de soporte". Cuantas más capas independientes coincidan en la
    misma zona, mayor la fiabilidad de que el precio encuentre comprador
    ahí ("Soporte de Alta Fiabilidad").

    Devuelve una lista de zonas por debajo del precio actual, ordenadas de
    más cercana a más profunda, cada una con: price, distance_pct,
    indicators (etiquetas de los métodos que confluyen ahí), n_layers
    (nº de capas distintas) y reliability (etiqueta textual).

    Usada tanto por el Plan de Entrada/Salida (report.py) como por el check
    "cerca de un soporte" de la Señal de Entrada (analysis.py) — antes eran
    2 sistemas separados resolviendo la misma pregunta con lógicas
    distintas; ahora comparten una única implementación.
    """
    raw = []  # (etiqueta, precio, capa)

    mm50, mm100, mm200 = tech.get("mm50"), tech.get("mm100"), tech.get("mm200")
    if mm50 and mm50 < price:
        raw.append(("MM50", mm50, "media_movil"))
    if mm100 and mm100 < price:
        raw.append(("MM100", mm100, "media_movil"))
    if mm200 and mm200 < price:
        raw.append(("MM200", mm200, "media_movil"))

    fib_data = tech.get("fibonacci")
    if fib_data and fib_data.get("levels"):
        for label in ("38.2%", "50.0%", "61.8%", "78.6%"):
            lvl = fib_data["levels"].get(label)
            if lvl and lvl < price:
                raw.append((f"Fibonacci {label}", lvl, "fibonacci"))

    support_data = tech.get("historical_support")
    if support_data and support_data.get("clusters"):
        for cl in support_data["clusters"]:
            if cl["level"] < price:
                raw.append((f"Soporte histórico ({cl['touches']}× rebotes)", cl["level"], "historico"))

    if not raw:
        return []

    # Agrupar por confluencia: de más cercano al precio a más profundo,
    # fusionando cada candidato con la zona abierta más reciente si cae
    # dentro del margen (las capas ya vienen pre-ordenadas por precio
    # dentro de cada capa, y el orden global por precio agrupa bien las
    # zonas sin necesitar una búsqueda cuadrática más compleja)
    raw.sort(key=lambda c: c[1], reverse=True)
    zones = []
    for label, lvl, layer in raw:
        placed = False
        for z in zones:
            if abs(lvl - z["_avg"]) / z["_avg"] <= CONFLUENCE_MARGIN:
                z["_members"].append((label, lvl, layer))
                z["_avg"] = sum(m[1] for m in z["_members"]) / len(z["_members"])
                placed = True
                break
        if not placed:
            zones.append({"_avg": lvl, "_members": [(label, lvl, layer)]})

    result = []
    for z in zones:
        n_layers = len(set(m[2] for m in z["_members"]))
        result.append({
            "price":        round(z["_avg"], 2),
            "distance_pct": round((z["_avg"] - price) / price * 100, 1),
            "indicators":   [m[0] for m in z["_members"]],
            "n_layers":     n_layers,
            "reliability":  _RELIABILITY_LABELS.get(n_layers, _RELIABILITY_LABEL_3PLUS),
        })

    result.sort(key=lambda z: z["price"], reverse=True)
    return result


def fetch_technical_data(ticker: str) -> dict:
    """RSI(14), MM50, MM200 con metadatos de frescura."""
    try:
        t = yf.Ticker(ticker)
        # Se piden 2 años para tener margen suficiente: la media móvil de 200
        # sesiones necesita 200 días PREVIOS a cada punto del gráfico. Si solo
        # pidiéramos 1 año, la MM200 del gráfico solo tendría datos válidos en
        # los últimos ~50 días del periodo (el resto sería NaN por falta de
        # histórico previo dentro de la ventana pedida) — por eso se veía
        # "demasiado corta" respecto a la MM50.
        hist_full = t.history(period="2y", interval="1d")

        if hist_full.empty or len(hist_full) < 50:
            return {"error": "Histórico insuficiente"}

        closes_full = hist_full["Close"]
        price       = float(closes_full.iloc[-1])

        # Fecha del último dato
        last_date = hist_full.index[-1]
        if hasattr(last_date, "strftime"):
            last_date_str = last_date.strftime("%Y-%m-%d")
        else:
            last_date_str = str(last_date)[:10]
        days_old  = _days_since(last_date_str)
        freshness = _freshness_status(days_old, STALE_PRICE)

        rsi   = _calc_rsi(closes_full)
        mm50  = round(float(closes_full.tail(50).mean()), 4)
        mm100 = round(float(closes_full.tail(100).mean()), 4) if len(closes_full) >= 100 else None
        mm200 = round(float(closes_full.tail(200).mean()), 4) if len(closes_full) >= 200 else None

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

        # ── Nuevos indicadores: MACD, ADX, OBV, Fibonacci ────────────────
        macd_data = _calc_macd(closes_full)
        adx_val   = _calc_adx(hist_full["High"], hist_full["Low"], closes_full)
        obv_data  = _calc_obv_signal(closes_full, hist_full["Volume"])
        week52_h  = float(closes_full.tail(252).max())
        week52_l  = float(closes_full.tail(252).min())
        fib_data  = _calc_fibonacci_zone(price, week52_h, week52_l)

        dates_str_full = [
            (d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10])
            for d in hist_full.index
        ]
        support_data = _calc_historical_support(closes_full, dates_str_full, price)
        rel_strength_data = fetch_relative_strength(closes_full)

        # ── Serie histórica para gráfico ─────────────────────────────────
        # Las medias móviles se calculan sobre los 2 años completos (para que
        # la MM200 tenga suficiente margen previo en TODO el tramo mostrado),
        # y luego se recorta la serie final al último año para el gráfico.
        mm50_series  = closes_full.rolling(window=50).mean()
        mm200_series = closes_full.rolling(window=200).mean() if len(closes_full) >= 200 else None

        # ── Cruces: Golden/Death Cross reciente + cruce de precio con volumen ──
        last_ma_cross    = _calc_ma_cross_recency(closes_full, dates_str_full)
        price_cross_mm50 = _calc_price_ma_cross(closes_full, mm50_series, hist_full["Volume"],
                                                 dates_str_full, "MM50")
        price_cross_mm200 = (_calc_price_ma_cross(closes_full, mm200_series, hist_full["Volume"],
                                                    dates_str_full, "MM200")
                              if mm200_series is not None else None)
        cross_proximity = _calc_cross_proximity(mm50, mm200, price)

        # Recorte a ~1 año de sesiones (252 aprox.) para el gráfico
        display_start = max(0, len(closes_full) - 252)

        price_history = []
        for i in range(display_start, len(closes_full)):
            d = hist_full.index[i]
            date_str = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
            price_history.append({
                "date":  date_str,
                "close": round(float(closes_full.iloc[i]), 4),
                "mm50":  round(float(mm50_series.iloc[i]), 4) if not mm50_series.isna().iloc[i] else None,
                "mm200": (round(float(mm200_series.iloc[i]), 4)
                          if mm200_series is not None and not mm200_series.isna().iloc[i] else None),
                "macd":        macd_data["macd_series"][i]      if macd_data else None,
                "macd_signal": macd_data["signal_series"][i]    if macd_data else None,
                "macd_hist":   macd_data["histogram_series"][i] if macd_data else None,
            })

        return {
            "price":        price,
            "rsi":          rsi,
            "rsi_label":    rsi_lbl,
            "rsi_css":      rsi_cls,
            "mm50":         mm50,
            "mm50_signal":  mm50_signal,
            "mm50_css":     mm50_cls,
            "dist_mm50":    dist_mm50,
            "mm100":        mm100,
            "mm200":        mm200,
            "mm200_signal": mm200_signal,
            "mm200_css":    mm200_cls,
            "dist_mm200":   dist_mm200,
            "cross_signal": cross_signal,
            "last_ma_cross":      last_ma_cross,
            "price_cross_mm50":   price_cross_mm50,
            "price_cross_mm200":  price_cross_mm200,
            "cross_proximity":    cross_proximity,
            "price_history":price_history,
            "macd":         macd_data,
            "adx":          adx_val,
            "obv":          obv_data,
            "fibonacci":    fib_data,
            "historical_support": support_data,
            "relative_strength": rel_strength_data,
            "week52_high_calc": week52_h,
            "week52_low_calc":  week52_l,
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

def _calc_dividend_frequency(t) -> str | None:
    """
    Estima la periodicidad del dividendo contando cuántos pagos ha habido
    en los últimos ~400 días (margen sobre 1 año para no perder un pago
    por desfase de calendario). No usa un campo directo de Yahoo porque
    no expone la periodicidad de forma fiable para todos los tickers.
    """
    try:
        divs = t.dividends
        if divs is None or divs.empty:
            return None
        last_ts = divs.index[-1]
        cutoff  = last_ts - pd.Timedelta(days=400)
        recent  = divs[divs.index >= cutoff]
        n = len(recent)
        if n >= 10: return "Mensual"
        if n >= 3:  return "Trimestral"
        if n == 2:  return "Semestral"
        if n == 1:  return "Anual"
        return None
    except Exception:
        return None


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

        # ── EBIT e Interest Expense TTM (para Cobertura de Intereses) ──────
        # interest_expense también lo usa calc_wacc (dcf.py) para el coste
        # de deuda implícito — antes ese campo nunca se rellenaba desde
        # aquí, así que WACC siempre caía al fallback (Rf + 1.5pp) aunque
        # hubiera datos reales disponibles.
        ebit_ttm = None
        if income_stmt is not None and not income_stmt.empty:
            for label in ["EBIT", "Operating Income"]:
                if label in income_stmt.index:
                    row = income_stmt.loc[label].dropna()
                    if len(row) > 0:
                        ebit_ttm = float(row.iloc[:4].sum())
                        break

        interest_expense_ttm = None
        if income_stmt is not None and not income_stmt.empty:
            for label in ["Interest Expense", "Interest Expense Non Operating"]:
                if label in income_stmt.index:
                    row = income_stmt.loc[label].dropna()
                    if len(row) > 0:
                        interest_expense_ttm = abs(float(row.iloc[:4].sum()))
                        break

        # ── EPS trimestral ────────────────────────────────────────────────
        eps_q = []
        try:
            qe = t.quarterly_earnings
            if qe is not None and not qe.empty:
                for idx, row in qe.iterrows():
                    eps_val = row.get("Earnings") if "Earnings" in row else None
                    if eps_val is None:
                        eps_val = row.iloc[0] if len(row) > 0 else None
                    date_str = str(idx)[:10] if idx else ""
                    if eps_val is not None and date_str:
                        eps_q.append({"date": date_str, "value": float(eps_val)})
            # Fallback: Basic EPS desde quarterly_income_stmt
            if not eps_q and income_stmt is not None and not income_stmt.empty:
                for label in ["Basic EPS", "Diluted EPS", "EPS"]:
                    if label in income_stmt.index:
                        eps_row = income_stmt.loc[label]
                        for i, (date, val) in enumerate(eps_row.items()):
                            if i >= 4: break
                            if val is not None:
                                import math
                                if not math.isnan(float(val)):
                                    eps_q.append({"date": str(date)[:10], "value": float(val)})
                        if eps_q:
                            break
        except Exception:
            eps_q = []

        ttm_revenue    = sum(q["value"] for q in ttm_quarters if q["value"] == q["value"])
        ttm_net_income = sum(q["value"] for q in net_income_q if q["value"] == q["value"])

        # ── Crecimiento YoY ───────────────────────────────────────────────
        revenue_yoy   = None
        earnings_yoy  = None
        rev_year_cur  = None   # valor absoluto revenue año actual
        rev_year_prev = None   # valor absoluto revenue año anterior
        rev_date_cur  = None   # fecha fin de año fiscal actual
        rev_date_prev = None   # fecha fin de año fiscal anterior
        ni_year_cur   = None
        ni_year_prev  = None
        ni_date_cur   = None
        ni_date_prev  = None

        rev_annual = t.financials
        if rev_annual is not None and not rev_annual.empty:
            for label in ["Total Revenue", "Revenue"]:
                if label in rev_annual.index:
                    row = rev_annual.loc[label].dropna()
                    if len(row) >= 2:
                        rev_year_cur  = float(row.iloc[0])
                        rev_year_prev = float(row.iloc[1])
                        rev_date_cur  = str(row.index[0])[:10]
                        rev_date_prev = str(row.index[1])[:10]
                        revenue_yoy   = (rev_year_cur - rev_year_prev) / abs(rev_year_prev) * 100
                    break

        ni_annual = t.income_stmt
        if ni_annual is not None and not ni_annual.empty:
            for label in ["Net Income", "Net Income Common Stockholders"]:
                if label in ni_annual.index:
                    row = ni_annual.loc[label].dropna()
                    if len(row) >= 2:
                        ni_year_cur   = float(row.iloc[0])
                        ni_year_prev  = float(row.iloc[1])
                        ni_date_cur   = str(row.index[0])[:10]
                        ni_date_prev  = str(row.index[1])[:10]
                        earnings_yoy  = (ni_year_cur - ni_year_prev) / abs(ni_year_prev) * 100
                    break

        # Yahoo Finance devuelve dividendYield unas veces como fracción
        # decimal (0.0142 = 1.42%) y otras veces ya como porcentaje
        # (1.42 = 1.42%), sin previo aviso ni consistencia por ticker.
        # ARREGLO ANTERIOR (insuficiente): solo corregíamos si el valor
        # bruto era > 1, asumiendo que ese era el único caso "ya en
        # porcentaje". Pero para empresas de yield bajo (<1%, ej. MSFT,
        # AAPL, AVGO) Yahoo puede devolver el valor YA en formato
        # porcentaje pese a ser < 1 (ej. 0.91 significando "0.91%", no una
        # fracción de 91%) — el test ">1" no detectaba esto y el resto de
        # la app (que multiplica ×100 para mostrar) lo convertía en 91%.
        #
        # ARREGLO ROBUSTO: en vez de un umbral fijo, se usa un dato
        # independiente para desambiguar — dividendRate (importe anual en
        # $/acción) ÷ precio da el yield real esperado. Se compara el
        # valor bruto de Yahoo contra las DOS interpretaciones posibles
        # (como fracción, o como porcentaje) y se elige la que más se
        # acerque al yield real calculado de forma independiente.
        _dy_raw   = info.get("dividendYield")
        _div_rate = info.get("dividendRate")
        _dy_norm  = _dy_raw
        if _dy_raw is not None:
            if _div_rate and price and price > 0:
                _expected_fraction = _div_rate / price
                _expected_percent  = _expected_fraction * 100
                _dist_as_fraction = abs(_dy_raw - _expected_fraction)
                _dist_as_percent  = abs(_dy_raw - _expected_percent)
                _dy_norm = (_dy_raw / 100) if _dist_as_percent < _dist_as_fraction else _dy_raw
            else:
                # Sin dividendRate para contrastar: fallback al umbral
                # anterior (mejor que nada, aunque no cubre el caso de
                # yields bajos ya en formato porcentaje)
                _dy_norm = (_dy_raw / 100 if _dy_raw > 1 else _dy_raw)

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
            "quick_ratio":    info.get("quickRatio"),
            "free_cash_flow": info.get("freeCashflow"),
            "operating_cf":   info.get("operatingCashflow"),

            # Crecimiento
            "revenue_yoy":  revenue_yoy  if revenue_yoy  is not None else (info.get("revenueGrowth",  0) * 100 if info.get("revenueGrowth")  else None),
            "earnings_yoy": earnings_yoy if earnings_yoy is not None else (info.get("earningsGrowth", 0) * 100 if info.get("earningsGrowth") else None),
            "rev_year_cur":   rev_year_cur,
            "rev_year_prev":  rev_year_prev,
            "rev_date_cur":   rev_date_cur,
            "rev_date_prev":  rev_date_prev,
            "ni_year_cur":    ni_year_cur,
            "ni_year_prev":   ni_year_prev,
            "ni_date_cur":    ni_date_cur,
            "ni_date_prev":   ni_date_prev,

            # Dividendos
            "dividend_yield":     _dy_norm,
            "dividend_rate":      info.get("dividendRate"),
            "ex_dividend_date":   info.get("exDividendDate"),
            "dividend_frequency": _calc_dividend_frequency(t),

            # Otros
            "short_ratio":            info.get("shortRatio"),
            "shares_short":           info.get("sharesShort"),
            "shares_short_prior":     info.get("sharesShortPriorMonth"),
            "short_percent_of_float": info.get("shortPercentOfFloat"),
            "float_shares":           info.get("floatShares"),
            "shares_outstanding":     info.get("sharesOutstanding"),
            "average_volume":         info.get("averageVolume") or info.get("averageDailyVolume10Day"),
            "date_short_interest":    info.get("dateShortInterest"),
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
            "eps_q":           eps_q,
            "ebitda":          info.get("ebitda"),
            "ebit_ttm":        ebit_ttm,
            "interest_expense": interest_expense_ttm,

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

# SEC exige User-Agent con nombre + email, formato: "AppName/Version (email)"
SEC_HEADERS = {
    "User-Agent":      "StockScannerApp/1.0 (analisis@stockscanner.app)",
    "Accept":          "application/json",
    "Accept-Encoding": "gzip, deflate",
}

# Conceptos de ingresos en orden de preferencia
REVENUE_CONCEPTS = [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
    "SalesRevenueGoodsNet",
    "RevenueNet",
    "InterestAndDividendIncomeOperating",
    "RevenuesNetOfInterestExpense",
    "HealthCareOrganizationRevenue",
]

NET_INCOME_CONCEPTS = [
    "NetIncomeLoss",
    "NetIncomeLossAvailableToCommonStockholdersBasic",
    "ProfitLoss",
]


_CIK_MAP_CACHE: dict = {}   # ticker -> CIK, cacheado a nivel de proceso — el
                             # listado completo de la SEC son varios MB, no
                             # tiene sentido volver a descargarlo en cada
                             # análisis si ya lo tenemos de una consulta previa


def _get_cik(ticker: str) -> str | None:
    """Obtiene el CIK de la SEC para un ticker dado (con caché de proceso)."""
    global _CIK_MAP_CACHE
    if not _CIK_MAP_CACHE:
        try:
            r = requests.get(
                "https://www.sec.gov/files/company_tickers.json",
                headers=SEC_HEADERS, timeout=12
            )
            if r.status_code != 200:
                print(f"[SEC CIK] HTTP {r.status_code}")
                return None
            data = r.json()
            for entry in data.values():
                t = entry.get("ticker", "").upper()
                if t:
                    _CIK_MAP_CACHE[t] = str(entry["cik_str"]).zfill(10)
        except Exception as e:
            print(f"[SEC CIK] Error: {e}")
            return None
    return _CIK_MAP_CACHE.get(ticker.upper())


def _get_concept(cik: str, concept: str, unit: str = "USD") -> list:
    """Descarga una serie de datos del SEC EDGAR XBRL API."""
    url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{concept}.json"
    try:
        r = requests.get(url, headers=SEC_HEADERS, timeout=20)
        if r.status_code == 404:
            return []
        if r.status_code != 200:
            print(f"[SEC {concept}] HTTP {r.status_code}")
            return []
        data     = r.json()
        units    = data.get("units", {}).get(unit, [])
        filtered = [
            u for u in units
            if u.get("form") in ("10-Q", "10-K")
            and u.get("end")
            and u.get("val") is not None
        ]
        filtered.sort(key=lambda x: x.get("end", ""), reverse=True)
        return filtered
    except Exception as e:
        print(f"[SEC {concept}] Error: {e}")
        return []


def _last_4_quarters(series: list) -> list:
    """
    Extrae los 4 últimos trimestres estancos.
    Acepta períodos 60-135 días para cubrir calendarios fiscales atípicos.
    Excluye 10-K (acumulados anuales) — solo usa 10-Q estancos.
    """
    from datetime import datetime as dt
    quarterly = []
    seen_ends = set()
    for item in series:
        start = item.get("start", "")
        end   = item.get("end",   "")
        form  = item.get("form",  "")
        if not start or not end or form != "10-Q":
            continue
        try:
            days = (dt.strptime(end, "%Y-%m-%d") - dt.strptime(start, "%Y-%m-%d")).days
        except Exception:
            continue
        if 60 <= days <= 135 and end not in seen_ends:
            quarterly.append(item)
            seen_ends.add(end)
        if len(quarterly) == 4:
            break
    return quarterly


def _fetch_first_concept(cik: str, concepts: list) -> list:
    """Prueba conceptos en orden y devuelve el primero con datos."""
    for concept in concepts:
        data = _get_concept(cik, concept)
        if data:
            return data
    return []


def fetch_sec_data(ticker: str) -> dict | None:
    """Ingresos y beneficio neto TTM desde SEC EDGAR con metadatos de frescura."""
    cik = _get_cik(ticker)
    if not cik:
        return None

    rev_series = _fetch_first_concept(cik, REVENUE_CONCEPTS)
    rev_q      = _last_4_quarters(rev_series)
    ni_series  = _fetch_first_concept(cik, NET_INCOME_CONCEPTS)
    ni_q       = _last_4_quarters(ni_series)

    if not rev_q:
        return None

    ttm_revenue    = sum(q.get("val", 0) for q in rev_q)
    ttm_net_income = sum(q.get("val", 0) for q in ni_q) if ni_q else None

    quarters_fmt = [
        {"date": q["end"], "value": q["val"], "filed": q.get("filed",""), "form": q.get("form","")}
        for q in rev_q
    ]
    ni_fmt = [
        {"date": q["end"], "value": q["val"], "filed": q.get("filed",""), "form": q.get("form","")}
        for q in ni_q
    ] if ni_q else []

    latest_end   = rev_q[0].get("end",   "") if rev_q else ""
    latest_filed = rev_q[0].get("filed", "") if rev_q else ""
    days_end     = _days_since(latest_end)
    days_filed   = _days_since(latest_filed)
    sec_freshness = _freshness_status(days_end, STALE_SEC)

    return {
        "cik":            cik,
        "ttm_revenue":    ttm_revenue,
        "ttm_net_income": ttm_net_income,
        "quarters":       quarters_fmt,
        "ni_quarters":    ni_fmt,
        "currency":       "USD",
        "meta": {
            "fetch_time":       _now().strftime("%Y-%m-%d %H:%M UTC"),
            "latest_end":       latest_end,
            "latest_filed":     latest_filed,
            "days_since_end":   days_end,
            "days_since_filed": days_filed,
            "freshness":        sec_freshness,
            "trust":            TRUST["OFICIAL"],
            "source":           f"SEC EDGAR (CIK {cik}) — último trimestre: {latest_end}, filing: {latest_filed}",
            "n_quarters_found": len(rev_q),
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
