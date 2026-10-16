"""Tests for cumulative-volume behavior in the live candle collector."""
import unittest

from candle_engine import volume_delta


class VolumeDeltaTests(unittest.TestCase):
    def test_first_tick_sets_baseline_without_inventing_volume(self):
        self.assertEqual(volume_delta(None, 100), (0.0, 100))

    def test_increase_is_recorded_as_delta(self):
        self.assertEqual(volume_delta(100, 107), (7, 107))

    def test_volume_reset_sets_new_baseline(self):
        self.assertEqual(volume_delta(500, 4), (0.0, 4))
        self.assertEqual(volume_delta(4, 9), (5, 9))

    def test_missing_reading_preserves_previous_baseline(self):
        self.assertEqual(volume_delta(20, None), (0.0, 20))


if __name__ == "__main__":
    unittest.main()
