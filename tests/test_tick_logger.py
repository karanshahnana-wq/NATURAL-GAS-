"""Regression tests for Kotak SFeed tick serialization across SDK object layouts."""
import unittest

from tools.kotak_tick_logger import tick_fields


class SlotTick:
    __slots__ = ("instrument_token", "last_traded_price", "volume_traded_today")

    def __init__(self):
        self.instrument_token = "12345"
        self.last_traded_price = 306.2
        self.volume_traded_today = 1200


class TickLoggerTests(unittest.TestCase):
    def test_serializes_sdk_style_slots_without_dict(self):
        result = tick_fields(SlotTick())
        self.assertEqual(result["instrument_token"], "12345")
        self.assertEqual(result["last_traded_price"], 306.2)
        self.assertEqual(result["volume_traded_today"], 1200)

    def test_serializes_public_scalar_attributes(self):
        class Tick:
            def __init__(self):
                self.ltp = 305.5
                self._internal = "skip"
                self.callback = lambda: None

        result = tick_fields(Tick())
        self.assertEqual(result, {"ltp": 305.5})


if __name__ == "__main__":
    unittest.main()
