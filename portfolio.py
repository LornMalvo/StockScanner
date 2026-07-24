"""
portfolio.py — v2.2
Portfolio Tracker personal con:
  - Gestión de posiciones (ticker, precio compra, nº acciones)
  - P&L en tiempo real (USD y EUR)
  - Peso de cada posición
  - Diversificación por sector
  - Seguimiento de señal de entrada vs momento de compra
Persistencia: st.session_state (en memoria durante la sesión)
"""

import streamlit as st
import yfinance as yf
from datetime import datetime, timezone


# ─────────────────────────────────────────────────────────────────────────────
# GESTIÓN DE POSICIONES — session_state
# ─────────────────────────────────────────────────────────────────────────────

def _init_portfolio():
    if "portfolio_positions" not in st.session_state:
        st.session_state.portfolio_positions = {}
    # {ticker: {shares, avg_cost, sector, added_date, diagnosis_at_buy}}


def get_positions() -> dict:
    _init_portfolio()
    return st.session_state.portfolio_positions


def add_position(ticker: str, shares: float, avg_cost: float,
                 sector: str = "", diagnosis: str = ""):
    _init_portfolio()
    ticker = ticker.upper().strip()
    existing = st.session_state.portfolio_positions.get(ticker)
    if existing:
        # Promedio ponderado
        old_shares = existing["shares"]
        old_cost   = existing["avg_cost"]
        total      = old_shares + shares
        new_cost   = (old_shares * old_cost + shares * avg_cost) / total
        st.session_state.portfolio_positions[ticker] = {
            **existing,
            "shares":   total,
            "avg_cost": round(new_cost, 4),
        }
    else:
        st.session_state.portfolio_positions[ticker] = {
            "shares":           shares,
            "avg_cost":         avg_cost,
            "sector":           sector,
            "added_date":       datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "diagnosis_at_buy": diagnosis,
        }


def remove_position(ticker: str):
    _init_portfolio()
    st.session_state.portfolio_positions.pop(ticker.upper(), None)


# ─────────────────────────────────────────────────────────────────────────────
# DATOS EN TIEMPO REAL
# ─────────────────────────────────────────────────────────────────────────────

def fetch_portfolio_quotes(tickers: list) -> dict:
    """Obtiene precio actual y sector para cada ticker."""
    quotes = {}
    for ticker in tickers:
        try:
            t    = yf.Ticker(ticker)
            info = t.info
            price  = info.get("currentPrice") or info.get("regularMarketPrice") or 0
            sector = info.get("sector", "")
            name   = info.get("shortName") or info.get("longName") or ticker
            quotes[ticker] = {
                "price":  price,
                "sector": sector,
                "name":   name[:28],
            }
        except Exception:
            quotes[ticker] = {"price": 0, "sector": "", "name": ticker}
    return quotes


# ─────────────────────────────────────────────────────────────────────────────
# RENDER — PORTFOLIO TRACKER
# ─────────────────────────────────────────────────────────────────────────────

