"""
Etapa 4 — Optimización de portafolio.
Auto-fetch de tasa libre de riesgo desde ^TNX (bono tesoro USA 10Y).
Pausa interactiva para edición final de tickers antes de optimizar.
"""
from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd

from .config import OrchestratorConfig

logger = logging.getLogger("orchestrator.portfolio_stage")


# ---------------------------------------------------------------------------
# Tasa libre de riesgo
# ---------------------------------------------------------------------------

def _fetch_risk_free_rate(rf_default: float) -> tuple[float, str]:
    """
    Descarga la tasa del bono del tesoro USA a 10 años (^TNX) de Yahoo Finance.
    Retorna (rf_decimal, source_label).
    """
    try:
        import yfinance as yf
        ticker = yf.Ticker("^TNX")
        hist = ticker.history(period="5d")
        if not hist.empty and "Close" in hist.columns:
            rf_pct = float(hist["Close"].iloc[-1])
            rf = rf_pct / 100.0
            date_str = hist.index[-1].strftime("%Y-%m-%d")
            return rf, f"US 10Y Treasury ^TNX ({rf_pct:.2f}% al {date_str})"
    except Exception as e:
        logger.warning(f"No se pudo obtener ^TNX: {e}")

    return rf_default, f"fallback (default: {rf_default*100:.2f}%)"


# ---------------------------------------------------------------------------
# Pausa interactiva
# ---------------------------------------------------------------------------

def _interactive_edit(tickers: list[str]) -> list[str]:
    """
    Muestra la lista final y permite al usuario hacer ajustes antes de optimizar.
    """
    print(f"\n  Tickers para optimización: {tickers}")
    print(f"  Modifica la lista ('+NVDA -MSFT') o presiona Enter para optimizar:")
    try:
        raw = input("  > ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n  [Continuando sin cambios]")
        return tickers

    if not raw:
        return tickers

    current = list(tickers)
    for token in raw.split():
        token = token.strip()
        if not token:
            continue
        if token.startswith("-"):
            tk = token[1:].upper()
            if tk in current:
                current.remove(tk)
                print(f"    ✗ Eliminado: {tk}")
        else:
            tk = token.lstrip("+").upper()
            if tk not in current:
                current.append(tk)
                print(f"    + Agregado: {tk}")

    return current


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def run(
    tickers: list[str],
    df_prices: pd.DataFrame,
    config: OrchestratorConfig,
    interactive: bool = True,
    tickers_override: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, float]:
    """
    Ejecuta la optimización de 9 portafolios + frontera eficiente.

    Returns:
        df_opt      — DataFrame 9×N MultiIndex (Método × Objetivo)
        df_frontier — DataFrame con puntos de la frontera eficiente
        rf          — tasa libre de riesgo usada
    """
    print(f"\n{'='*60}")
    print(f"  Etapa 4 — Optimización de Portafolio")
    print(f"{'='*60}")

    # 1. Tasa libre de riesgo
    if config.rf_override is not None:
        rf = float(config.rf_override)
        rf_source = f"override manual ({rf*100:.2f}%)"
    else:
        rf, rf_source = _fetch_risk_free_rate(config.rf_default)

    print(f"\n  Tasa libre de riesgo: {rf*100:.3f}% — {rf_source}")

    # 2. Pausa interactiva (solo CLI; Streamlit usa widgets)
    if tickers_override is not None:
        confirmed = tickers_override
    elif interactive:
        confirmed = _interactive_edit(tickers)
    else:
        confirmed = tickers

    if len(confirmed) < 3:
        raise ValueError(
            f"Se necesitan al menos 3 tickers para optimizar el portafolio. "
            f"Confirmados: {confirmed}"
        )

    print(f"\n  Optimizando {len(confirmed)} activos con rf={rf*100:.3f}%")
    print(f"  Generando 9 portafolios: Markowitz/CAPM/Montecarlo × min-vol/max-retorno/max-Sharpe")

    # 3. Ejecutar optimización via adaptador
    from .adapters.portfolio_adapter import run_portfolio

    df_opt, df_frontier, df_rend = run_portfolio(
        tickers=confirmed,
        df_prices=df_prices,
        rf=rf,
        frontier_points=config.frontier_points,
    )

    # 4. Resumen de resultados
    print(f"\n  Portafolios generados ({len(df_opt)} de 9):")
    if not df_opt.empty:
        for idx in df_opt.index:
            row = df_opt.loc[idx]
            method, obj = idx if isinstance(idx, tuple) else (str(idx), "")
            converged = row.get("Convergido", True)
            sharpe = row.get("Sharpe", 0)
            ret = row.get("Retorno", 0)
            vol = row.get("Volatilidad", 0)
            status = "✅" if converged else "⚠️"
            print(
                f"    {status} {method:12s} × {obj:18s} | "
                f"Sharpe={sharpe:.3f}  Ret={ret:.1%}  Vol={vol:.1%}"
            )

    print(f"\n  Frontera eficiente: {len(df_frontier)} puntos")
    print(f"{'='*60}\n")

    return df_opt, df_frontier, rf, df_rend
