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
    Detecta además una divergencia alcista simplificada: si el precio marca
    un mínimo más bajo que el mínimo anterior reciente, pero el histograma
    MACD en ese punto es más alto que en el mínimo anterior, el impulso
    bajista se está debilitando aunque el precio siga cayendo — señal de
    posible agotamiento de la tendencia bajista.
    """
    try:
        ema12  = closes.ewm(span=12, adjust=False).mean()
        ema26  = closes.ewm(span=26, adjust=False).mean()
        macd   = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        hist   = macd - signal

        macd_now, signal_now, hist_now = float(macd.iloc[-1]), float(signal.iloc[-1]), float(hist.iloc[-1])
        macd_prev, signal_prev = float(macd.iloc[-2]), float(signal.iloc[-2])

        # Cruce alcista: MACD cruza por encima de la señal en la última sesión
        bullish_cross = (macd_prev <= signal_prev) and (macd_now > signal_now)
        bearish_cross = (macd_prev >= signal_prev) and (macd_now < signal_now)

        # Divergencia alcista simplificada sobre los últimos 60 días:
        # localizar los dos mínimos de precio más recientes (ventana ±5 días)
        # y comparar el histograma MACD en esos dos puntos.
        divergence = False
        window = min(60, len(closes) - 1)
        recent_closes = closes.tail(window)
        recent_hist   = hist.tail(window)
        local_min_idx = []
        vals = recent_closes.values
        for i in range(5, len(vals) - 5):
            seg = vals[i-5:i+6]
            if vals[i] == seg.min():
                local_min_idx.append(i)
        if len(local_min_idx) >= 2:
            i1, i2 = local_min_idx[-2], local_min_idx[-1]
            price_lower_low = vals[i2] < vals[i1]
            hist_higher_low = recent_hist.iloc[i2] > recent_hist.iloc[i1]
            divergence = price_lower_low and hist_higher_low

        return {
            "macd": round(macd_now, 4), "signal": round(signal_now, 4),
            "histogram": round(hist_now, 4),
            "bullish_cross": bullish_cross, "bearish_cross": bearish_cross,
            "bullish_divergence": divergence,
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

        # Cluster más fuerte (más toques) por debajo del precio
        clusters.sort(key=lambda c: len(c["touches"]), reverse=True)
        best = clusters[0]
        if len(best["touches"]) < 2:
            return None   # exigir al menos 2 toques para considerarlo "soporte" real

        touch_idxs = [t[0] for t in best["touches"]]
        last_touch_idx = max(touch_idxs)
        last_touch_date = dates[last_touch_idx] if last_touch_idx < len(dates) else None
        distance_pct = (price - best["avg"]) / price * 100

        return {
            "level":        round(best["avg"], 2),
            "touches":      len(best["touches"]),
            "distance_pct": round(distance_pct, 1),
            "last_touch_date": last_touch_date,
        }
    except Exception:
        return None


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

        # ── Serie histórica para gráfico ─────────────────────────────────
        # Las medias móviles se calculan sobre los 2 años completos (para que
        # la MM200 tenga suficiente margen previo en TODO el tramo mostrado),
        # y luego se recorta la serie final al último año para el gráfico.
        mm50_series  = closes_full.rolling(window=50).mean()
        mm200_series = closes_full.rolling(window=200).mean() if len(closes_full) >= 200 else None

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
            "mm200":        mm200,
            "mm200_signal": mm200_signal,
            "mm200_css":    mm200_cls,
            "dist_mm200":   dist_mm200,
            "cross_signal": cross_signal,
            "price_history":price_history,
            "macd":         macd_data,
            "adx":          adx_val,
            "obv":          obv_data,
            "fibonacci":    fib_data,
            "historical_support": support_data,
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
        # (1.42 = 1.42%), sin previo aviso ni consistencia por ticker —
        # esto causaba que algunos dividend yields se mostraran como 142%
        # en vez de 1.42%. Normalizamos aquí una única vez: ningún dividend
        # yield real de una empresa cotizada supera el 100% (fracción 1.0),
        # así que si el valor bruto es > 1 asumimos que ya viene en
        # porcentaje y lo convertimos a fracción decimal, para que el resto
        # de la app (que multiplica ×100 para mostrar) lo trate de forma
        # uniforme sin importar qué formato haya devuelto Yahoo esta vez.
        _dy_raw  = info.get("dividendYield")
        _dy_norm = (_dy_raw / 100 if (_dy_raw is not None and _dy_raw > 1) else _dy_raw)

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
            "dividend_yield": _dy_norm,
            "dividend_rate":  info.get("dividendRate"),

            # Otros
            "short_ratio":            info.get("shortRatio"),
            "shares_short":           info.get("sharesShort"),
            "shares_short_prior":     info.get("sharesShortPriorMonth"),
            "short_percent_of_float": info.get("shortPercentOfFloat"),
            "float_shares":           info.get("floatShares"),
            "shares_outstanding":     info.get("sharesOutstanding"),
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


def _get_cik(ticker: str) -> str | None:
    """Obtiene el CIK de la SEC para un ticker dado."""
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
            if entry.get("ticker", "").upper() == ticker.upper():
                cik = str(entry["cik_str"]).zfill(10)
                return cik
    except Exception as e:
        print(f"[SEC CIK] Error: {e}")
    return None


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
