"""
Financial Orchestrator — Streamlit UI v2
Pipeline top-down institucional: S&P 500 y BVC Colombia
"""
from __future__ import annotations

import sys
from pathlib import Path
from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

# ─────────────────────────────────────────────────────────────────────────────
# Configuración de página
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Financial Orchestrator",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

  html, body, .stApp, [class*="css"] { font-family: 'Inter', sans-serif; }
  .stApp {
    background: radial-gradient(1200px 600px at 15% -10%, #16213E 0%, #0B0F19 55%) fixed;
  }
  .block-container { padding-top: 1.2rem; max-width: 1400px; }

  h1, h2, h3 { letter-spacing: -0.02em; }

  /* KPI cards */
  .metric-card {
    background: linear-gradient(160deg, #171C2E 0%, #12172494 100%);
    border: 1px solid #262D45;
    border-radius: 14px; padding: 16px 18px;
    text-align: center; margin-bottom: 8px;
    transition: transform .15s ease, border-color .15s ease, box-shadow .15s ease;
  }
  .metric-card:hover {
    transform: translateY(-2px);
    border-color: #4C8BF5;
    box-shadow: 0 8px 24px rgba(76,139,245,0.12);
  }
  .metric-value { font-size: 1.65rem; font-weight: 800; color: #F5F7FF;
                  font-variant-numeric: tabular-nums; }
  .metric-label { font-size: 0.70rem; color: #7C87A8;
                  text-transform: uppercase; letter-spacing: 0.10em; margin-top: 5px;
                  font-weight: 600; }
  .metric-delta { font-size: 0.82rem; font-weight: 600; margin-top: 4px; }

  .positive { color: #34D399; }
  .negative { color: #F87171; }
  .neutral  { color: #FBBF24; }

  /* Encabezados de etapa */
  .stage-header {
    background: linear-gradient(90deg, rgba(76,139,245,0.16) 0%, rgba(76,139,245,0.03) 65%, transparent 100%);
    border-left: 3px solid #4C8BF5;
    border-radius: 0 10px 10px 0;
    padding: 12px 20px; margin: 22px 0 12px 0;
    font-size: 1.02rem; font-weight: 700; color: #F5F7FF;
    letter-spacing: -0.01em;
  }

  /* Cajas informativas */
  .info-box {
    background: rgba(37,99,235,0.08);
    border: 1px solid rgba(37,99,235,0.35);
    border-radius: 10px; padding: 13px 17px;
    font-size: 0.87rem; color: #A9C4F5; margin-bottom: 12px;
    line-height: 1.55;
  }
  .info-box b { color: #D6E3FB; }

  /* Sidebar */
  div[data-testid="stSidebarContent"] {
    background: linear-gradient(180deg, #131A2C 0%, #0E1322 100%);
    border-right: 1px solid #1E2740;
  }
  div[data-testid="stSidebarContent"] hr { border-color: #1E2740; }

  /* Botones */
  .stButton>button[kind="primary"] {
    background: linear-gradient(135deg, #4C8BF5, #2563EB);
    border: none; font-weight: 700; border-radius: 10px;
    transition: filter .15s ease, transform .1s ease;
  }
  .stButton>button[kind="primary"]:hover { filter: brightness(1.12); transform: translateY(-1px); }
  .stButton>button { border-radius: 10px; }

  /* Tabs */
  .stTabs [data-baseweb="tab-list"] {
    gap: 4px; background: #12172410; border-bottom: 1px solid #1E2740;
  }
  .stTabs [data-baseweb="tab"] {
    border-radius: 8px 8px 0 0; padding: 8px 18px; font-weight: 600;
  }
  .stTabs [aria-selected="true"] {
    background: rgba(76,139,245,0.12);
    border-bottom: 2px solid #4C8BF5;
  }

  /* Dataframes y gráficas: esquinas suaves */
  div[data-testid="stDataFrame"] {
    border: 1px solid #262D45; border-radius: 12px; overflow: hidden;
  }
  div[data-testid="stPlotlyChart"] {
    border: 1px solid #1E2740; border-radius: 14px;
    padding: 4px; background: #12172440;
  }

  /* Expanders / alerts */
  div[data-testid="stExpander"] { border: 1px solid #262D45; border-radius: 12px; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Session state
# ─────────────────────────────────────────────────────────────────────────────
DEFAULTS = {
    "stage": 0,
    "df_prices": None, "skipped": [],
    "df_stat": None, "buy_list": [], "buy_list_edited": [],
    "df_fund": None, "fund_passed": [], "final_tickers": [],
    "df_opt": None, "df_frontier": None, "df_rend": None,
    "rf": 0.045, "rf_label": "",
    "combined_portfolio": None,
    "portfolios_calculated": False,
    "output_path": None, "config": None,
    "names": {},
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v


def reset():
    for k, v in DEFAULTS.items():
        st.session_state[k] = v


# ─────────────────────────────────────────────────────────────────────────────
# Constantes visuales
# ─────────────────────────────────────────────────────────────────────────────
DARK = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(18,23,36,0.5)",
    font=dict(family="Inter,Arial", color="#E7EBF5", size=12),
    title_font=dict(size=15, color="#F5F7FF"),
    margin=dict(t=52, b=38, l=38, r=18),
    xaxis=dict(gridcolor="#1E2740", zerolinecolor="#262D45"),
    yaxis=dict(gridcolor="#1E2740", zerolinecolor="#262D45"),
    hoverlabel=dict(bgcolor="#171C2E", bordercolor="#4C8BF5",
                    font=dict(family="Inter,Arial", color="#F5F7FF")),
    legend=dict(bgcolor="rgba(0,0,0,0)"),
)
COLORS = ["#4C8BF5","#00C853","#FFD600","#FF6D00","#E040FB",
          "#00BCD4","#FF5252","#69F0AE","#FFAB40","#40C4FF"]


def kpi(col, label, value, delta="", css=""):
    with col:
        st.markdown(f"""
        <div class="metric-card">
          <div class="metric-label">{label}</div>
          <div class="metric-value">{value}</div>
          <div class="metric-delta {css}">{delta}</div>
        </div>""", unsafe_allow_html=True)


def pct(v, decimals=1):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "N/A"
    return f"{float(v)*100:+.{decimals}f}%"


def money(v, decimals=2):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "N/A"
    return f"${float(v):.{decimals}f}"


@st.cache_data(ttl=7 * 24 * 3600, show_spinner=False)
def get_company_names(tickers: tuple) -> dict:
    """Nombre corto de cada compañía vía yfinance. Cache 7 días."""
    import yfinance as yf
    names = {}
    for t in tickers:
        try:
            info = yf.Ticker(t).info or {}
            names[t] = info.get("shortName") or info.get("longName") or t
        except Exception:
            names[t] = t
    return names


def disp(ticker: str) -> str:
    """'Apple Inc. (AAPL)' si el nombre está disponible; si no, el ticker."""
    name = (st.session_state.get("names") or {}).get(ticker)
    return f"{name} ({ticker})" if name and name != ticker else ticker


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────
def render_sidebar():
    with st.sidebar:
        st.markdown("## 📊 Financial Orchestrator")
        st.caption("Pipeline institucional top-down")
        st.divider()

        # Tickers
        st.markdown("### 📈 Universo de activos")
        preset = st.selectbox("Preset", [
            "S&P 500 — 50 tickers (config.yml)",
            "S&P 500 — Top 15 diversificado",
            "BVC Colombia",
            "Personalizado",
        ])
        if preset == "S&P 500 — 50 tickers (config.yml)":
            cfg_path = Path(__file__).parent / "config.yml"
            if cfg_path.exists():
                import yaml
                with open(cfg_path) as f:
                    cfg_data = yaml.safe_load(f)
                default_tickers = ", ".join(cfg_data.get("tickers", []))
            else:
                default_tickers = "AAPL, MSFT, GOOGL"
        elif preset == "S&P 500 — Top 15 diversificado":
            default_tickers = ("AAPL, MSFT, GOOGL, NVDA, JPM, BAC, XOM, CVX, "
                               "UNH, JNJ, PG, KO, CAT, NKE, HD")
        elif preset == "BVC Colombia":
            default_tickers = "PFBCOLOM.CL, ECOPETL.CL, NUTRESA.CL, ISA.CL, CEMARGOS.CL"
        else:
            default_tickers = "AAPL, MSFT, GOOGL, NVDA, JPM"

        tickers_raw = st.text_area("Tickers (separados por coma)",
                                    value=default_tickers, height=120)
        tickers = [t.strip().upper() for t in tickers_raw.split(",") if t.strip()]
        benchmark = st.text_input("Benchmark", value="^GSPC")
        start_date = st.text_input(
            "Inicio histórico",
            value=(date.today() - timedelta(days=3*365)).strftime("%Y-%m-%d"))
        st.divider()

        # Filtro 1
        st.markdown("### 🔬 Filtro 1 — Estadístico")
        threshold = st.slider("Score mínimo", 0.20, 0.80, 0.40, 0.05)

        st.markdown("**Pesos de indicadores** (deben sumar 1.0)")
        col_a, col_b = st.columns(2)
        with col_a:
            w_reg = st.slider("Regresión", 0.0, 1.0, 0.40, 0.05, key="w_reg")
            w_pct = st.slider("Percentil",  0.0, 1.0, 0.30, 0.05, key="w_pct")
        with col_b:
            w_mm   = st.slider("Med. Móviles", 0.0, 1.0, 0.10, 0.05, key="w_mm")
            w_macd = st.slider("MACD",         0.0, 1.0, 0.10, 0.05, key="w_macd")
            w_rsi  = st.slider("RSI",          0.0, 1.0, 0.05, 0.05, key="w_rsi")
            w_fib  = st.slider("Fibonacci",    0.0, 1.0, 0.05, 0.05, key="w_fib")

        total_w = round(w_reg + w_pct + w_mm + w_macd + w_rsi + w_fib, 2)
        w_tec = round(w_mm + w_macd + w_rsi + w_fib, 2)
        if abs(total_w - 1.0) > 0.05:
            st.warning(f"Los pesos suman {total_w:.2f} (deben ser ~1.0). "
                       "Se normalizarán automáticamente.")
        else:
            st.caption(f"✅ Suma pesos: {total_w:.2f} | w_tec={w_tec:.2f}")
        st.divider()

        # Filtro 2
        st.markdown("### 🏦 Filtro 2 — Fundamental")
        filter2_mode = st.radio("Modo", ["buy_only", "buy_hold"],
                                captions=["Solo compra", "Compra + mantener"])
        st.divider()

        # Tasa libre de riesgo
        st.markdown("### 📐 Tasa libre de riesgo")
        rf_mode = st.radio("Fuente", ["Auto (^TNX 10Y)", "Manual"])
        rf_manual = None
        if rf_mode == "Manual":
            rf_manual = st.number_input("Rf (%)", 0.0, 20.0, 4.5, 0.05) / 100
        st.divider()

        col_run, col_reset = st.columns(2)
        run_clicked = col_run.button("🚀 Ejecutar", type="primary", use_container_width=True)
        col_reset.button("🔄 Reset", on_click=reset, use_container_width=True)

    return {
        "tickers": tickers, "benchmark": benchmark, "start_date": start_date,
        "threshold": threshold,
        "w_reg": w_reg, "w_pct": w_pct, "w_tec": w_tec,
        "w_mm": w_mm, "w_macd": w_macd, "w_rsi": w_rsi, "w_fib": w_fib,
        "filter2_mode": filter2_mode, "rf_override": rf_manual, "run": run_clicked,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Gráficas
# ─────────────────────────────────────────────────────────────────────────────

def fig_scores(df_stat: pd.DataFrame, threshold: float) -> go.Figure:
    df = df_stat[df_stat["score"].notna()].sort_values("score", ascending=True)
    colors = ["#00C853" if p else "#FF1744" for p in df["passes_filter1"]]
    fig = go.Figure(go.Bar(
        x=df["score"], y=[disp(t) for t in df.index], orientation="h",
        marker_color=colors,
        text=[f"{v:.3f}" for v in df["score"]], textposition="outside",
    ))
    fig.add_vline(x=threshold, line_dash="dash", line_color="#FFD600",
                  annotation_text=f"threshold={threshold}")
    fig.update_layout(title="Score Estadístico (verde=BUY)", height=max(280, len(df)*26), **DARK)
    return fig


def fig_technical_indicators(df_stat: pd.DataFrame) -> go.Figure:
    """Heatmap de señales técnicas por ticker."""
    df = df_stat[df_stat["score"].notna()].sort_values("score", ascending=False)
    indicators = ["signal_mm", "signal_macd", "signal_rsi", "signal_fib"]
    labels = ["Med. Móviles", "MACD", "RSI", "Fibonacci"]

    z, text_vals = [], []
    for _, row in df.iterrows():
        row_z, row_t = [], []
        for ind in indicators:
            sig = str(row.get(ind, "N/A")).upper()
            if "COMPRA" in sig or "BUY" in sig:
                row_z.append(1); row_t.append("🟢 Compra")
            elif "VENTA" in sig or "SELL" in sig:
                row_z.append(-1); row_t.append("🔴 Venta")
            else:
                row_z.append(0); row_t.append("⚪ Neutro")
        z.append(row_z); text_vals.append(row_t)

    fig = go.Figure(go.Heatmap(
        z=z, x=labels, y=[disp(t) for t in df.index],
        text=text_vals, texttemplate="%{text}",
        colorscale=[[0,"#7f1d1d"],[0.5,"#1E2130"],[1,"#064e3b"]],
        zmin=-1, zmax=1, showscale=False,
    ))
    fig.update_layout(
        title="Señales Técnicas por Ticker",
        height=max(280, len(df)*32), **DARK,
    )
    return fig


def fig_regression_stats(df_stat: pd.DataFrame) -> go.Figure:
    """Scatter Beta vs Correlación con tamaño=R²."""
    df = df_stat[df_stat["beta"].notna() & df_stat["corr"].notna()].copy()
    if df.empty:
        return None
    dfr = df.reset_index()
    dfr["compania"] = dfr["ticker"].map(disp)
    fig = px.scatter(
        dfr, x="beta", y="corr",
        size=df["r2"].fillna(0).abs() * 100 + 5,
        color="score", color_continuous_scale="RdYlGn",
        text="ticker", hover_name="compania",
        hover_data=["alpha","beta","r2","corr","pct_rank"],
        title="Beta vs Correlación con Benchmark (tamaño = R²)",
        labels={"beta":"Beta","corr":"Correlación","score":"Score"},
        range_color=[0, 1],
    )
    fig.add_vline(x=1, line_dash="dot", line_color="#8B92A5",
                  annotation_text="β=1 (mercado)")
    fig.add_hline(y=0, line_dash="dot", line_color="#8B92A5")
    fig.update_traces(textposition="top center")
    fig.update_layout(height=420, **DARK)
    return fig


def fig_dcf_comparison(df_fund: pd.DataFrame) -> go.Figure:
    """Precio actual vs objetivo DCF vs objetivo Múltiplos."""
    df = df_fund[df_fund["current_price"].notna()].copy()
    if df.empty:
        return None
    df = df.sort_values("upside_dcf", ascending=False, na_position="last")
    tickers = list(df.index)
    current = [float(df.loc[t, "current_price"] or 0) for t in tickers]
    dcf     = [float(df.loc[t, "dcf_price"]     or 0) for t in tickers]
    mult    = [float(df.loc[t, "mult_price"]     or 0) for t in tickers]

    x_labels = [disp(t) for t in tickers]
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Precio Actual", x=x_labels, y=current,
                         marker_color="#8B92A5"))
    fig.add_trace(go.Bar(name="Obj. Intrínseco (DCF/DDM)", x=x_labels, y=dcf,
                         marker_color="#4C8BF5",
                         text=[pct(df.loc[t,"upside_dcf"]) for t in tickers],
                         textposition="outside"))
    fig.add_trace(go.Bar(name="Obj. Relativo (Múlt./P-BV)", x=x_labels, y=mult,
                         marker_color="#00C853",
                         text=[pct(df.loc[t,"upside_mult"]) for t in tickers],
                         textposition="outside"))
    fig.update_layout(barmode="group",
                      title="Precio Actual vs Objetivos de Valoración",
                      yaxis_title="Precio (USD/COP)",
                      height=440, **DARK)
    return fig


def fig_portfolios_scatter(df_opt: pd.DataFrame) -> go.Figure:
    method_colors = {"Markowitz":"#4C8BF5","Capm":"#00C853","Montecarlo":"#FFD600"}
    fig = go.Figure()
    for idx in df_opt.index:
        row = df_opt.loc[idx]
        m, o = idx if isinstance(idx, tuple) else (str(idx), "")
        fig.add_trace(go.Scatter(
            x=[float(row.get("Volatilidad",0) or 0)*100],
            y=[float(row.get("Retorno",0) or 0)*100],
            mode="markers+text",
            name=f"{m} – {o}",
            marker=dict(size=14, color=method_colors.get(m,"#8B92A5")),
            text=[f"{o[:6]}"],
            textposition="top center",
            hovertemplate=f"<b>{m} – {o}</b><br>Vol: %{{x:.1f}}%<br>Ret: %{{y:.1f}}%<br>Sharpe: {float(row.get('Sharpe',0) or 0):.3f}<extra></extra>",
        ))
    fig.update_layout(title="9 Portafolios: Retorno vs Volatilidad",
                      xaxis_title="Volatilidad (%)", yaxis_title="Retorno (%)",
                      height=420, **DARK)
    return fig


def fig_frontier_with_portfolios(df_frontier, df_opt) -> go.Figure:
    fig = go.Figure()
    if df_frontier is not None and not df_frontier.empty:
        fig.add_trace(go.Scatter(
            x=df_frontier["Volatilidad"]*100, y=df_frontier["Retorno"]*100,
            mode="lines", name="Frontera Eficiente",
            line=dict(color="#4C8BF5", width=2.5),
        ))
    if df_opt is not None and not df_opt.empty:
        mc = {"Markowitz":"#4C8BF5","Capm":"#00C853","Montecarlo":"#FFD600"}
        for idx in df_opt.index:
            row = df_opt.loc[idx]
            m, o = idx if isinstance(idx, tuple) else (str(idx),"")
            fig.add_trace(go.Scatter(
                x=[float(row.get("Volatilidad",0) or 0)*100],
                y=[float(row.get("Retorno",0) or 0)*100],
                mode="markers", name=f"{m[:3]}-{o[:3]}",
                marker=dict(size=9, color=mc.get(m,"#8B92A5"), symbol="star"),
                hovertemplate=f"<b>{m} – {o}</b><br>Sharpe={float(row.get('Sharpe',0) or 0):.3f}<extra></extra>",
            ))
    fig.update_layout(title="Frontera Eficiente",
                      xaxis_title="Volatilidad (%)", yaxis_title="Retorno (%)",
                      height=380, **DARK)
    return fig


def fig_weights_heatmap(df_opt, portfolio_tickers) -> go.Figure:
    if df_opt is None or df_opt.empty:
        return None
    labels = [f"{idx[0][:4]}-{idx[1][:6]}" if isinstance(idx,tuple) else str(idx)
              for idx in df_opt.index]
    matrix = [[float(df_opt.loc[idx].get(t, 0) or 0)*100
               for t in portfolio_tickers]
              for idx in df_opt.index]
    fig = px.imshow(matrix, x=portfolio_tickers, y=labels,
                    color_continuous_scale=["#1E2130","#4C8BF5","#00C853"],
                    zmin=0, zmax=100, text_auto=".0f",
                    title="Pesos (%) — 9 Portafolios", aspect="auto")
    fig.update_layout(height=300, **DARK)
    return fig


def fig_pie_weights(weights: dict, title: str) -> go.Figure:
    tickers = [k for k, v in weights.items() if float(v or 0) > 0.001]
    values  = [float(weights[t] or 0)*100 for t in tickers]
    fig = go.Figure(go.Pie(
        labels=[disp(t) for t in tickers], values=values,
        marker_colors=COLORS[:len(tickers)],
        textinfo="label+percent",
        hovertemplate="%{label}: %{value:.1f}%<extra></extra>",
    ))
    fig.update_layout(title=title, height=360, **DARK)
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Pantalla de bienvenida
# ─────────────────────────────────────────────────────────────────────────────
def render_welcome():
    st.markdown("""
    <div style="text-align:center;padding:56px 20px 40px">
      <div style="font-size:3rem">📊</div>
      <h1 style="font-size:2.3rem;margin:12px 0 8px;font-weight:800;
                 background:linear-gradient(90deg,#F5F7FF 30%,#4C8BF5 100%);
                 -webkit-background-clip:text;-webkit-text-fill-color:transparent;">
        Financial Orchestrator</h1>
      <p style="color:#7C87A8;max-width:600px;margin:0 auto 6px;font-size:1.02rem">
        Pipeline institucional top-down · S&P 500 y BVC Colombia
      </p>
      <p style="color:#4C8BF5;font-size:0.82rem;letter-spacing:0.08em;
                text-transform:uppercase;font-weight:600">
        Descarga → Filtro estadístico → Valoración → Optimización → Memo PDF
      </p>
    </div>""", unsafe_allow_html=True)

    cols = st.columns(5)
    steps = [
        ("1️⃣","Descarga","Cache Parquet · Retry x3"),
        ("2️⃣","Filtro 1","Score estadístico + técnico"),
        ("3️⃣","Filtro 2","DCF · Múltiplos · señal"),
        ("4️⃣","Portfolio","9 portafolios · Portafolio unificado"),
        ("5️⃣","Memo PDF","Investing memo completo"),
    ]
    for col,(icon,title,desc) in zip(cols,steps):
        with col:
            st.markdown(f"""
            <div class="metric-card">
              <div style="font-size:1.5rem">{icon}</div>
              <div style="color:#FAFAFA;font-weight:600;margin:6px 0 4px">{title}</div>
              <div class="metric-label">{desc}</div>
            </div>""", unsafe_allow_html=True)
    st.info("👈 Configura los parámetros en el panel lateral y pulsa **🚀 Ejecutar**")


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline
# ─────────────────────────────────────────────────────────────────────────────
def run_pipeline(params: dict):
    from orchestrator.config import OrchestratorConfig
    from orchestrator import data_pipeline, stat_filter

    tickers = params["tickers"]
    if not tickers:
        st.error("Debes ingresar al menos un ticker.")
        return

    # Normalizar pesos
    total_w = params["w_reg"] + params["w_pct"] + params["w_tec"]
    if total_w > 0 and abs(total_w - 1.0) > 0.01:
        params["w_reg"] /= total_w
        params["w_pct"] /= total_w
        params["w_tec"] /= total_w
        params["w_tec"] = round(1.0 - params["w_reg"] - params["w_pct"], 4)

    try:
        config = OrchestratorConfig(
            tickers=tickers, benchmark=params["benchmark"],
            start_date=params["start_date"],
            w_reg=round(params["w_reg"], 4),
            w_pct=round(params["w_pct"], 4),
            w_tec=round(params["w_tec"], 4),
            filter1_threshold=params["threshold"],
            filter2_mode=params["filter2_mode"],
            rf_override=params["rf_override"],
        )
    except ValueError as e:
        st.error(f"Error de configuración: {e}")
        return

    st.session_state.config = config

    # ── Etapa 1 ──────────────────────────────────────────────────────
    st.markdown('<div class="stage-header">📥 Etapa 1 — Descarga de datos</div>',
                unsafe_allow_html=True)
    all_tickers = list(dict.fromkeys(tickers + [params["benchmark"]]))
    prog = st.progress(0, text=f"Descargando {len(all_tickers)} tickers...")

    with st.spinner(""):
        df_prices, skipped = data_pipeline.download_prices(all_tickers, config)
    prog.progress(100, text="✅ Descarga completa")

    st.session_state.df_prices = df_prices
    st.session_state.skipped   = skipped

    # Nombres de compañías (cache 7 días — no repite llamadas entre corridas)
    with st.spinner("Obteniendo nombres de compañías..."):
        inv = tuple(sorted(t for t in df_prices.columns if t != params["benchmark"]))
        st.session_state.names = get_company_names(inv)

    c1,c2,c3 = st.columns(3)
    kpi(c1,"Descargados", str(len(df_prices.columns)))
    kpi(c2,"Fallidos", str(len(skipped)),
        ", ".join(skipped[:3]) if skipped else "ninguno",
        "negative" if skipped else "positive")
    kpi(c3,"Periodo",
        f"{df_prices.index[0].strftime('%Y-%m-%d')} → {df_prices.index[-1].strftime('%Y-%m-%d')}")

    # ── Etapa 2 ──────────────────────────────────────────────────────
    st.markdown('<div class="stage-header">🔬 Etapa 2 — Filtro 1: Análisis Estadístico y Técnico</div>',
                unsafe_allow_html=True)
    with st.spinner("Analizando indicadores en paralelo..."):
        df_stat, buy_list = stat_filter.run(df_prices, config)

    st.session_state.df_stat = df_stat
    st.session_state.buy_list = buy_list
    st.session_state.buy_list_edited = buy_list.copy()

    total_inv = len([t for t in df_prices.columns if t != params["benchmark"]])
    c1,c2,c3,c4 = st.columns(4)
    kpi(c1,"Analizados", str(total_inv))
    kpi(c2,"BUY (F1)", str(len(buy_list)),
        f"score ≥ {params['threshold']}", "positive" if buy_list else "negative")
    kpi(c3,"Rechazados", str(total_inv-len(buy_list)))
    avg_score = df_stat["score"].mean() if not df_stat.empty else 0
    kpi(c4,"Score promedio", f"{avg_score:.3f}")

    # Tabs con detalles
    tab_score, tab_tech, tab_stat = st.tabs([
        "📊 Scores", "📈 Indicadores Técnicos", "📉 Estadísticos (α β R²)"
    ])

    with tab_score:
        if not df_stat.empty:
            st.plotly_chart(fig_scores(df_stat, params["threshold"]),
                            use_container_width=True)
            _render_score_table(df_stat)

    with tab_tech:
        _render_technical_table(df_stat, params)

    with tab_stat:
        _render_regression_table(df_stat)

    st.session_state.stage = 2
    st.rerun()


def _render_score_table(df_stat: pd.DataFrame):
    """Tabla de scores — columnas numéricas reales (ordenables) + barra de progreso."""
    cols_show = [c for c in ["score","pot_reg","pot_pct","passes_filter1"] if c in df_stat.columns]
    df_show = df_stat[cols_show].copy()
    df_show.insert(0, "compania", [disp(t) for t in df_show.index])
    for c in ["pot_reg", "pot_pct"]:
        if c in df_show.columns:
            df_show[c] = pd.to_numeric(df_show[c], errors="coerce") * 100
    df_show["passes_filter1"] = df_show["passes_filter1"].map(
        lambda x: "✅ BUY" if x else "❌ NO")
    df_show = df_show.sort_values("score", ascending=False)
    st.dataframe(
        df_show, use_container_width=True, hide_index=True,
        column_config={
            "compania": st.column_config.TextColumn("Compañía", width="medium"),
            "score": st.column_config.ProgressColumn(
                "Score", min_value=0.0, max_value=1.0, format="%.3f"),
            "pot_reg": st.column_config.NumberColumn("Potencial Reg.", format="%+.1f%%"),
            "pot_pct": st.column_config.NumberColumn("Potencial Pct.", format="%+.1f%%"),
            "passes_filter1": st.column_config.TextColumn("Filtro 1", width="small"),
        },
    )


def _render_technical_table(df_stat: pd.DataFrame, params: dict):
    """Tabla de indicadores técnicos con valores numéricos y heatmap."""
    st.markdown("""
    <div class="info-box">
    <b>¿Qué significan los indicadores?</b><br>
    <b>Medias Móviles (MM)</b>: Compara el precio vs sus promedios históricos.
    Compra cuando cruza al alza.<br>
    <b>MACD</b>: Momentum. Histograma positivo y creciente = impulso alcista.<br>
    <b>RSI</b>: Sobrecompra (>70) o sobreventa (<30). Valores 30-70 = zona neutral.<br>
    <b>Fibonacci</b>: El precio en zonas de soporte (retroceso 38.2%–61.8%) sugiere rebote.
    </div>""", unsafe_allow_html=True)

    sig_cols = [c for c in ["signal_mm","signal_macd","signal_rsi","signal_fib"] if c in df_stat.columns]
    num_cols = [c for c in ["rsi_value","macd_hist","score"] if c in df_stat.columns]
    df_show = df_stat[sig_cols + num_cols].copy()
    df_show.insert(0, "compania", [disp(t) for t in df_show.index])

    for c in sig_cols:
        df_show[c] = df_show[c].apply(_shorten_signal)
    for c in ["rsi_value", "macd_hist", "score"]:
        if c in df_show.columns:
            df_show[c] = pd.to_numeric(df_show[c], errors="coerce")

    if "score" in df_show.columns:
        df_show = df_show.sort_values("score", ascending=False)
    st.dataframe(
        df_show, use_container_width=True, hide_index=True,
        column_config={
            "compania": st.column_config.TextColumn("Compañía", width="medium"),
            "signal_mm": st.column_config.TextColumn("MM", width="small"),
            "signal_macd": st.column_config.TextColumn("MACD", width="small"),
            "signal_rsi": st.column_config.TextColumn("RSI", width="small"),
            "signal_fib": st.column_config.TextColumn("Fibonacci", width="small"),
            "rsi_value": st.column_config.NumberColumn("RSI Valor", format="%.1f"),
            "macd_hist": st.column_config.NumberColumn("MACD Hist", format="%+.4f"),
            "score": st.column_config.ProgressColumn(
                "Score", min_value=0.0, max_value=1.0, format="%.3f"),
        },
    )

    if not df_stat.empty and all(c in df_stat.columns for c in sig_cols):
        st.plotly_chart(fig_technical_indicators(df_stat), use_container_width=True)

    # Explicación de pesos usados
    c1,c2,c3,c4 = st.columns(4)
    kpi(c1,"Peso MM",       f"{params['w_mm']*100:.0f}%")
    kpi(c2,"Peso MACD",     f"{params['w_macd']*100:.0f}%")
    kpi(c3,"Peso RSI",      f"{params['w_rsi']*100:.0f}%")
    kpi(c4,"Peso Fibonacci",f"{params['w_fib']*100:.0f}%")


def _render_regression_table(df_stat: pd.DataFrame):
    """Tabla de estadísticos de regresión."""
    st.markdown("""
    <div class="info-box">
    <b>Alpha (α)</b>: Retorno independiente del mercado (logarítmico). Positivo = supera al benchmark.<br>
    <b>Beta (β)</b>: Sensibilidad al mercado. β>1 = más volátil que el mercado; β<1 = más defensivo.<br>
    <b>R²</b>: Qué % del movimiento del activo se explica por el benchmark (0=nada, 1=todo).<br>
    <b>Correlación</b>: Dirección de movimiento vs benchmark (-1 a +1).<br>
    <b>Percentil actual</b>: Dónde está el precio actual en su historia (0%=mínimo histórico, 100%=máximo).
    </div>""", unsafe_allow_html=True)

    reg_cols = [c for c in ["alpha","beta","r2","corr","pct_rank","std_20","score"] if c in df_stat.columns]
    df_show = df_stat[reg_cols].copy()
    df_show.insert(0, "compania", [disp(t) for t in df_show.index])
    for c in reg_cols:
        df_show[c] = pd.to_numeric(df_show[c], errors="coerce")
    if "pct_rank" in df_show.columns:
        df_show["pct_rank"] = df_show["pct_rank"] * 100

    if "score" in df_show.columns:
        df_show = df_show.sort_values("score", ascending=False)
    st.dataframe(
        df_show, use_container_width=True, hide_index=True,
        column_config={
            "compania": st.column_config.TextColumn("Compañía", width="medium"),
            "alpha": st.column_config.NumberColumn("Alpha", format="%+.4f"),
            "beta": st.column_config.NumberColumn("Beta", format="%.3f"),
            "r2": st.column_config.NumberColumn("R²", format="%.3f"),
            "corr": st.column_config.NumberColumn("Correlación", format="%.3f"),
            "pct_rank": st.column_config.NumberColumn("Percentil Actual", format="%.1f%%"),
            "std_20": st.column_config.NumberColumn("Std 20d", format="%.4f"),
            "score": st.column_config.ProgressColumn(
                "Score", min_value=0.0, max_value=1.0, format="%.3f"),
        },
    )

    fig = fig_regression_stats(df_stat)
    if fig:
        st.plotly_chart(fig, use_container_width=True)


def _shorten_signal(s: str) -> str:
    if not isinstance(s, str) or s == "N/A":
        return "⚪ N/A"
    su = s.upper()
    if "COMPRA" in su or "BUY" in su:
        return "🟢 Compra"
    if "VENTA" in su or "SELL" in su:
        return "🔴 Venta"
    return "⚪ Neutro"


# ─────────────────────────────────────────────────────────────────────────────
# Pausa F1 → F2
# ─────────────────────────────────────────────────────────────────────────────
def render_f1_edit():
    cfg  = st.session_state.config
    buy  = st.session_state.buy_list
    all_tickers = [t for t in st.session_state.df_prices.columns if t != cfg.benchmark]

    st.markdown('<div class="stage-header">✏️ Editar lista antes del análisis fundamental</div>',
                unsafe_allow_html=True)
    edited = st.multiselect(
        f"Filtro 1 seleccionó {len(buy)} tickers. Agrega o elimina según tu criterio:",
        options=sorted(set(all_tickers)), default=sorted(set(buy)),
        format_func=disp,
    )
    st.session_state.buy_list_edited = edited
    if not edited:
        st.warning("Selecciona al menos 1 ticker.")
    else:
        if st.button(f"▶ Analizar {len(edited)} tickers fundamentalmente",
                     type="primary", use_container_width=True):
            st.session_state.stage = 3
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Etapa 3: Análisis fundamental
# ─────────────────────────────────────────────────────────────────────────────
def run_fundamental():
    from orchestrator import fundamental_filter

    cfg     = st.session_state.config
    tickers = st.session_state.buy_list_edited

    st.markdown('<div class="stage-header">🏦 Etapa 3 — Filtro 2: Valoración Fundamental (DCF + Múltiplos)</div>',
                unsafe_allow_html=True)

    st.markdown("""
    <div class="info-box">
    <b>¿Qué es el Upside/Downside?</b><br>
    Es la diferencia porcentual entre el <b>precio objetivo calculado</b> y el <b>precio actual de mercado</b>.<br>
    <b>Upside DCF</b> = (Precio objetivo por Flujo de Caja Descontado / Precio actual) − 1<br>
    <b>Upside Múltiplos</b> = (Precio objetivo por comparables de pares / Precio actual) − 1<br>
    Un valor <span class="positive">positivo</span> indica que el activo cotiza <b>por debajo</b> de su valor intrínseco (potencial de alza).
    Un valor <span class="negative">negativo</span> indica que cotiza <b>por encima</b> (sobrevaluado).
    </div>""", unsafe_allow_html=True)

    with st.spinner(f"DCF + múltiplos para {len(tickers)} tickers (paralelo)..."):
        df_fund, fund_passed = fundamental_filter.run(tickers, cfg, interactive=False)

    st.session_state.df_fund   = df_fund
    st.session_state.fund_passed = fund_passed
    st.session_state.final_tickers = fund_passed.copy()

    c1,c2,c3,c4 = st.columns(4)
    kpi(c1,"Analizados", str(len(tickers)))
    kpi(c2,"BUY/HOLD", str(len(fund_passed)), cfg.filter2_mode,
        "positive" if fund_passed else "negative")
    kpi(c3,"Rechazados (SELL)", str(len(tickers)-len(fund_passed)))
    wacc_avg = df_fund["wacc"].dropna().mean() if "wacc" in df_fund.columns else None
    kpi(c4,"WACC promedio", f"{wacc_avg*100:.1f}%" if wacc_avg else "N/A")

    # Gráfica comparativa
    if not df_fund.empty:
        f = fig_dcf_comparison(df_fund)
        if f:
            st.plotly_chart(f, use_container_width=True)

    # Tabla detallada
    _render_fund_table(df_fund)

    st.session_state.stage = 4
    st.rerun()


def _render_fund_table(df_fund: pd.DataFrame):
    cols = [c for c in ["signal","valuation_model","sector","current_price","dcf_price","mult_price",
                         "upside_dcf","upside_mult","wacc","peers_count"] if c in df_fund.columns]
    df_show = df_fund[cols].copy()
    df_show.insert(0, "compania", [disp(t) for t in df_show.index])

    if "signal" in df_show.columns:
        df_show["signal"] = df_show["signal"].map(
            {"buy": "🟢 BUY", "hold": "🟡 HOLD", "sell": "🔴 SELL"}).fillna("⚪ N/A")
    for col in ["upside_dcf", "upside_mult", "wacc"]:
        if col in df_show.columns:
            df_show[col] = pd.to_numeric(df_show[col], errors="coerce") * 100
    for col in ["current_price", "dcf_price", "mult_price"]:
        if col in df_show.columns:
            df_show[col] = pd.to_numeric(df_show[col], errors="coerce")

    if "upside_dcf" in df_show.columns:
        df_show = df_show.sort_values("upside_dcf", ascending=False, na_position="last")
    st.dataframe(
        df_show, use_container_width=True, hide_index=True,
        column_config={
            "compania": st.column_config.TextColumn("Compañía", width="medium"),
            "signal": st.column_config.TextColumn("Señal", width="small"),
            "valuation_model": st.column_config.TextColumn(
                "Modelo", help="DCF+Mult para no financieras; DDM+P/BV para financieras"),
            "sector": st.column_config.TextColumn("Sector"),
            "current_price": st.column_config.NumberColumn("Precio Actual", format="$%.2f"),
            "dcf_price": st.column_config.NumberColumn(
                "Obj. Intrínseco", format="$%.2f", help="DCF, o DDM Gordon si es financiera"),
            "mult_price": st.column_config.NumberColumn(
                "Obj. Relativo", format="$%.2f", help="Múltiplos de pares, o P/BV aj. ROE si es financiera"),
            "upside_dcf": st.column_config.NumberColumn("Upside Intr.", format="%+.1f%%"),
            "upside_mult": st.column_config.NumberColumn("Upside Rel.", format="%+.1f%%"),
            "wacc": st.column_config.NumberColumn(
                "WACC/Ke", format="%.1f%%", help="WACC; Ke (costo del equity) si es financiera"),
            "peers_count": st.column_config.NumberColumn("Peers", format="%d", width="small"),
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Pausa F2 → Portfolio
# ─────────────────────────────────────────────────────────────────────────────
def render_f2_edit():
    cfg         = st.session_state.config
    fund_passed = st.session_state.fund_passed
    all_avail   = [t for t in st.session_state.df_prices.columns if t != cfg.benchmark]

    st.markdown('<div class="stage-header">✏️ Confirmar tickers para optimización</div>',
                unsafe_allow_html=True)
    edited = st.multiselect(
        f"Filtro 2 seleccionó {len(fund_passed)} tickers. Mínimo 3 requeridos:",
        options=sorted(set(all_avail)), default=sorted(set(fund_passed)),
        format_func=disp,
    )
    st.session_state.final_tickers = edited
    if len(edited) < 3:
        st.warning(f"Necesitas al menos 3 tickers (tienes {len(edited)}).")
    else:
        if st.button(f"▶ Optimizar portafolio con {len(edited)} activos",
                     type="primary", use_container_width=True):
            st.session_state.final_tickers = edited
            st.session_state.portfolios_calculated = False
            st.session_state.combined_portfolio = None
            st.session_state.stage = 5
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Etapa 4: Portafolio + Portafolio Unificado
# ─────────────────────────────────────────────────────────────────────────────
def run_portfolio():
    from orchestrator import portfolio_stage

    cfg     = st.session_state.config
    tickers = st.session_state.final_tickers
    prices  = st.session_state.df_prices

    st.markdown('<div class="stage-header">📐 Etapa 4 — Optimización: 9 Portafolios</div>',
                unsafe_allow_html=True)

    if not st.session_state.get("portfolios_calculated"):
        with st.spinner("Optimizando 9 portafolios (Markowitz / CAPM / Montecarlo)..."):
            df_opt, df_frontier, rf, df_rend = portfolio_stage.run(
                tickers, prices, cfg, interactive=False)
        st.session_state.df_opt      = df_opt
        st.session_state.df_frontier = df_frontier
        st.session_state.df_rend     = df_rend
        st.session_state.rf          = rf
        st.session_state.rf_label    = f"{rf*100:.3f}% (US 10Y Treasury ^TNX)"
        st.session_state.portfolios_calculated = True
    else:
        df_opt      = st.session_state.df_opt
        df_frontier = st.session_state.df_frontier
        rf          = st.session_state.rf
        df_rend     = st.session_state.df_rend

    # KPIs
    best_sharpe = float(df_opt["Sharpe"].max()) if not df_opt.empty and "Sharpe" in df_opt.columns else 0
    c1,c2,c3,c4 = st.columns(4)
    kpi(c1,"Portafolios", f"{len(df_opt)}/9", "Markowitz · CAPM · Montecarlo")
    kpi(c2,"Mejor Sharpe", f"{best_sharpe:.3f}", "max entre 9 portafolios")
    kpi(c3,"Rf usada", f"{rf*100:.2f}%", "US 10Y Treasury ^TNX")
    kpi(c4,"Activos", str(len(tickers)), "en el portafolio")

    # Tabs de portafolio
    portfolio_tickers = [t for t in tickers if t in df_opt.columns]
    tab_9, tab_frontier, tab_weights = st.tabs([
        "📊 9 Portafolios", "📈 Frontera Eficiente", "🗺️ Mapa de Pesos"
    ])

    with tab_9:
        _render_9_portfolios_table(df_opt, portfolio_tickers)
        st.plotly_chart(fig_portfolios_scatter(df_opt), use_container_width=True)

    with tab_frontier:
        st.plotly_chart(fig_frontier_with_portfolios(df_frontier, df_opt),
                        use_container_width=True)

    with tab_weights:
        f = fig_weights_heatmap(df_opt, portfolio_tickers)
        if f:
            st.plotly_chart(f, use_container_width=True)


def _render_9_portfolios_table(df_opt: pd.DataFrame, portfolio_tickers: list):
    rows = []
    for idx in df_opt.index:
        row = df_opt.loc[idx]
        m, o = idx if isinstance(idx, tuple) else (str(idx),"")
        r = {
            "Método": m, "Objetivo": o,
            "Retorno": pct(row.get("Retorno",0)),
            "Volatilidad": pct(row.get("Volatilidad",0)),
            "Sharpe": f"{float(row.get('Sharpe',0) or 0):.3f}",
            "Conv.": "✅" if row.get("Convergido", True) else "⚠️",
        }
        for t in portfolio_tickers:
            r[t] = f"{float(row.get(t,0) or 0)*100:.1f}%"
        rows.append(r)
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_combined_portfolio(df_opt, df_rend, tickers, rf):
    st.markdown('<div class="stage-header">🎯 Portafolio Unificado — Elige tu estrategia</div>',
                unsafe_allow_html=True)

    st.markdown("""
    <div class="info-box">
    El <b>Portafolio Unificado</b> combina los 9 portafolios en uno solo según la ponderación elegida.<br>
    <b>Min Volatilidad</b>: maximiza estabilidad (menor riesgo anual). &nbsp;
    <b>Max Retorno</b>: maximiza el retorno esperado. &nbsp;
    <b>Max Sharpe</b>: mejor relación riesgo/retorno. &nbsp;
    <b>Information Ratio</b>: mejor exceso de retorno vs benchmark por unidad de tracking error.
    </div>""", unsafe_allow_html=True)

    method_labels = {
        "sharpe":         "⭐ Max Sharpe (ponderado por Sharpe ratio)",
        "max_retorno":    "📈 Max Retorno (prioriza el portafolio de mayor retorno)",
        "min_volatilidad":"🛡️ Min Volatilidad (prioriza el de menor riesgo)",
        "ir":             "📊 Information Ratio (ponderado por IR vs benchmark)",
        "consenso":       "⚖️ Consenso (tú defines los % de cada objetivo)",
    }
    selected = st.radio(
        "Método de ponderación del portafolio unificado:",
        list(method_labels.keys()),
        format_func=lambda x: method_labels[x],
        horizontal=False,
    )

    objetivo_principal = "Max Sharpe"
    peso_principal = 0.6
    if selected == "consenso":
        st.markdown("**Define el peso de cada objetivo** (el resto se reparte equitativamente):")
        col1, col2 = st.columns(2)
        with col1:
            obj = st.selectbox("Objetivo principal", ["Max Sharpe","Max Retorno","Min Volatilidad"])
            objetivo_principal = obj
        with col2:
            peso_principal = st.slider("Peso (%)", 40, 80, 60, 5) / 100

    if st.button("🔢 Calcular Portafolio Unificado", type="primary", use_container_width=True):
        from orchestrator.adapters.portfolio_adapter import get_combined_portfolio

        cfg = st.session_state.config
        with st.spinner("Calculando portafolio unificado..."):
            combined = get_combined_portfolio(
                df_opt=df_opt,
                tickers=tickers,
                method=selected,
                df_rend=df_rend,
                benchmark=cfg.benchmark,
                objetivo_principal=objetivo_principal,
                peso_principal=peso_principal,
            )
        if combined:
            combined["method_label"] = method_labels[selected]
        st.session_state.combined_portfolio = combined

    combined = st.session_state.get("combined_portfolio")
    if combined:
        _show_combined_results(combined, combined.get("method_label", method_labels.get(selected, "seleccionado")))
        st.markdown("---")
        if st.button("📄 Continuar → Generar Investing Memo (PDF/HTML)",
                     type="primary", use_container_width=True):
            st.session_state.stage = 6
            st.rerun()


def _show_combined_results(combined: dict, method_label: str):
    """Muestra resultados del portafolio unificado."""
    st.success(f"✅ Portafolio unificado calculado: **{method_label}**")

    ret  = float(combined.get("retorno", 0) or 0)
    vol  = float(combined.get("volatilidad", 0) or 0)
    shr  = float(combined.get("sharpe", 0) or 0)

    c1,c2,c3 = st.columns(3)
    kpi(c1,"Retorno Esperado", pct(ret), "anual")
    kpi(c2,"Volatilidad", pct(vol), "anual")
    kpi(c3,"Sharpe Ratio", f"{shr:.3f}", "")

    # Pesos
    pesos = combined.get("pesos", {})
    if pesos:
        col_pie, col_table = st.columns([1.2, 0.8])
        with col_pie:
            st.plotly_chart(fig_pie_weights(pesos, "Distribución del Portafolio Unificado"),
                            use_container_width=True)
        with col_table:
            st.markdown("**Pesos por activo:**")
            peso_rows = [
                {"Ticker": t, "Peso (%)": f"{float(p or 0)*100:.2f}%",
                 "Peso decimal": f"{float(p or 0):.4f}"}
                for t, p in sorted(pesos.items(), key=lambda x: -(x[1] or 0))
                if float(p or 0) > 0.0001
            ]
            st.dataframe(pd.DataFrame(peso_rows), use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# Etapa 5: Reporte PDF/HTML
# ─────────────────────────────────────────────────────────────────────────────
def run_report():
    from orchestrator import report_builder

    cfg   = st.session_state.config
    combined = st.session_state.get("combined_portfolio")

    st.markdown('<div class="stage-header">📄 Etapa 5 — Investing Memo (HTML / PDF)</div>',
                unsafe_allow_html=True)

    with st.spinner("Generando investing memo..."):
        output_path = report_builder.build(
            df_stat=st.session_state.df_stat,
            df_fund=st.session_state.df_fund,
            df_opt=st.session_state.df_opt,
            df_frontier=st.session_state.df_frontier,
            df_prices=st.session_state.df_prices,
            final_tickers=st.session_state.final_tickers,
            rf=st.session_state.rf,
            rf_label=st.session_state.rf_label,
            config=cfg,
            skipped=st.session_state.skipped,
            combined_portfolio=combined,
        )
    st.session_state.output_path = output_path

    html_path = Path(output_path)
    if html_path.exists():
        content = html_path.read_bytes()
        ext = html_path.suffix
        mime = "application/pdf" if ext == ".pdf" else "text/html"
        label = "📥 Descargar PDF" if ext == ".pdf" else "📥 Descargar HTML"
        st.success(f"✅ Memo generado: `{html_path.name}`")
        st.download_button(label=label, data=content, file_name=html_path.name,
                           mime=mime, use_container_width=True, type="primary")
        if ext == ".html":
            st.info("💡 Abre el HTML en Chrome → Ctrl+P → 'Guardar como PDF' "
                    "para obtener el PDF sin instalar GTK.")
    else:
        st.error("No se pudo generar el archivo.")


# ─────────────────────────────────────────────────────────────────────────────
# Re-display colapsados
# ─────────────────────────────────────────────────────────────────────────────