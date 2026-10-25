"""Free Natural Gas X watch panel.

Important: this module does not scrape X or pretend to have retrieved X posts.
It provides links to public account timelines/searches plus a small public Google
News RSS digest. Direct automatic X post collection requires an authorized,
available X data access method.
"""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from functools import lru_cache
from threading import Lock
from time import monotonic
from urllib.parse import quote
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from fastapi import APIRouter

router = APIRouter()
_CACHE_SECONDS = 600
_cache_lock = Lock()
_cache = {"checked": 0.0, "data": None}

# User's requested shortlist. Handles are treated as user-configured links,
# not proof that the accounts are active or that their posts have been fetched.
ACCOUNTS = [
    {"handle": "BabyGotGas", "focus": "Weather, storage expectations and gas fundamentals"},
    {"handle": "nfinancetrading", "focus": "COT positioning and macro context"},
    {"handle": "NatGasWeather", "focus": "Weather-model changes and heating demand"},
    {"handle": "NGInews", "focus": "Natural-gas industry news"},
    {"handle": "PipelineFlows", "focus": "Pipeline flows and supply fundamentals"},
    {"handle": "NGdaily1", "focus": "Gas trading commentary and spreads"},
    {"handle": "RealGasFundies", "focus": "Natural-gas fundamentals"},
    {"handle": "USAEnergyNatGas", "focus": "Energy derivatives commentary"},
    {"handle": "bluegoldr", "focus": "Weather and storage research"},
    {"handle": "CelsiusEnergyFM", "focus": "European gas and fundamentals"},
    {"handle": "GasAlphaHQ", "focus": "Weather and storage analysis"},
    {"handle": "EIAgov", "focus": "Official US energy statistics"},
    {"handle": "EIA_NatGas", "focus": "Natural-gas statistics (account needs verification)"},
    {"handle": "SergioChapa", "focus": "LNG and export developments"},
    {"handle": "BrynneKKelly", "focus": "Energy market perspective"},
    {"handle": "tmarzecmanser", "focus": "European gas and LNG"},
    {"handle": "GasBuddy", "focus": "Broader fuel-market context"},
    {"handle": "EnergyChamber", "focus": "Energy industry developments (account needs verification)"},
    {"handle": "SPGlobalEnergy", "focus": "Energy market intelligence"},
    {"handle": "LNGPrime", "focus": "Global LNG developments"},
]

NEWS_QUERIES = [
    ("Natural gas, storage and weather", "natural gas Henry Hub storage weather LNG when:7d"),
    ("LNG and pipeline disruptions", "US LNG feedgas pipeline outage natural gas when:7d"),
    ("EIA and supply-demand", "EIA natural gas storage production demand when:7d"),
]


def _rss_items(query: str, label: str):
    url = (
        "https://news.google.com/rss/search?q=" + quote(query, safe="")
        + "&hl=en-US&gl=US&ceid=US:en"
    )
    request = Request(url, headers={"User-Agent": "MCX-Natural-Gas-Radar/1.0"})
    with urlopen(request, timeout=5) as response:
        if response.status != 200:
            return []
        root = ET.fromstring(response.read())
    items = []
    for item in root.findall("./channel/item")[:8]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        published_raw = (item.findtext("pubDate") or "").strip()
        source_el = item.find("source")
        source = (source_el.text or "").strip() if source_el is not None else "Google News RSS"
        if not title or not link:
            continue
        try:
            published = parsedate_to_datetime(published_raw).astimezone(timezone.utc).isoformat()
        except Exception:
            published = published_raw or None
        items.append({
            "title": title,
            "url": link,
            "published": published,
            "source": source,
            "category": label,
            "kind": "news_article",
            **score_headline(title),
        })
    return items


# Transparent keyword sentiment heuristic. This is a headline tag, not a trading signal.
_BULLISH_TERMS = {
    "cold": 1.0, "colder": 1.2, "freeze": 1.2, "freezing": 1.2, "storm": 0.8,
    "higher demand": 1.0, "demand rises": 1.0, "storage draw": 1.2, "withdrawal": 0.8,
    "lng exports rise": 1.2, "feedgas rises": 1.0, "production falls": 1.2,
    "supply outage": 1.0, "pipeline outage": 1.0, "bullish": 1.0, "surge": 0.5,
}
_BEARISH_TERMS = {
    "warm": 1.0, "warmer": 1.2, "mild": 0.8, "storage build": 1.2, "injection": 0.8,
    "production rises": 1.2, "record production": 1.2, "lng outage": 1.0,
    "feedgas falls": 1.0, "demand falls": 1.0, "bearish": 1.0, "plunge": 0.5,
}

def score_headline(title: str) -> dict:
    text = (title or "").lower()
    bull_hits = [term for term in _BULLISH_TERMS if term in text]
    bear_hits = [term for term in _BEARISH_TERMS if term in text]
    bull = sum(_BULLISH_TERMS[t] for t in bull_hits)
    bear = sum(_BEARISH_TERMS[t] for t in bear_hits)
    score = round(bull - bear, 2)
    tag = "bullish-leaning" if score >= 0.75 else "bearish-leaning" if score <= -0.75 else "mixed/unclear"
    return {"sentiment_tag": tag, "sentiment_score": score,
            "bullish_terms": bull_hits, "bearish_terms": bear_hits,
            "sentiment_method": "transparent keyword heuristic; context may reverse interpretation"}

def _get_news():
    now = monotonic()
    with _cache_lock:
        if _cache["data"] is not None and now - _cache["checked"] < _CACHE_SECONDS:
            return _cache["data"]
    items, errors = [], []
    for label, query in NEWS_QUERIES:
        try:
            items.extend(_rss_items(query, label))
        except Exception as exc:
            errors.append(type(exc).__name__)
    # Deduplicate by canonical link and sort newest first where timestamps parse.
    unique = {}
    for item in items:
        unique[item["url"]] = item
    items = list(unique.values())
    items.sort(key=lambda x: x.get("published") or "", reverse=True)
    result = {
        "status": "connected" if items else "unavailable",
        "items": items[:20],
        "sentiment_summary": {
            "bullish_leaning": sum(1 for x in items if x.get("sentiment_tag") == "bullish-leaning"),
            "bearish_leaning": sum(1 for x in items if x.get("sentiment_tag") == "bearish-leaning"),
            "mixed_or_unclear": sum(1 for x in items if x.get("sentiment_tag") == "mixed/unclear"),
            "method": "keyword heuristic; not a standalone trading signal",
        },
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "Google News public RSS",
        "note": (
            "These are news articles, not X posts. Account timelines below open X directly. "
            "No X posts are fabricated or scraped."
        ),
        "errors": sorted(set(errors)),
    }
    with _cache_lock:
        _cache.update(checked=now, data=result)
    return result


@router.get("/api/x-radar")
def api_x_radar():
    """Return the curated account launcher and currently reachable public news RSS."""
    accounts = []
    for account in ACCOUNTS:
        handle = account["handle"]
        accounts.append({
            **account,
            "profile_url": f"https://x.com/{handle}",
            "search_url": "https://x.com/search?q=" + quote(f"from:{handle} (gas OR LNG OR EIA OR storage)", safe=""),
        })
    news = _get_news()
    return {
        "status": "ok",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "x_collection": {
            "status": "not_connected",
            "message": "Automatic X post collection is not enabled: no authorized X API credentials or other verified permitted post feed are configured.",
        },
        "accounts": accounts,
        "news": news,
        "refresh_interval_seconds": 300,
    }
