# STATUS — financial-orchestrator

> Snapshot **mutable** del estado de trabajo. Se **LEE al iniciar sesión** y se
> **ACTUALIZA al cerrarla** (o cerca del límite de tokens). No es la bitácora
> (append-only, el *por qué*); esto refleja el **ahora** — dónde retomar.

**Última actualización:** 2026-07-02

## En qué estamos
Roadmap corregido (decisión de Nicolas): **A1 sector → A2 SQLite → A3 backtest**.
**A1 CERRADO** (2026-07-02, confirmado por Nicolas). Siguiente: **A2 — SQLite**.

## Hecho en la última sesión
- **A1**: `orchestrator/adapters/financial_models.py` — detección de sector financiero
  + DDM Gordon + P/BV ajustado por ROE. Enrutamiento en `fundamental_adapter.analyze_ticker`.
- Contrato `FUND_RESULT_SCHEMA` extendido: columnas `sector` y `valuation_model`.
- 10 tests unitarios (`tests/test_financial_models.py`) — todos pasan, sin red.
- Bitácora: entrada 2026-07-02 corrige el orden del roadmap (supersede la del 2026-06-13).
- Memo PDF: modelo de valoración por activo + nota de consideraciones metodológicas.
- Streamlit: nombres de compañía (cache 7d), tablas interactivas (column_config), tema visual.
- **Bugfix**: KeyError '^GSPC' en portafolio unificado por IR — `portfolio_stage` ahora anexa
  rendimientos de