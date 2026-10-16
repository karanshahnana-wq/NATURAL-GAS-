import unittest

import main


class TenFactorAssessmentTests(unittest.TestCase):
    def test_framework_always_exposes_ten_factors(self):
        result = main._factor_assessment(None, {})
        self.assertEqual(result["total_factors"], 10)
        self.assertEqual(len(result["factors"]), 10)
        self.assertEqual(len({factor["factor"] for factor in result["factors"]}), 10)

    def test_missing_inputs_are_not_scored_or_fabricated(self):
        result = main._factor_assessment(None, {})
        self.assertEqual(result["status"], "insufficient_data")
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["available_weight"], 0)
        self.assertEqual(result["label"], "WAIT — insufficient verified directional inputs")
        for factor in result["factors"]:
            if not factor["available"]:
                self.assertEqual(factor["direction"], "unavailable")
                self.assertEqual(factor["weight"], 0)

    def test_storage_without_consensus_is_context_only(self):
        drivers = {
            "eia_storage": {
                "status": "connected",
                "period": "2026-10-09",
                "weekly_change_bcf": 64.0,
                "source": "U.S. EIA",
                "consensus_bcf": None,
            }
        }
        result = main._factor_assessment(None, drivers)
        storage = next(f for f in result["factors"] if f["factor"] == "EIA weekly storage")
        self.assertTrue(storage["available"])
        self.assertEqual(storage["direction"], "context_only")
        self.assertEqual(storage["weight"], 0)
        self.assertIn("consensus/seasonal benchmark not connected", storage["evidence"])


if __name__ == "__main__":
    unittest.main()
