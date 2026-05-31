# =============================================================================
# DATOS.PY — DESCARGA DE DATOS
# Fuentes: Yahoo Finance (yfinance) + datos.gov.co (requests)
# =============================================================================
#
# ESTRUCTURA:
#   - descargar_yahoo()     : descarga precios de Yahoo Finance
#   - descargar_fics()      : descarga precios de FICs colombianos
#   - combinar_activos()    : une ambas fuentes en un solo DataFrame
#   - calcular_rendimientos(): genera hoja 2 (rendimientos diarios)
#
# SALIDA ESTÁNDAR:
#   Todos los DataFrames tienen:
#   - Index: fechas (datetime)
#   - Columnas: nombre corto del activo
#   - Valores: precio de cierre ajustado
#
# =============================================================================

import yfinance as yf
import pandas as pd
import requests
import time
from datetime import datetime, timedelta
from config import (
    DATOS_GOV_URL, COL_FECHA_GOV, COL_FONDO_GOV,
    COL_PRECIO_GOV, LIMITE_API
)


# -----------------------------------------------------------------------------
# SECCIÓN 1: YAHOO FINANCE
# -----------------------------------------------------------------------------

def descargar_yahoo(tickers: list, fecha_inicio: str, fecha_fin: str = None) -> pd.DataFrame:
    """
    Descarga precios de cierre ajustado desde Yahoo Finance.

    Parámetros:
        tickers     : lista de tickers (ej: ['AAPL', 'NVDA', '^GSPC'])
        fecha_inicio: string formato 'YYYY-MM-DD'
        fecha_fin   : string formato 'YYYY-MM-DD' (default: hoy)

    Retorna:
        DataFrame con fechas en índice y tickers como columnas
    """
    if not tickers:
        return pd.DataFrame()

    if fecha_fin is None:
        fecha_fin = datetime.today().strftime('%Y-%m-%d')

    print(f"Descargando Yahoo Finance: {tickers}")

    raw = yf.download(
        tickers=tickers,
        start=fecha_inicio,
        end=fecha_fin,
        auto_adjust=True,
        progress=False
    )

    # Extraer columna Close
    if len(tickers) == 1:
        df = raw[['Close']].copy()
        df.columns = [tickers[0]]
    else:
        df = raw['Close'].copy()
        df = df[tickers]  # Mantener orden original

    df.index = pd.to_datetime(df.index)
    df.index.name = 'fecha'

    print(f"  Yahoo Finance: {len(df)} filas descargadas")
    return df


# -----------------------------------------------------------------------------
# SECCIÓN 2: DATOS.GOV.CO — FICs COLOMBIANOS
# -----------------------------------------------------------------------------

def _obtener_nombres_fics() -> list:
    """Obtiene todos los nombres únicos de FICs en el dataset."""
    nombres = []
    offset = 0

    while True:
        params = {
            "$select": COL_FONDO_GOV,
            "$group": COL_FONDO_GOV,
            "$limit": LIMITE_API,
            "$offset": offset,
            "$order": COL_FONDO_GOV
        }
        try:
            r = requests.get(DATOS_GOV_URL, params=params, timeout=60)
            r.raise_for_status()
            registros = r.json()
            if not registros:
                break
            nombres.extend([x.get(COL_FONDO_GOV, '') for x in registros if x.get(COL_FONDO_GOV)])
            if len(registros) < LIMITE_API:
                break
            offset += LIMITE_API
            time.sleep(0.5)
        except Exception as e:
            print(f"Error obteniendo nombres FICs: {e}")
            break

    return nombres


def _resolver_nombre_fic(keyword: str, nombres_disponibles: list) -> str:
    """
    Busca el nombre exacto de un FIC usando palabras clave.
    Retorna el primer nombre que contenga todas las palabras clave.
    """
    def normalizar(texto):
        mapa = {
            'á':'a','é':'e','í':'i','ó':'o','ú':'u',
            'Á':'A','É':'E','Í':'I','Ó':'O','Ú':'U',
            'ñ':'n','Ñ':'N','ü':'u'
        }
        resultado = texto.upper()
        for k, v in mapa.items():
            resultado = resultado.replace(k, v)
        return resultado

    palabras = [normalizar(p) for p in keyword.split()]
    nombres_norm = {n: normalizar(n) for n in nombres_disponibles}

    coincidencias = [
        nombre_real for nombre_real, nombre_n in nombres_norm.items()
        if all(p in nombre_n for p in palabras)
    ]

    if coincidencias:
        return coincidencias[0]
    return None


