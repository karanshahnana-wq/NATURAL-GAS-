# MCX Natural Gas Radar — v0.1.1

Single-file FastAPI starter for Render. The UI is embedded in `main.py`, so it does not require a `static/` directory and fixes the previous Render crash.

## Render
- Runtime: Python 3
- Build: `pip install -r requirements.txt`
- Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`

## Important
All displayed market values are synthetic UI placeholders. Kotak Neo, Henry Hub, USD/INR, weather, EIA storage and historical MCX data are not connected. This version does not produce validated trading forecasts and does not place orders.
