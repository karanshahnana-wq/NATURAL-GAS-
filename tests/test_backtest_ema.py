"""Deterministic tests for next-bar execution and explicit transaction costs."""
import unittest

from tools.backtest_ema import backtest


class BacktestTests(unittest.TestCase):
    def setUp(self):
        closes = [10, 12, 14, 11, 8, 7]
        opens = [10, 11, 13, 13, 10, 7]
        self.candles = []
        for i, (op, close) in enumerate(zip(opens, closes)):
            self.candles.append({
                "timestamp": f"2026-10-{10+i:02d}T09:00:00+05:30",
                "open": op, "high": max(op, close) + 1,
                "low": min(op, close) - 1, "close": close,
            })

    def test_signal_executes_at_next_candle_open(self):
        result = backtest(self.candles, fast=1, slow=2, quantity=1,
                          fee_per_unit_side=0, slippage_bps=0)
        self.assertGreater(result["trades"], 0)
        self.assertEqual(result["trade_details"][0]["entry_time"], self.candles[2]["timestamp"])
        self.assertEqual(result["trade_details"][0]["entry_fill"], self.candles[2]["open"])

    def test_fees_reduce_net_pnl(self):
        no_fee = backtest(self.candles, fast=1, slow=2, quantity=2,
                          fee_per_unit_side=0, slippage_bps=0)
        with_fee = backtest(self.candles, fast=1, slow=2, quantity=2,
                            fee_per_unit_side=1.5, slippage_bps=0)
        self.assertAlmostEqual(no_fee["net_pnl_rupees"] - with_fee["net_pnl_rupees"],
                               with_fee["trades"] * 2 * 1.5 * 2)

    def test_rejects_invalid_ema_periods(self):
        with self.assertRaises(ValueError):
            backtest(self.candles, fast=5, slow=2)


if __name__ == "__main__":
    unittest.main()
