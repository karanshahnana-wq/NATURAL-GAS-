# Live data verification and research tools

These tools are read-only and never submit orders.

## 1. Capture Kotak MCX Natural Gas ticks

Run on a machine with Python dependencies installed and the private NEO_* environment variables configured. Never commit credentials.

```bash
python -m pip install -r requirements.txt
python tools/kotak_tick_logger.py --minutes 15 --format csv --output data/kotak_ticks.csv
```

For newline-delimited JSON instead:

```bash
python tools/kotak_tick_logger.py --minutes 15 --format jsonl --output data/kotak_ticks.jsonl
```

The script logs UTC timestamp, resolved contract/expiry, LTP, broker volume field, OI fields when present, and an explicitly labelled **approximate** VWAP derived from LTP times observed cumulative-volume increments. This is not the exchange's official VWAP and is not guaranteed to be byte-for-byte equal to the terminal. Compare terminal and logger values at the same timestamp every 15 minutes; document the terminal's exact field definitions and any display rounding. Do not share raw logs if they contain account-specific metadata.

## 2. Candle aggregation tests

```bash
python -m unittest discover -s tests -v
```

The tests cover OHLCV aggregation, minute/five-minute boundaries, and malformed ticks using deterministic synthetic fixtures. They do not certify live Kotak feed accuracy.

## 3. Validate authorized historical MCX CSV data

Obtain historical data from Kotak or an authorized provider. Convert it to CSV with columns timestamp,open,high,low,close,volume and a timezone-aware ISO-8601 timestamp.

```bash
python tools/analyze_mcx_history.py authorized_mcx_history.csv --output history_analysis.json
```

The report flags invalid OHLC, zero/negative volume, close-return outliers beyond three standard deviations, and calculates a first-pass calendar-date overnight-gap distribution. Verify session calendars, contract rollover, data adjustments, and outliers against the vendor before using results for risk decisions.

## 4. Persistent SQLite storage on Render

The candle engine now enables SQLite WAL and uses a conflict-safe upsert. WAL improves concurrent access; it does not make an ephemeral filesystem persistent. Set RADAR_CANDLE_DB_PATH to a path on a mounted persistent Render disk (for example, /var/data/natural_gas_candles.sqlite3) and attach/configure that disk in Render before relying on history across deploys. A persistent disk can have a cost; confirm the plan and price in Render first.

## 5. Limits

- The live capture requires Kotak market-data permissions, valid private environment variables, and market-hours access.
- Some WebSocket messages may not contain OI or OI change. Missing broker fields are left blank; they are never fabricated.
- The history analyzer does not download vendor data or bypass rate limits.
- Backtests still require authorized, quality-controlled history, explicit entry/exit rules, fees, slippage, lot sizes, and rollover rules.
