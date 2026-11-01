"""Unified Trading Radar: read-only dashboard with explicit broker diagnostics."""
from pathlib import Path
from datetime import datetime, timezone
from threading import Lock
from typing import Any
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from kotak_connection import connection_status, create_authenticated_client

app = FastAPI(title="Unified Trading Radar", version="0.2.0")
PAGE = Path(__file__).with_name("unified_dashboard.html")
_test_lock = Lock()
_test_result: dict[str, Any] = {
    "tested_at_utc": None, "authentication_verified": False,
    "live_quote_verified": False, "ltp": None, "symbol": None, "message": "Not tested yet."
}

def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()

@app.get("/", response_class=HTMLResponse)
def home():
    return HTMLResponse(PAGE.read_text(encoding="utf-8"))

@app.get("/api/health")
def health():
    return {"app": "Unified Trading Radar", "status": "online",
            "timestamp_utc": now_utc(), "order_placement": "disabled"}

@app.get("/api/connections")
def connections():
    cfg = connection_status()
    with _test_lock:
        test = dict(_test_result)
    return {
        "timestamp_utc": now_utc(),
        "kotak": {
            "credentials_configured": bool(cfg.get("configured")),
            "missing_variables": cfg.get("missing", []),
            "sdk_available": bool(cfg.get("sdk_available")),
            "authentication_verified": bool(test["authentication_verified"]),
            "live_quote_verified": bool(test["live_quote_verified"]),
            "last_tested_at_utc": test["tested_at_utc"],
            "test_symbol": test["symbol"],
            "ltp": test["ltp"],
            "status": "verified" if test["live_quote_verified"] else ("missing_configuration" if not cfg.get("configured") else "not_tested"),
            "note": test["message"],
        },
        "tradingview": {"chart_embed": "available", "broker_data_bridge": "not_connected",
                        "note": "TradingView is a separate chart service; its embed is not Kotak market data."},
        "signals": {"status": "not_enabled",
                    "note": "Signals remain disabled until real candles, contract metadata, option-chain data and risk tests are validated."},
        "option_chain": {"status": "not_connected", "note": "Option-chain data is not yet wired into this app."},
        "order_placement": "disabled",
    }

@app.post("/api/kotak-test")
def kotak_test():
    cfg = connection_status()
    if not cfg.get("configured"):
        with _test_lock:
            _test_result.update(tested_at_utc=now_utc(), authentication_verified=False,
                live_quote_verified=False, ltp=None, symbol=None,
                message="Missing Render environment variables: " + ", ".join(cfg.get("missing", [])) + ". Add them in Render Environment; do not send secrets in chat.")
        return JSONResponse(status_code=409, content={"status": "missing_configuration", **connections()["kotak"]})
    try:
        client = create_authenticated_client()
    except Exception as exc:
        # Keep diagnostics useful without returning SDK payloads or credentials.
        message = str(exc)
        allowed_prefixes = (
            "Kotak Neo credentials", "Kotak Neo SDK", "NEO_MOBILE_NUMBER",
            "NEO_TOTP_SECRET", "Kotak says", "Kotak rejected",
        )
        safe = message if message.startswith(allowed_prefixes) else "Kotak authentication failed. Check the Render environment values and the latest Render application logs for a sanitized error."
        with _test_lock:
            _test_result.update(tested_at_utc=now_utc(), authentication_verified=False,
                live_quote_verified=False, ltp=None, symbol=None, message=safe)
        return JSONResponse(status_code=502, content={"status": "authentication_failed", **connections()["kotak"]})
    with _test_lock:
        _test_result.update(tested_at_utc=now_utc(), authentication_verified=True,
            live_quote_verified=False, ltp=None, symbol="NIFTY 50", message="Authentication succeeded; requesting a real NIFTY quote.")
    try:
        token = __import__("os").getenv("NEO_TEST_INSTRUMENT_TOKEN", "Nifty 50").strip()
        segment = __import__("os").getenv("NEO_TEST_EXCHANGE_SEGMENT", "nse_cm").strip()
        response = client.quotes(instrument_tokens=[{"instrument_token": token, "exchange_segment": segment}], quote_type="ltp")
        rows = response if isinstance(response, list) else (response.get("data", []) if isinstance(response, dict) else [])
        row = next((item for item in rows if isinstance(item, dict) and item.get("ltp") not in (None, "")), None)
        if row is None:
            raise ValueError("No usable LTP returned for the configured test instrument.")
        ltp = float(row["ltp"])
        if ltp <= 0:
            raise ValueError("Broker returned a non-positive LTP.")
        display = str(row.get("display_symbol") or token)
        with _test_lock:
            _test_result.update(tested_at_utc=now_utc(), authentication_verified=True,
                live_quote_verified=True, ltp=ltp, symbol=display,
                message="Kotak authentication and real quote test succeeded.")
        return {"status": "verified", **connections()["kotak"]}
    except Exception:
        with _test_lock:
            _test_result.update(tested_at_utc=now_utc(), authentication_verified=True,
                live_quote_verified=False, ltp=None, symbol="NIFTY 50",
                message="Login succeeded, but the quote test failed. Check the test instrument token/exchange segment in Render and Kotak market-data permissions.")
        return JSONResponse(status_code=502, content={"status": "quote_failed", **connections()["kotak"]})

@app.get("/api/market-data")
def market_data(symbol: str = "NIFTY 50", interval: str = "5"):
    with _test_lock:
        test = dict(_test_result)
    if not test["live_quote_verified"]:
        return JSONResponse(status_code=503, content={
            "status": "not_connected", "timestamp_utc": now_utc(), "symbol": symbol,
            "data": None, "message": "No verified live market data. Run the Kotak connection test; candles are not fabricated."
        })
    # A verified one-off LTP is not a candle history; keep chart candles disabled until historical data is implemented.
    return JSONResponse(status_code=501, content={
        "status": "quote_only", "timestamp_utc": now_utc(), "symbol": symbol,
        "ltp": test["ltp"], "data": None,
        "message": "Live quote verified, but historical candle aggregation is not implemented yet."
    })
