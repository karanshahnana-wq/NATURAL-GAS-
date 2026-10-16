"""Live MCX Natural Gas candle collector built on Kotak Neo SFeed WebSocket.

Stores only ticks actually received from the broker. No demo/synthetic data is written.
The default SQLite path is local/ephemeral on Render unless RADAR_CANDLE_DB_PATH
is pointed at a persistent disk.
"""
from __future__ import annotations

import asyncio
from contextlib import closing
import os
import logging
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_INTERVALS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}
_logger = logging.getLogger("mcx_candle_collector")
_lock = threading.RLock()
_state: dict[str, Any] = {
    "enabled": False, "status": "not_started", "message": "Collector has not started.",
    "connected": False, "contract": None, "expiry": None, "instrument_token": None,
    "exchange_segment": None, "last_tick_utc": None, "last_error": None,
    "ticks_received": 0, "candles_written": 0, "started_at": None,
    "collector_attempts": 0, "messages_received": 0, "ignored_messages": 0,
    "last_message_type": None, "last_matching_tick_utc": None,
}
_thread: threading.Thread | None = None
_stop = threading.Event()
_last_cumulative_volume: float | None = None


def volume_delta(previous: float | None, current: float | None) -> tuple[float, float | None]:
    """Return a non-negative cumulative-volume delta and the next baseline.

    Missing readings keep the previous baseline; resets are treated as a new
    baseline and never create a negative-volume candle.
    """
    if current is None:
        return 0.0, previous
    if previous is None or current < previous:
        return 0.0, current
    return current - previous, current


def _db_path() -> str:
    return os.getenv("RADAR_CANDLE_DB_PATH", "/tmp/natural_gas_candles.sqlite3")


def _connect() -> sqlite3.Connection:
    path = _db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=10000")
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
                    "INSERT INTO candles "
                    "(contract,expiry,interval,bucket_epoch,open,high,low,close,volume,tick_count,updated_utc) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(contract,expiry,interval,bucket_epoch) DO UPDATE SET "
                    "open=excluded.open, high=excluded.high, low=excluded.low, close=excluded.close, "
                    "volume=excluded.volume, tick_count=excluded.tick_count, updated_utc=excluded.updated_utc",
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
    # A successful subscription is not proof of a functioning market-data feed.
    # Report stale ticks explicitly so the UI cannot confuse an idle socket with live data.
    last_tick = result.get("last_tick_utc")
    tick_age_seconds = None
    if last_tick:
        try:
            last_dt = datetime.fromisoformat(str(last_tick).replace("Z", "+00:00"))
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            tick_age_seconds = max(0.0, (datetime.now(timezone.utc) - last_dt.astimezone(timezone.utc)).total_seconds())
        except (TypeError, ValueError):
            tick_age_seconds = None
    result["tick_age_seconds"] = round(tick_age_seconds, 1) if tick_age_seconds is not None else None
    result["data_fresh"] = tick_age_seconds is not None and tick_age_seconds <= 120
    if result.get("connected") and not result["data_fresh"]:
        result["status"] = "stale"
        result["message"] = "WebSocket may be connected, but no recent valid MCX tick was received; verify market session and broker feed."
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
                      started_at=datetime.now(timezone.utc).isoformat(), last_error=None,
                      collector_attempts=0, messages_received=0, ignored_messages=0,
                      last_message_type=None, last_matching_tick_utc=None)
    _logger.info("MCX candle collector thread starting")
    _thread = threading.Thread(target=_thread_main, args=(client_factory, quote_resolver),
                               name="mcx-candle-collector", daemon=True)
    _thread.start()


def _thread_main(client_factory: Callable[[], Any], quote_resolver: Callable[[], dict[str, Any]]) -> None:
    try:
        asyncio.run(_stream(client_factory, quote_resolver))
    except Exception as exc:
        _logger.exception("MCX candle collector stopped unexpectedly")
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
            _logger.warning("MCX SFeed disconnected; retrying (%s)", type(exc).__name__)
            with _lock:
                _state.update(connected=False, status="reconnecting",
                              message="Live feed disconnected; collector will retry automatically.",
                              last_error=type(exc).__name__, collector_attempts=_state["collector_attempts"] + 1)
            if _stop.is_set():
                return
            await asyncio.sleep(backoff)
            backoff = min(30, backoff * 2)


