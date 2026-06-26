# Financial Orchestrator

Pipeline de análisis institucional top-down que integra tres módulos Python existentes.

## Instalación

```bash
pip install -r requirements.txt
```

## Uso rápido

```bash
# 5 tickers S&P 500 (cold cache, ~5 min)
python main.py --tickers AAPL MSFT GOOGL NVDA JPM

# Con config YAML
cp config.yml.example config.yml
python main.py --config config.yml

# Solo compras con umbral más estricto
python main.py --tickers AAPL MSFT GOOGL --filter1-threshold 0.65 --filter2-mode buy_only

# Mezcla S&P 500 + BVC Colombia
python main.py --tickers AAPL MSFT PFBCOLOM.CL ECOPETL.CL --benchmark ^GSPC

# Dry run (solo filtros, sin PDF)
python main.py --tickers AAPL MSFT GOOGL NVDA --dry-run --verbose
```

## App interactiva (Streamlit)

Versión visual del pipeline, con controles para tickers, umbrales y gráficos.

```bash
# 1. Instalar dependencias (incluye streamlit)
pip install -r requirements.txt

# 2. Lanzar la app
streamlit run streamlit_app.py
```

Se abre en el navegador (por defecto http://localhost:8501). Para usar otro puerto:

```bash
streamlit run streamlit_app.py --server.port 8502
```

> Nota: requiere las mismas variables de entorno de los módulos fuente (ver más abajo).
> El PDF de la etapa 5 usa **WeasyPrint**, que **no** se instala por defecto (Streamlit Cloud
> no soporta sus librerías nativas). Sin él, la app cae a un fallback `.html`/`.json` en `output/`.
> Para generar PDF en local: `pip install weasyprint` (en Windows requiere GTK).

## Variables de entorno (módulos fuente)

```bash
export QUANT_DASHBOARD_PATH=/ruta/a/quant-dashboard/app.py
export ANALISIS_INSTITUCIONAL_PATH=/ruta/a/ANALISIS_INSTITUCIONAL
export PORTFOLIO_ANALYZER_PATH=/ruta/a/portfolio-analyzer
```

Si no se definen, el orquestador busca los módulos en el directorio hermano.

## Flujo del pipeline

```
Etapa 1: Descarga robusta (yfinance, cache Parquet, retry x3)
Etapa 2: Filtro 1 estadístico — solo BUY (ProcessPoolExecutor)
Etapa 3: Filtro 2 fundamental — DCF + múltiplos (pausa interactiva)
Etapa 4: Optimización — 9 portafolios + frontera eficiente (rf = ^TNX auto)
Etapa 5: PDF investing memo (WeasyPrint + Jinja2)
```

## Solución de problemas

- **ImportError streamlit**: el adaptador quant ya inyecta un stub — verifica `QUANT_DASHBOARD_PATH`
- **Menos de 3 activos**: baja `--filter1-threshold` o cambia a `--filter2-mode buy_hold`
- **WeasyPrint falla**: el sistema guarda un `.html` y `.json` como fallback en `output/`
- **Ticker no descarga**: aparecerá en la lista de "fallidos" y se omitirá automáticamente
