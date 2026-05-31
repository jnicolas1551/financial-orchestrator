"""
Etapa 3 — Filtro 2: Análisis fundamental en paralelo + pausa interactiva.
El usuario puede elegir modo buy_only / buy_hold y editar la lista resultante.
"""
from __future__ import annotations

import logging
from concurrent.futures import ProcessPoolExecutor, as_completed

import pandas as pd

from .config import OrchestratorConfig

logger = logging.getLogger("orchestrator.fundamental_filter")


# ---------------------------------------------------------------------------
# Worker (nivel de módulo — picklable)
# ---------------------------------------------------------------------------

def _fund_worker(ticker: str, config_dict: dict) -> dict:
    """
    Ejecuta análisis DCF + múltiplos para un ticker.
    Importa fundamental_adapter dentro del worker.
    """
    import sys
    from pathlib import Path

    worker_dir = Path(__file__).parent.parent
    if str(worker_dir) not in sys.path:
        sys.path.insert(0, str(worker_dir))

    from orchestrator.adapters import fundamental_adapter
    return fundamental_adapter.analyze_ticker(ticker, config_dict)


# ---------------------------------------------------------------------------
# Pausa interactiva
# ---------------------------------------------------------------------------

def _interactive_edit(tickers: list[str], label: str) -> list[str]:
    """
    Muestra la lista actual y permite al usuario agregar/eliminar tickers.
    Formato: '+NVDA -MSFT AMZN' (+ agregar, - eliminar, sin prefijo = agregar)
    """
    print(f"\n  {label}: {tickers}")
    print(f"  Modifica la lista (ej: '+NVDA -MSFT') o presiona Enter para continuar:")
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
                print(f"    ! {tk} no estaba en la lista")
        else:
            tk = token.lstrip("+").upper()
            if tk not in current:
                current.append(tk)
                print(f"    + Agregado: {tk}")
            else:
                print(f"    ! {tk} ya estaba en la lista")

    return current


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def run(
    tickers: list[str],
    config: OrchestratorConfig,
    interactive: bool = True,
    tickers_override: list[str] | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """
    Ejecuta análisis fundamental en paralelo sobre los tickers que pasaron F1.
    Aplica Filtro 2 (buy_only o buy_hold) y pausa para edición interactiva.

    Returns:
        df_fund    — DataFrame con resultados fundamentales (FUND_RESULT_SCHEMA)
        final_list — lista de tickers confirmados para portfolio
    """
    total = len(tickers)
    workers = min(config.max_workers_fund, total)

    print(f"\n{'='*60}")
    print(f"  Etapa 3 — Filtro 2: Análisis Fundamental")
    print(f"  {total} tickers | {workers} workers | modo={config.filter2_mode}")
    print(f"{'='*60}")

    config_dict = {
        "growth_explicit": config.growth_explicit,
        "terminal_growth": config.terminal_growth,
        "explicit_years": config.explicit_years,
    }

    results: list[dict] = []

    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_fund_worker, ticker, config_dict): ticker
            for ticker in tickers
        }

        completed = 0
        for future in as_completed(futures):
            completed += 1
            try:
                res = future.result()
                results.append(res)
                signal_icon = {"buy": "✅", "hold": "🔶", "sell": "❌"}.get(res.get("signal", ""), "⚠️")
                print(
                    f"  [{completed:3d}/{total}] {res['ticker']:12s} "
                    f"{signal_icon} {res.get('signal','error'):4s} | "
                    f"DCF={res.get('upside_dcf', 0) or 0:+.0%}  "
                    f"Mult={res.get('upside_mult', 0) or 0:+.0%}"
                )
            except Exception as e:
                ticker_err = futures[future]
                logger.error(f"[{ticker_err}] Worker falló: {e}")
                results.append({
                    "ticker": ticker_err, "signal": "error",
                    "passes_filter2": False, "error": str(e)
                })

    # Construir df_fund
    df_fund = pd.DataFrame(results).set_index("ticker")
    for col in ["dcf_price", "mult_price", "current_price", "upside_dcf",
                "upside_mult", "signal", "wacc", "peers_count", "passes_filter2"]:
        if col not in df_fund.columns:
            df_fund[col] = None

    # Aplicar Filtro 2 según modo
    if config.filter2_mode == "buy_only":
        df_fund["passes_filter2"] = df_fund["signal"] == "buy"
    else:  # buy_hold
        df_fund["passes_filter2"] = df_fund["signal"].isin(["buy", "hold"])

    passed = df_fund[df_fund["passes_filter2"]].index.tolist()
    failed = total - len(passed)

    print(f"\n  Filtro 2 resultado (modo: {config.filter2_mode}):")
    print(f"    PASS : {len(passed)} tickers")
    print(f"    FAIL : {failed} tickers")

    # Mostrar tabla resumen
    if passed:
        print(f"\n  Tickers que pasan Filtro 2:")
        for tk in passed:
            row = df_fund.loc[tk]
            print(
                f"    {tk:15s} {row.get('signal','?'):4s} | "
                f"DCF={row.get('upside_dcf',0) or 0:+.0%}  "
                f"Mult={row.get('upside_mult',0) or 0:+.0%}  "
                f"WACC={row.get('wacc',0) or 0:.1%}"
            )

    # Pausa interactiva (solo en CLI; Streamlit la maneja con widgets)
    if tickers_override is not None:
        final_list = tickers_override
    elif interactive:
        final_list = _interactive_edit(passed, "Tickers confirmados para portafolio")
    else:
        final_list = passed

    print(f"\n  Lista final después de edición: {final_list}")
    print(f"{'='*60}\n")

    return df_fund, final_list
