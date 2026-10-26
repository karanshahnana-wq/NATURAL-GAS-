"""Verified public fundamentals for the MCX Natural Gas Radar.

Only official/traceable source responses are exposed. Missing feeds stay unavailable;
headline sentiment is an explainable triage hint, never a trading signal.
"""
from __future__ import annotations

import csv
import io
import os
import time
import json
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from threading import Lock
from urllib.parse import quote
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from fastapi import APIRouter, Header, HTTPException

router = APIRouter()
log = logging.getLogger("radar.fundamentals")
_cache_lock = Lock()
_cache: dict[str, tuple[float, dict]] = {}
CACHE_SECONDS = 900
UA = "MCX-Natural-Gas-Radar/1.0 (public market-data research)"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_bytes(url: str, timeout: float = 8.0) -> bytes:
    req = Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urlopen(req, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"upstream_http_{response.status}")
        return response.read()


def cached(key: str, loader, ttl: int = CACHE_SECONDS) -> dict:
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    try:
        value = loader()
    except Exception as exc:
        value = {"status": "unavailable", "error_type": type(exc).__name__,
                 "checked_at_utc": utc_now(), "note": "Provider request failed; no value inferred."}
        log.info("Fundamental source %s unavailable (%s)", key, type(exc).__name__)
    with _cache_lock:
        _cache[key] = (now, value)
    return value


def eia_storage() -> dict:
    key = os.getenv("EIA_API_KEY", "").strip()
    if not key:
        return {"status": "not_configured", "source": "U.S. EIA API v2",
                "note": "Set EIA_API_KEY in Render to fetch official weekly storage observations.",
                "checked_at_utc": utc_now()}
    params = ("api_key=" + quote(key, safe="") +
              "&frequency=weekly&data%5B0%5D=value&facets%5Bseries%5D%5B%5D=NW2_EPG0_SWO_R48_BCF"
              "&sort%5B0%5D%5Bcolumn%5D=period&sort%5B0%5D%5Bdirection%5D=desc&length=3")
    payload = json.loads(fetch_bytes("https://api.eia.gov/v2/natural-gas/stor/wkly/data/?" + params).decode())
    rows = payload.get("response", {}).get("data", [])
    if not rows:
        return {"status": "empty", "source": "U.S. EIA API v2", "checked_at_utc": utc_now()}
    latest = rows[0]
    prior = rows[1] if len(rows) > 1 else {}
    value = float(latest["value"]) if latest.get("value") is not None else None
    prior_value = float(prior["value"]) if prior.get("value") is not None else None
    return {"status": "connected", "source": "U.S. EIA API v2",
            "series": "Lower 48 working gas in underground storage",
            "period": latest.get("period"), "value_bcf": value,
            "previous_period": prior.get("period"), "previous_value_bcf": prior_value,
            "weekly_change_bcf": round(value-prior_value, 2) if value is not None and prior_value is not None else None,
            "consensus_bcf": None, "surprise_bcf": None,
            "note": "Official observation only. Consensus and surprise are unavailable unless separately verified.",
            "checked_at_utc": utc_now()}


def cot_natural_gas() -> dict:
    """Parse the CFTC public disaggregated futures-only weekly report when available."""
    raw = fetch_bytes("https://www.cftc.gov/dea/newcot/f_disagg.txt", timeout=12).decode("utf-8-sig", errors="replace")
    rows = list(csv.DictReader(io.StringIO(raw)))
    matches = [r for r in rows if "NATURAL GAS" in str(r.get("Market_and_Exchange_Names", "")).upper()
               and "NEW YORK MERCANTILE" in str(r.get("Market_and_Exchange_Names", "")).upper()]
    if not matches:
        return {"status": "not_found", "source": "CFTC Disaggregated Commitments of Traders",
                "note": "No matching Natural Gas NYMEX row found in the current public file.", "checked_at_utc": utc_now()}
    row = matches[0]
    def number(*keys):
        for key in keys:
            raw_value = row.get(key)
            if raw_value not in (None, ""):
                try:
                    return int(str(raw_value).replace(",", "").strip())
                except ValueError:
                    continue
        return None
    long = number("M_Money_Positions_Long_All", "Managed_Money_Positions_Long_All")
    short = number("M_Money_Positions_Short_All", "Managed_Money_Positions_Short_All")
    report_date = row.get("Report_Date_as_YYYY-MM-DD") or row.get("As_of_Date_In_Form_YYMMDD")
    if long is None or short is None:
        return {"status": "schema_changed", "source": "CFTC Disaggregated Commitments of Traders",
                "report_date": report_date, "available_columns": list(row.keys())[:30],
                "note": "CFTC file loaded but expected managed-money columns were not found; values not guessed.",
                "checked_at_utc": utc_now()}
    return {"status": "connected", "source": "CFTC Disaggregated Commitments of Traders",
            "report_date": report_date, "market": row.get("Market_and_Exchange_Names"),
            "managed_money_long": long, "managed_money_short": short,
            "managed_money_net": long-short,
            "note": "Weekly positions, not real-time data. Positioning is context and does not time a reversal.",
            "checked_at_utc": utc_now()}


