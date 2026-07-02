# =============================================================================
# OPTIMIZACION.PY — OPTIMIZACIÓN DE PORTAFOLIO
# Genera 9 portafolios óptimos: 3 métodos × 3 objetivos
# =============================================================================
#
# OBJETIVOS:
#   - max_retorno    : maximizar retorno del portafolio
#   - max_sharpe     : maximizar Sharpe Ratio
#   - min_volatilidad: minimizar volatilidad
#
# MÉTODOS:
#   - markowitz  : retornos basados en promedio histórico
#   - capm       : retornos basados en CAPM
#   - montecarlo : retornos basados en percentil 50 Montecarlo
#
# =============================================================================

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from config import PESO_MINIMO, PESO_MAXIMO, DIAS_ANIO_DEFAULT


def _calcular_metricas_portafolio(
    pesos: np.ndarray,
    retornos: pd.Series,
    cov_anual: pd.DataFrame,
    rf: float
) -> tuple:
    """
    Calcula retorno, volatilidad y Sharpe de un portafolio dado sus pesos.

    Retorna:
        (retorno, volatilidad, sharpe)
    """
    retorno = np.dot(pesos, retornos)
    varianza = np.dot(pesos.T, np.dot(cov_anual.values, pesos))
    volatilidad = np.sqrt(varianza)
    sharpe = (retorno - rf) / volatilidad if volatilidad > 0 else 0
    return retorno, volatilidad, sharpe


def optimizar_portafolio(
    retornos: pd.Series,
    cov_anual: pd.DataFrame,
    rf: float,
    objetivo: str
) -> dict:
    """
    Optimiza los pesos del portafolio para un objetivo específico.

    Parámetros:
        retornos : Series con retorno esperado por activo
        cov_anual: DataFrame covarianza anualizada
        rf       : tasa libre de riesgo en decimal
        objetivo : 'max_retorno' | 'max_sharpe' | 'min_volatilidad'

    Retorna:
        dict con pesos óptimos y métricas resultantes
    """
    n = len(retornos)
    pesos_iniciales = np.array([1/n] * n)

    # Restricciones: suma de pesos = 1
    restricciones = [{'type': 'eq', 'fun': lambda x: np.sum(x) - 1}]

    # Límites: cada peso entre PESO_MINIMO y PESO_MAXIMO
    limites = tuple((PESO_MINIMO, PESO_MAXIMO) for _ in range(n))

    # Función objetivo según el tipo
    if objetivo == 'max_retorno':
        def funcion_obj(pesos):
            retorno, _, _ = _calcular_metricas_portafolio(pesos, retornos, cov_anual, rf)
            return -retorno  # negativo porque scipy minimiza

    elif objetivo == 'max_sharpe':
        def funcion_obj(pesos):
            _, _, sharpe = _calcular_metricas_portafolio(pesos, retornos, cov_anual, rf)
            return -sharpe

    elif objetivo == 'min_volatilidad':
        def funcion_obj(pesos):
            _, volatilidad, _ = _calcular_metricas_portafolio(pesos, retornos, cov_anual, rf)
            return volatilidad

    else:
        raise ValueError(f"Objetivo no reconocido: {objetivo}")

    # Optimización
    resultado = minimize(
        funcion_obj,
        pesos_iniciales,
        method='SLSQP',
        bounds=limites,
        constraints=restricciones,
        options={'maxiter': 1000, 'ftol': 1e-9}
    )

    pesos_opt = resultado.x
    retorno_opt, vol_opt, sharpe_opt = _calcular_metricas_portafolio(
        pesos_opt, retornos, cov_anual, rf
    )

    return {
        'pesos':       dict(zip(retornos.index, pesos_opt)),
        'retorno':     retorno_opt,
        'volatilidad': vol_opt,
        'sharpe':      sharpe_opt,
        'convergido':  resultado.success
    }


