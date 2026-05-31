"""
Financial Orchestrator — Entry point.
Pipeline top-down: descarga → filtro estadístico → filtro fundamental
                  → optimización de portafolio → PDF investing memo.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, timedelta

# Forzar UTF-8 en la consola Windows para evitar UnicodeEncodeError con flechas/emojis
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from orchestrator.config import OrchestratorConfig
from orchestrator import data_pipeline, stat_filter, fundamental_filter
from orchestrator import portfolio_stage, report_builder


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

def run_pipeline(config: OrchestratorConfig) -> str:
    """
    Ejecuta el pipeline completo de 5 etapas.
    Returns la ruta al PDF generado.
    """
    t_start = time.time()

    print(f"\n{'#'*60}")
    print(f"  Financial Orchestrator v1.0.0")
    print(f"  {len(config.tickers)} tickers | benchmark={config.benchmark}")
    print(f"  Periodo: {config.start_date} -> hoy")
    print(f"{'#'*60}")

    # ----------------------------------------------------------------
    # Etapa 1 — Descarga de datos
    # Asegurar que el benchmark también se descarga
    # ----------------------------------------------------------------
    all_tickers = list(dict.fromkeys(config.tickers + [config.benchmark]))
    df_prices, skipped = data_pipeline.download_prices(all_tickers, config)

    if df_prices.empty:
        print("ERROR: No se pudo descargar ningún ticker.")
        sys.exit(1)

    downloaded_tickers = list(df_prices.columns)

    # ----------------------------------------------------------------
    # Etapa 2 — Filtro 1: Análisis estadístico (solo BUY)
    # ----------------------------------------------------------------
    df_stat, buy_list = stat_filter.run(df_prices, config)

    if not buy_list:
        print("\n❌ Ningún ticker superó el Filtro 1 estadístico.")
        print(f"   Sugerencia: reduce --filter1-threshold (actual: {config.filter1_threshold})")
        sys.exit(1)

    # ----------------------------------------------------------------
    # Etapa 3 — Filtro 2: Análisis fundamental + edición interactiva
    # ----------------------------------------------------------------
    df_fund, final_tickers = fundamental_filter.run(buy_list, config)

    if not final_tickers:
        print("\n❌ Ningún ticker superó el Filtro 2 fundamental.")
        print(f"   Sugerencia: cambia --filter2-mode a 'buy_hold' o revisa los parámetros DCF.")
        sys.exit(1)

    # Gate: mínimo 3 activos para optimización
    if len(final_tickers) < 3:
        print(f"\n❌ Se necesitan al menos 3 activos para optimizar el portafolio.")
        print(f"   Confirmados: {final_tickers}")
        print(f"\n  Resumen del pipeline:")
        print(f"    Entrada:   {len(config.tickers)}")
        print(f"    Descarga:  {len(downloaded_tickers)}")
        print(f"    Filtro 1:  {len(buy_list)}")
        print(f"    Filtro 2:  {len(final_tickers)}")
        sys.exit(1)

    # ----------------------------------------------------------------
    # Etapa 4 — Optimización de portafolio + pausa interactiva
    # ----------------------------------------------------------------
    df_opt, df_frontier, rf, _df_rend = portfolio_stage.run(
        final_tickers, df_prices, config
    )
    rf_label = f"{rf*100:.3f}% (US 10Y Treasury)" \
        if config.rf_override is None else f"{rf*100:.3f}% (manual override)"

    # ----------------------------------------------------------------
    # Etapa 5 — PDF Investing Memo
    # ----------------------------------------------------------------
    # Usar la lista de tickers confirmados en portfolio_stage
    # (puede diferir de final_tickers si el usuario los editó en Stage 4)
    confirmed_tickers = [t for t in final_tickers if t in df_prices.columns]

    output_path = report_builder.build(
        df_stat=df_stat,
        df_fund=df_fund,
        df_opt=df_opt,
        df_frontier=df_frontier,
        df_prices=df_prices,
        final_tickers=confirmed_tickers,
        rf=rf,
        rf_label=rf_label,
        config=config,
        skipped=skipped,
    )

    # ----------------------------------------------------------------
    # Resumen final
    # ----------------------------------------------------------------
    elapsed = time.time() - t_start
    print(f"\n{'#'*60}")
    print(f"  ✅ PIPELINE COMPLETADO en {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"  Entrada:   {len(config.tickers)} tickers")
    print(f"  Descarga:  {len(downloaded_tickers)} exitosos | {len(skipped)} fallidos")
    print(f"  Filtro 1:  {len(buy_list)} BUY")
    print(f"  Filtro 2:  {len(confirmed_tickers)} seleccionados")
    print(f"  Output:    {output_path}")
    print(f"{'#'*60}\n")

    return output_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    def_start = (date.today() - timedelta(days=3 * 365)).strftime("%Y-%m-%d")

    p = argparse.ArgumentParser(
        description="Financial Orchestrator — Pipeline de análisis institucional top-down",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Universo
    p.add_argument("--tickers", nargs="+", metavar="TICKER",
                   help="Lista de tickers (ej: AAPL MSFT PFBCOLOM.CL)")
    p.add_argument("--config", metavar="PATH",
                   help="Ruta a archivo YAML de configuración")
    p.add_argument("--benchmark", default="^GSPC",
                   help="Ticker del benchmark")
    p.add_argument("--start-date", dest="start_date", default=def_start,
                   metavar="YYYY-MM-DD", help="Fecha de inicio del histórico")

    # Filtro 1
    p.add_argument("--filter1-threshold", dest="filter1_threshold",
                   type=float, default=None,
                   help="Threshold mínimo de score para pasar Filtro 1 (0-1)")
    p.add_argument("--w-reg", dest="w_reg", type=float, default=None,
                   help="Peso regresión en score estadístico")
    p.add_argument("--w-pct", dest="w_pct", type=float, default=None,
                   help="Peso percentil en score estadístico")
    p.add_argument("--w-tec", dest="w_tec", type=float, default=None,
                   help="Peso técnico en score estadístico")

    # Filtro 2
    p.add_argument("--filter2-mode", dest="filter2_mode",
                   choices=["buy_only", "buy_hold"], default=None,
                   help="Modo Filtro 2: 'buy_only' (solo compra) o 'buy_hold'")

    # Tasa libre de riesgo
    p.add_argument("--rf", type=float, default=None,
                   help="Override manual de tasa libre de riesgo (decimal, ej: 0.045). "
                        "Si no se especifica, se descarga ^TNX automáticamente.")

    # Cache
    p.add_argument("--cache-dir", dest="cache_dir", default=None,
                   help="Directorio de cache de precios")
    p.add_argument("--cache-ttl", dest="cache_ttl", type=int, default=None,
                   help="TTL del cache en horas")
    p.add_argument("--no-cache", dest="no_cache", action="store_true",
                   help="Forzar re-descarga ignorando el cache")

    # Output
    p.add_argument("--output-dir", dest="output_dir", default=None,
                   help="Directorio para el PDF generado")
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="Ejecutar solo filtros (sin portafolio ni PDF)")
    p.add_argument("--verbose", action="store_true",
                   help="Logging detallado")

    return p.parse_args()


def main() -> None:
    args = parse_args()
    _setup_logging(args.verbose)

    # Construir configuración
    config = OrchestratorConfig.load_from_cli(args)
    config.no_cache = getattr(args, "no_cache", False)

    if not config.tickers:
        print("ERROR: Debes proporcionar tickers via --tickers o --config.")
        print("Ejemplo: python main.py --tickers AAPL MSFT GOOGL")
        sys.exit(1)

    if getattr(args, "dry_run", False):
        # Dry run: solo etapas 1-3
        print("\n[DRY RUN] Ejecutando solo filtros (sin portafolio ni PDF)\n")
        all_tickers = list(dict.fromkeys(config.tickers + [config.benchmark]))
        df_prices, skipped = data_pipeline.download_prices(all_tickers, config)
        df_stat, buy_list = stat_filter.run(df_prices, config)
        if buy_list:
            df_fund, final_tickers = fundamental_filter.run(buy_list, config)
        print(f"\n[DRY RUN] Completado. {len(final_tickers if buy_list else [])} tickers pasaron ambos filtros.")
        return

    run_pipeline(config)


if __name__ == "__main__":
    main()
