"""
Contratos de DataFrames entre etapas del pipeline.
Sirven como documentación y para validación ligera.
"""
from __future__ import annotations

import pandas as pd

# --- Schemas de columnas requeridas por etapa ---

PRICES_SCHEMA = {
    "description": "Precios de cierre ajustados por ticker",
    "index": "DatetimeIndex (fechas de trading)",
    "columns": "List[str] — un ticker por columna",
    "values": "float64 — precio de cierre ajustado",
}

STAT_RESULT_SCHEMA = {
    "description": "Resultados del Filtro 1 estadístico",
    "index": "str (ticker)",
    "required_columns": [
        "score",          # float: score ponderado final (0-1)
        "pot_reg",        # float: potencial por regresión
        "pot_pct",        # float: potencial por percentil
        "signal_mm",      # str:   señal medias móviles
        "signal_macd",    # str:   señal MACD
        "signal_rsi",     # str:   señal RSI
        "signal_fib",     # str:   señal Fibonacci
        "passes_filter1", # bool:  True si score >= threshold (BUY)
    ],
}

FUND_RESULT_SCHEMA = {
    "description": "Resultados del Filtro 2 fundamental",
    "index": "str (ticker)",
    "required_columns": [
        "dcf_price",      # float: precio intrínseco (DCF; DDM si financiera)
        "mult_price",     # float: precio relativo (múltiplos; P/BV si financiera)
        "current_price",  # float: precio actual de mercado
        "upside_dcf",     # float: (dcf_price/current_price) - 1
        "upside_mult",    # float: (mult_price/current_price) - 1
        "signal",         # str:   "buy" | "hold" | "sell"
        "wacc",           # float: WACC (Ke si financiera)
        "peers_count",    # int:   número de peers usados
        "passes_filter2", # bool:  True si pasa el filtro configurado
        "sector",         # str:   sector yfinance (detección financieras)
        "valuation_model",# str:   "DCF+Mult" | "DDM+P/BV"
    ],
}

OPT_RESULT_SCHEMA = {
    "description": "9 portafolios optimizados (MultiIndex Método × Objetivo)",
    "index": "MultiIndex(Método, Objetivo) — 9 filas",
    "columns": "pesos por ticker + Retorno, Volatilidad, Sharpe, Convergido",
}

FRONTIER_SCHEMA = {
    "description": "Puntos de la frontera eficiente",
    "index": "int (0..N)",
    "required_columns": ["Volatilidad", "Retorno", "Sharpe"],
}


def validate_dataframe(df: pd.DataFrame, schema_name: str) -> None:
    """
    Valida que un DataFrame tenga las columnas requeridas por su schema.
    Lanza ValueError con detalle si falta alguna columna.
    """
    schemas = {
        "stat": STAT_RESULT_SCHEMA,
        "fund": FUND_RESULT_SCHEMA,
        "frontier": FRONTIER_SCHEMA,
    }
    schema = schemas.get(schema_name)
    if schema is None or "required_columns" not in schema:
        return

    required = set(schema["required_columns"])
    present = set(df.columns)
    missing = required - present
    if missing:
        raise ValueError(
            f"DataFrame '{schema_name}' le faltan columnas requeridas: {missing}. "
            f"Presentes: {present}"
        )