def optimizar_todos(
    tablas_activos: dict,
    cov_anual: pd.DataFrame,
    rf: float
) -> pd.DataFrame:
    """
    Genera los 9 portafolios óptimos: 3 métodos × 3 objetivos.

    Retorna:
        DataFrame con estructura:
        - Columnas: activos + [Retorno, Volatilidad, Sharpe]
        - Índice multinivel: (método, objetivo)
    """
    from config import METODOS_RETORNO, OBJETIVOS_OPTIMIZACION

    resultados = []

    for metodo in METODOS_RETORNO:
        if metodo not in tablas_activos:
            continue

        df_tabla = tablas_activos[metodo]
        retornos = df_tabla.loc['Retorno']
        cols_activos = retornos.index.tolist()
        cov_activos = cov_anual.loc[cols_activos, cols_activos]

        for objetivo in OBJETIVOS_OPTIMIZACION:
            try:
                opt = optimizar_portafolio(retornos, cov_activos, rf, objetivo)

                fila = {
                    'Método':      metodo.capitalize(),
                    'Objetivo':    objetivo.replace('_', ' ').title(),
                    'Retorno':     opt['retorno'],
                    'Volatilidad': opt['volatilidad'],
                    'Sharpe':      opt['sharpe'],
                    'Convergido':  opt['convergido'],
                }

                # Agregar pesos por activo
                for activo, peso in opt['pesos'].items():
                    fila[activo] = peso

                resultados.append(fila)

            except Exception as e:
                print(f"  Error optimizando {metodo}/{objetivo}: {e}")

    if not resultados:
        return pd.DataFrame()

    df_resultado = pd.DataFrame(resultados)
    df_resultado = df_resultado.set_index(['Método', 'Objetivo'])

    return df_resultado
def portafolio_combinado_sharpe(df_opt: pd.DataFrame, cols_activos: list) -> dict:
    """
    Combina los 9 portafolios óptimos en uno solo ponderado por Sharpe.
    Excluye portafolios con Sharpe negativo.
    
    Retorna:
        dict con pesos combinados y métricas del portafolio resultante
    """
    # Filtrar portafolios con Sharpe positivo
    df_positivos = df_opt[df_opt['Sharpe'] > 0].copy()
    
    if df_positivos.empty:
        # Si todos son negativos, usar promedio simple
        df_positivos = df_opt.copy()
    
    # Pesos de ponderación basados en Sharpe
    suma_sharpe = df_positivos['Sharpe'].sum()
    pesos_port = df_positivos['Sharpe'] / suma_sharpe
    
    # Calcular pesos combinados por activo
    pesos_combinados = {}
    for activo in cols_activos:
        if activo in df_positivos.columns:
            pesos_combinados[activo] = (
                df_positivos[activo] * pesos_port
            ).sum()
    
    # Normalizar para que sumen 1
    suma_pesos = sum(pesos_combinados.values())
    if suma_pesos > 0:
        pesos_combinados = {k: v/suma_pesos for k, v in pesos_combinados.items()}
    
    # Métricas del portafolio combinado
    retorno_combinado = (df_positivos['Retorno'] * pesos_port).sum()
    vol_combinada = (df_positivos['Volatilidad'] * pesos_port).sum()
    sharpe_combinado = (df_positivos['Sharpe'] * pesos_port).sum()
    
    return {
        'pesos':       pesos_combinados,
        'retorno':     retorno_combinado,
        'volatilidad': vol_combinada,
        'sharpe':      sharpe_combinado,
        'n_portafolios_usados': len(df_positivos)
    }


def frontera_eficiente(
    retornos: pd.Series,
    cov_anual: pd.DataFrame,
    rf: float,
    n_puntos: int = 100
) -> pd.DataFrame:
    """
    Genera puntos de la frontera eficiente para graficar.

    Retorna:
        DataFrame con columnas [Volatilidad, Retorno, Sharpe]
    """
    n = len(retornos)
    pesos_iniciales = np.array([1/n] * n)
    limites = tuple((PESO_MINIMO, PESO_MAXIMO) for _ in range(n))

    # Rango de retornos objetivo
    ret_min = retornos.min()
    ret_max = retornos.max()
    retornos_objetivo = np.linspace(ret_min, ret_max, n_puntos)

    puntos = []

    for ret_obj in retornos_objetivo:
        restricciones = [
            {'type': 'eq', 'fun': lambda x: np.sum(x) - 1},
            {'type': 'eq', 'fun': lambda x, r=ret_obj: np.dot(x, retornos) - r}
        ]

        resultado = minimize(
            lambda x: np.sqrt(np.dot(x.T, np.dot(cov_anual.values, x))),
            pesos_iniciales,
            method='SLSQP',
            bounds=limites,
            constraints=restricciones,
            options={'maxiter': 500, 'ftol': 1e-9}
        )

        if resultado.success:
            pesos = resultado.x
            _, vol, sharpe = _calcular_metricas_portafolio(pesos, retornos, cov_anual, rf)
            puntos.append({
                'Volatilidad': vol,
                'Retorno':     ret_obj,
                'Sharpe':      sharpe
            })

    return pd.DataFrame(puntos)


