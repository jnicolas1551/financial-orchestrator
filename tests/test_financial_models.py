"""
Tests unitarios de financial_models — funciones puras, sin red.
Ejecutar: py -m pytest tests/test_financial_models.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator.adapters import financial_models as fm


# ---------------------------------------------------------------------------
# Detección de sector
# ---------------------------------------------------------------------------

def test_is_financial_detecta_bancos():
    assert fm.is_financial("Financial Services", "Banks - Diversified")
    assert fm.is_financial("Financial Services", None)
    assert fm.is_financial(None, "Banks - Regional")
    assert fm.is_financial(None, "Insurance - Life")


def test_is_financial_no_detecta_otros_sectores():
    assert not fm.is_financial("Technology", "Consumer Electronics")
    assert not fm.is_financial("Energy", "Oil & Gas Integrated")
    assert not fm.is_financial(None, None)


# ---------------------------------------------------------------------------
# DDM
# ---------------------------------------------------------------------------

def _info_banco(**overrides):
    """Perfil tipo JPM aproximado."""
    base = {
        "beta": 1.1,
        "dividendRate": 5.0,
        "trailingAnnualDividendRate": 4.6,
        "returnOnEquity": 0.15,
        "payoutRatio": 0.30,
    }
    base.update(overrides)
    return base


def test_ddm_precio_positivo_y_formula():
    r = fm.run_ddm(_info_banco(), rf=0.045, erp=0.055)
    # Ke = 0.045 + 1.1*0.055 = 0.1055
    assert abs(r["ke"] - 0.1055) < 1e-9
    # g sostenible = 0.15*0.70 = 0.105 → capado a Ke - 0.015 = 0.0905
    assert abs(r["g"] - 0.0905) < 1e-9
    # V = 5.0 / (0.1055 - 0.0905) = 333.33
    assert abs(r["price"] - 5.0 / 0.015) < 0.01


def test_ddm_sin_dividendo_devuelve_none():
    r = fm.run_ddm(_info_banco(dividendRate=None, trailingAnnualDividendRate=None),
                   rf=0.045)
    assert r["price"] is None
    assert "no aplicable" in r["note"]


def test_ddm_usa_trailing_si_no_hay_forward():
    r = fm.run_ddm(_info_banco(dividendRate=None), rf=0.045, erp=0.055)
    # D1 = 4.6 * (1 + g)
    expected_d1 = 4.6 * (1 + r["g"])
    assert abs(r["d1"] - expected_d1) < 1e-9
    assert r["price"] > 0


def test_ddm_g_nunca_supera_ke():
    # ROE altísimo con payout bajo → g sostenible enorme, debe caparse
    r = fm.run_ddm(_info_banco(returnOnEquity=0.90, payoutRatio=0.05), rf=0.045)
    assert r["g"] < r["ke"]
    assert r["price"] is not None and r["price"] > 0


# ---------------------------------------------------------------------------
# P/BV
# ---------------------------------------------------------------------------

def _peers(pbs_roes):
    return [{"priceToBook": pb, "returnOnEquity": roe} for pb, roe in pbs_roes]


def test_pbv_mediana_y_ajuste_roe():
    info = {"bookValue": 100.0, "returnOnEquity": 0.20}
    peers = _peers([(1.0, 0.10), (1.5, 0.10), (2.0, 0.10)])
    r = fm.run_pbv(info, peers)
    # mediana P/B = 1.5; ajuste = 0.20/0.10 = 2.0 → capado a 1.5
    assert r["median_pb"] == 1.5
    assert r["roe_adj"] == 1.5
    assert abs(r["price"] - 1.5 * 1.5 * 100.0) < 1e-9


def test_pbv_sin_book_value():
    r = fm.run_pbv({"bookValue": None}, _peers([(1.0, 0.1)]))
    assert r["price"] is None


def test_pbv_sin_peers_validos():
    r = fm.run_pbv({"bookValue": 50.0}, _peers([(None, 0.1), (0, 0.1)]))
    assert r["price"] is None


def test_pbv_ajuste_capado_a_la_baja():
    info = {"bookValue": 100.0, "returnOnEquity": 0.02}
    peers = _peers([(1.0, 0.20)])
    r = fm.run_pbv(info, peers)
    # 0.02/0.20 = 0.1 → capado a 0.5
    assert r["roe_adj"] == 0.5
