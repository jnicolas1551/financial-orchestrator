"""
Adaptador para ANALISIS_INSTITUCIONAL/modules/.
Inyecta la ruta del módulo en sys.path y expone una función
analyze_ticker() lista para ser llamada desde ProcessPoolExecutor.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Localización del módulo ANALISIS_INSTITUCIONAL
# ---------------------------------------------------------------------------

def _find_ai_path() -> Path:
    """
    Resuelve la ruta a ANALISIS_INSTITUCIONAL/ en este orden:
    1. Variable de entorno ANALISIS_INSTITUCIONAL_PATH
    2. Directorio hermano ../ANALISIS_INSTITUCIONAL/
    """
    env_path = os.environ.get("ANALISIS_INSTITUCIONAL_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p

    here = Path(__file__).resolve()
    sibling = here.parents[2].parent / "ANALISIS_INSTITUCIONAL"
    if sibling.exists():
        return sibling

    raise FileNotFoundError(
        "No se encontró ANALISIS_INSTITUCIONAL/. "
        "Define ANALISIS_INSTITUCIONAL_PATH con la ruta absoluta."
    )


def _ensure_path() -> Path:
    """Inserta el directorio en sys.path si no está ya."""
    ai_path = _find_ai_path()
    str_path = str(ai_path)
    if str_path not in sys.path:
        sys.path.insert(0, str_path)
    return ai_path


# ---------------------------------------------------------------------------
# Imports lazy de los módulos
# ---------------------------------------------------------------------------

def _import_modules():
    """Importa y devuelve los módulos necesarios."""
    _ensure_path()
    from modules import data_fetcher, dcf_model, multiples_model, country_data
    return data_fetcher, dcf_model, multiples_model, country_data


# ---------------------------------------------------------------------------
# analyze_ticker — función de alto nivel para el orquestador
# ---------------------------------------------------------------------------

def analyze_ticker(ticker: str, config_dict: dict) -> dict:
    """
    Ejecuta el análisis fundamental completo para un ticker.
    Devuelve un dict con los resultados (serializable para ProcessPoolExecutor).

    Parámetros (en config_dict):
        growth_explicit, terminal_growth, explicit_years,
        multiples_weights (dict, opcional)
    """
    data_fetcher, dcf_model, multiples_model, country_data = _import_modules()

    result = {
        "ticker": ticker,
        "dcf_price": None,
        "mult_price": None,
        "current_price": None,
        "upside_dcf": None,
        "upside_mult": None,
        "signal": "error",
        "wacc": None,
        "peers_count": 0,
        "error": None,
    }

    try:
        # 1. Descargar datos de la empresa
        raw = data_fetcher.fetch_company_data(ticker)
        metrics = raw.get("metrics", {})
        fcf_history = raw.get("fcf_history", [])
        country_params = raw.get("country", {})
        auto_peers = raw.get("auto_peers", [])

        if not metrics:
            result["error"] = "No se obtuvieron métricas"
            return result

        current_price = metrics.get("current_price") or metrics.get("price")
        result["current_price"] = current_price

        # Parámetros DCF
        growth_explicit = config_dict.get("growth_explicit", 0.08)
        terminal_growth = config_dict.get("terminal_growth", 0.025)
        explicit_years = config_dict.get("explicit_years", 5)

        # 2. WACC — detectar Colombia por sufijo .CL
        if ticker.upper().endswith(".CL"):
            country_params = country_data.get_country_params("Colombia")

        wacc_data = dcf_model.calculate_wacc(metrics, country_params)
        result["wacc"] = wacc_data.get("wacc")

        # 3. FCF base
        fcf_data = dcf_model.get_fcf_base(metrics, fcf_history)

        # 4. DCF
        dcf_result = dcf_model.run_dcf(
            metrics, fcf_data, wacc_data,
            growth_explicit=growth_explicit,
            terminal_growth=terminal_growth,
            explicit_years=explicit_years,
        )
        dcf_price = dcf_result.get("price_per_share")
        result["dcf_price"] = dcf_price

        # 5. Múltiplos de pares
        peers = data_fetcher.fetch_peers_data(auto_peers[:6]) if auto_peers else []
        result["peers_count"] = len(peers)

        weights = config_dict.get("multiples_weights", {
            "ev_ebitda": 40, "pe_ratio": 30, "ebitda_margin": 30
        })

        mult_result = multiples_model.run_multiples_analysis(metrics, peers, weights)
        mult_price = mult_result.get("combined_price")
        result["mult_price"] = mult_price

        # 6. Señal: promedio de upsides DCF y múltiplos vs precio actual
        if current_price and current_price > 0:
            upsides = []
            if dcf_price and dcf_price > 0:
                result["upside_dcf"] = (dcf_price / current_price) - 1
                upsides.append(result["upside_dcf"])
            if mult_price and mult_price > 0:
                result["upside_mult"] = (mult_price / current_price) - 1
                upsides.append(result["upside_mult"])

            if upsides:
                avg_upside = sum(upsides) / len(upsides)
                if avg_upside > 0.05:
                    result["signal"] = "buy"
                elif avg_upside >= -0.05:
                    result["signal"] = "hold"
                else:
                    result["signal"] = "sell"
            else:
                result["signal"] = "hold"
        else:
            result["signal"] = "hold"

    except Exception as e:
        result["error"] = str(e)
        result["signal"] = "error"

    return result
