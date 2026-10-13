from datetime import datetime, timezone
from pathlib import Path
import os, random, math
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

ROOT = Path(__file__).parent
app = FastAPI(title="MCX Natural Gas Radar", version="0.1.0")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

DEMO_MODE = os.getenv("RADAR_DEMO_MODE", "true").lower() == "true"

def demo_snapshot():
    # Clearly synthetic data for UI development only. Never use as a trading signal.
    now = datetime.now(timezone.utc).isoformat()
    close = 263.70
    price = round(close + math.sin(datetime.now().minute / 8) * 1.8 - 0.4, 2)
    change = round(price - close, 2)
    pct = round(change / close * 100, 2)
    return {
        "mode": "DEMO — SYNTHETIC DATA" if DEMO_MODE else "LIVE ADAPTER NOT CONFIGURED",
        "timestamp_utc": now,
        "contract": "MCX Natural Gas Futures (demo placeholder — select active expiry)",
        "price": price, "previous_close": close, "change": change, "change_pct": pct,
        "day_high": round(max(price + 1.1, 265.1), 2),
        "day_low": round(min(price - 1.0, 261.9), 2),
        "volume": 18420, "open_interest": 44558, "oi_change": 3269,
        "vwap": round(price - 0.35, 2),
        "levels": {"support_1": 260.0, "support_2": 257.5, "resistance_1": 265.0, "resistance_2": 268.0},
        "signals": {
            "daily_bias": "WAIT FOR LIVE DATA",
            "intraday_setup": "No trade — demo mode",
            "overnight_gap": "Not forecast — historical validation required",
            "confidence": None,
            "reason": "These figures are synthetic placeholders used to build the interface. They are not current MCX prices or recommendations."
        },
        "inputs": {
            "mcx_price": "Synthetic placeholder",
            "henry_hub": "Not connected",
            "usd_inr": "Not connected",
            "weather": "Not connected",
            "eia_storage": "Not connected",
            "news": "Not connected"
        }
    }

@app.get("/", response_class=HTMLResponse)
def home():
    return FileResponse(ROOT / "index.html")

@app.get("/api/health")
def health():
    return {"ok": True, "app": "MCX Natural Gas Radar", "demo_mode": DEMO_MODE, "version": "0.1.0"}

@app.get("/api/snapshot")
def snapshot():
    return demo_snapshot()

@app.get("/api/history/status")
def history_status():
    return {
        "status": "not_connected",
        "message": "Historical MCX candles are not connected yet. Next build step: ingest an authorized historical source and store contract-aware candles.",
        "needed": ["timestamp", "expiry", "open", "high", "low", "close", "volume", "open_interest"]
    }