def descargar_fics(keywords: list, fecha_inicio: str, fecha_fin: str = None) -> pd.DataFrame:
    """
    Descarga precios de FICs colombianos desde datos.gov.co.

    Parámetros:
        keywords    : lista de palabras clave para buscar cada FIC
                      (ej: ['RENTAFACIL', 'UNIVERSITAS'])
        fecha_inicio: string formato 'YYYY-MM-DD'
        fecha_fin   : string formato 'YYYY-MM-DD' (default: hoy)

    Retorna:
        DataFrame con fechas en índice y nombres cortos como columnas
    """
    if not keywords:
        return pd.DataFrame()

    if fecha_fin is None:
        fecha_fin = datetime.today().strftime('%Y-%m-%d')

    print(f"Descargando FICs Colombia: {keywords}")

    # Paso 1: obtener nombres reales del dataset
    nombres_disponibles = _obtener_nombres_fics()
    if not nombres_disponibles:
        print("  Error: no se pudo obtener listado de FICs")
        return pd.DataFrame()

    # Paso 2: resolver nombres exactos
    mapa_nombres = {}
    for keyword in keywords:
        nombre_exacto = _resolver_nombre_fic(keyword, nombres_disponibles)
        if nombre_exacto:
            mapa_nombres[nombre_exacto] = keyword
            print(f"  OK [{keyword}] → {nombre_exacto[:50]}")
        else:
            print(f"  NO ENCONTRADO [{keyword}]")

    if not mapa_nombres:
        return pd.DataFrame()

    # Paso 3: descargar precios
    nombres_exactos = list(mapa_nombres.keys())
    valores_in = ", ".join([f"'{n.replace(chr(39), chr(39)*2)}'" for n in nombres_exactos])
    cond_where = (
        f"{COL_FECHA_GOV} >= '{fecha_inicio}T00:00:00' "
        f"AND {COL_FECHA_GOV} <= '{fecha_fin}T23:59:59' "
        f"AND {COL_FONDO_GOV} IN ({valores_in})"
    )

    registros = []
    offset = 0
    while True:
        params = {
            "$select": f"{COL_FECHA_GOV}, {COL_FONDO_GOV}, {COL_PRECIO_GOV}",
            "$where": cond_where,
            "$order": f"{COL_FECHA_GOV} ASC",
            "$limit": LIMITE_API,
            "$offset": offset,
        }
        try:
            r = requests.get(DATOS_GOV_URL, params=params, timeout=60)
            r.raise_for_status()
            pagina = r.json()
            if not pagina:
                break
            registros.extend(pagina)
            if len(pagina) < LIMITE_API:
                break
            offset += LIMITE_API
            time.sleep(1.0)
        except Exception as e:
            print(f"  Error descargando FICs: {e}")
            break

    if not registros:
        return pd.DataFrame()

    # Paso 4: transformar a DataFrame
    df = pd.DataFrame(registros)
    df[COL_FECHA_GOV] = pd.to_datetime(df[COL_FECHA_GOV], dayfirst=True, errors='coerce')
    df[COL_PRECIO_GOV] = pd.to_numeric(df[COL_PRECIO_GOV], errors='coerce')
    df = df.dropna()
    df[COL_FONDO_GOV] = df[COL_FONDO_GOV].map(mapa_nombres)

    df_pivot = pd.pivot_table(
        data=df,
        index=COL_FECHA_GOV,
        columns=COL_FONDO_GOV,
        values=COL_PRECIO_GOV,
        aggfunc='mean'
    )
    df_pivot.columns.name = None
    df_pivot.index.name = 'fecha'

    print(f"  FICs Colombia: {len(df_pivot)} filas descargadas")
    return df_pivot


# -----------------------------------------------------------------------------
# SECCIÓN 3: COMBINAR FUENTES
# -----------------------------------------------------------------------------

