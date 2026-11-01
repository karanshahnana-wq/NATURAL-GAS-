"""Unified Trading Radar foundation.

Read-only signal dashboard. It does not place orders and never fabricates prices.
Kotak readiness is not the same as a successful live quote; the UI labels that distinction.
"""
from pathlib import Path
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from kotak_connection import connection_status

app = FastAPI(title="Unified Trading Radar", version="0.1.0")
PAGE = Path(__file__).with_name("unified_dashboard.html")


@app.get("/", response_class=HTMLResponse)
def home():
    return HTMLResponse(PAGE.read_text(encoding="utf-8"))


@app.get("/api/health")
def health():
    return {
        "app": "Unified Trading Radar",
        "status": "online",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "order_placement": "disabled",
    }


@app.get("/api/connections")
def connections():
    kotak = connection_status()
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "kotak": {
            "credentials_configured": bool(kotak.get("configured")),
            "sdk_available": bool(kotak.get("sdk_available")),
            "authentication_verified": False,
            "live_quote_verified": False,
            "status": "configuration_check_only",
            "note": "Credentials being present does not prove login or a live market feed. A live quote test is still required.",
        },
        "tradingview": {
            "chart_embed": "available",
            "broker_data_bridge": "not_connected",
            "note": "Charts are embedded from TradingView; this does not mean TradingView data is being relayed from Kotak.",
        },
        "signals": {
            "status": "not_enabled",
            "note": "No live signal is produced until validated market-data adapters and strategy tests are connected.",
        },
        "order_placement": "disabled",
    }


@app.get("/api/market-data")
def market_data():
    return JSONResponse(status_code=503, content={
        "status": "not_connected",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "data": None,
        "message": "Live market adapter is not yet verified. No prices or signals are fabricated.",
    })
