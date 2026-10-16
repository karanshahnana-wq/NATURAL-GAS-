"""Regression tests for historical OHLCV validation and overnight gap summaries."""
import unittest

from tools.analyze_mcx_history import analyze


def row(timestamp, op, high, low, close, volume=100):
    return {
        "timestamp": timestamp,
        "open": str(op),
        "high": str(high),
        "low": str(low),
        "close": str(close),
        "volume": str(volume),
    }


class HistoryAnalysisTests(unittest.TestCase):
    def test_sorts_out_of_order_rows_before_gap_analysis(self):
        rows = [
            row("2026-10-16T09:00:00+05:30", 300, 302, 299, 301),
            row("2026-10-14T09:00:00+05:30", 295, 301, 294, 300),
            row("2026-10-15T09:00:00+05:30", 303, 306, 302, 305),
        ]
        result = analyze(rows)
        self.assertEqual(result["rows_valid"], 3)
        self.assertEqual(len(result["overnight_gaps"]), 2)
        self.assertEqual(result["overnight_gaps"][0]["from_date"], "2026-10-14")
        self.assertEqual(result["overnight_gaps"][0]["to_date"], "2026-10-15")
        self.assertEqual(result["overnight_gaps"][0]["gap_pct"], 1.0)

    def test_flags_duplicate_timestamps(self):
        rows = [
            row("2026-10-14T09:00:00+05:30", 295, 301, 294, 300),
            row("2026-10-14T09:00:00+05:30", 296, 302, 295, 301),
        ]
        result = analyze(rows)
        self.assertEqual(result["rows_valid"], 1)
        self.assertTrue(any(flag["issue"] == "duplicate_timestamp" for flag in result["quality_flags"]))

    def test_invalid_ohlc_is_excluded(self):
        result = analyze([row("2026-10-14T09:00:00+05:30", 300, 290, 295, 301)])
        self.assertEqual(result["rows_valid"], 0)
        self.assertEqual(result["quality_flags"][0]["issue"], "invalid_ohlc")


if __name__ == "__main__":
    unittest.main()
