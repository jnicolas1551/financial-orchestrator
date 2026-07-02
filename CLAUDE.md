# CLAUDE.md — financial-orchestrator

> Extiende la base en `PROYECTOS_CLAUDE/CLAUDE.md`. Aquí solo lo propio del proyecto + bitácora.

## 1. Qué es
**Pipeline top-down de 5 etapas** que integra los otros 3 proyectos: descarga → filtro estadístico
→ filtro fundamental (DCF + múltiplos) → optimización de portafolio → **PDF investing memo**.
CLI (`main.py`) + app Streamlit (`streamlit_app.py`). **Estado: en desarrollo.**
~~Flaw conocido: DCF aplicado a bancos~~ **Resuelto 2026-07-02**: detección de sector enruta
financieras a **DDM + P/BV** (`orchestrator/adapters/financial_models.py`). Pendiente validar en vivo.

## 2. Cómo se ejecuta
```bash
py -m pip install -r requirements.txt
py main.py --tickers AAPL MSFT GOOGL NVDA JPM     # ~5 min cold cache
py main.py --config config.yml                    # 50 tickers S&P 500
py main.py --tickers AAPL MSFT GOOGL --dry-run --verbose   # solo filtros, sin PDF
streamlit run streamlit_app.py                    # versión interactiva
```
**Env vars** (si no, busca los módulos en carpetas hermanas):
`QUANT_DASHBOARD_PATH`, `ANALISIS_INSTITUCIONAL_PATH`, `PORTFOLIO_ANALYZER_PATH`.

## 3. Arquitectura real
| Archivo | Responsabilidad real |
|---|---|
| `main.py` | Orquesta las 5 etapas + CLI (argparse). Gate: **mínimo 3 activos** para optimizar. |
| `orchestrator/contracts.py` | Schemas de DataFrames entre etapas (`stat`, `fund`, `frontier`) + validación. |
| `orchestrator/data_pipeline.py` | Etapa 1: descarga yfinance, cache **Parquet**, retry. |
| `orchestrator/stat_filter.py` | Etapa 2: score estadístico en **ProcessPoolExecutor** (paralelo), retiene solo BUY. |
| `orchestrator/fundamental_filter.py` | Etapa 3: DCF+múltiplos paralelo + **pausa interactiva** `input()` (`+TICK -TICK`). |
| `orchestrator/portfolio_stage.py` | Etapa 4: optimización + frontera. |
| `orchestrator/report_builder.py` | Etapa 5: **WeasyPrint + Jinja2** (`templates/investing_memo.html`). |
| `orchestrator/adapters/` | `fundamental_adapter`, `portfolio_adapter`, `quant_adapter` — envuelven los 3 proyectos fuente. |
| `orchestrator/adapters/financial_models.py` | **Sector financiero**: detección (`is_financial`) + DDM Gordon + P/BV ajustado por ROE. Autocontenido (yfinance directo), funciones puras testeables. Tests: `tests/test_financial_models.py`. |
| `quant/` | **Copia vendorizada** de `portfolio-analyzer` (calculos/config/datos/optimizacion idénticos). |

## 4. Decisiones de modelo / parámetros (en `config.yml`)
- **Filtro 1:** `threshold=0.40`, pesos `w_reg=0.40 / w_pct=0.30 / w_tec=0.30` (score ponderado 0-1).
- **Filtro 2:** `filter2_mode = buy_only` | `buy_hold`.
- **Fundamental DCF:** `growth_explicit=0.08`, `terminal_growth=0.025`, `explicit_years=5`.
- **Rf:** auto-descarga `^TNX` (US 10Y Treasury); override con `--rf`. Benchmark `^GSPC`.
- **Cache:** `cache/` Parquet, `cache_ttl_hours=24`. Histórico por defecto: 3 años atrás.

## 5. Particularidades y trampas
- `quant_adapter` **inyecta un stub de `streamlit`** para importar el código del dashboard sin servidor
  (de ahí el ImportError típico → revisar `QUANT_DASHBOARD_PATH`).
- Fuerza UTF-8 en stdout de Windows (flechas/emojis rompen la consola si no).
- Si WeasyPrint falla, guarda `.html` y `.json` de fallback en `output/`.
- `quant/` es copia, **no symlink**: un cambio en portfolio-analyzer NO se propaga aquí automáticamente.

---

## Bitácora de decisiones
> Append-only, entrada nueva arriba. Formato `### AAAA-MM-DD — Título` + **Qué:** / **Por qué:**.

### 2026-07-02 — Detección de sector implementada (A1); orden del roadmap corregido
**Qué:** (1) Se reabrió y corrigió el orden del roadmap por decisión explícita de Nicolas:
**A1 detección de sector → A2 DB SQLite → A3 backtest walk-forward** (la entrada del
2026-06-13 decía DB primero; queda superseded). (2) Implementado A1: `financial_models.py`
detecta sector financiero y enruta a **DDM Gordon + P/BV ajustado por ROE** en vez de
DCF+múltiplos (EV/EBITDA tampoco aplica a bancos). Mismo contrato de columnas:
`dcf_price`=precio intrínseco, `mult_price`=precio relativo, `wacc`=Ke; columnas nuevas
`sector` y `valuation_model`. 10 tests unitarios sin red.
**Por qué:** DCF-FCFF es estructuralmente engañoso en financieras (la deuda es el producto).
Se implementó autocontenido en el orchestrator (no en ANALISIS_INSTITUCIONAL) para no tocar
el proyecto estable; migrar el modelo a su casa natural queda como deuda técnica menor.
Ke usa `rf_override|rf_default` (el rf vivo de ^TNX se calcula en etapa 4, posterior).

<!-- BITACORA START -->
### 2026-06-13 — quant/ es copia vendorizada, no symlink
**Qué:** los módulos de portfolio-analyzer (`calculos`, `config`, `datos`, `optimizacion`) están
copiados dentro de `quant/`.
**Por qué:** aísla el orchestrator de cambios accidentales y simplifica el deploy. Trade-off: hay que
re-sincronizar manualmente si se corrige un cálculo en portfolio-analyzer. Pendiente: unificar tras la DB.

### 2026-06-13 — DCF uniforme sin detección de sector (flaw conocido)
**Qué:** el Filtro 2 aplica DCF-FCFF a todos los tickers, incluidos bancos.
**Por qué:** es deuda técnica conocida. La corrección (detección bancario/no-bancario → DDM) es la
**decisión cerrada #2** de la base y va después de la DB. No reabrir el orden.
<!-- BITACORA END -->
