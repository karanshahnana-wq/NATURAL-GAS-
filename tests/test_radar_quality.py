import unittest

from options_schema import extract_option_sides
from x_radar import score_headline


class OptionsSchemaTests(unittest.TestCase):
    def test_documented_call_put_payload(self):
        payload = {"data": {
            "call": [{"strikePrice": 300, "ltp": 12.5, "openInterest": 100, "volume": 20}],
            "put": [{"strikePrice": 300, "ltp": 10.0, "openInterest": 120, "volume": 25}],
        }}
        data, calls, puts, status = extract_option_sides(payload)
        self.assertTrue(status["valid"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(puts), 1)
        self.assertIn("call", data)

    def test_non_object_payload_is_rejected(self):
        _, calls, puts, status = extract_option_sides(["not", "an", "object"])
        self.assertFalse(status["valid"])
        self.assertEqual(calls, [])
        self.assertEqual(puts, [])

    def test_broker_error_is_rejected(self):
        _, calls, puts, status = extract_option_sides({"error": "invalid request"})
        self.assertFalse(status["valid"])
        self.assertEqual(calls, [])
        self.assertEqual(puts, [])

    def test_headline_sentiment_is_explainable(self):
        bullish = score_headline("Cold weather boosts natural gas demand")
        bearish = score_headline("Warmer weather and record production weigh on natural gas")
        self.assertEqual(bullish["sentiment_tag"], "bullish-leaning")
        self.assertTrue(bullish["bullish_terms"])
        self.assertEqual(bearish["sentiment_tag"], "bearish-leaning")
        self.assertTrue(bearish["bearish_terms"])


if __name__ == "__main__":
    unittest.main()
