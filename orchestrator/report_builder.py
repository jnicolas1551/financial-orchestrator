"""
Etapa 5 — Generación del PDF Investing Memo.
Usa Jinja2 para renderizar el template HTML y WeasyPrint para convertirlo a PDF.
Las gráficas se embeben como imágenes base64.
"""
from __future__ import annotations

import base64
import io
import json
import logging
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # backend sin interfaz gráfica
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import pandas as pd

from .config import OrchestratorConfig

logger = logging.getLogger("orchestrator.report_builder")

_TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "investing_memo.html"


# ---------------------------------------------------------------------------
# Helpers de gráficas
# ---------------------------------------------------------------------------

def _fig_to_b64(fig: plt.Figure) -> str:
    """Convierte una figura matplotlib a string base64 PNG."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def _make_correlation_chart(df_stat: pd.DataFrame, df_prices: pd.DataFrame,
                             final_tickers: list[str], benchmark: str) -> str | None:
    """Genera la gráfica de barras de correlación vs benchmark."""
    try:
        # Calcular correlaciones
        corrs = {}
        for tk in final_tickers:
            if tk in df_prices.columns and benchmark in df_prices.columns:
                corr = df_prices[tk].corr(df_prices[benchmark])
                corrs[tk] = round(corr, 3)

        if not corrs:
            return None

        tickers_sorted = sorted(corrs, key=lambda x: corrs[x], reverse=True)
        values = [corrs[tk] for tk in tickers_sorted]
        colors = ["#2563eb" if v >= 0 else "#dc2626" for v in values]

        fig, ax = plt.subplots(figsize=(max(8, len(tickers_sorted) * 0.6), 4))
        bars = ax.bar(tickers_sorted, values, color=colors, alpha=0.85, edgecolor="white")
        ax.axhline(0, color="#1a1a2e", linewidth=0.8)
        ax.set_ylabel("Correlación vs " + benchmark)
        ax.set_title(f"Correlación vs {benchmark}", fontsize=11, fontweight="bold")
        ax.set_ylim(-1.1, 1.1)
        ax.yaxis.set_major_formatter(mtick.FormatStrFormatter("%.2f"))
        ax.tick_params(axis="x", rotation=45)
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + (0.03 if val >= 0 else -0.06),
                    f"{val:.2f}", ha="center", va="bottom", fontsize=7)
        fig.tight_layout()
        return _fig_to_b64(fig)
    except Exception as e:
        logger.warning(f"No se pudo generar gráfica de correlación: {e}")
        return None


def _make_frontier_chart(df_frontier: pd.DataFrame, df_opt: pd.DataFrame) -> str | None:
    """Genera la gráfica de la frontera eficiente con los 9 portafolios marcados."""
    try:
        fig, ax = plt.subplots(figsize=(8, 5))

        # Línea de la frontera
        if not df_frontier.empty and all(
            c in df_frontier.columns for c in ["Volatilidad", "Retorno"]
        ):
            ax.plot(
                df_frontier["Volatilidad"] * 100,
                df_frontier["Retorno"] * 100,
                "b-", linewidth=2, alpha=0.7, label="Frontera Eficiente"
            )

        # Los 9 portafolios
        if not df_opt.empty:
            markers = {"Max Sharpe": "★", "Min Volatilidad": "▼", "Max Retorno": "▲"}
            colors_m = {"Markowitz": "#2563eb", "Capm": "#059669", "Montecarlo": "#d97706"}
            for idx in df_opt.index:
                row = df_opt.loc[idx]
                method, obj = idx if isinstance(idx, tuple) else (str(idx), "")
                vol = row.get("Volatilidad", 0) * 100
                ret = row.get("Retorno", 0) * 100
                color = colors_m.get(method, "#6b7280")
                marker = "o"
                ax.scatter(vol, ret, color=color, marker=marker, s=80, zorder=5, alpha=0.9)
                ax.annotate(f"{obj[:3]}", (vol, ret), textcoords="offset points",
                            xytext=(5, 3), fontsize=7, color=color)

        ax.set_xlabel("Volatilidad (%)")
        ax.set_ylabel("Retorno Esperado (%)")
        ax.set_title("Frontera Eficiente — 9 Portafolios Optimizados",
                     fontsize=11, fontweight="bold")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        return _fig_to_b64(fig)
    except Exception as e:
        logger.warning(f"No se pudo generar gráfica de frontera: {e}")
        return None


# ---------------------------------------------------------------------------
# Construcción del contexto Jinja2
# ---------------------------------------------------------------------------

def _build_context(
    df_stat: pd.DataFrame,
    df_fund: pd.DataFrame,
    df_opt: pd.DataFrame,
    df_frontier: pd.DataFrame,
    df_prices: pd.DataFrame,
    final_tickers: list[str],
    rf: float,
    rf_label: str,
    config: OrchestratorConfig,
    skipped: list[str],
    combined_portfolio: dict | None = None,
) -> dict:
    """Arma el diccionario de contexto para el template Jinja2."""
    run_date = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Tabla de activos (Sección 1)
    assets_table = []
    for tk in final_tickers:
        market = "BVC Colombia" if tk.upper().endswith(".CL") else "S&P 500"
        stat_row = df_stat.loc[tk] if tk in df_stat.index else {}
        fund_row = df_fund.loc[tk] if tk in df_fund.index else {}
        assets_table.append({
            "ticker":        tk,
            "market":        market,
            "score":         float(stat_row.get("score", 0) or 0),
            "signal":        str(fund_row.get("signal", "N/A")),
            "current_price": fund_row.get("current_price"),
            "upside_dcf":    fund_row.get("upside_dcf"),
            "upside_mult":   fund_row.get("upside_mult"),
            "wacc":          fund_row.get("wacc"),
            "valuation_model": str(fund_row.get("valuation_model") or "DCF+Mult"),
            "sector":        fund_row.get("sector"),
        })

    # Detalles por activo (Sección 2)
    asset_details = []
    for row in assets_table:
        tk = row["ticker"]
        fund_row = df_fund.loc[tk] if tk in df_fund.index else {}
        asset_details.append({
            **row,
            "dcf_price":   fund_row.get("dcf_price"),
            "mult_price":  fund_row.get("mult_price"),
            "peers_count": int(fund_row.get("peers_count", 0) or 0),
        })

    # Filas de portafolio (Sección 4)
    portfolio_tickers = list(final_tickers)
    portfolio_rows = []
    if not df_opt.empty:
        for idx in df_opt.index:
            row = df_opt.loc[idx]
            method, obj = idx if isinstance(idx, tuple) else (str(idx), "")
            weights = {}
            for tk in portfolio_tickers:
                val = row.get(tk, 0)
                weights[tk] = float(val) if pd.notna(val) else 0.0
            portfolio_rows.append({
                "method":     str(method),
                "objective":  str(obj),
                "weights":    weights,
                "retorno":    float(row.get("Retorno", 0) or 0),
                "volatilidad": float(row.get("Volatilidad", 0) or 0),
                "sharpe":     float(row.get("Sharpe", 0) or 0),
            })

    # Tabla técnica (indicadores estadísticos + señales técnicas)
    def _sig(s):
        if not isinstance(s, str) or s == "N/A":
            return "Neutro"
        su = s.upper()
        if "COMPRA" in su or "BUY" in su:
            return "Compra"
        if "VENTA" in su or "SELL" in su:
            return "Venta"
        return "Neutro"

    stat_table = []
    for tk in final_tickers:
        if tk not in df_stat.index:
            continue
        row = df_stat.loc[tk]
        stat_table.append({
            "ticker":      tk,
            "score":       float(row.get("score", 0) or 0),
            "alpha":       row.get("alpha"),
            "beta":        row.get("beta"),
            "r2":          row.get("r2"),
            "corr":        row.get("corr"),
            "pct_rank":    row.get("pct_rank"),
            "rsi_value":   row.get("rsi_value"),
            "macd_hist":   row.get("macd_hist"),
            "signal_mm":   _sig(str(row.get("signal_mm", ""))),
            "signal_macd": _sig(str(row.get("signal_macd", ""))),
            "signal_rsi":  _sig(str(row.get("signal_rsi", ""))),
            "signal_fib":  _sig(str(row.get("signal_fib", ""))),
        })

    # Portafolio unificado
    combined_ctx = None
    if combined_portfolio:
        pesos = combined_portfolio.get("pesos", {})
        combined_ctx = {
            "method_label": combined_portfolio.get("method_label", "Seleccionado"),
            "retorno":      float(combined_portfolio.get("retorno", 0) or 0),
            "volatilidad":  float(combined_portfolio.get("volatilidad", 0) or 0),
            "sharpe":       float(combined_portfolio.get("sharpe", 0) or 0),
            "pesos_sorted": sorted(
                [(t, float(p or 0)) for t, p in pesos.items() if float(p or 0) > 0.0001],
                key=lambda x: -x[1]
            ),
        }

    # Mercados presentes
    markets = set()
    for tk in final_tickers:
        markets.add("BVC Colombia" if tk.upper().endswith(".CL") else "S&P 500")
    markets_label = " + ".join(sorted(markets))

    return {
        "run_date":          run_date,
        "total_input":       len(config.tickers),
        "total_downloaded":  len(df_prices.columns),
        "total_f1":          int(df_stat["passes_filter1"].sum()) if "passes_filter1" in df_stat.columns else 0,
        "total_f2":          int(df_fund["passes_filter2"].sum()) if "passes_filter2" in df_fund.columns else 0,
        "total_final":       len(final_tickers),
        "markets_label":     markets_label,
        "benchmark":         config.benchmark,
        "start_date":        config.start_date,
        "filter1_threshold": config.filter1_threshold,
        "w_reg":             config.w_reg,
        "w_pct":             config.w_pct,
        "w_tec":             config.w_tec,
        "filter2_mode":      config.filter2_mode,
        "rf_label":          rf_label,
        "growth_explicit":   config.growth_explicit,
        "terminal_growth":   config.terminal_growth,
        "explicit_years":    config.explicit_years,
        "has_financials":    any(a["valuation_model"] == "DDM+P/BV" for a in assets_table),
        "assets_table":       assets_table,
        "asset_details":      asset_details,
        "stat_table":         stat_table,
        "portfolio_tickers":  portfolio_tickers,
        "portfolio_rows":     portfolio_rows,
        "combined_portfolio": combined_ctx,
    }


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def build(
    df_stat: pd.DataFrame,
    df_fund: pd.DataFrame,
    df_opt: pd.DataFrame,
    df_frontier: pd.DataFrame,
    df_prices: pd.DataFrame,
    final_tickers: list[str],
    rf: float,
    rf_label: str,
    config: OrchestratorConfig,
    skipped: list[str] | None = None,
    combined_portfolio: dict | None = None,
) -> str:
    """
    Genera el PDF del investing memo.

    Returns:
        Ruta al PDF generado en output/
    """
    print(f"\n{'='*60}")
    print(f"  Etapa 5 — Generación del PDF Investing Memo")
    print(f"{'='*60}")

    from jinja2 import Environment, FileSystemLoader

    # 1. Contexto Jinja2
    context = _build_context(
        df_stat, df_fund, df_opt, df_frontier,
        df_prices, final_tickers, rf, rf_label, config, skipped or [],
        combined_portfolio=combined_portfolio,
    )

    # 2. Gráficas
    print("  Generando gráficas...")
    context["charts"] = {
        "correlation": _make_correlation_chart(
            df_stat, df_prices, final_tickers, config.benchmark
        ),
        "frontier": _make_frontier_chart(df_frontier, df_opt),
    }

    # 3. Renderizar HTML
    print("  Renderizando template HTML...")
    template_dir = str(_TEMPLATE_PATH.parent)
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template(_TEMPLATE_PATH.name)
    html_content = template.render(**context)

    # 4. Fallback JSON si WeasyPrint no está disponible
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_name = config.pdf_filename or f"investing_memo_{timestamp}.pdf"
    pdf_path = Path(config.output_dir) / pdf_name

    try:
        print("  Convirtiendo a PDF (WeasyPrint)...")
        from weasyprint import HTML
        HTML(string=html_content, base_url=str(_TEMPLATE_PATH.parent)).write_pdf(str(pdf_path))
        print(f"\n  PDF generado: {pdf_path}")
    except Exception as e:
        logger.error(f"WeasyPrint no disponible: {e}")
        # Guardar HTML como fallback
        html_path = pdf_path.with_suffix(".html")
        html_path.write_text(html_content, encoding="utf-8")
        # Guardar JSON de análisis como fallback de datos
        json_path = pdf_path.with_suffix(".json")
        safe_context = {k: v for k, v in context.items() if k != "charts"}