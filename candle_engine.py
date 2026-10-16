"""Live MCX Natural Gas candle collector built on Kotak Neo SFeed WebSocket.

Stores only ticks actually received from the broker. No demo/synthetic data is written.
The default SQLite path is local/ephemeral on Render unless RADAR_CANDLE_DB_PATH
is pointed at a persistent disk.
"""
from __future__ import annotations

import asyncio
from contextlib import closing
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_INTERVALS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}
_lock = threading.RLock()
_state: dict[str, Any] = {
    "enabled": False, "status": "not_started", "message": "Collector has not started.",
    "connected": False, "contract": None, "expiry": None, "instrument_token": None,
    "exchange_segment": None, "last_tick_utc": None, "last_error": None,
    "ticks_received": 0, "candles_written": 0, "started_at": None,
}
_thread: threading.Thread | None = None
_stop = threading.Event()
_last_cumulative_volume: float | None = None


def _db_path() -> str:
    return os.getenv("RADAR_CANDLE_DB_PATH", "/tmp/natural_gas_candles.sqlite3")


def _connect() -> sqlite3.Connection:
    path = _db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.execute("""CREATE TABLE IF NOT EXISTS candles (
        contract TEXT NOT NULL, expiry TEXT NOT NULL, interval TEXT NOT NULL,
        bucket_epoch INTEGER NOT NULL, open REAL NOT NULL, high REAL NOT NULL,
        low REAL NOT NULL, close REAL NOT NULL, volume REAL NOT NULL DEFAULT 0,
        tick_count INTEGER NOT NULL DEFAULT 0, updated_utc TEXT NOT NULL,
        PRIMARY KEY(contract, expiry, interval, bucket_epoch)
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_candles_time ON candles(interval, bucket_epoch)")
    return conn


def _utc_timestamp(value: Any) -> float:
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    if isinstance(value, (int, float)) and value > 0:
        # SDK timestamps are Unix seconds; guard against milliseconds.
        return float(value) / 1000 if value > 10_000_000_000 else float(value)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except Exception:
            pass
    return time.time()


def aggregate_tick_batch(ticks: list[dict[str, Any]], interval_seconds: int = 60) -> list[dict[str, Any]]:
    """Pure OHLCV aggregator used by tests; bucket boundaries are UTC Unix-time based."""
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")
    buckets: dict[int, dict[str, Any]] = {}
    for tick in ticks:
        try:
            epoch, price = float(tick["timestamp"]), float(tick["price"])
            volume = max(0.0, float(tick.get("volume_delta", 0) or 0))
        except (KeyError, TypeError, ValueError):
            continue
        if epoch <= 0 or price <= 0:
            continue
        bucket = int(epoch // interval_seconds) * interval_seconds
        candle = buckets.get(bucket)
        if candle is None:
            buckets[bucket] = {"bucket_epoch": bucket, "open": price, "high": price,
                                "low": price, "close": price, "volume": volume, "tick_count": 1}
        else:
            candle["high"] = max(candle["high"], price)
            candle["low"] = min(candle["low"], price)
            candle["close"] = price
            candle["volume"] += volume
            candle["tick_count"] += 1
    return [buckets[key] for key in sorted(buckets)]


def _write_tick(contract: str, expiry: str, epoch: float, price: float, volume_delta: float) -> None:
    global _last_cumulative_volume
    stamp = datetime.fromtimestamp(epoch, timezone.utc).isoformat()
    writes = 0
    with closing(_connect()) as conn:
        for interval, seconds in _INTERVALS.items():
            bucket = int(epoch // seconds) * seconds
            row = conn.execute(
                "SELECT open, high, low, close, volume, tick_count FROM candles "
                "WHERE contract=? AND expiry=? AND interval=? AND bucket_epoch=?",
                (contract, expiry, interval, bucket),
            ).fetchone()
            if row:
                op, hi, lo, _cl, vol, count = row
                conn.execute(
                    "UPDATE candles SET high=?, low=?, close=?, volume=?, tick_count=?, updated_utc=? "
                    "WHERE contract=? AND expiry=? AND interval=? AND bucket_epoch=?",
                    (max(hi, price), min(lo, price), price, vol + volume_delta,
                     count + 1, stamp, contract, expiry, interval, bucket),
                )
            else:
                conn.execute(
                    "INSERT OR REPLACE INTO candles "
                    "(contract,expiry,interval,bucket_epoch,open,high,low,close,volume,tick_count,updated_utc) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (contract, expiry, interval, bucket, price, price, price, price,
                     volume_delta, 1, stamp),
                )
            writes += 1
        conn.commit()
    with _lock:
        _state["candles_written"] += writes


def get_status() -> dict[str, Any]:
    with _lock:
        result = dict(_state)
    result["database_path_configured"] = bool(os.getenv("RADAR_CANDLE_DB_PATH"))
    result["storage_note"] = (
        "Custom database path configured; confirm it points to persistent storage."
        if result["database_path_configured"]
        else "Default SQLite path is ephemeral on Render; set RADAR_CANDLE_DB_PATH to a mounted persistent disk before relying on history across deploys."
    )
    try:
        with closing(_connect()) as conn:
            row = conn.execute("SELECT COUNT(*), MAX(updated_utc) FROM candles").fetchone()
        result["stored_candle_rows"] = row[0]
        result["last_candle_update_utc"] = row[1]
    except Exception:
        result["stored_candle_rows"] = 0
        result["last_candle_update_utc"] = None
    return result


def get_candles(interval: str = "5m", limit: int = 300) -> dict[str, Any]:
    if interval not in _INTERVALS:
        raise ValueError("interval must be one of: 1m, 5m, 15m, 1h")
    limit = max(1, min(int(limit), 1000))
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT contract, expiry, bucket_epoch, open, high, low, close, volume, tick_count, updated_utc "
            "FROM candles WHERE interval=? ORDER BY bucket_epoch DESC LIMIT ?",
            (interval, limit),
        ).fetchall()
    rows.reverse()
    candles = [{
        "contract": r[0], "expiry": r[1],
        "timestamp_utc": datetime.fromtimestamp(r[2], timezone.utc).isoformat(),
        "open": r[3], "high": r[4], "low": r[5], "close": r[6],
        "volume": r[7], "tick_count": r[8], "updated_utc": r[9],
    } for r in rows]
    return {"interval": interval, "count": len(candles), "candles": candles,
            "source": "Kotak Neo SFeed live ticks", "synthetic": False}


def start_collector(client_factory: Callable[[], Any], quote_resolver: Callable[[], dict[str, Any]]) -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    with _lock:
        _state.update(enabled=True, status="starting", message="Preparing authenticated MCX futures feed.",
                      started_at=datetime.now(timezone.utc).isoformat(), last_error=None)
    _thread = threading.Thread(target=_thread_main, args=(client_factory, quote_resolver),
                               name="mcx-candle-collector", daemon=True)
    _thread.start()


def _thread_main(client_factory: Callable[[], Any], quote_resolver: Callable[[], dict[str, Any]]) -> None:
    try:
        asyncio.run(_stream(client_factory, quote_resolver))
    except Exception as exc:
        with _lock:
            _state.update(connected=False, status="error",
                          message="Live candle collector stopped before receiving data.",
                          last_error=type(exc).__name__)


async def _stream(client_factory: Callable[[], Any], quote_resolver: Callable[[], dict[str, Any]]) -> None:
    """Keep the live collector running through transient socket/auth/network failures."""
    backoff = 2
    while not _stop.is_set():
        try:
            await _stream_once(client_factory, quote_resolver)
            if _stop.is_set():
                return
            raise ConnectionError("Kotak SFeed stream ended.")
        except Exception as exc:
            with _lock:
                _state.update(connected=False, status="reconnecting",
                              message="Live feed disconnected; collector will retry automatically.",
                              last_error=type(exc).__name__)
            if _stop.is_set():
                return
            await asyncio.sleep(backoff)
            backoff = min(30, backoff * 2)


async def _stream_once(client_factory: Callable[[], Any], quote_resolver: Callable[[], dict[str, Any]]) -> None:
    from neo_api_client.websocket.feed import WsToken, SFeedScrip
    global _last_cumulative_volume
    # Resolve a current futures token using the same contract lookup as the verified quote.
    quote = await asyncio.to_thread(quote_resolver)
    segment = str(quote.get("exchange_segment") or "mcx_fo")
    token = str(quote.get("instrument_token") or "")
    contract = str(quote.get("contract") or "")
    expiry = str(quote.get("expiry") or "")
    if not token:
        raise RuntimeError("Kotak quote resolver did not expose an instrument token.")
    client = await asyncio.to_thread(client_factory)
    with _lock:
        _state.update(status="connecting", connected=False, contract=contract, expiry=expiry,
                      instrument_token=token, exchange_segment=segment,
                      message="Contract resolved; connecting to Kotak SFeed.")
    async with client.create_websocket() as ws:
        await ws.subscribe_scrips([WsToken(segment, token)])
        with _lock:
            _state.update(status="connected_waiting_for_ticks", connected=True,
                          message="WebSocket subscribed; waiting for genuine MCX tick updates.")
        async for message in ws:
            if _stop.is_set():
                break
            if not isinstance(message, SFeedScrip):
                continue
            if str(getattr(message, "instrument_token", "")) != token:
                continue
            raw_price = getattr(message, "last_traded_price", None)
            try:
                price = float(raw_price)
            except (TypeError, ValueError):
                continue
            if price <= 0:
                continue
            epoch = _utc_timestamp(getattr(message, "last_trade_time", None) or
                                   getattr(message, "last_update_time", None))
            cumulative = getattr(message, "volume_traded_today", None)
            delta = 0.0
            try:
                current_volume = float(cumulative) if cumulative is not None else None
            except (TypeError, ValueError):
                current_volume = None
            if current_volume is not None and _last_cumulative_volume is not None:
                # A reset/rollover is not interpreted as negative volume.
                delta = max(0.0, current_volume - _last_cumulative_volume)
            if current_volume is not None:
                # When the session volume resets, treat this tick as a new baseline.
                if _last_cumulative_volume is not None and current_volume < _last_cumulative_volume:
                    delta = 0.0
                _last_cumulative_volume = current_volume
            await asyncio.to_thread(_write_tick, contract, expiry, epoch, price, delta)
            with _lock:
                _state.update(status="collecting", connected=True,
                              message="Receiving genuine Kotak SFeed ticks and updating candles.",
                              last_tick_utc=datetime.fromtimestamp(epoch, timezone.utc).isoformat(),
                              ticks_received=_state["ticks_received"] + 1, last_error=None)
