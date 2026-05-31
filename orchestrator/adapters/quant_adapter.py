"""
Adaptador para quant-dashboard/app.py.
Inyecta un stub de Streamlit antes de importar el módulo monolítico,
evitando que se active el runtime de Streamlit.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path

# ---------------------------------------------------------------------------
# Localización del módulo quant-dashboard
# ---------------------------------------------------------------------------

def _find_quant_path() -> Path:
    """
    Resuelve la ruta a quant-dashboard/app.py en este orden:
    1. Variable de entorno QUANT_DASHBOARD_PATH
    2. Directorio hermano ../quant-dashboard/app.py
    """
    env_path = os.environ.get("QUANT_DASHBOARD_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p

    # Hermano del directorio padre de financial-orchestrator
    here = Path(__file__).resolve()
    # financial-orchestrator/orchestrator/adapters/quant_adapter.py
    sibling = here.parents[2].parent / "quant-dashboard" / "app.py"
    if sibling.exists():
        return sibling

    raise FileNotFoundError(
        "No se encontró quant-dashboard/app.py. "
        "Define la variable de entorno QUANT_DASHBOARD_PATH con la ruta absoluta."
    )


# ---------------------------------------------------------------------------
# Stub de Streamlit — debe insertarse ANTES de cualquier import del módulo
# ---------------------------------------------------------------------------

def _inject_streamlit_stub() -> None:
    """
    Inserta un módulo ficticio de streamlit en sys.modules para que
    los decoradores @st.cache_data y referencias a st.session_state
    no fallen al importar app.py fuera del contexto Streamlit.
    """
    if "streamlit" in sys.modules:
        return  # ya inyectado o ya importado realmente

    stub = types.ModuleType("streamlit")

    # @st.cache_data(ttl=...) — decorator que devuelve la función sin cambios
    stub.cache_data = lambda *args, **kwargs: (lambda f: f)
    stub.cache_resource = lambda *args, **kwargs: (lambda f: f)

    # st.session_state — dict-like
    stub.session_state = {}

    # st.sidebar, st.columns, etc. — devuelven stub para encadenamiento
    _noop = lambda *a, **kw: None
    stub.sidebar = _ContextNoop()   # soporta "with st.sidebar:" y st.sidebar.X()
    stub.columns = lambda *a, **kw: [_ContextNoop()] * (a[0] if a else 2)
    stub.write = _noop
    stub.title = _noop
    stub.header = _noop
    stub.subheader = _noop
    stub.info = _noop
    stub.warning = _noop
    stub.error = _noop
    stub.success = _noop
    stub.spinner = lambda *a, **kw: _ContextNoop()
    stub.expander = lambda *a, **kw: _ContextNoop()
    stub.tabs = lambda labels: [stub] * len(labels)
    stub.plotly_chart = _noop
    stub.dataframe = _noop
    stub.metric = _noop
    stub.selectbox = lambda *a, **kw: kw.get("index", 0)
    stub.slider = lambda *a, **kw: kw.get("value", 0)
    stub.number_input = lambda *a, **kw: kw.get("value", 0.0)
    stub.checkbox = lambda *a, **kw: kw.get("value", False)
    stub.button = lambda *a, **kw: False
    stub.stop = _noop
    stub.set_page_config = _noop
    stub.download_button = _noop
    stub.multiselect = lambda *a, **kw: kw.get("default", [])
    stub.text_input = lambda *a, **kw: kw.get("value", "")
    stub.date_input = lambda *a, **kw: None
    stub.form = lambda *a, **kw: _ContextNoop()
    stub.form_submit_button = lambda *a, **kw: False
    # Atributos adicionales encontrados en quant-dashboard/app.py
    stub.markdown = _noop
    stub.caption = _noop
    stub.exception = _noop
    stub.file_uploader = lambda *a, **kw: None
    stub.progress = lambda *a, **kw: None
    stub.radio = lambda *a, **kw: (a[1][0] if len(a) > 1 and a[1] else None)
    stub.rerun = _noop
    stub.empty = lambda: stub
    stub.container = lambda: _ContextNoop()
    stub.image = _noop
    stub.divider = _noop
    stub.code = _noop
    stub.json = _noop
    stub.latex = _noop
    stub.balloons = _noop
    stub.toast = _noop
    stub.status = lambda *a, **kw: _ContextNoop()

    sys.modules["streamlit"] = stub


class _ContextNoop:
    """
    Context manager que no hace nada.
    Soporta encadenamiento de atributos: st.sidebar.selectbox(...)
    y uso como context manager: with st.sidebar:
    """
    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def __call__(self, *a, **kw):
        return self

    def __getattr__(self, name):
        # Atributos especiales que devuelven valores sensatos
        if name == "session_state":
            return {}
        return _ContextNoop()

    def __iter__(self):
        return iter([])

    def __bool__(self):
        return False


# ---------------------------------------------------------------------------
# Carga dinámica del módulo
# ---------------------------------------------------------------------------

_quant_app = None


def _load_quant_app():
    global _quant_app
    if _quant_app is not None:
        return _quant_app

    _inject_streamlit_stub()

    quant_path = _find_quant_path()

    # Usamos AST para extraer SOLO funciones, imports y constantes.
    # app.py de quant-dashboard ejecuta UI de Streamlit a nivel de módulo
    # (st.set_page_config, with st.sidebar:, etc.) que falla fuera del runtime.
    # Estrategia: conservar TODOS los FunctionDef/Import/Assign de constantes
    # y DESCARTAR los nodos que son UI pura (Expr con st.*, With, If top-level).
    import ast as _ast
    import types as _types

    with open(quant_path, encoding="utf-8") as _f:
        _src = _f.read()

    _tree = _ast.parse(_src, filename=str(quant_path))

    # Encontrar la línea donde empieza el primer bloque With de la UI.
    # Todo lo anterior son imports + funciones + constantes (seguro ejecutar).
    # Todo lo posterior es UI de Streamlit (falla fuera del runtime).
    _ui_start_line = float("inf")
    for _node in _tree.body:
        if isinstance(_node, (_ast.With, _ast.If, _ast.For, _ast.While,
                               _ast.Try, _ast.TryStar)):
            _ui_start_line = _node.lineno
            break

    _keep = []
    for _node in _tree.body:
        # Solo incluir nodos que están ANTES del inicio de la UI
        if _node.lineno >= _ui_start_line:
            continue

        if isinstance(_node, (
            _ast.Import, _ast.ImportFrom,
            _ast.FunctionDef, _ast.AsyncFunctionDef,
            _ast.ClassDef,
            _ast.Assign, _ast.AugAssign, _ast.AnnAssign,
        )):
            _keep.append(_node)
        # Descartar Expr top-level (st.set_page_config, st.markdown, etc.)

    _filtered = _ast.Module(body=_keep, type_ignores=[])
    _ast.fix_missing_locations(_filtered)
    _code = compile(_filtered, str(quant_path), "exec")

    mod = _types.ModuleType("quant_app")
    mod.__file__ = str(quant_path)
    exec(_code, mod.__dict__)

    _quant_app = mod
    return _quant_app


# ---------------------------------------------------------------------------
# API pública del adaptador
# ---------------------------------------------------------------------------

def get_functions():
    """
    Devuelve un dict con todas las funciones necesarias del módulo quant.
    Uso: fns = get_functions(); fns['calc_stats'](ln_prices, benchmark)
    """
    mod = _load_quant_app()
    return {
        "calc_stats":           mod.calc_stats,
        "calc_precio_valorado": mod.calc_precio_valorado,
        "calc_ln":              mod.calc_ln,
        "calc_returns":         mod.calc_returns,
        "calc_base100":         mod.calc_base100,
        "unify_dates":          mod.unify_dates,
        "get_mm_signal":        mod.get_mm_signal,
        "get_macd_signal":      mod.get_macd_signal,
        "get_rsi_signal":       mod.get_rsi_signal,
        "get_fib_signal":       mod.get_fib_signal,
        "calc_mm":              mod.calc_mm,
        "calc_macd":            mod.calc_macd,
        "calc_rsi":             mod.calc_rsi,
        "calc_fibonacci":       mod.calc_fibonacci,
        "detect_zigzag_pivots": mod.detect_zigzag_pivots,
    }


def calc_stats(ln_prices, benchmark_col: str):
    return _load_quant_app().calc_stats(ln_prices, benchmark_col)

def calc_precio_valorado(stats_result: dict, w_reg: float, w_pct: float) -> dict:
    return _load_quant_app().calc_precio_valorado(stats_result, w_reg, w_pct)

def calc_ln(prices):
    return _load_quant_app().calc_ln(prices)

def unify_dates(prices_df):
    return _load_quant_app().unify_dates(prices_df)

def get_mm_signal(mm_df, periods=None):
    return _load_quant_app().get_mm_signal(mm_df, periods)

def get_macd_signal(macd_df):
    return _load_quant_app().get_macd_signal(macd_df)

def get_rsi_signal(rsi_series, buy_th=30, sell_th=70):
    return _load_quant_app().get_rsi_signal(rsi_series, buy_th, sell_th)

def get_fib_signal(prices_series, reversal_pct=0.05, min_duration_days=30):
    return _load_quant_app().get_fib_signal(prices_series, reversal_pct, min_duration_days)

def calc_mm(prices_series, periods=None):
    return _load_quant_app().calc_mm(prices_series, periods)

def calc_macd(prices_series, fast=12, slow=26, signal=9):
    return _load_quant_app().calc_macd(prices_series, fast, slow, signal)

def calc_rsi(prices_series, period=14):
    return _load_quant_app().calc_rsi(prices_series, period)