async def _stream_once(client_factory: Callable[[], Any], quote_resolver: Callable[[], dict[str, Any]]) -> None:
    from neo_api_client.websocket.feed import WsToken, SFeedScrip
    global _last_cumulative_volume
    # Each socket session starts with a fresh cumulative-volume baseline. A reconnect
    # must not compare today's volume against a stale value from a previous contract/session.
    _last_cumulative_volume = None
    # Resolve a current futures token using the same contract lookup as the verified quote.
    quote = await asyncio.to_thread(quote_resolver)
    segment = str(quote.get("exchange_segment") or "mcx_fo")
    token = str(quote.get("instrument_token") or "")
    contract = str(quote.get("contract") or "")
    expiry = str(quote.get("expiry") or "")
    if not token:
        raise RuntimeError("Kotak quote resolver did not expose an instrument token.")
    client = await asyncio.to_thread(client_factory)
    _logger.info("Resolved MCX stream contract=%s expiry=%s segment=%s token_present=%s", contract, expiry, segment, bool(token))
    with _lock:
        _state.update(status="connecting", connected=False, contract=contract, expiry=expiry,
                      instrument_token=token, exchange_segment=segment,
                      message="Contract resolved; connecting to Kotak SFeed.")
    async with client.create_websocket() as ws:
        await ws.subscribe_scrips([WsToken(segment, token)])
        _logger.info("Subscribed to Kotak SFeed for contract=%s; waiting for ticks", contract)
        with _lock:
            _state.update(status="connected_waiting_for_ticks", connected=True,
                          message="WebSocket subscribed; waiting for genuine MCX tick updates.")
        iterator = ws.__aiter__()
        while not _stop.is_set():
            try:
                # Detect a dead/stalled socket even when it never raises an error.
                message = await asyncio.wait_for(iterator.__anext__(), timeout=45.0)
            except asyncio.TimeoutError as exc:
                raise ConnectionError("No Kotak SFeed message received for 45 seconds.") from exc
            except StopAsyncIteration:
                break
            if _stop.is_set():
                break
            message_type = type(message).__name__
            with _lock:
                _state["messages_received"] += 1
                _state["last_message_type"] = message_type
            if not isinstance(message, SFeedScrip):
                with _lock:
                    _state["ignored_messages"] += 1
                continue
            if str(getattr(message, "instrument_token", "")) != token:
                with _lock:
                    _state["ignored_messages"] += 1
                continue
            raw_price = getattr(message, "last_traded_price", None)
            try:
                price = float(raw_price)
            except (TypeError, ValueError):
                continue
            if price <= 0:
                with _lock:
                    _state["ignored_messages"] += 1
                continue
            epoch = _utc_timestamp(getattr(message, "last_trade_time", None) or
                                   getattr(message, "last_update_time", None))
            cumulative = getattr(message, "volume_traded_today", None)
            try:
                current_volume = float(cumulative) if cumulative is not None else None
            except (TypeError, ValueError):
                current_volume = None
            delta, _last_cumulative_volume = volume_delta(_last_cumulative_volume, current_volume)
            await asyncio.to_thread(_write_tick, contract, expiry, epoch, price, delta)
            _logger.debug("Accepted MCX SFeed tick contract=%s price=%s", contract, price)
            with _lock:
                _state.update(status="collecting", connected=True,
                              message="Receiving genuine Kotak SFeed ticks and updating candles.",
                              last_tick_utc=datetime.fromtimestamp(epoch, timezone.utc).isoformat(),
                              ticks_received=_state["ticks_received"] + 1, last_error=None,
                              last_matching_tick_utc=datetime.fromtimestamp(epoch, timezone.utc).isoformat())
