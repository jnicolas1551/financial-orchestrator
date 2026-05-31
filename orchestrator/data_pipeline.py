"""
Etapa 1 — Descarga robusta de precios con cache Parquet.
Diseñado para 100-200 tickers: secuencial con validación estricta,
retry exponencial y rate-limiting suave.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

from .config import OrchestratorConfig

logger = logging.getLogger("orchestrator.data_pipeline")

# Constantes de robustez
_MAX_RETRIES = 3
_RETRY_DELAYS = [2, 5, 10]     # segundos entre reintentos
_INTER_TICKER_SLEEP = 0.4       # pausa entre tickers para evitar rate limiting
_MIN_ROWS = 30                  # mínimo de filas para datos válidos
_MAX_FORWARD_FILL_DAYS = 5      # máximo de NaN a rellenar hacia adelante
_PROGRESS_EVERY = 10            # imprimir progreso cada N tickers


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _meta_path(ticker: str, cache_dir: str) -> Path:
    safe = ticker.replace(".", "_").replace("^", "")
    return Path(cache_dir, "meta", f"{safe}.json")


def _parquet_path(ticker: str, cache_dir: str) -> Path:
    safe = ticker.replace(".", "_").replace("^", "")
    today = datetime.now().strftime("%Y%m%d")
    return Path(cache_dir, "prices", f"{safe}_{today}.parquet")


def _is_cache_valid(ticker: str, cache_dir: str, ttl_hours: int) -> bool:
    """Devuelve True si el cache existe y está dentro del TTL."""
    meta = _meta_path(ticker, cache_dir)
    if not meta.exists():
        return False
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
        downloaded_at = datetime.fromisoformat(data["downloaded_at"])
        age_hours = (datetime.now(timezone.utc) - downloaded_at).total_seconds() / 3600
        if age_hours > ttl_hours:
            return False
        # Verificar que el parquet también existe
        pq = Path(cache_dir, "prices", data.get("parquet_file", ""))
        return pq.exists()
    except Exception:
        return False


def _load_cache(ticker: str, cache_dir: str) -> pd.Series | None:
    """Carga la serie de precios desde el cache Parquet."""
    meta = _meta_path(ticker, cache_dir)
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
        pq = Path(cache_dir, "prices", data["parquet_file"])
        df = pd.read_parquet(pq)
        return df["Close"]
    except Exception as e:
        logger.warning(f"[{ticker}] Error leyendo cache: {e}")
        return None


def _save_cache(ticker: str, series: pd.Series, cache_dir: str, ttl_hours: int) -> None:
    """Guarda la serie de precios en Parquet y escribe el JSON sidecar."""
    safe = ticker.replace(".", "_").replace("^", "")
    today = datetime.now().strftime("%Y%m%d")
    filename = f"{safe}_{today}.parquet"
    pq_path = Path(cache_dir, "prices", filename)

    df_to_save = series.rename("Close").to_frame()
    df_to_save.to_parquet(pq_path, index=True)

    meta = {
        "ticker": ticker,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "ttl_hours": ttl_hours,
        "parquet_file": filename,
        "rows": len(series),
    }
    _meta_path(ticker, cache_dir).write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Descarga individual robusta
# ---------------------------------------------------------------------------

def _download_ticker(ticker: str, start_date: str) -> pd.Series | None:
    """
    Descarga el histórico de precios para un ticker via yf.Ticker().history().
    Retorna una pd.Series(index=DatetimeIndex, values=float) o None si falla.
    """
    for attempt in range(_MAX_RETRIES):
        try:
            t = yf.Ticker(ticker)
            hist = t.history(start=start_date, auto_adjust=True)

            if hist.empty:
                logger.warning(f"[{ticker}] Respuesta vacía (intento {attempt+1}/{_MAX_RETRIES})")
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(_RETRY_DELAYS[attempt])
                continue

            close = hist["Close"].dropna()

            # Validar: mínimo de filas
            if len(close) < _MIN_ROWS:
                logger.warning(
                    f"[{ticker}] Datos insuficientes: {len(close)} filas "
                    f"(mínimo {_MIN_ROWS})"
                )
                return None

            # Validar: precios positivos
            if (close <= 0).any():
                logger.warning(f"[{ticker}] Contiene precios <= 0, limpiando...")
                close = close[close > 0]

            if len(close) < _MIN_ROWS:
                logger.warning(f"[{ticker}] Datos insuficientes tras limpieza")
                return None

            return close

        except Exception as e:
            logger.warning(
                f"[{ticker}] Error en intento {attempt+1}/{_MAX_RETRIES}: {type(e).__name__}: {e}"
            )
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_DELAYS[attempt])

    return None


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def download_prices(
    tickers: list[str],
    config: OrchestratorConfig,
) -> tuple[pd.DataFrame, list[str]]:
    """
    Descarga precios de cierre ajustados para todos los tickers.

    Flujo por ticker:
      1. Verificar cache (TTL 24h por defecto)
      2. Si no hay cache → descargar via yf.Ticker().history()
      3. Validar datos (≥30 filas, precios > 0)
      4. Guardar en Parquet + JSON sidecar
      5. Sleep 0.4s entre tickers para respetar rate limits

    Returns:
        df_prices  — DataFrame con precios alineados (intersección de fechas)
        skipped    — lista de tickers que fallaron permanentemente
    """
    # Deduplicar preservando orden
    unique_tickers = list(dict.fromkeys(tickers))
    total = len(unique_tickers)

    series_dict: dict[str, pd.Series] = {}
    skipped: list[str] = []
    cached_count = 0
    downloaded_count = 0

    print(f"\n{'='*60}")
    print(f"  Etapa 1 — Descarga de datos ({total} tickers)")
    print(f"{'='*60}")

    for i, ticker in enumerate(unique_tickers, 1):
        # Progreso parcial
        if i % _PROGRESS_EVERY == 0 or i == total:
            print(
                f"  [{i:3d}/{total}] cache={cached_count} | "
                f"nuevos={downloaded_count} | fallidos={len(skipped)}"
            )

        # 1. Verificar cache
        if not getattr(config, "no_cache", False) and \
           _is_cache_valid(ticker, config.cache_dir, config.cache_ttl_hours):
            series = _load_cache(ticker, config.cache_dir)
            if series is not None:
                series_dict[ticker] = series
                cached_count += 1
                logger.debug(f"[{ticker}] Cache hit")
                continue
            # Cache corrupto → redescargar
            logger.warning(f"[{ticker}] Cache inválido, redescargando...")

        # 2. Descargar
        series = _download_ticker(ticker, config.start_date)

        if series is None:
            logger.error(f"[{ticker}] Fallo permanente — omitido")
            skipped.append(ticker)
            time.sleep(_INTER_TICKER_SLEEP)
            continue

        # 3. Guardar en cache
        try:
            _save_cache(ticker, series, config.cache_dir, config.cache_ttl_hours)
        except Exception as e:
            logger.warning(f"[{ticker}] No se pudo guardar cache: {e}")

        series_dict[ticker] = series
        downloaded_count += 1

        # 4. Pausa anti rate-limiting
        time.sleep(_INTER_TICKER_SLEEP)

    print(f"\n  Resumen: {len(series_dict)} descargados exitosamente | {len(skipped)} fallidos")
    if skipped:
        print(f"  Fallidos: {skipped}")

    if not series_dict:
        raise RuntimeError(
            "No se pudo descargar ningún ticker. "
            "Verifica conectividad y que los tickers sean válidos en Yahoo Finance."
        )

    # 5. Construir DataFrame alineado
    df_prices = pd.DataFrame(series_dict)

    # Alinear por intersección de días de trading comunes
    df_prices = df_prices.dropna(how="all")

    # Forward-fill gaps pequeños (máx N días) — típico en BVC Colombia
    df_prices = df_prices.ffill(limit=_MAX_FORWARD_FILL_DAYS)

    # Eliminar columnas con demasiados NaN (> 20% de filas)
    thresh = int(len(df_prices) * 0.80)
    df_prices = df_prices.dropna(axis=1, thresh=thresh)

    # Quitar filas donde todos los valores son NaN
    df_prices = df_prices.dropna(how="all")

    removed = set(series_dict.keys()) - set(df_prices.columns)
    if removed:
        logger.warning(f"Tickers removidos por datos insuficientes: {removed}")
        skipped.extend(list(removed))

    df_prices.index = pd.to_datetime(df_prices.index)
    df_prices = df_prices.sort_index()

    print(f"  DataFrame final: {len(df_prices)} filas × {len(df_prices.columns)} tickers")
    print(f"  Periodo: {df_prices.index[0].date()} -> {df_prices.index[-1].date()}")
    print(f"{'='*60}\n")

    return df_prices, skipped