def combinar_activos(
    tickers_yahoo: list,
    keywords_fics: list,
    benchmark: str,
    fecha_inicio: str,
    fecha_fin: str = None
) -> tuple:
    """
    Combina datos de Yahoo Finance y datos.gov.co en un solo DataFrame.
    El benchmark siempre va como última columna.

    Retorna:
        tuple: (df_precios, nombre_benchmark)
        df_precios: DataFrame con todos los activos + benchmark al final
    """
    dfs = []

    # Descargar Yahoo Finance (incluye benchmark)
    todos_yahoo = tickers_yahoo + ([benchmark] if benchmark not in tickers_yahoo else [])
    if todos_yahoo:
        df_yahoo = descargar_yahoo(todos_yahoo, fecha_inicio, fecha_fin)
        if not df_yahoo.empty:
            dfs.append(df_yahoo)

    # Descargar FICs Colombia
    if keywords_fics:
        df_fics = descargar_fics(keywords_fics, fecha_inicio, fecha_fin)
        if not df_fics.empty:
            dfs.append(df_fics)

    if not dfs:
        raise ValueError("No se pudieron descargar datos de ninguna fuente.")

    # Combinar en un solo DataFrame
    df_combinado = pd.concat(dfs, axis=1)

    # Eliminar filas con cualquier NaN
    filas_antes = len(df_combinado)
    df_combinado = df_combinado.dropna()
    filas_eliminadas = filas_antes - len(df_combinado)

    if filas_eliminadas > 0:
        print(f"  Filas eliminadas por NaN: {filas_eliminadas}")

   # Si benchmark está vacío, tomar el último activo
    if not benchmark or benchmark not in df_combinado.columns:
        benchmark = df_combinado.columns[-1]

    # Reordenar: activos primero, benchmark al final
    activos = [c for c in df_combinado.columns if c != benchmark]
    df_combinado = df_combinado[activos + [benchmark]]

    print(f"  Total combinado: {len(df_combinado)} fechas · {len(df_combinado.columns)} activos")
    return df_combinado, benchmark


# -----------------------------------------------------------------------------
# SECCIÓN 4: CALCULAR RENDIMIENTOS (HOJA 2)
# -----------------------------------------------------------------------------

def calcular_rendimientos(df_precios: pd.DataFrame, pesos: dict) -> pd.DataFrame:
    """
    Calcula rendimientos diarios de todos los activos.
    Fórmula: (precio_actual / precio_anterior) - 1

    Agrega columna 'PORTAFOLIO' como suma producto de rendimientos × pesos.

    Parámetros:
        df_precios: DataFrame de precios (salida de combinar_activos)
        pesos     : dict {ticker: peso} para cada activo (sin benchmark)

    Retorna:
        DataFrame de rendimientos con columna PORTAFOLIO agregada
    """
    df_rend = df_precios.pct_change().dropna()

    # Calcular columna portafolio
    activos_sin_bench = [c for c in df_rend.columns if c in pesos]
    if activos_sin_bench and pesos:
        pesos_serie = pd.Series(pesos)
        pesos_alineados = pesos_serie.reindex(activos_sin_bench).fillna(0)
        df_rend['PORTAFOLIO'] = df_rend[activos_sin_bench].dot(pesos_alineados)

    return df_rend

# -----------------------------------------------------------------------------
# CARGA DESDE EXCEL LOCAL
# -----------------------------------------------------------------------------

def cargar_excel(ruta_archivo: str, hoja: str = None) -> pd.DataFrame:
    """
    Carga precios desde un archivo Excel local.
    Formato esperado: primera columna = fechas, resto = activos.
    Mismo formato que la base de datos del sistema.

    Parámetros:
        ruta_archivo: ruta completa al archivo .xlsx
        hoja        : nombre de la hoja (None = primera hoja)

    Retorna:
        DataFrame con fechas en índice y activos como columnas
    """
    df = pd.read_excel(
        ruta_archivo,
        sheet_name=hoja if hoja else 0,
        index_col=0,
        parse_dates=True
    )

    df.index = pd.to_datetime(df.index, errors='coerce')
    df = df.dropna(how='all')
    df.index.name = 'fecha'
    df.columns = [str(c).strip().upper() for c in df.columns]

    print(f"Excel cargado: {len(df)} filas · {len(df.columns)} activos")
    print(f"Rango: {df.index.min().date()} → {df.index.max().date()}")
    print(f"Activos: {list(df.columns)}")

    return df
