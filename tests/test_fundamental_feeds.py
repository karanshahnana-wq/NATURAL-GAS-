import os
import unittest
from unittest.mock import patch

import fundamental_feeds as feeds


class FundamentalFeedTests(unittest.TestCase):
    def test_eia_requires_key_without_fabricating_data(self):
        with patch.dict(os.environ, {"EIA_API_KEY": ""}):
            result = feeds.eia_storage()
        self.assertEqual(result["status"], "not_configured")
        self.assertNotIn("value_bcf", result)
        self.assertIsNone(result.get("surprise_bcf"))

    def test_weather_api_response_is_labeled_regional_proxy(self):
        def fake_fetch(url, timeout=8.0):
            if "/points/" in url:
                import json
                return json.dumps({"properties": {"forecast": "https://api.weather.gov/gridpoints/LIX/1,1/forecast"}}).encode()
            import json
            return json.dumps({"properties": {"periods": [{"name": "Tonight", "temperature": 52,
                "temperatureUnit": "F", "shortForecast": "Clear", "startTime": "2026-10-26T00:00:00-05:00"}]}}).encode()
        with patch.object(feeds, "fetch_bytes", side_effect=fake_fetch):
            result = feeds.weather_forecast()
        self.assertEqual(result["status"], "connected")
        self.assertIn("regional proxy", result["location"])
        self.assertEqual(result["periods"][0]["temperature"], 52)

    def test_news_digest_deduplicates_and_preserves_original_link(self):
        rss = b"""<?xml version="1.0"?><rss><channel><item><title>Natural gas pipeline outage reported</title><link>https://example.com/story</link><pubDate>Mon, 26 Oct 2026 08:00:00 GMT</pubDate><source>Example News</source></item></channel></rss>"""
        with patch.object(feeds, "fetch_bytes", return_value=rss):
            result = feeds.news_digest()
        self.assertEqual(result["status"], "connected")
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["url"], "https://example.com/story")
        self.assertEqual(result["items"][0]["source"], "Example News")

    def test_missing_x_api_is_explicit(self):
        with patch.object(feeds, "cached", side_effect=lambda key, loader, ttl=feeds.CACHE_SECONDS: {"status": "not_configured"}):
            result = feeds.build_fundamental_watch()
        self.assertEqual(result["x_posts"]["status"], "not_connected")
        self.assertIsNone(result["trading_signal"])


if __name__ == "__main__":
    unittest.main()
