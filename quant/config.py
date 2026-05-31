# =============================================================================
# CONFIG.PY — CONSTANTES DEL SISTEMA
# Portfolio Analyzer · Versión 1.0
# =============================================================================
#
# INSTRUCCIÓN: Este archivo contiene las constantes globales del sistema.
# No contiene variables de entrada del usuario (esas van en el dashboard).
# Solo modifica aquí si cambia la estructura del sistema.
#
# =============================================================================

# -----------------------------------------------------------------------------
# FUENTES DE DATOS
# -----------------------------------------------------------------------------

# URL base de datos.gov.co para FICs colombianos
DATOS_GOV_URL = "https://www.datos.gov.co/resource/qhpu-8ixx.json"
DATOS_GOV_DATASET_ID = "qhpu-8ixx"

# Columnas del dataset de datos.gov.co
COL_FECHA_GOV = "fecha_corte"
COL_FONDO_GOV = "nombre_patrimonio"
COL_PRECIO_GOV = "valor_unidad_operaciones"

# Límite de registros por llamada a la API
LIMITE_API = 50000

# -----------------------------------------------------------------------------
# PERÍODOS DE ANÁLISIS
# -----------------------------------------------------------------------------

# Opciones disponibles en el selector del dashboard
# Formato: {etiqueta visible: años en decimal}
PERIODOS_DISPONIBLES = {
    "6 meses":          0.5,
    "1 año":            1.0,
    "2 años":           2.0,
    "3 años":           3.0,
    "5 años":           5.0,
    "Máximo disponible": None,
}
# -----------------------------------------------------------------------------
# PARÁMETROS DE CÁLCULO
# -----------------------------------------------------------------------------

# Días hábiles por año (default · modificable en dashboard)
DIAS_ANIO_DEFAULT = 365

# Tasa libre de riesgo default (%) · modificable en dashboard
RF_DEFAULT = 4.5

# Número de iteraciones para Montecarlo
MONTECARLO_ITERACIONES = 1000

# Percentil usado en Montecarlo como retorno representativo
MONTECARLO_PERCENTIL = 50

# Percentiles para análisis estadístico (tabla 6)
PERCENTILES_ANALISIS = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]

# -----------------------------------------------------------------------------
# OPTIMIZACIÓN DE PORTAFOLIO
# -----------------------------------------------------------------------------

# Restricciones de pesos (cada activo entre 0% y 100%)
PESO_MINIMO = 0.0
PESO_MAXIMO = 1.0

# Los tres objetivos de optimización
OBJETIVOS_OPTIMIZACION = [
    "max_retorno",
    "max_sharpe",
    "min_volatilidad"
]

# Los tres métodos de retorno
METODOS_RETORNO = [
    "markowitz",
    "capm",
    "montecarlo"
]

# -----------------------------------------------------------------------------
# DASHBOARD
# -----------------------------------------------------------------------------

# Título de la aplicación
APP_TITULO = "Portfolio Analyzer · Análisis Cuantitativo de Portafolio"
APP_SUBTITULO = "Modelos: Markowitz · CAPM · Montecarlo"

# Nombre del archivo Excel exportado
EXCEL_EXPORT_NOMBRE = "portafolio_analisis.xlsx"

# -----------------------------------------------------------------------------
# VALIDACIONES
# -----------------------------------------------------------------------------

# Mínimo de activos requeridos (sin contar benchmark)
MIN_ACTIVOS = 2

# Máximo de activos permitidos
MAX_ACTIVOS = 20

# Mínimo de datos requeridos para el análisis
MIN_DATOS = 100
