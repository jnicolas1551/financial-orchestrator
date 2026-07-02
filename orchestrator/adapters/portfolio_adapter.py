"""
Adaptador para el motor de cálculo de portafolio.
Prioridad: quant/ interno → PORTFOLIO_ANALYZER_PATH env → portfolio-analyzer/ sibling.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd


# ---------------------------------------------------------------------------
# Localización del módulo de cálculo
# ---------------------------------------------------------------------------

def _find_pa_path() -> Path:
    here = Path(__file__).resolve()
    project_root = here.parents[2]  # financial-orchestrator/

    # 1. Carpeta quant/ empaquetada dentro del proyecto (Streamlit Cloud)
    internal = project_root / "quant"
    if internal.exists() and (internal / "optimizacion.py").exists():
        return internal

    # 2. Variable de entorno PORTFOLIO_ANALYZER_PATH
    env_path = os.environ.get("PORTFOLIO_ANALYZER_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p

    # 3. Carpeta sibling portfolio-analyzer/ (desarrollo local sin quant/)
    sibling = project_root.parent / "portfolio-analyzer"
    if sibling.exists():
        return sibling

    raise FileNotFoundError(
        "No se encontró el motor de cálculo. "
        "Opciones: carpeta quant/ en el proyecto, "
        "variable PORTFOLIO_ANALYZER_PATH, o carpeta portfolio-analyzer/ sibling."
    )


def _ensure_path() -> None:
    pa_path = _find_pa_path()
    str_path = str(pa_path)
    if str_path not in sys.path:
        sys.path.insert(0, str_path)


def _import_modules():
    _ensure_path()
    import calculos
    import optimizacion
    import datos as datos_mod
    return calculos, optimizacion, datos_mod


# ---------------------------------------------------------------------------
# run_portfolio — entrada principal para el orquestador
# ---------------------------------------------------------------------------

def run_portfolio(
    tickers: list[str],
    df_prices: pd.DataFrame,
    rf: float = 0.045,
    dias_anio: int = 365,
    frontier_points: int = 100,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Ejecuta la optimización completa de portafolio.

    Devuelve:
        df_opt      — DataFrame 9×N (MultiIndex Método×Objetivo)
        df_frontier — DataFrame de puntos de la frontera eficiente
    """
    calculos, optimizacion, datos_mod = _import_modules()

    # Filtrar df_prices a los tickers seleccionados
    available = [t for t in tickers if t in df_prices.columns]
    if len(available) < 3:
        raise ValueError(
            f"Se necesitan al menos 3 tickers con datos de precios. "
            f"Disponibles: {available}"
        )
    df_slice = df_prices[available].copy()

    # Pesos iniciales iguales (para cálculo de rendimientos base)
    pesos_iguales = {t: 1 / len(available) for t in available}

    # Calcular rendimientos
    df_rend = datos_mod.calcular_rendimientos(df_slice, pesos_iguales)

    # Covarianza diaria y anual
    df_cov_d = calculos.covarianza_diaria(df_rend)
    df_cov_a = calculos.covarianza_anual(df_cov_d, dias_anio)

    # Montecarlo
    retornos_mc = calculos.montecarlo_iteraciones(df_rend, dias_anio=dias_anio)

    # Tabla de activos (retornos por método)
    tablas_act = calculos.tabla_activos(
        df_rend, df_cov_a, pesos_iguales, rf,
        benchmark=df_rend.columns[-1] if "PORTAFOLIO" in df_rend.columns else available[0],
        retornos_montecarlo=retornos_mc,
        dias_anio=dias_anio,
    )

    # Optimizar 9 portafolios
    df_opt = optimizacion.optimizar_todos(tablas_act, df_cov_a, rf)

    # Frontera eficiente — usar retornos Markowitz como base
    retornos_base = tablas_act.get("markowitz", tablas_act.get(list(tablas_act.keys())[0]))
    if retornos_base is not None and "Retorno" in retornos_base.index:
        retornos_serie = retornos_base.loc["Retorno"]
    else:
        # Fallback: calcular retorno anual simple
        retornos_serie = (df_rend[available].mean() * dias_anio)

    df_frontier = optimizacion.frontera_eficiente(
        retornos_serie, df_cov_a, rf, n_puntos=frontier_points
    )

    return df_opt, df_frontier, df_rend


# ---------------------------------------------------------------------------
# Portafolio unificado / combinado
# ---------------------------------------------------------------------------

def get_combined_portfolio(
    df_opt: pd.DataFrame,
    tickers: list[str],
    method: str = "sharpe",
    df_rend: pd.DataFrame | None = None,
    benchmark: str | None = None,
    dias_anio: int = 365,
    objetivo_principal: str = "Max Sharpe",
    peso_principal: float = 0.60,
) -> dict:
    """
    Calcula el portafolio unificado según el método elegido.

    method:
        "sharpe"    → portafolio_combinado_sharpe
        "ir"        → portafolio_combinado_ir  (requiere df_rend + benchmark)
        "consenso"  → portafolio_consenso (objetivo_principal + peso_principal)
        "max_retorno"     → portafolio_consenso con objetivo Max Retorno, peso=1.0
        "min_volatilidad" → portafolio_consenso con objetivo Min Volatilidad, peso=1.0
    """
    _ensure_path()
    import optimizacion
    import calculos

    cols = [t for t in tickers if t in df_opt.columns]
    if not cols:
        return {}

    if method == "sharpe":
        return optimizacion.portafolio_combinado_sharpe(df_opt, cols)

    elif method == "ir" and df_rend is not None and benchmark is not None:
        if benchmark not in df_rend.columns:
            raise ValueError(
                f"Information Ratio requiere los rendimientos del benchmark "
                f"'{benchmark}' en df_rend (columnas: {list(df_rend.columns)}). "
                f"Re-ejecuta la etapa de portafolio o usa otro método de ponderación."
            )
        periodos = {"historico": None}
        df_ir = calculos.information_ratio(df_rend, benchmark, periodos, dias_anio)
        return optimizacion.portafolio_combinado_ir(df_opt, df_ir, cols)

    elif method == "max_retorno":
        return optimizacion.portafolio_consenso(df_opt, cols, "Max Retorno", 1.0)

    elif method == "min_volatili