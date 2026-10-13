# MCX Natural Gas Radar — starter v0.1

A first responsive web-app scaffold for the research project. It separates:
1. Daily directional bias
2. Intraday entry/exit planning
3. Overnight opening-gap research

## Important data status
The dashboard currently runs in **DEMO — SYNTHETIC DATA** mode. Numbers are generated placeholders used to build the UI. They are not current MCX quotes, forecasts, backtests, or trade recommendations. Do not trade from this demo.

## Run locally
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```
Open http://127.0.0.1:8000

## Configuration
`RADAR_DEMO_MODE=true` is the default. Setting it to false does not make data live; the live adapter is not implemented yet.

## Next build sequence
- Confirm Kotak Neo MCX instrument search, quote and WebSocket response using authorized credentials, stored only in server-side environment secrets.
- Build an adapter that fails closed when data is stale/missing.
- Ingest authorized MCX historical candles with expiry-aware contracts and volume/OI where available.
- Add Henry Hub, USD/INR, EIA storage surprises, weather revisions and timestamped news.
- Build walk-forward tests for daily direction, intraday setups and overnight gaps separately, including transaction costs.
- Only show probabilities after calibration and out-of-sample validation.

No order placement is implemented.