def render_portfolio(fx_rate: float | None = None):
    st.markdown("""
    <div style="font-family:'IBM Plex Mono',monospace;font-size:0.75rem;color:#0284c7;
                text-transform:uppercase;letter-spacing:0.1em;padding:1rem 0 0.5rem 0;">
    💼 GESTIÓN DE CARTERA
    </div>
    <div style="font-size:0.82rem;color:#64748b;margin-bottom:1rem;">
    Registra tus posiciones y sigue su evolución en tiempo real.
    Los datos se guardan durante la sesión activa.
    </div>
    """, unsafe_allow_html=True)

    positions = get_positions()

    # ── Formulario añadir posición ────────────────────────────────────────
    with st.expander("➕ Añadir / actualizar posición", expanded=not bool(positions)):
        c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
        with c1:
            new_ticker = st.text_input("Ticker", placeholder="AAPL", key="pf_ticker").strip().upper()
        with c2:
            new_shares = st.number_input("Nº acciones", min_value=0.001, value=1.0,
                                          step=1.0, key="pf_shares")
        with c3:
            new_cost   = st.number_input("Precio de compra (USD)", min_value=0.01,
                                          value=100.0, step=0.01, key="pf_cost")
        with c4:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Añadir", key="pf_add", use_container_width=True):
                if new_ticker:
                    add_position(new_ticker, new_shares, new_cost)
                    st.success(f"{new_ticker} añadido")
                    st.rerun()

    if not positions:
        st.markdown(
            '<div style="text-align:center;padding:2rem;color:#64748b;">'
            'Todavía no tienes posiciones. Añade tu primera posición arriba.</div>',
            unsafe_allow_html=True)
        return

    # ── Obtener cotizaciones actuales ─────────────────────────────────────
    with st.spinner("Actualizando cotizaciones…"):
        quotes = fetch_portfolio_quotes(list(positions.keys()))

    # ── Cálculos globales ─────────────────────────────────────────────────
    total_cost_usd  = 0.0
    total_value_usd = 0.0
    sector_values   = {}
    rows_data       = []

    for ticker, pos in positions.items():
        q        = quotes.get(ticker, {})
        price    = q.get("price", 0)
        sector   = pos.get("sector") or q.get("sector", "N/A")
        name     = q.get("name", ticker)
        shares   = pos["shares"]
        avg_cost = pos["avg_cost"]

        cost_val  = shares * avg_cost
        curr_val  = shares * price
        pnl       = curr_val - cost_val
        pnl_pct   = (pnl / cost_val * 100) if cost_val else 0

        total_cost_usd  += cost_val
        total_value_usd += curr_val

        # Sector breakdown
        sector_values[sector] = sector_values.get(sector, 0) + curr_val

        rows_data.append({
            "ticker":    ticker,
            "name":      name,
            "sector":    sector,
            "shares":    shares,
            "avg_cost":  avg_cost,
            "price":     price,
            "cost_val":  cost_val,
            "curr_val":  curr_val,
            "pnl":       pnl,
            "pnl_pct":   pnl_pct,
            "diag_buy":  pos.get("diagnosis_at_buy", ""),
            "date_add":  pos.get("added_date", ""),
        })

    total_pnl     = total_value_usd - total_cost_usd
    total_pnl_pct = (total_pnl / total_cost_usd * 100) if total_cost_usd else 0
    pnl_col       = "#059669" if total_pnl >= 0 else "#dc2626"

    def fmt_usd(v, show_eur=True):
        s = f"${v:,.2f}"
        if show_eur and fx_rate:
            s += f' <span style="color:#64748b;font-size:0.82em;">(€{v*fx_rate:,.2f})</span>'
        return s

    # ── Resumen global ────────────────────────────────────────────────────
    st.markdown(
        '<div class="metric-card" style="border-left:3px solid #0284c7;">'
        '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:0.5rem;">'
        f'<div style="background:#f4f6f9;border-radius:6px;padding:0.5rem 0.7rem;">'
        f'<div style="font-size:0.67rem;color:#64748b;">Valor actual</div>'
        f'<div style="font-family:\'IBM Plex Mono\',monospace;color:#0f172a;font-weight:700;font-size:1rem;">{fmt_usd(total_value_usd)}</div></div>'
        f'<div style="background:#f4f6f9;border-radius:6px;padding:0.5rem 0.7rem;">'
        f'<div style="font-size:0.67rem;color:#64748b;">Coste total</div>'
        f'<div style="font-family:\'IBM Plex Mono\',monospace;color:#64748b;font-weight:600;">{fmt_usd(total_cost_usd)}</div></div>'
        f'<div style="background:#f4f6f9;border-radius:6px;padding:0.5rem 0.7rem;">'
        f'<div style="font-size:0.67rem;color:#64748b;">P&L total</div>'
        f'<div style="font-family:\'IBM Plex Mono\',monospace;color:{pnl_col};font-weight:700;">{fmt_usd(total_pnl)}</div></div>'
        f'<div style="background:#f4f6f9;border-radius:6px;padding:0.5rem 0.7rem;">'
        f'<div style="font-size:0.67rem;color:#64748b;">Rentabilidad</div>'
        f'<div style="font-family:\'IBM Plex Mono\',monospace;color:{pnl_col};font-weight:700;">{total_pnl_pct:+.2f}%</div></div>'
        '</div></div>',
        unsafe_allow_html=True
    )

    # ── Tabla de posiciones ───────────────────────────────────────────────
    st.markdown('<div style="font-size:0.7rem;color:#0284c7;text-transform:uppercase;letter-spacing:0.1em;margin:1rem 0 0.4rem 0;">POSICIONES</div>', unsafe_allow_html=True)

    hs = "padding:0.35rem 0.5rem;font-size:0.67rem;color:#64748b;text-transform:uppercase;letter-spacing:0.06em;border-bottom:1px solid #e2e8f0;"
    header = (
        f'<tr style="background:#f8fafc;">'
        f'<th style="{hs}text-align:left;">Empresa</th>'
        f'<th style="{hs}text-align:right;">Acciones</th>'
        f'<th style="{hs}text-align:right;">P. Compra</th>'
        f'<th style="{hs}text-align:right;">P. Actual</th>'
        f'<th style="{hs}text-align:right;">Valor</th>'
        f'<th style="{hs}text-align:right;">P&L</th>'
        f'<th style="{hs}text-align:right;">%</th>'
        f'<th style="{hs}text-align:right;">Peso</th>'
        f'<th style="{hs}text-align:center;">Acción</th>'
        '</tr>'
    )

    rows_html = ""
    for r in sorted(rows_data, key=lambda x: x["curr_val"], reverse=True):
        pnl_c   = "#059669" if r["pnl"] >= 0 else "#dc2626"
        sign    = "+" if r["pnl"] >= 0 else ""
        weight  = (r["curr_val"] / total_value_usd * 100) if total_value_usd else 0
        ticker  = r["ticker"]

        eur_val = f'<span style="color:#64748b;font-size:0.75em;">(€{r["curr_val"]*fx_rate:,.0f})</span>' if fx_rate else ""
        eur_pnl = f'<span style="color:#64748b;font-size:0.75em;">(€{r["pnl"]*fx_rate:,.0f})</span>' if fx_rate else ""

        rows_html += (
            f'<tr style="background:#ffffff;border-bottom:1px solid #eef1f5;" id="row-{ticker}">'
            f'<td style="padding:0.35rem 0.5rem;">'
            f'<span style="font-family:\'IBM Plex Mono\',monospace;font-weight:700;color:#0284c7;">{ticker}</span>'
            f'<span style="font-size:0.72rem;color:#64748b;margin-left:0.3rem;">{r["name"]}</span></td>'
            f'<td style="font-family:\'IBM Plex Mono\',monospace;text-align:right;padding:0.35rem 0.5rem;color:#64748b;">{r["shares"]:,.0f}</td>'
            f'<td style="font-family:\'IBM Plex Mono\',monospace;text-align:right;padding:0.35rem 0.5rem;color:#64748b;">${r["avg_cost"]:,.2f}</td>'
            f'<td style="font-family:\'IBM Plex Mono\',monospace;text-align:right;padding:0.35rem 0.5rem;color:#0f172a;">${r["price"]:,.2f}</td>'
            f'<td style="font-family:\'IBM Plex Mono\',monospace;text-align:right;padding:0.35rem 0.5rem;color:#0f172a;">${r["curr_val"]:,.0f} {eur_val}</td>'
            f'<td style="font-family:\'IBM Plex Mono\',monospace;text-align:right;padding:0.35rem 0.5rem;color:{pnl_c};">{sign}${abs(r["pnl"]):,.0f} {eur_pnl}</td>'
            f'<td style="font-family:\'IBM Plex Mono\',monospace;text-align:right;padding:0.35rem 0.5rem;color:{pnl_c};font-weight:700;">{sign}{r["pnl_pct"]:.1f}%</td>'
            f'<td style="text-align:right;padding:0.35rem 0.5rem;">'
            f'<div style="background:#334155;border-radius:3px;height:6px;width:60px;margin-left:auto;">'
            f'<div style="height:6px;border-radius:3px;background:#0284c7;width:{min(weight,100):.0f}%;"></div></div>'
            f'<span style="font-size:0.7rem;color:#64748b;">{weight:.1f}%</span></td>'
            f'<td style="text-align:center;padding:0.35rem 0.5rem;">'
            f'<span style="font-size:0.7rem;color:#64748b;">{r["date_add"]}</span></td>'
            '</tr>'
        )

    st.markdown(
        '<div style="overflow-x:auto;">'
        '<table style="width:100%;border-collapse:collapse;font-size:0.83rem;">'
        f'<thead>{header}</thead><tbody>{rows_html}</tbody></table></div>',
        unsafe_allow_html=True
    )

    # Botones de eliminar
    st.markdown('<div style="margin-top:0.5rem;font-size:0.72rem;color:#64748b;">Eliminar posición:</div>', unsafe_allow_html=True)
    btn_cols = st.columns(min(len(rows_data), 6))
    for i, r in enumerate(rows_data):
        with btn_cols[i % len(btn_cols)]:
            if st.button(f"✕ {r['ticker']}", key=f"del_{r['ticker']}", use_container_width=True):
                remove_position(r["ticker"])
                st.rerun()

    # ── Diversificación por sector ────────────────────────────────────────
    if sector_values and total_value_usd > 0:
        st.markdown('<div style="font-size:0.7rem;color:#0284c7;text-transform:uppercase;letter-spacing:0.1em;margin:1.2rem 0 0.5rem 0;">DIVERSIFICACIÓN POR SECTOR</div>', unsafe_allow_html=True)
        sector_rows = ""
        for sec, val in sorted(sector_values.items(), key=lambda x: x[1], reverse=True):
            pct = val / total_value_usd * 100
            # Colorear concentración excesiva
            bar_col = "#dc2626" if pct > 40 else "#d97706" if pct > 25 else "#0284c7"
            sector_rows += (
                f'<div style="display:flex;align-items:center;gap:0.5rem;padding:0.3rem 0;">'
                f'<span style="font-size:0.8rem;color:#1e293b;min-width:160px;">{sec or "Sin clasificar"}</span>'
                f'<div style="flex:1;background:#334155;border-radius:3px;height:10px;">'
                f'<div style="width:{pct:.0f}%;height:10px;border-radius:3px;background:{bar_col};"></div></div>'
                f'<span style="font-family:\'IBM Plex Mono\',monospace;color:{bar_col};'
                f'min-width:3.5rem;text-align:right;">{pct:.1f}%</span>'
                f'<span style="color:#64748b;font-size:0.75rem;min-width:4rem;text-align:right;">${val/1e3:.0f}K</span>'
                f'</div>'
            )
        if any(v/total_value_usd > 0.40 for v in sector_values.values()):
            sector_rows += (
                '<div style="margin-top:0.5rem;font-size:0.72rem;color:#dc2626;">'
                '⚠ Concentración elevada en un sector (&gt;40%). Considera diversificar.</div>'
            )
        st.markdown(f'<div class="metric-card">{sector_rows}</div>', unsafe_allow_html=True)
