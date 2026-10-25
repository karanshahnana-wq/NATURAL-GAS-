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
        })
    return items


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
