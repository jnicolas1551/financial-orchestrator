# =============================================================================
# CALCULOS.PY — MOTOR DE CÁLCULO FINANCIERO
# Tablas 1-14 del modelo de análisis de portafolio
# =============================================================================

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from config import (
    DIAS_ANIO_DEFAULT, PERCENTILES_ANALISIS,
    MONTECARLO_ITERACIONES, MONTECARLO_PERCENTIL
)


def filtrar_periodo(df: pd.DataFrame, años) -> pd.DataFrame:
    if años is None:
        return df
    fecha_fin = df.index.max()
    fecha_inicio = fecha_fin - timedelta(days=int(años * 365))
    return df[df.index >= fecha_inicio]


def precios_base100(df_precios: pd.DataFrame) -> pd.DataFrame:
    return (df_precios / df_precios.iloc[0]) * 100


def retorno_nominal(df_precios: pd.DataFrame, periodos: dict) -> pd.DataFrame:
    resultados = {}
    for nombre, años in periodos.items():
        df_periodo = filtrar_periodo(df_precios, años)
        if len(df_periodo) < 2:
            continue
        resultados[nombre] = (df_periodo.iloc[-1] / df_periodo.iloc[0]) - 1
    return pd.DataFrame(resultados).T


def retorno_ea(df_nominal: pd.DataFrame, periodos: dict,
               dias_anio: int = DIAS_ANIO_DEFAULT,
               total_dias: int = None) -> pd.DataFrame:
    resultados = {}
    for nombre, años in periodos.items():
        if nombre not in df_nominal.index:
            continue
        nominal = df_nominal.loc[nombre]
        if años is None:
            dias_periodo = total_dias if total_dias else dias_anio
        else:
            dias_periodo = int(años * dias_anio)
        if dias_periodo == 0:
            continue
        ea = (1 + nominal) ** (dias_anio / dias_periodo) - 1
        resultados[nombre] = ea
    return pd.DataFrame(resultados).T


def volatilidad_diaria(df_rendimientos: pd.DataFrame, periodos: dict) -> pd.DataFrame:
    resultados = {}
    cols = [c for c in df_rendimientos.columns if c != 'PORTAFOLIO']
    for nombre, años in periodos.items():
        df_periodo = filtrar_periodo(df_rendimientos[cols], años)
        if len(df_periodo) < 2:
            continue
        resultados[nombre] = df_periodo.std()
    return pd.DataFrame(resultados).T


def volatilidad_anual(df_vol_diaria: pd.DataFrame, dias_anio: int = DIAS_ANIO_DEFAULT) -> pd.DataFrame:
    return df_vol_diaria * np.sqrt(dias_anio)


def sharpe_ratio(df_ea: pd.DataFrame, df_vol_anual: pd.DataFrame, rf: float) -> pd.DataFrame:
    return (df_ea - rf) / df_vol_anual


def analisis_percentiles(df_rendimientos: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in df_rendimientos.columns if c != 'PORTAFOLIO']
    percentiles = [p/100 for p in PERCENTILES_ANALISIS]
    resultado = df_rendimientos[cols].quantile(percentiles)
    resultado.index = [f"{int(p*100)}%" for p in percentiles]
    return resultado


def rango_percentil_actual(df_rendimientos: pd.DataFrame) -> pd.Series:
    cols = [c for c in df_rendimientos.columns if c != 'PORTAFOLIO']
    ultimo_rendimiento = df_rendimientos[cols].iloc[-1]
    resultado = {}
    for col in cols:
        serie = df_rendimientos[col].dropna()
        percentil = (serie < ultimo_rendimiento[col]).mean()
        resultado[col] = percentil
    return pd.Series(resultado, name='Rango Percentil Actual')


def matriz_correlacion(df_rendimientos: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in df_rendimientos.columns if c != 'PORTAFOLIO']
    return df_rendimientos[cols].corr()


def covarianza_diaria(df_rendimientos: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in df_rendimientos.columns if c != 'PORTAFOLIO']
    return df_rendimientos[cols].cov()


def covarianza_anual(df_cov_diaria: pd.DataFrame, dias_anio: int = DIAS_ANIO_DEFAULT) -> pd.DataFrame:
    return df_cov_diaria * dias_anio


def montecarlo_muestra(df_rendimientos: pd.DataFrame, dias_anio: int = DIAS_ANIO_DEFAULT) -> pd.Series:
    cols = [c for c in df_rendimientos.columns if c != 'PORTAFOLIO']
    n = len(df_rendimientos)
    if n <= dias_anio:
        return df_rendimientos[cols].mean()
    idx_random = np.random.randint(0, n - dias_anio)
    muestra = df_rendimientos[cols].iloc[idx_random: idx_random + dias_anio]
    return muestra.mean()


def montecarlo_iteraciones(df_rendimientos: pd.DataFrame,
                           n_iter: int = MONTECARLO_ITERACIONES,
                           percentil: int = MONTECARLO_PERCENTIL,
                           dias_anio: int = DIAS_ANIO_DEFAULT) -> pd.Series:
    cols = [c for c in df_rendimientos.columns if c != 'PORTAFOLIO']
    n = len(df_rendimientos)
    arr = df_rendimientos[cols].values
    if n <= dias_anio:
        return pd.Series(arr.mean(axis=0), index=cols)
    indices = np.random.randint(0, n - dias_anio, size=n_iter)
    promedios = np.array([
        arr[idx: idx + dias_anio].mean(axis=0)
        for idx in indices
    ])
    resultado = np.percentile(promedios, percentil, axis=0)
    return pd.Series(resultado, index=cols)


