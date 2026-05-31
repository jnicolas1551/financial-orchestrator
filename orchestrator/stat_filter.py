"""
Etapa 2 — Filtro 1: Análisis estadístico y técnico en paralelo.
Genera un score por ticker y retiene SOLO los de BUY (score >= threshold).
"""
from __future__ import annotations

import logging
import os
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from .config import OrchestratorConfig

logger = logging.getLogger("orchestrator.stat_filter")


# ---------------------------------------------------------------------------
# Worker (función a nivel de módulo — picklable para ProcessPoolExecutor)
# ---------------------------------------------------------------------------

def _stat_worker(ticker: str, parquet_path: str, benchmark_ticker: str,
                 w_reg: float, w_pct: float, w_tec: float,
                 all_tickers_parquet: str) -> dict:
    """
    Analiza un ticker estadística y técnicamente.
    Recibe rutas a parquet en vez de DataFrames (no picklables entre procesos).

    Returns dict con score y señales.
    """
    result = {
        "ticker": ticker,
        # Score final
        "score": 0.0,
        "pot_reg": 0.0,
        "pot_pct": 0.0,
        "precio_valorado": None,
        "last_price": None,
        # Estadísticos de regresión
        "alpha": None,
        "beta": None,
        "r2": None,
        "corr": None,
        "pct_rank": None,
        "std_20": None,
        # Señales técnicas (texto)
        "signal_mm": "N/A",
        "signal_macd": "N/A",
        "signal_rsi": "N/A",
        "signal_fib": "N/A",
        # Valores numéricos de indicadores
        "rsi_value": None,
        "macd_hist": None,
        "passes_filter1": False,
        "error": None,
    }

    try:
        # Importar el adaptador dentro del worker (cada proceso tiene su propio espacio)
        import sys
        worker_dir = Path(__file__).parent.parent
        if str(worker_dir) not in sys.path:
            sys.path.insert(0, str(worker_dir))

        from orchestrator.adapters import quant_adapter

        # Cargar el DataFrame completo de precios
        df_all = pd.read_parquet(all_tickers_parquet)

        if ticker not in df_all.columns:
            result["error"] = f"Ticker {ticker} no encontrado en df_prices"
            return result

        # Determinar benchmark disponible
        benchmark = benchmark_ticker if benchmark_ticker in df_all.columns else df_all.columns[0]

        # Preparar sub-DataFrame con ticker + benchmark
        cols = [ticker]
        if benchmark != ticker:
            cols.append(benchmark)
        df_sub = df_all[cols].dropna()

        if len(df_sub) < 30:
            result["error"] = "Datos insuficientes para análisis estadístico"
            return result

        # Calcular log-precios y estadísticos
        ln_prices = quant_adapter.calc_ln(df_sub)
        stats = quant_adapter.calc_stats(ln_prices, benchmark_col=benchmark)

        if ticker not in stats:
            result["error"] = "calc_stats no devolvió resultado para el ticker"
            return result

        # Score ponderado (regresión + percentil)
        scored = quant_adapter.calc_precio_valorado(stats, w_reg=w_reg, w_pct=w_pct)

        ticker_scored = scored.get(ticker, {})
        pot_reg = ticker_scored.get("pot_val_reg", 0.0) or 0.0
        pot_pct = ticker_scored.get("pot_val_pct", 0.0) or 0.0
        last_price = ticker_scored.get("last_price")
        precio_valorado = ticker_scored.get("precio_valorado")

        # Estadísticos de regresión (del dict de calc_stats)
        stats_tk = stats.get(ticker, {})
        result["alpha"]    = round(stats_tk.get("alpha", 0) or 0, 6)
        result["beta"]     = round(stats_tk.get("beta", 0) or 0, 4)
        result["r2"]       = round(stats_tk.get("r2", 0) or 0, 4)
        result["corr"]     = round(stats_tk.get("corr", 0) or 0, 4)
        result["pct_rank"] = round(stats_tk.get("pct_rank", 0) or 0, 4)
        result["std_20"]   = round(stats_tk.get("std_20", 0) or 0, 6)
        result["last_price"]       = last_price
        result["precio_valorado"]  = precio_valorado

        # Señales técnicas
        prices_series = df_sub[ticker]

        try:
            mm_df = quant_adapter.calc_mm(prices_series)
            mm_signals = quant_adapter.get_mm_signal(mm_df)
            signal_mm = mm_signals[0] if mm_signals else "N/A"
        except Exception:
            signal_mm = "N/A"

        try:
            macd_df = quant_adapter.calc_macd(prices_series)
            signal_macd = quant_adapter.get_macd_signal(macd_df)
            result["macd_hist"] = round(float(macd_df["hist"].iloc[-1]), 4) if "hist" in macd_df.columns else None
        except Exception:
            signal_macd = "N/A"

        try:
            rsi = quant_adapter.calc_rsi(prices_series)
            result["rsi_value"] = round(float(rsi.iloc[-1]), 2)
            signal_rsi = quant_adapter.get_rsi_signal(rsi)
        except Exception:
            signal_rsi = "N/A"

        try:
            fib_signal, _, _ = quant_adapter.get_fib_signal(prices_series)
            signal_fib = fib_signal
        except Exception:
            signal_fib = "N/A"

        # Score técnico: proporción de señales de compra
        tec_signals = [signal_mm, signal_macd, signal_rsi, signal_fib]
        buy_count = sum(1 for s in tec_signals if isinstance(s, str) and "COMPRA" in s.upper())
        score_tec = buy_count / len(tec_signals) if tec_signals else 0.0

        # Score final ponderado (los pesos suman 1.0 validado en config)
        # Normalizar pot_reg y pot_pct a [0,1] usando signo (positivo = alcista)
        pot_reg_norm = min(max((pot_reg + 1) / 2, 0.0), 1.0)
        pot_pct_norm = min(max((pot_pct + 1) / 2, 0.0), 1.0)
        score = w_reg * pot_reg_norm + w_pct * pot_pct_norm + w_tec * score_tec

        result.update({
            "score": round(score, 4),
            "pot_reg": round(pot_reg, 4),
            "pot_pct": round(pot_pct, 4),
            "signal_mm": signal_mm,
            "signal_macd": signal_macd,
            "signal_rsi": signal_rsi,
            "signal_fib": signal_fib,
        })

    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"

    return result


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def run(
    df_prices: pd.DataFrame,
    config: OrchestratorConfig,
) -> tuple[pd.DataFrame, list[str]]:
    """
    Ejecuta el análisis estadístico en paralelo sobre todos los tickers.

    Returns:
        df_stat   — DataFrame con scores y señales (STAT_RESULT_SCHEMA)
        buy_list  — lista de tickers que pasaron Filter 1 (BUY)
    """
    # Excluir benchmark — no es un activo invertible
    tickers = [t for t in df_prices.columns if t != config.benchmark]
    total = len(tickers)
    workers = min(config.max_workers_stat, max(1, total))

    print(f"\n{'='*60}")
    print(f"  Etapa 2 — Filtro 1: Análisis Estadístico")
    print(f"  {total} tickers | {workers} workers | threshold={config.filter1_threshold}")
    print(f"  Pesos: w_reg={config.w_reg} w_pct={config.w_pct} w_tec={config.w_tec}")
    print(f"{'='*60}")

    # Guardar df_prices en un parquet temporal para que los workers lo lean
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
        tmp_path = tmp.name
    df_prices.to_parquet(tmp_path)

    results: list[dict] = []

    try:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    _stat_worker,
                    ticker,
                    "",  # parquet_path individual (no usado, cargamos todo el df)
                    config.benchmark,
                    config.w_reg,
                    config.w_pct,
                    config.w_tec,
                    tmp_path,
                ): ticker
                for ticker in tickers
            }

            completed = 0
            for future in as_completed(futures):
                completed += 1
                try:
                    res = future.result()
                    results.append(res)
                    if res.get("error"):
                        logger.warning(f"[{res['ticker']}] {res['error']}")
                except Exception as e:
                    ticker_err = futures[future]
                    logger.error(f"[{ticker_err}] Worker falló: {e}")
                    results.append({"ticker": ticker_err, "score": 0.0,
                                    "passes_filter1": False, "error": str(e)})

                if completed % 10 == 0 or completed == total:
                    passed_so_far = sum(1 for r in results if r.get("passes_filter1"))
                    print(f"  [{completed:3d}/{total}] procesados | {passed_so_far} con BUY hasta ahora")

    finally:
        Path(tmp_path).unlink(missing_ok=True)

    # Construir df_stat
    df_stat = pd.DataFrame(results).set_index("ticker")

    # Aplicar threshold: solo BUY (no hay categoría hold en F1)
    df_stat["passes_filter1"] = df_stat["score"] >= config.filter1_threshold

    buy_list = df_stat[df_stat["passes_filter1"]].index.tolist()
    rejected = total - len(buy_list)

    print(f"\n  Filtro 1 resultado:")
    print(f"    BUY   (score >= {config.filter1_threshold}): {len(buy_list)} tickers")
    print(f"    FAIL  (score <  {config.filter1_threshold}): {rejected} tickers")

    if buy_list:
        top = df_stat[df_stat["passes_filter1"]].sort_values("score", ascending=False)
        print(f"\n  Top 5 por score:")
        for tk, row in top.head(5).iterrows():
            print(f"    {tk:15s} score={row['score']:.3f}")
    print(f"{'='*60}\n")

    return df_stat, buy_list
