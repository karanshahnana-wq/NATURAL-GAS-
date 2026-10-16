#!/usr/bin/env python3
"""Validate authorized MCX OHLCV CSV history and summarize overnight gaps.

Expected CSV columns: timestamp, open, high, low, close, volume.
Timestamps should be ISO-8601 and include a timezone when possible.
This tool does not download data or invent missing candles.
"""
import argparse
import csv
import json
import math
import statistics
from datetime import datetime
from pathlib import Path


def analyze(rows):
    clean, flags = [], []
    for idx, row in enumerate(rows, start=2):
        try:
            stamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
            o, h, l, c = (float(row[k]) for k in ("open", "high", "low", "close"))
            v = float(row.get("volume", 0) or 0)
            if min(o, h, l, c) <= 0 or h < max(o, c, l) or l > min(o, c, h):
                flags.append({"row": idx, "issue": "invalid_ohlc"})
                continue
            if v <= 0:
                flags.append({"row": idx, "issue": "zero_or_negative_volume"})
            clean.append({"timestamp": stamp.isoformat(), "open": o, "high": h, "low": l, "close": c, "volume": v})
        except (KeyError, TypeError, ValueError):
            flags.append({"row": idx, "issue": "missing_or_invalid_fields"})
    returns = []
    for i in range(1, len(clean)):
        prev, curr = clean[i-1], clean[i]
        returns.append((curr["close"] / prev["close"] - 1) * 100)
    if len(returns) >= 3:
        mean = statistics.mean(returns)
        stdev = statistics.pstdev(returns)
        if stdev > 0:
            for i, ret in enumerate(returns):
                if abs(ret - mean) > 3 * stdev:
                    flags.append({"row": i + 3, "issue": "close_return_over_3_sigma", "return_pct": round(ret, 4)})
    gaps = []
    # A new calendar date is treated as a session boundary; vendor session calendars may need refinement.
    for prev, curr in zip(clean, clean[1:]):
        if curr["timestamp"][:10] != prev["timestamp"][:10]:
            gap = (curr["open"] / prev["close"] - 1) * 100
            gaps.append({"from_date": prev["timestamp"][:10], "to_date": curr["timestamp"][:10],
                         "previous_close": prev["close"], "next_open": curr["open"], "gap_pct": round(gap, 4)})
    gap_values = [x["gap_pct"] for x in gaps]
    summary = {
        "rows_input": len(rows), "rows_valid": len(clean), "quality_flags": flags,
        "overnight_gaps": gaps,
        "gap_statistics": {
            "count": len(gap_values),
            "mean_pct": round(statistics.mean(gap_values), 4) if gap_values else None,
            "median_pct": round(statistics.median(gap_values), 4) if gap_values else None,
            "min_pct": round(min(gap_values), 4) if gap_values else None,
            "max_pct": round(max(gap_values), 4) if gap_values else None,
        },
        "warning": "Calendar-date gaps are a first-pass proxy; align with official MCX trading sessions and contract expiries before using for risk decisions."
    }
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", help="authorized historical OHLCV CSV")
    parser.add_argument("--output", default="history_analysis.json")
    args = parser.parse_args()
    with open(args.csv_file, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    result = analyze(rows)
    Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "quality_flags" and k != "overnight_gaps"}, indent=2))
    print(f"Detailed analysis written to {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
