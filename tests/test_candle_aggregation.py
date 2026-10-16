"""Unit tests for candle aggregation boundaries and OHLCV correctness."""
import unittest
from candle_engine import aggregate_tick_batch


class CandleAggregationTests(unittest.TestCase):
    def test_ten_ticks_build_one_minute_ohlcv(self):
        # 10 ticks in one minute, cumulative volume deltas total 45.
        ticks = [
            {"timestamp": 1_800_000_000 + i * 5, "price": p, "volume_delta": i}
            for i, p in enumerate([300, 302, 299, 304, 301, 305, 298, 303, 300, 306])
        ]
        result = aggregate_tick_batch(ticks, interval_seconds=60)
        self.assertEqual(len(result), 1)
        c = result[0]
        self.assertEqual((c["open"], c["high"], c["low"], c["close"]), (300, 306, 298, 306))
        self.assertEqual(c["volume"], sum(range(10)))
        self.assertEqual(c["tick_count"], 10)

    def test_minute_boundary_does_not_drop_tick(self):
        base = 1_800_000_000
        ticks = [
            {"timestamp": base + 59, "price": 301, "volume_delta": 2},
            {"timestamp": base + 60, "price": 304, "volume_delta": 3},
        ]
        result = aggregate_tick_batch(ticks, interval_seconds=60)
        self.assertEqual(len(result), 2)
        self.assertEqual([c["tick_count"] for c in result], [1, 1])
        self.assertEqual([c["close"] for c in result], [301, 304])

    def test_five_minute_boundary(self):
        base = 1_800_000_000
        ticks = [
            {"timestamp": base + 299, "price": 301, "volume_delta": 2},
            {"timestamp": base + 300, "price": 304, "volume_delta": 3},
        ]
        result = aggregate_tick_batch(ticks, interval_seconds=300)
        self.assertEqual(len(result), 2)
        self.assertEqual(sum(c["tick_count"] for c in result), 2)
        self.assertEqual(sum(c["volume"] for c in result), 5)

    def test_bad_ticks_are_ignored(self):
        result = aggregate_tick_batch([
            {"timestamp": 1_800_000_000, "price": 0, "volume_delta": 5},
            {"timestamp": 1_800_000_001, "price": 301, "volume_delta": -2},
            {"timestamp": None, "price": 302, "volume_delta": 1},
        ], interval_seconds=60)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["volume"], 0)
        self.assertEqual(result[0]["tick_count"], 1)


if __name__ == "__main__":
    unittest.main()
