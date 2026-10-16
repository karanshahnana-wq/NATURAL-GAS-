#!/usr/bin/env python3
"""Capture Kotak Neo MCX Natural Gas SFeed ticks to CSV or JSONL.

Run during market hours on a machine with the same private NEO_* environment
variables as the app. This script is read-only: it never places orders.
Example:
  python tools/kotak_tick_logger.py --minutes 15 --format csv
"""
from __future__ import annotations
import argparse
import asyncio
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kotak_connection import connection_status, create_authenticated_client
from main import get_live_mcx_quote


def attr(obj, *names):
    for name in names:
        try:
            value = getattr(obj, name, None)
        except Exception:
            continue
        if value is not None:
            return value
    return None


def tick_fields(message):
    """Serialize public scalar tick fields even when the SDK uses __slots__."""
    fields = {}
    try:
        source = vars(message)
    except (TypeError, AttributeError):
        source = {}
    for name, value in source.items():
        if name.startswith("_") or callable(value):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            fields[name] = value
    for name in (
        "instrument_token", "last_traded_price", "ltp", "last_trade_time",
        "last_update_time", "volume_traded_today", "open_interest", "oi",
        "oi_change", "open_int_change", "last_traded_quantity",
    ):
        value = attr(message, name)
        if value is not None:
            fields.setdefault(name, value)
    return fields


async def capture(minutes: float, output: Path, fmt: str):
    from neo_api_client.websocket.feed import WsToken, SFeedScrip
    if not connection_status().get("configured"):
        raise RuntimeError("Kotak credentials are not configured in NEO_* environment variables.")
    contract = await asyncio.to_thread(get_live_mcx_quote)
    token = str(contract.get("instrument_token") or "")
    segment = str(contract.get("exchange_segment") or "mcx_fo")
    if not token:
        raise RuntimeError("Kotak did not resolve an MCX futures instrument token.")
    client = await asyncio.to_thread(create_authenticated_client)
    output.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + minutes * 60
    cumulative_volume = None
    weighted_sum = 0.0
    weighted_qty = 0.0
    count = 0
    keys = ["timestamp_utc", "contract", "expiry", "instrument_token", "ltp",
            "volume_traded_today", "volume_delta_estimate", "open_interest",
            "oi_change", "vwap_estimate", "vwap_note", "raw_tick_json"]
    with output.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys) if fmt == "csv" else None
        if writer and handle.tell() == 0:
            writer.writeheader()
        async with client.create_websocket() as ws:
            await ws.subscribe_scrips([WsToken(segment, token)])
            print(f"Subscribed to {contract.get('contract')} expiry={contract.get('expiry')} token={token}")
            iterator = ws.__aiter__()
            while time.monotonic() < deadline:
                try:
                    message = await asyncio.wait_for(
                        iterator.__anext__(), timeout=min(5.0, max(0.1, deadline - time.monotonic()))
                    )
                except asyncio.TimeoutError:
                    continue
                except StopAsyncIteration:
                    break
                if not isinstance(message, SFeedScrip):
                    continue
                if str(attr(message, "instrument_token", "token") or "") != token:
                    continue
                ltp_raw = attr(message, "last_traded_price", "ltp")
                try:
                    ltp = float(ltp_raw)
                except (TypeError, ValueError):
                    continue
                if ltp <= 0:
                    continue
                tick_time = attr(message, "last_trade_time", "last_update_time")
                if isinstance(tick_time, (int, float)):
                    seconds = float(tick_time) / 1000 if float(tick_time) > 10_000_000_000 else float(tick_time)
                    now = datetime.fromtimestamp(seconds, timezone.utc).isoformat()
                elif isinstance(tick_time, str) and tick_time.strip():
                    try:
                        parsed = datetime.fromisoformat(tick_time.replace("Z", "+00:00"))
                        if parsed.tzinfo is None:
                            parsed = parsed.replace(tzinfo=timezone.utc)
                        now = parsed.astimezone(timezone.utc).isoformat()
                    except ValueError:
                        now = datetime.now(timezone.utc).isoformat()
                else:
                    now = datetime.now(timezone.utc).isoformat()
                cumulative_raw = attr(message, "volume_traded_today", "volume")
                try:
                    cumulative = float(cumulative_raw) if cumulative_raw is not None else None
                except (TypeError, ValueError):
                    cumulative = None
                delta = 0.0
                if cumulative is not None:
                    if cumulative_volume is not None and cumulative >= cumulative_volume:
                        delta = cumulative - cumulative_volume
                    cumulative_volume = cumulative
                # This is a tick-weighted proxy, not exchange-calculated VWAP:
                # SFeed quote updates do not necessarily represent each individual trade.
                if delta > 0:
                    weighted_sum += ltp * delta
                    weighted_qty += delta
                vwap = weighted_sum / weighted_qty if weighted_qty else None
                raw = {
                    "timestamp_utc": now, "contract": contract.get("contract"),
                    "expiry": contract.get("expiry"), "instrument_token": token,
                    "ltp": format(ltp, ".10g"),
                    "volume_traded_today": cumulative_raw, "volume_delta_estimate": delta,
                    "open_interest": attr(message, "open_interest", "oi"),
                    "oi_change": attr(message, "oi_change", "open_int_change"),
                    "vwap_estimate": format(vwap, ".10g") if vwap is not None else None,
                    "vwap_note": "Approximation from LTP x cumulative-volume increments; not broker/exchange VWAP",
                    "raw_tick_json": json.dumps(tick_fields(message), separators=(",", ":"), default=str)
                }
                if writer:
                    writer.writerow(raw)
                else:
                    handle.write(json.dumps(raw, separators=(",", ":"), default=str) + "\n")
                handle.flush()
                count += 1
                if count % 10 == 0:
                    print(f"{now} ltp={raw['ltp']} vol={cumulative_raw} oi={raw['open_interest']} ticks={count}")
    print(f"Capture ended. ticks={count} file={output.resolve()}")
    if count == 0:
        print("WARNING: No matching SFeed ticks were received. The file is not evidence of a working live feed.", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minutes", type=float, default=15, help="capture duration (default: 15)")
    parser.add_argument("--output", default="data/kotak_ticks.csv", help="output path")
    parser.add_argument("--format", choices=("csv", "jsonl"), default="csv")
    args = parser.parse_args()
    if args.minutes <= 0:
        parser.error("--minutes must be positive")
    try:
        asyncio.run(capture(args.minutes, Path(args.output), args.format))
    except KeyboardInterrupt:
        print("Capture interrupted by user.")
    except Exception as exc:
        print(f"Capture failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