def portafolio_combinado_ir(df_opt: pd.DataFrame, df_ir: pd.DataFrame, cols_activos: list) -> dict:
    """
    Combina los 9 portafolios óptimos ponderado por Information Ratio promedio.
    Excluye portafolios donde el IR promedio es negativo.
    """
    ir_promedio = df_ir.mean()
    ir_port = {}
    for idx in df_opt.index:
        metodo = idx[0].lower()
        activos_ir = [c for c in cols_activos if c in ir_promedio.index]
        pesos_port = pd.Series({c: df_opt.loc[idx, c] for c in activos_ir if c in df_opt.columns})
        ir_port[idx] = (pesos_port * ir_promedio[activos_ir]).sum()

    ir_series = pd.Series(ir_port)
    df_positivos = df_opt[ir_series > 0].copy()
    pesos_ir = ir_series[ir_series > 0]

    if df_positivos.empty:
        df_positivos = df_opt.copy()
        pesos_ir = ir_series.abs()

    suma_ir = pesos_ir.sum()
    pesos_norm = pesos_ir / suma_ir

    pesos_combinados = {}
    for activo in cols_activos:
        if activo in df_positivos.columns:
            pesos_combinados[activo] = (df_positivos[activo] * pesos_norm).sum()

    suma_pesos = sum(pesos_combinados.values())
    if suma_pesos > 0:
        pesos_combinados = {k: v/suma_pesos for k, v in pesos_combinados.items()}

    retorno_combinado = (df_positivos['Retorno'] * pesos_norm).sum()
    vol_combinada = (df_positivos['Volatilidad'] * pesos_norm).sum()
    sharpe_combinado = (df_positivos['Sharpe'] * pesos_norm).sum()

    return {
        'pesos':                pesos_combinados,
        'retorno':              retorno_combinado,
        'volatilidad':          vol_combinada,
        'sharpe':               sharpe_combinado,
        'n_portafolios_usados': len(df_positivos)
    }


def portafolio_consenso(
    df_opt: pd.DataFrame,
    cols_activos: list,
    objetivo_principal: str,
    peso_principal: float = 0.60
) -> dict:
    """
    Crea un portafolio consenso asignando peso_principal al objetivo_principal
    y distribuyendo el resto equitativamente entre los otros objetivos.

    Ejemplo: objetivo_principal='Max Retorno', peso_principal=0.60
      - Cada portafolio 'Max Retorno' recibe 60% / 3 = 20%
      - Cada uno de los otros 6 recibe 40% / 6 = 6.67%

    Parametros:
        df_opt            : DataFrame de optimizar_todos() (MultiIndex Metodo/Objetivo)
        cols_activos      : lista de tickers activos
        objetivo_principal: 'Max Retorno' | 'Max Sharpe' | 'Min Volatilidad'
        peso_principal    : fraccion asignada al objetivo principal (0-1)

    Retorna:
        dict con pesos, retorno, volatilidad, sharpe, objetivo_principal, peso_principal
    """
    if df_opt.empty:
        return {'pesos': {}, 'retorno': 0.0, 'volatilidad': 0.0, 'sharpe': 0.0,
                'objetivo_principal': objetivo_principal, 'peso_principal': peso_principal,
                'n_portafolios_usados': 0}

    peso_otros = 1.0 - peso_principal
    objetivos_col = df_opt.index.get_level_values('Objetivo')

    n_ppal  = (objetivos_col == objetivo_principal).sum()
    n_otros = len(df_opt) - n_ppal
    if n_ppal == 0:
        n_ppal = 1

    # Peso de cada fila
    pesos_filas = pd.Series(index=df_opt.index, dtype=float)
    for idx in df_opt.index:
        if idx[1] == objetivo_principal:
            pesos_filas[idx] = peso_principal / n_ppal
        else:
            pesos_filas[idx] = peso_otros / n_otros if n_otros > 0 else 0.0

    # Pesos combinados por activo
    pesos_combinados = {}
    for activo in cols_activos:
        if activo in df_opt.columns:
            pesos_combinados[activo] = (df_opt[activo] * pesos_filas).sum()

    suma = sum(pesos_combinados.values())
    if suma > 0:
        pesos_combinados = {k: v / suma for k, v in pesos_combinados.items()}

    retorno     = (df_opt['Retorno']     * pesos_filas).sum()
    volatilidad = (df_opt['Volatilidad'] * pesos_filas).sum()
    sharpe      = (df_opt['Sharpe']      * pesos_filas).sum()

    return {
        'pesos':               pesos_combinados,
        'retorno':             retorno,
        'volatilidad':         volatilidad,
        'sharpe':              sharpe,
        'objetivo_principal':  objetivo_principal,
        'peso_principal':      peso_principal,
        'n_portafolios_usados': len(df_opt),
    }