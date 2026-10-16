#!/usr/bin/env python3
"""Event-driven EMA crossover backtest on authorized MCX OHLCV CSV data.

Signals are calculated at candle close and executed no earlier than the next
candle open. Fees and adverse slippage are explicit inputs; no market orders
are sent. Results are research output, not a recommendation.
"""
import argparse
import csv
import json
import math
from datetime import datetime
from pathlib import Path


def load_candles(path):
    candles = []
    with open(path, newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            try:
                stamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
                op, high, low, close = (float(row[k]) for k in ("open", "high", "low", "close"))
                if min(op, high, low, close) <= 0 or high < max(op, close, low) or low > min(op, close, high):
                    continue
                candles.append({"timestamp": stamp.isoformat(), "open": op, "high": high,
                                "low": low, "close": close})
            except (KeyError, TypeError, ValueError):
                continue
    candles.sort(key=lambda row: row["timestamp"])
    unique = {}
    for candle in candles:
        unique.setdefault(candle["timestamp"], candle)
    return list(unique.values())


def ema(values, period):
    if period < 1 or len(values) < period:
        return [None] * len(values)
    result = [None] * len(values)
    current = sum(values[:period]) / period
    result[period - 1] = current
    alpha = 2.0 / (period + 1)
    for i in range(period, len(values)):
        current = alpha * values[i] + (1 - alpha) * current
        result[i] = current
    return result


def backtest(candles, fast=9, slow=21, quantity=1.0, fee_per_unit_side=0.0, slippage_bps=0.0):
    if fast < 1 or slow <= fast:
        raise ValueError("Require 1 <= fast < slow.")
    if quantity <= 0 or fee_per_unit_side < 0 or slippage_bps < 0:
        raise ValueError("Quantity must be positive; fees and slippage must be non-negative.")
    if len(candles) <= slow:
        raise ValueError(f"Need more than {slow} valid candles; got {len(candles)}.")
    closes = [float(row["close"]) for row in candles]
    fast_ema, slow_ema = ema(closes, fast), ema(closes, slow)
    position = 0
    entry = None
    entry_time = None
    trades = []
    slip = slippage_bps / 10000.0

    def fill(price, direction, entering):
        # Adverse slippage: buys pay up, sells receive less.
        side = direction if entering else -direction
        return price * (1 + slip if side > 0 else 1 - slip)

    def close_position(price, stamp, raw_price):
        nonlocal position, entry, entry_time
        exit_fill = fill(raw_price, position, entering=False)
        gross = position * (exit_fill - entry) * quantity
        fees = 2 * fee_per_unit_side * quantity
        trades.append({
            "entry_time": entry_time, "exit_time": stamp,
            "direction": "long" if position > 0 else "short",
            "entry_fill": round(entry, 6), "exit_fill": round(exit_fill, 6),
            "gross_pnl": round(gross, 4), "fees": round(fees, 4),
            "net_pnl": round(gross - fees, 4),
        })
        position, entry, entry_time = 0, None, None

    # A crossover observed at close i is executed at open i+1.
    for i in range(slow - 1, len(candles) - 1):
        if fast_ema[i] is None or slow_ema[i] is None or fast_ema[i - 1] is None:
            continue
        desired = 1 if fast_ema[i] > slow_ema[i] else -1 if fast_ema[i] < slow_ema[i] else 0
        if desired == position:
            continue
        next_bar = candles[i + 1]
        if position:
            close_position(next_bar["open"], next_bar["timestamp"], next_bar["open"])
        if desired:
            position = desired
            entry = fill(next_bar["open"], position, entering=True)
            entry_time = next_bar["timestamp"]

    if position:
        last = candles[-1]
        close_position(last["close"], last["timestamp"], last["close"])

    net_values = [trade["net_pnl"] for trade in trades]
    wins = sum(1 for value in net_values if value > 0)
    gross_profit = sum(value for value in net_values if value > 0)
    gross_loss = -sum(value for value in net_values if value < 0)
    equity, peak, max_drawdown = 0.0, 0.0, 0.0
    for value in net_values:
        equity += value
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    return {
        "strategy": "EMA crossover, long/short",
        "signal_timing": "signal at candle close; execution at next candle open",
        "candles": len(candles), "fast_ema": fast, "slow_ema": slow,
        "quantity_units": quantity, "fee_per_unit_per_side_rupees": fee_per_unit_side,
        "slippage_bps_per_side": slippage_bps, "trades": len(trades),
        "win_rate_pct": round(100 * wins / len(trades), 2) if trades else None,
        "net_pnl_rupees": round(sum(net_values), 4),
        "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else None,
        "max_drawdown_rupees_trade_equity": round(max_drawdown, 4),
        "trade_details": trades,
        "warning": "Research only. Supply actual contract lot size, brokerage/taxes, realistic slippage, rollover-adjusted authorized history and MCX session rules. No out-of-sample validation is performed."
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", help="authorized OHLCV CSV: timestamp,open,high,low,close,volume")
    parser.add_argument("--fast", type=int, default=9)
    parser.add_argument("--slow", type=int, default=21)
    parser.add_argument("--quantity", type=float, required=True, help="units or lots, according to your CSV/fee assumptions")
    parser.add_argument("--fee-per-unit-side", type=float, required=True, help="rupees per unit per side, including allocated fees/taxes")
    parser.add_argument("--slippage-bps", type=float, required=True, help="adverse slippage basis points per side")
    parser.add_argument("--output", default="backtest_result.json")
    args = parser.parse_args()
    result = backtest(load_candles(args.csv_file), args.fast, args.slow,
                      args.quantity, args.fee_per_unit_side, args.slippage_bps)
    Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "trade_details"}, indent=2))
    print(f"Detailed results written to {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