def weather_forecast() -> dict:
    # Public NOAA forecast API; identify the client and follow returned forecast URL.
    points = json.loads(fetch_bytes("https://api.weather.gov/points/30.10,-91.10").decode())
    forecast_url = points.get("properties", {}).get("forecast")
    if not forecast_url:
        raise RuntimeError("no_forecast_url")
    payload = json.loads(fetch_bytes(forecast_url).decode())
    periods = payload.get("properties", {}).get("periods", [])[:8]
    return {"status": "connected", "source": "NOAA National Weather Service",
            "location": "Henry Hub area, Louisiana (regional proxy, not a national HDD model)",
            "periods": [{"name": p.get("name"), "start": p.get("startTime"),
                         "temperature": p.get("temperature"), "unit": p.get("temperatureUnit"),
                         "short_forecast": p.get("shortForecast"), "wind": p.get("windSpeed")}
                        for p in periods],
            "note": "Regional forecast only; not a US-wide heating-degree-day or weather-model comparison.",
            "checked_at_utc": utc_now()}


def news_digest() -> dict:
    queries = [
        ("US weather and storage", "Henry Hub natural gas weather model EIA storage"),
        ("LNG feedgas and exports", "US LNG feedgas exports terminal outage"),
        ("Pipeline and production", "US natural gas production pipeline outage force majeure"),
        ("Global LNG", "global LNG supply demand export terminal"),
    ]
    items = []
    for category, query in queries:
        url = ("https://news.google.com/rss/search?q=" + quote(query + " when:3d", safe="")
               + "&hl=en-US&gl=US&ceid=US:en")
        root = ET.fromstring(fetch_bytes(url, timeout=7))
        for item in root.findall("./channel/item")[:6]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            published_raw = (item.findtext("pubDate") or "").strip()
            source_node = item.find("source")
            source = (source_node.text or "").strip() if source_node is not None else "Google News RSS"
            if not title or not link:
                continue
            try:
                dt = parsedate_to_datetime(published_raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                published = dt.astimezone(timezone.utc).isoformat()
            except Exception:
                published = None
            items.append({"title": title, "url": link, "published_utc": published,
                          "source": source, "category": category, "kind": "news_article"})
    unique = {x["url"]: x for x in items}
    sorted_items = sorted(unique.values(), key=lambda x: x.get("published_utc") or "", reverse=True)
    return {"status": "connected" if sorted_items else "empty", "source": "Google News public RSS",
            "items": sorted_items[:25], "checked_at_utc": utc_now(),
            "note": "Articles, not X posts. Verify the original report before acting; no headline is a trading signal."}


def build_fundamental_watch() -> dict:
    return {
        "status": "ok",
        "checked_at_utc": utc_now(),
        "feeds": {
            "eia_storage": cached("eia_storage", eia_storage, 21600),
            "cftc_cot": cached("cftc_cot", cot_natural_gas, 21600),
            "noaa_weather": cached("noaa_weather", weather_forecast, 1800),
            "news": cached("news", news_digest, 900),
        },
        "x_posts": {"status": "not_connected",
                    "note": "No authorized X API/feed configured. Account links are not evidence that posts were retrieved."},
        "trading_signal": None,
        "warning": "Research only. Missing feeds remain unavailable; no synthetic observations, forecasts, or trading signals are generated.",
    }


@router.get("/api/fundamental-watch")
def api_fundamental_watch():
    return build_fundamental_watch()


@router.post("/api/fundamental-watch/refresh")
def refresh_fundamental_watch(authorization: str | None = Header(default=None)):
    token = os.getenv("RADAR_INGEST_TOKEN", "").strip()
    if not token:
        raise HTTPException(status_code=503, detail="RADAR_INGEST_TOKEN is not configured on the server.")
    if authorization != "Bearer " + token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    with _cache_lock:
        _cache.clear()
    result = build_fundamental_watch()
    return {"status": "refreshed", "result": result}
