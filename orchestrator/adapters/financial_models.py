"""
Modelos de valoración para el sector financiero (bancos, aseguradoras, etc.).

Motivación (decisión cerrada #2): DCF-FCFF es estructuralmente engañoso en
financieras porque la deuda ES el producto, no financiamiento. Modelos correctos:
  - DDM (Gordon):  V = D1 / (Ke - g)          → precio intrínseco
  - P/BV ajustado por ROE vs peers            → precio relativo

Autocontenido en el orchestrator (no depende de ANALISIS_INSTITUCIONAL).
Funciones puras reciben dicts → testeables sin red.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Detección de sector financiero
# ---------------------------------------------------------------------------

_FINANCIAL_KEYWORDS = ("financial", "bank", "insurance", "capital markets")


def is_financial(sector: str | None, industry: str | None = None) -> bool:
    """True si el sector/industria corresponde a una financiera."""
    text = f"{sector or ''} {industry or ''}".lower()
    return any(kw in text for kw in _FINANCIAL_KEYWORDS)


def get_sector_info(ticker: str, metrics: dict | None = None) -> dict:
    """
    Resuelve sector/industria. Primero busca en metrics (ya descargados);
    si no están, hace un fetch puntual a yfinance.
    """
    metrics = metrics or {}
    sector = metrics.get("sector")
    industry = metrics.get("industry")

    if not sector:
        import yfinance as yf
        try:
            info = yf.Ticker(ticker).info or {}
            sector = info.get("sector")
            industry = industry or info.get("industry")
        except Exception:
            pass

    return {"sector": sector, "industry": industry}


# ---------------------------------------------------------------------------
# DDM — Gordon Growth (precio intrínseco)
# ---------------------------------------------------------------------------

def run_ddm(
    info: dict,
    rf: float,
    erp: float = 0.055,
    terminal_growth: float = 0.025,
    min_spread: float = 0.015,
) -> dict:
    """
    V = D1 / (Ke - g)

    info (dict estilo yfinance.info):
        beta, dividendRate (forward anual), trailingAnnualDividendRate,
        returnOnEquity, payoutRatio
    Ke por CAPM: rf + beta * ERP.
    g sostenible: ROE * (1 - payout), capado a Ke - min_spread (Gordon exige g < Ke).
    """
    beta = info.get("beta") or 1.0
    ke = rf + beta * erp

    roe = info.get("returnOnEquity")
    payout = info.get("payoutRatio")
    if roe is not None and payout is not None and 0 <= payout <= 1:
        g = max(0.0, roe * (1 - payout))
    else:
        g = terminal_growth
    g = min(g, ke - min_spread)

    d_fwd = info.get("dividendRate")            # dividendo anual forward
    d_trail = info.get("trailingAnnualDividendRate")
    if d_fwd and d_fwd > 0:
        d1 = d_fwd
    elif d_trail and d_trail > 0:
        d1 = d_trail * (1 + g)
    else:
        return {"price": None, "ke": ke, "g": g,
                "note": "Sin dividendo → DDM no aplicable"}

    if ke <= g:
        return {"price": None, "ke": ke, "g": g, "note": "Ke <= g"}

    return {"price": d1 / (ke - g), "ke": ke, "g": g, "d1": d1, "note": None}


# ---------------------------------------------------------------------------
# P/BV ajustado por ROE (precio relativo)
# ---------------------------------------------------------------------------

def run_pbv(info: dict, peers_info: list[dict]) -> dict:
    """
    Precio objetivo = P/B mediano de peers × ajuste ROE × book value per share.
    Ajuste ROE = ROE empresa / ROE mediano peers, capado a [0.5, 1.5]
    (una financiera más rentable que sus pares merece prima de P/B, y viceversa).

    info: bookValue (por acción en yfinance), returnOnEquity
    peers_info: lista de dicts con priceToBook y returnOnEquity
    """
    bvps = info.get("bookValue")
    if not bvps or bvps <= 0:
        return {"price": None, "peers_used": 0, "note": "Sin book value"}

    peer_pbs = [p.get("priceToBook") for p in peers_info
                if p.get("priceToBook") and p["priceToBook"] > 0]
    if not peer_pbs:
        return {"price": None, "peers_used": 0, "note": "Sin P/B de peers"}

    peer_pbs.sort()
    n = len(peer_pbs)
    median_pb = (peer_pbs[n // 2] if n % 2 else
                 (peer_pbs[n // 2 - 1] + peer_pbs[n // 2]) / 2)

    # Ajuste por ROE relativo
    adj = 1.0
    roe = info.get("returnOnEquity")
    peer_roes = [p.get("returnOnEquity") for p in peers_info
                 if p.get("returnOnEquity") and p["returnOnEquity"] > 0]
    if roe and roe > 0 and peer_roes:
        peer_roes.sort()
        m = len(peer_roes)
        median_roe = (peer_roes[m // 2] if m % 2 else
                      (peer_roes[m // 2 - 1] + peer_roes[m // 2]) / 2)
        if median_roe > 0:
            adj = max(0.5, min(1.5, roe / median_roe))

    return {"price": median_pb * adj * bvps, "peers_used": n,
            "median_pb": median_pb, "roe_adj": adj, "note": None}


# ---------------------------------------------------------------------------
# Orquestación: análisis completo de una financiera
# ---------------------------------------------------------------------------

def analyze_financial(ticker: str, config_dict: dict) -> dict:
    """
    Análisis completo para una financiera: DDM + P/BV vía yfinance.
    Devuelve dict con las MISMAS claves que el flujo DCF para mantener
    el contrato FUND_RESULT_SCHEMA:
        dcf_price   ← precio DDM (intrínseco)
        mult_price  ← precio P/BV (relativo)
        wacc        ← Ke (costo del equity; no hay WACC en este modelo)
    """
    import yfinance as yf

    rf = config_dict.get("rf", 0.045)
    erp = config_dict.get("erp", 0.055)
    terminal_growth = config_dict.get("terminal_growth", 0.025)

    tk = yf.Ticker(ticker)
    info = tk.info or {}

    current_price = (info.get("currentPrice")
                     or info.get("regularMarketPrice")
                     or info.get("previousClose"))

    ddm = run_ddm(info, rf=rf, erp=erp, terminal_growth=terminal_growth)

    # Peers: los que traiga el config (auto_peers) — fetch puntual de cada uno
    peers_info: list[dict] = []
    for peer in (config_dict.get("auto_peers") or [])[:6]:
        try:
            p_info = yf.Ticker(peer).info or {}
            peers_info.append({
                "priceToBook": p_info.get("priceToBook"),
                "returnOnEquity": p_info.get("returnOnEquity"),
            })
        except Exception:
            continue

    pbv = run_pbv(info, peers_info)

    return {
        "current_price": current_price,
        "dcf_price": ddm["price"],
        "mult_price": pbv["price"],
        "wacc": ddm["ke"],
        "peers_count": pbv["peers_used"],
        "ddm_note": ddm.get("note"),
        "pbv_note": pbv.get("note"),
    }
