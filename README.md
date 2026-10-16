# MCX Natural Gas Radar

Phone-first FastAPI dashboard for read-only MCX Natural Gas research. The application can request a live Kotak Neo futures quote when valid broker credentials, market-data permissions, SDK dependencies, and market access are configured. Missing broker fields are shown as unavailable; the application must not fabricate prices.

## Current status

- **Live quote:** Kotak integration exists; actual availability depends on the deployed environment and broker response.
- **Candles:** SFeed candle collector and aggregation engine exist; validate the live feed against the Kotak terminal before relying on it.
- **Technical indicators:** descriptive EMA/RSI/ATR outputs from stored verified candles; not a validated trading strategy.
- **Global drivers:** some reference-feed integrations exist, but each source and timestamp must be checked. Missing weather, EIA, FX, LNG, pipeline, demand, CFTC, or consensus data must remain unavailable rather than inferred.
- **Signals:** daily/intraday/overnight outputs are research-only. No signal is validated for live trading and no orders are placed.
- **Historical research:** CSV validation and a next-bar EMA crossover backtest harness are included. Backtests require authorized, quality-controlled MCX data, contract-roll handling, correct lot size, realistic brokerage/taxes, and slippage.

## Run locally

```bash
python -m pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

For deployment, use the hosting provider's Python runtime and set the start command to `uvicorn main:app --host 0.0.0.0 --port $PORT`.

## Configure Kotak Neo safely

Set these as private environment variables in the hosting provider; never commit them or paste them into chat:

- `NEO_CONSUMER_KEY`
- `NEO_MOBILE_NUMBER`
- `NEO_UCC`
- `NEO_MPIN`
- `NEO_TOTP_SECRET`

Optional: `NEO_ENVIRONMENT` (defaults to `prod`), `RADAR_DEMO_MODE`, and `RADAR_CANDLE_DB_PATH`. Verify all credentials and API TOTP registration in Kotak. A configured environment does not itself prove authentication or market data are working.

## Regression tests

```bash
python -m unittest discover -s tests -v
```

The GitHub Actions regression workflow passed on the current main commit as of 16 October 2026. This verifies deterministic tests only, not broker connectivity, production deployment, forecast accuracy, or profitability.

## Live data, storage, and backtest verification

See [docs/LIVE_DATA_VERIFICATION.md](docs/LIVE_DATA_VERIFICATION.md) for tick capture, candle regression tests, authorized historical CSV validation, backtest execution with explicit costs/slippage, and persistent storage setup. SQLite WAL does not make an ephemeral host filesystem persistent; configure a mounted persistent disk before depending on history across deploys.

## Next completion gates

1. Validate Kotak WebSocket tick fields against the broker terminal at matching timestamps, including units and cumulative-vs-last-trade volume semantics.
2. Confirm the actual deployed environment and safely diagnose authentication/quote failures without exposing secrets.
3. Run the regression suite and inspect any failures before changes are considered complete.
4. Connect and timestamp each fundamental factor from traceable sources; keep missing factors explicitly unavailable and do not present an incomplete score as a fully validated 10-factor score.
5. Backtest only on authorized, cleaned MCX history with session boundaries, contract rollover, costs, slippage, and out-of-sample evaluation.
6. Enable persistent storage only after confirming the host's disk configuration.

**Risk note:** Research software only. No trading signal is guaranteed. Do not trade based solely on this dashboard or treat sample backtest results as evidence of future performance.
