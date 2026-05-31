"""
Configuración central del orquestador financiero.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class OrchestratorConfig:
    # --- Universo de activos ---
    tickers: list[str] = field(default_factory=list)
    benchmark: str = "^GSPC"
    start_date: str = ""  # "YYYY-MM-DD"; si vacío se calcula 3 años atrás

    # --- Filtro 1 estadístico (solo BUY) ---
    w_reg: float = 0.40            # peso regresión
    w_pct: float = 0.30            # peso percentil
    w_tec: float = 0.30            # peso técnico (MM/MACD/RSI/Fibo)
    filter1_threshold: float = 0.50

    # --- Filtro 2 fundamental ---
    filter2_mode: str = "buy_only"  # "buy_only" | "buy_hold"

    # --- Cache ---
    cache_dir: str = "cache/"
    cache_ttl_hours: int = 24
    fund_cache_ttl_hours: int = 168  # 7 días para datos fundamentales

    # --- Paralelismo ---
    max_workers_stat: Optional[int] = None   # default: cpu_count()
    max_workers_fund: Optional[int] = None   # default: cpu_count() // 2

    # --- Parámetros fundamentales ---
    growth_explicit: float = 0.08
    terminal_growth: float = 0.025
    explicit_years: int = 5

    # --- Tasa libre de riesgo ---
    rf_default: float = 0.045    # fallback si ^TNX no disponible
    rf_override: Optional[float] = None  # override manual vía CLI

    # --- Portafolio ---
    frontier_points: int = 100

    # --- Output ---
    output_dir: str = "output/"
    pdf_filename: Optional[str] = None  # auto-generado si None

    def __post_init__(self) -> None:
        # Calcular start_date por defecto: 3 años atrás
        if not self.start_date:
            from datetime import date, timedelta
            self.start_date = (date.today() - timedelta(days=3 * 365)).strftime("%Y-%m-%d")

        # Validar pesos del filtro 1
        total_w = self.w_reg + self.w_pct + self.w_tec
        if abs(total_w - 1.0) > 0.01:
            raise ValueError(
                f"Los pesos del Filtro 1 deben sumar 1.0 (actual: {total_w:.3f}). "
                f"w_reg={self.w_reg}, w_pct={self.w_pct}, w_tec={self.w_tec}"
            )
        for name, val in [("w_reg", self.w_reg), ("w_pct", self.w_pct), ("w_tec", self.w_tec)]:
            if not 0 <= val <= 1:
                raise ValueError(f"{name} debe estar en [0, 1] (actual: {val})")

        if not 0 < self.filter1_threshold <= 1:
            raise ValueError(f"filter1_threshold debe estar en (0, 1] (actual: {self.filter1_threshold})")

        if self.filter2_mode not in ("buy_only", "buy_hold"):
            raise ValueError(f"filter2_mode debe ser 'buy_only' o 'buy_hold' (actual: {self.filter2_mode})")

        # Resolver workers por defecto
        cpu = os.cpu_count() or 4
        if self.max_workers_stat is None:
            self.max_workers_stat = cpu
        if self.max_workers_fund is None:
            self.max_workers_fund = max(1, cpu // 2)

        # Crear directorios si no existen
        Path(self.cache_dir).mkdir(parents=True, exist_ok=True)
        Path(self.cache_dir, "prices").mkdir(exist_ok=True)
        Path(self.cache_dir, "meta").mkdir(exist_ok=True)
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def load_from_yaml(cls, path: str) -> "OrchestratorConfig":
        """Carga configuración desde un archivo YAML."""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        f1 = data.get("filter1", {})
        fund = data.get("fundamental", {})
        port = data.get("portfolio", {})

        return cls(
            tickers=data.get("tickers", []),
            benchmark=data.get("benchmark", "^GSPC"),
            start_date=data.get("start_date", ""),
            w_reg=f1.get("w_reg", 0.40),
            w_pct=f1.get("w_pct", 0.30),
            w_tec=f1.get("w_tec", 0.30),
            filter1_threshold=f1.get("threshold", 0.50),
            filter2_mode=data.get("filter2_mode", "buy_only"),
            cache_dir=data.get("cache_dir", "cache/"),
            cache_ttl_hours=data.get("cache_ttl_hours", 24),
            fund_cache_ttl_hours=data.get("fund_cache_ttl_hours", 168),
            growth_explicit=fund.get("growth_explicit", 0.08),
            terminal_growth=fund.get("terminal_growth", 0.025),
            explicit_years=fund.get("explicit_years", 5),
            rf_default=data.get("rf_default", 0.045),
            rf_override=data.get("rf", None),
            frontier_points=port.get("frontier_points", 100),
            output_dir=data.get("output_dir", "output/"),
        )

    @classmethod
    def load_from_cli(cls, args) -> "OrchestratorConfig":
        """Construye configuración desde argumentos de argparse."""
        base: dict = {}

        # Cargar config YAML base si se proporcionó
        if getattr(args, "config", None) and Path(args.config).exists():
            with open(args.config, "r", encoding="utf-8") as f:
                base = yaml.safe_load(f) or {}

        f1 = base.get("filter1", {})
        fund = base.get("fundamental", {})
        port = base.get("portfolio", {})

        def _get(attr, yaml_val, default):
            cli_val = getattr(args, attr, None)
            return cli_val if cli_val is not None else (yaml_val if yaml_val is not None else default)

        return cls(
            tickers=getattr(args, "tickers", None) or base.get("tickers", []),
            benchmark=_get("benchmark", base.get("benchmark"), "^GSPC"),
            start_date=_get("start_date", base.get("start_date"), ""),
            w_reg=_get("w_reg", f1.get("w_reg"), 0.40),
            w_pct=_get("w_pct", f1.get("w_pct"), 0.30),
            w_tec=_get("w_tec", f1.get("w_tec"), 0.30),
            filter1_threshold=_get("filter1_threshold", f1.get("threshold"), 0.50),
            filter2_mode=_get("filter2_mode", base.get("filter2_mode"), "buy_only"),
            cache_dir=_get("cache_dir", base.get("cache_dir"), "cache/"),
            cache_ttl_hours=_get("cache_ttl", base.get("cache_ttl_hours"), 24),
            growth_explicit=fund.get("growth_explicit", 0.08),
            terminal_growth=fund.get("terminal_growth", 0.025),
            explicit_years=fund.get("explicit_years", 5),
            rf_default=base.get("rf_default", 0.045),
            rf_override=_get("rf", base.get("rf"), None),
            frontier_points=port.get("frontier_points", 100),
            output_dir=_get("output_dir", base.get("output_dir"), "output/"),
        )