def tabla_activos(df_rendimientos: pd.DataFrame,
                  df_cov_anual: pd.DataFrame,
                  pesos: dict,
                  rf: float,
                  benchmark: str,
                  retornos_montecarlo: pd.Series,
                  dias_anio: int = DIAS_ANIO_DEFAULT) -> dict:
    cols_activos = [c for c in df_rendimientos.columns
                    if c != 'PORTAFOLIO' and c != benchmark]
    pesos_serie = pd.Series(pesos).reindex(cols_activos).fillna(1/len(cols_activos))
    vol_diaria = df_rendimientos[cols_activos].std()
    vol_anual_serie = vol_diaria * np.sqrt(dias_anio)
    rend_bench = df_rendimientos[benchmark]
    betas = {}
    for col in cols_activos:
        rend_activo = df_rendimientos[col]
        datos_validos = pd.concat([rend_activo, rend_bench], axis=1).dropna()
        if len(datos_validos) > 1:
            covarianza = datos_validos.cov().iloc[0, 1]
            varianza_bench = datos_validos.iloc[:, 1].var()
            betas[col] = covarianza / varianza_bench if varianza_bench != 0 else 0
        else:
            betas[col] = 0
    beta_serie = pd.Series(betas)
    rm_diario = df_rendimientos[benchmark].mean()
    rm_anual = (1 + rm_diario) ** dias_anio - 1
    cov_activos = df_cov_anual.loc[cols_activos, cols_activos]
    var_port_por_activo = pesos_serie * cov_activos.dot(pesos_serie)
    resultados = {}
    for metodo in ['markowitz', 'capm', 'montecarlo']:
        if metodo == 'markowitz':
            rend_diario = df_rendimientos[cols_activos].mean()
            retornos = (1 + rend_diario) ** dias_anio - 1
        elif metodo == 'capm':
            retornos = rf + beta_serie * (rm_anual - rf)
        elif metodo == 'montecarlo':
            rend_mc = retornos_montecarlo.reindex(cols_activos)
            retornos = (1 + rend_mc) ** dias_anio - 1
        sharpe = (retornos - rf) / vol_anual_serie
        df_tabla = pd.DataFrame({
            'Peso (w)':           pesos_serie,
            'Retorno':            retornos,
            'Volatilidad Anual':  vol_anual_serie,
            'Var/Vol Portafolio': var_port_por_activo,
            'Sharpe Ratio':       sharpe,
            'Beta':               beta_serie,
        }).T
        resultados[metodo] = df_tabla
    return resultados


def tabla_portafolio(tablas_activos: dict, pesos: dict, cols_activos: list) -> dict:
    pesos_serie = pd.Series(pesos).reindex(cols_activos).fillna(0)
    suma_pesos = pesos_serie.sum()
    resultados = {}
    for metodo, df_tabla in tablas_activos.items():
        retornos = df_tabla.loc['Retorno']
        vol_anual = df_tabla.loc['Volatilidad Anual']
        sharpe = df_tabla.loc['Sharpe Ratio']
        var_vol = df_tabla.loc['Var/Vol Portafolio']
        retorno_port = (pesos_serie * retornos).sum()
        vol_port = np.sqrt(var_vol.sum())
        sharpe_pond = (pesos_serie * sharpe).sum()
        sharpe_calc = retorno_port / vol_port if vol_port != 0 else 0
        df_port = pd.DataFrame({
            'Portafolio': {
                'Suma Pesos (w)':   suma_pesos,
                'Retorno':          retorno_port,
                'Volatilidad':      vol_port,
                'Sharpe Ponderado': sharpe_pond,
                'Sharpe Calculado': sharpe_calc,
            }
        })
        resultados[metodo] = df_port
    return resultados


def information_ratio(df_rendimientos: pd.DataFrame, benchmark: str,
                      periodos: dict, dias_anio: int = DIAS_ANIO_DEFAULT) -> pd.DataFrame:
    cols_activos = [c for c in df_rendimientos.columns
                    if c != 'PORTAFOLIO' and c != benchmark]
    rend_bench = df_rendimientos[benchmark]
    resultados = {}
    for nombre, años in periodos.items():
        df_periodo = filtrar_periodo(df_rendimientos, años)
        rend_bench_periodo = filtrar_periodo(rend_bench.to_frame(), años).iloc[:, 0]
        irs = {}
        for col in cols_activos:
            rend_activo = df_periodo[col]
            datos = pd.concat([rend_activo, rend_bench_periodo], axis=1).dropna()
            datos.columns = ['activo', 'bench']
            ret_activo = (1 + datos['activo'].mean()) ** dias_anio - 1
            ret_bench = (1 + datos['bench'].mean()) ** dias_anio - 1
            tracking_error = (datos['activo'] - datos['bench']).std() * np.sqrt(dias_anio)
            if tracking_error != 0:
                irs[col] = (ret_activo - ret_bench) / tracking_error
            else:
                irs[col] = 0
        resultados[nombre] = pd.Series(irs)
    return pd.DataFrame(resultados).T
