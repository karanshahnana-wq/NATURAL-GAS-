from datetime import datetime, timezone
from pathlib import Path
import os, math, time
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from kotak_connection import connection_status, create_authenticated_client

app = FastAPI(title="MCX Natural Gas Radar", version="0.4.0")
DEMO_MODE = os.getenv("RADAR_DEMO_MODE", "true").lower() == "true"
_last_kotak_test = 0.0
_quote_cache = {"checked_at": 0.0, "data": None}
_QUOTE_CACHE_SECONDS = 20
_driver_cache = {"checked_at": 0.0, "data": None}
_DRIVER_CACHE_SECONDS = 600

PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MCX Natural Gas Radar</title><style>
:root{color-scheme:dark;--bg:#0a1020;--p:#111b2e;--line:#263650;--t:#e8eef8;--m:#9cacc4;--a:#7dd3fc;--g:#34d399;--r:#fb7185;--y:#fbbf24}*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at top right,#172b49,#0a1020 48%);color:var(--t);font:15px/1.5 system-ui,Segoe UI,sans-serif}.top{padding:24px max(20px,calc((100vw - 1200px)/2));border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center;gap:16px}.eyebrow{font-size:11px;letter-spacing:1.5px;color:var(--a);font-weight:800}h1{font-size:clamp(25px,4vw,38px);margin:5px 0;letter-spacing:-1px}h2{font-size:19px;margin:0 0 12px}p{color:var(--m)}.muted{color:var(--m);font-size:13px}.pill{border:1px solid var(--y);color:var(--y);padding:6px 10px;border-radius:99px;font-size:11px;font-weight:800}button{background:var(--a);color:#07111f;border:0;border-radius:9px;padding:10px 14px;font-weight:800;cursor:pointer}.actions{display:flex;align-items:center;gap:10px}main{max-width:1200px;margin:auto;padding:20px}.notice{background:#2a2110;border:1px solid #8a6720;color:#f9e6b0;padding:12px 15px;border-radius:12px;margin-bottom:16px}.grid{display:grid;grid-template-columns:1.1fr 1fr;gap:15px}.panel{background:linear-gradient(145deg,#111b2e,#0d1729);border:1px solid var(--line);border-radius:16px;padding:20px;min-width:0}.label{font-size:11px;letter-spacing:1.3px;color:var(--a);font-weight:800}.price{font-size:clamp(38px,6vw,58px);font-weight:850;letter-spacing:-2px;margin:8px 0}.change{font-weight:800}.positive{color:var(--g)}.negative{color:var(--r)}.mini{display:grid;grid-template-columns:repeat(4,1fr);gap:9px;margin-top:20px}.mini div{background:#0a1425;border:1px solid var(--line);border-radius:9px;padding:10px}.mini span{display:block;color:var(--m);font-size:12px}.mini b{display:block;margin-top:5px}.range{height:5px;background:linear-gradient(90deg,var(--r),#64748b,var(--g));border-radius:5px;margin:24px 0 8px;position:relative}.range i{position:absolute;left:50%;top:-4px;width:13px;height:13px;border:3px solid var(--a);background:white;border-radius:50%}.range-labels{display:flex;justify-content:space-between;color:var(--m);font-size:12px}.three{display:grid;grid-template-columns:repeat(3,1fr);gap:15px;margin:15px 0}.value{font-size:18px;font-weight:800;margin:12px 0}.three p{min-height:45px}.foot{border-top:1px solid var(--line);padding-top:10px;color:var(--a);font-size:12px}.levels div,.inputs div{display:flex;justify-content:space-between;gap:10px;padding:11px 0;border-bottom:1px solid var(--line)}.levels div:last-child,.inputs div:last-child{border:0}.levels span,.inputs span{color:var(--m);font-size:12px}.current{background:#18304a;padding-left:8px!important;padding-right:8px!important;border-radius:8px}.roadmap{margin-top:15px}.roadmap li{padding:5px 0 10px}.roadmap li span{display:block;color:var(--m);font-size:13px}.testresult{margin-top:12px;white-space:pre-wrap;overflow-wrap:anywhere;color:var(--a);font-size:13px}.footbutton{margin-top:10px}footer{text-align:center;color:var(--m);font-size:12px;padding:22px}@media(max-width:760px){.top{align-items:flex-start;flex-direction:column;padding:20px}.actions{width:100%;justify-content:space-between}main{padding:12px}.grid,.three{grid-template-columns:1fr}.mini{grid-template-columns:repeat(2,1fr)}.panel{padding:16px}.three p{min-height:0}}
</style></head><body><header class="top"><div><div class="eyebrow">MARKET INTELLIGENCE WORKSPACE</div><h1>MCX Natural Gas Radar</h1><p style="margin:0">Daily direction · Intraday plan · Overnight gap research</p></div><div class="actions"><span id="mode" class="pill">LOADING</span><button onclick="loadData()">Refresh</button></div></header><main><div class="notice" id="notice"><b>Live quote integration:</b> main price is sourced from Kotak when available. VWAP, volume, open interest, levels and signals remain demo until separately connected.</div><section class="grid"><article class="panel"><div class="label" id="priceLabel">Natural Gas futures · Kotak quote</div><div class="price" id="price">—</div><div><span id="change" class="change">Change unavailable</span> <span class="muted">· Broker-reported previous close </span><b id="prev">Not connected</b></div><div class="muted" style="margin-top:6px">Updated <span id="updated">—</span></div><div class="range"><i id="dot"></i></div><div class="range-labels"><span>Low <b id="low">Not connected</b></span><span>High <b id="high">Not connected</b></span></div><div class="mini"><div><span>VWAP · demo</span><b id="vwap">—</b></div><div><span>Volume · demo</span><b id="volume">—</b></div><div><span>OI · demo</span><b id="oi">—</b></div><div><span>OI change · demo</span><b id="oichange">—</b></div></div></article><article class="panel"><div class="label">DAILY DIRECTION ENGINE</div><div class="value" id="bias">WAIT FOR LIVE DATA</div><p id="reason">Loading snapshot…</p><h2 style="margin-top:22px">Support / resistance · not calculated</h2><div class="levels"><div><span>Resistance 2</span><b id="r2">—</b></div><div><span>Resistance 1</span><b id="r1">—</b></div><div class="current"><span>Current price</span><b id="lp">—</b></div><div><span>Support 1</span><b id="s1">—</b></div><div><span>Support 2</span><b id="s2">—</b></div></div></article></section><h2 style="margin-top:25px">Three separate decisions</h2><section class="three"><article class="panel"><div class="label">01 · DAILY DIRECTION</div><div class="value" id="daily">Waiting for validated data</div><p>Trend, volatility, levels, global gas move and scheduled catalysts.</p><div class="foot">Bullish / bearish / neutral + invalidation</div></article><article class="panel"><div class="label">02 · INTRADAY ENTRY / EXIT</div><div class="value" id="intra">No trade in demo mode</div><p>Trigger, stop, targets and no-trade conditions before entry.</p><div class="foot">Setup + risk levels</div></article><article class="panel"><div class="label">03 · OVERNIGHT OPENING GAP</div><div class="value" id="overnight">Not forecast yet</div><p>Next MCX open versus prior close, using only information available before open.</p><div class="foot">Gap direction + size range + reversal risk</div></article></section><section class="grid"><article class="panel"><h2>Data connections</h2><div id="inputs" class="inputs"></div><h2 style="margin-top:18px">Kotak authentication test</h2><p>This makes one login attempt. It will not place orders or return your credentials.</p><button class="footbutton" onclick="testKotak()">Test Kotak login</button><div id="testresult" class="testresult" role="status"></div><button class="footbutton" onclick="testMcx()">Test MCX Natural Gas quote</button><div id="mcxresult" class="testresult" role="status"></div></article><article class="panel"><div class="label">BUILD ROADMAP</div><h2>Next modules</h2><ol class="roadmap"><li><b>Kotak Neo authentication</b><span>Run a safe login test, then verify the MCX instrument and quote method.</span></li><li><b>Historical MCX futures</b><span>Contract expiry, candles, volume and OI from an authorized source.</span></li><li><b>Global drivers</b><span>Henry Hub, USD/INR, weather revisions, EIA storage and timestamped news.</span></li><li><b>Walk-forward validation</b><span>Test against simple baselines after costs; never invent accuracy.</span></li></ol></article></section><footer>MCX Natural Gas Radar · responsive starter · no order placement</footer></main><script>async function loadData(){try{let r=await fetch('/api/snapshot',{cache:'no-store'});if(!r.ok)throw Error('API '+r.status);let d=await r.json(),f=v=>v==null?'—':Number(v).toLocaleString('en-IN',{maximumFractionDigits:2}),$=id=>document.getElementById(id);$('mode').textContent=d.mode;$('priceLabel').textContent=d.live_quote?'Natural Gas futures · Kotak quote':'Natural Gas futures · synthetic demo';$('notice').innerHTML=d.live_quote?'<b>Kotak quote connected:</b> Main price and change use Kotak. Other indicators remain demo until their own feeds are integrated.':'<b>Demo fallback:</b> Kotak quote unavailable; displayed price is synthetic and not for trading.';$('price').textContent='₹'+f(d.price);$('prev').textContent=d.previous_close==null?'Not connected':'₹'+f(d.previous_close);$('change').textContent=d.change==null?'Change unavailable':(d.change>=0?'+':'')+'₹'+f(d.change)+' ('+(d.change_pct>=0?'+':'')+f(d.change_pct)+'%)';$('change').className='change '+(d.change==null?'':(d.change>=0?'positive':'negative'));$('updated').textContent=(d.live_quote?'Kotak quote · ':'Demo snapshot · ')+new Date(d.timestamp_utc).toLocaleTimeString();$('low').textContent=d.day_low==null?'Not connected':'₹'+f(d.day_low);$('high').textContent=d.day_high==null?'Not connected':'₹'+f(d.day_high);$('vwap').textContent='₹'+f(d.vwap);$('volume').textContent=f(d.volume);$('oi').textContent=f(d.open_interest);$('oichange').textContent=f(d.oi_change);$('bias').textContent=d.signals.daily_bias;$('daily').textContent=d.signals.daily_bias;$('intra').textContent=d.signals.intraday_setup;$('overnight').textContent=d.signals.overnight_gap;$('reason').textContent=d.signals.reason;$('lp').textContent='₹'+f(d.price);for(let k of ['r1','r2','s1','s2'])$(k).textContent=d.levels&&d.levels[{r1:'resistance_1',r2:'resistance_2',s1:'support_1',s2:'support_2'}[k]]!=null?'₹'+f(d.levels[{r1:'resistance_1',r2:'resistance_2',s1:'support_1',s2:'support_2'}[k]]):'Unavailable';$('inputs').innerHTML=Object.entries(d.inputs).map(([k,v])=>'<div><span>'+k.replaceAll('_',' ')+'</span><b>'+v+'</b></div>').join('');const gd=d.global_drivers||{};const gRows=[['Henry Hub reference',gd.henry_hub_reference?('(d.day_high!=null&&d.day_low!=null)?d.day_high-d.day_low:0;$('dot').style.left=(span>0?Math.max(0,Math.min(100,(d.price-d.day_low)/span*100)):50)+'%'}catch(e){document.getElementById('mode').textContent='API ERROR';document.getElementById('reason').textContent=e.message}}async function testMcx(){let el=document.getElementById('mcxresult'),b=document.querySelectorAll('.footbutton')[1];b.disabled=true;b.textContent='Checking MCX…';el.textContent='Looking up Natural Gas futures and requesting a quote…';try{let r=await fetch('/api/kotak/mcx-test',{method:'POST',cache:'no-store'});let d=await r.json();el.textContent=d.message+(d.symbol?'\\nContract: '+d.symbol:'')+(d.ltp?'\\nLive/last price: '+d.ltp:'')+(d.timestamp?'\\nChecked: '+d.timestamp:'')}catch(e){el.textContent='MCX quote test failed. Refresh and try again later.'}finally{b.disabled=false;b.textContent='Test MCX Natural Gas quote'}}async function testKotak(){let el=document.getElementById('testresult'),b=document.querySelector('.footbutton');b.disabled=true;b.textContent='Testing…';el.textContent='Checking Kotak authentication…';try{let r=await fetch('/api/kotak/test',{method:'POST',cache:'no-store'});let d=await r.json();el.textContent=d.message+(d.code?'\nCode: '+d.code:'');}catch(e){el.textContent='Test request failed. Please refresh and try again.'}finally{b.disabled=false;b.textContent='Test Kotak login'}}loadData();</script></body></html>"""


def get_live_mcx_quote():
    """Return a cached Kotak MCX Natural Gas quote; never place orders."""
    now = time.monotonic()
    cached = _quote_cache.get("data")
    if cached and now - _quote_cache.get("checked_at", 0) < _QUOTE_CACHE_SECONDS:
        return cached
    client = create_authenticated_client()
    candidates = []
    for underlying in ("NATURALGAS", "NATURAL GAS"):
        try:
            chain = client.option_chain(exchange="mcx_fo", underlying=underlying, instrument_type="fut")
            data = chain.get("data", chain) if isinstance(chain, dict) else {}
            futures = data.get("fut", []) if isinstance(data, dict) else []
            for item in futures if isinstance(futures, list) else []:
                inst = item.get("inst", {}) if isinstance(item, dict) else {}
                neo_symbol = inst.get("neoSymbol", "")
                symbol = inst.get("symbol", "")
                expiry = str(inst.get("expiryDt", ""))
                if isinstance(neo_symbol, str) and neo_symbol.startswith("mcx_fo|") and "|" in neo_symbol:
                    candidates.append((neo_symbol, symbol, expiry))
            if candidates:
                break
        except Exception:
            continue
    if not candidates:
        rows = client.search_scrip(exchange_segment="mcx_fo", symbol="NATURALGAS", expiry="", option_type="FUT", strike_price="")
        for row in rows if isinstance(rows, list) else []:
            token = row.get("pSymbol")
            symbol = row.get("pTrdSymbol") or row.get("pSymbolName") or ""
            expiry = row.get("pExpiryDate") or row.get("lExpiryDate") or ""
            if token is not None and str(token).strip():
                candidates.append((f"mcx_fo|{token}", symbol, str(expiry)))
    if not candidates:
        raise RuntimeError("No Natural Gas futures contract returned by Kotak.")
    def expiry_key(row):
        from datetime import datetime as _dt
        for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d%b%Y"):
            try:
                return _dt.strptime(row[2], fmt)
            except Exception:
                pass
        return _dt.max
    neo_symbol, symbol, expiry = sorted(candidates, key=expiry_key)[0]
    segment, token = neo_symbol.split("|", 1)
    response = client.quotes(instrument_tokens=[{"instrument_token": token, "exchange_segment": segment}], quote_type="all")
    rows = response if isinstance(response, list) else response.get("data", []) if isinstance(response, dict) else []
    if isinstance(rows, dict):
        rows = [rows]
    quote = rows[0] if rows and isinstance(rows[0], dict) else {}
    ltp = quote.get("ltp") or quote.get("last_traded_price")
    if ltp is None:
        raise RuntimeError("Kotak did not return a last traded price.")
    def number(value):
        try:
            return float(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None
    ohlc = quote.get("ohlc") if isinstance(quote.get("ohlc"), dict) else {}
    result = {"price": number(ltp), "contract": symbol or neo_symbol, "expiry": expiry,
              "timestamp_utc": datetime.now(timezone.utc).isoformat(), "live_quote": True,
              "previous_close": number(ohlc.get("close")), "day_open": number(ohlc.get("open")),
              "day_high": number(ohlc.get("high")), "day_low": number(ohlc.get("low")),
              "change": number(quote.get("change")), "change_pct": number(quote.get("per_change")),
              "volume": number(quote.get("last_volume")), "vwap": number(quote.get("avg_cost")),
              "open_interest": number(quote.get("open_interest") or quote.get("oi")),
              "oi_change": number(quote.get("oi_change"))}
    _quote_cache["checked_at"], _quote_cache["data"] = now, result
    return result


def _get_json(url: str, timeout: float = 4.0):
    """Fetch a public JSON endpoint with a short timeout; return None on failure."""
    import json
    from urllib.request import Request, urlopen
    try:
        req = Request(url, headers={"User-Agent": "MCX-Natural-Gas-Radar/1.0"})
        with urlopen(req, timeout=timeout) as response:
            if response.status != 200:
                return None
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return None


def _yahoo_last(symbol: str):
    """Best-effort public delayed reference quote; not an exchange-authoritative MCX feed."""
    import urllib.parse
    encoded = urllib.parse.quote(symbol, safe="")
    payload = _get_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?range=5d&interval=1d")
    try:
        result = payload["chart"]["result"][0]
        meta = result["meta"]
        quote = result["indicators"]["quote"][0]
        closes = [v for v in quote.get("close", []) if isinstance(v, (int, float))]
        if not closes:
            return None
        return {"symbol": symbol, "price": float(meta.get("regularMarketPrice", closes[-1])),
                "previous_close": float(meta.get("chartPreviousClose", closes[-2] if len(closes) > 1 else closes[-1])),
                "currency": meta.get("currency"),
                "timestamp": datetime.fromtimestamp(meta.get("regularMarketTime", time.time()), timezone.utc).isoformat(),
                "source": "Yahoo Finance chart endpoint; reference data, may be delayed"}
    except Exception:
        return None


def _global_drivers():
    """Fetch cached public reference drivers. These are context, not direct MCX signals."""
    now = time.monotonic()
    if _driver_cache["data"] and now - _driver_cache["checked_at"] < _DRIVER_CACHE_SECONDS:
        return _driver_cache["data"]
    henry = _yahoo_last("NG=F")
    usdinr = _yahoo_last("INR=X")
    weather = _get_json("https://api.open-meteo.com/v1/forecast?latitude=30.10&longitude=-91.10&daily=temperature_2m_mean,temperature_2m_min,temperature_2m_max&temperature_unit=fahrenheit&forecast_days=3&timezone=America%2FChicago")
    weather_summary = None
    try:
        daily = weather["daily"]
        weather_summary = {"location":"Henry Hub area, Louisiana","dates":daily["time"],
                           "mean_f":daily["temperature_2m_mean"],"min_f":daily["temperature_2m_min"],
                           "max_f":daily["temperature_2m_max"],"source":"Open-Meteo forecast API"}
    except Exception:
        pass
    result = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "henry_hub_reference":henry,"usd_inr_reference":usdinr,"us_gulf_weather":weather_summary,
              "eia_storage":{"status":"not_connected","note":"Official EIA weekly storage series not yet configured"},
              "mcx_historical":{"status":"unavailable_from_kotak_api","note":"Kotak Neo historical-data docs exclude MCX futures; an authorized historical source is required"}}
    _driver_cache["checked_at"], _driver_cache["data"] = now, result
    return result


def snapshot():
    now = datetime.now(timezone.utc).isoformat()
    demo_close = 263.70
    demo_price = round(demo_close + math.sin(datetime.now().minute / 8) * 1.8 - .4, 2)
    kotak_status = connection_status()
    live_quote = None
    if kotak_status["configured"]:
        try:
            live_quote = get_live_mcx_quote()
        except Exception:
            live_quote = None
    price = live_quote["price"] if live_quote else demo_price
    drivers = _global_drivers()
    # Live quote fields are shown only when actually returned by Kotak.
    previous_close = live_quote.get("previous_close") if live_quote else None
    change = live_quote.get("change") if live_quote else None
    change_pct = live_quote.get("change_pct") if live_quote else None
    day_high = live_quote.get("day_high") if live_quote else None
    day_low = live_quote.get("day_low") if live_quote else None
    volume = live_quote.get("volume") if live_quote and live_quote.get("volume") is not None else None
    vwap = live_quote.get("vwap") if live_quote else None
    open_interest = live_quote.get("open_interest") if live_quote else None
    oi_change = live_quote.get("oi_change") if live_quote else None
    return {
        "mode": "KOTAK LIVE QUOTE" if live_quote else "DEMO — SYNTHETIC DATA",
        "live_quote": bool(live_quote),
        "timestamp_utc": live_quote["timestamp_utc"] if live_quote else now,
        "contract": live_quote["contract"] if live_quote else "MCX Natural Gas Futures (demo placeholder)",
        "price": price,
        "previous_close": previous_close, "change": change, "change_pct": change_pct,
        "day_open": live_quote.get("day_open") if live_quote else None,
        "day_high": day_high, "day_low": day_low, "volume": volume,
        "open_interest": open_interest, "oi_change": oi_change, "vwap": vwap,
        "levels": {"status": "not_calculated", "support_1": None, "support_2": None, "resistance_1": None, "resistance_2": None},
        "signals": {
            "daily_bias": "WAIT FOR LIVE DATA",
            "intraday_setup": "No trade — demo mode",
            "overnight_gap": "Not forecast — historical validation required",
            "reason": "Kotak quote fields are shown only when returned by the broker. Support/resistance and trade signals are unavailable until verified MCX candles and a tested strategy are connected."
        },
        "global_drivers": drivers,
        "inputs": {
            "mcx_price": "Kotak quote connected" if live_quote else "Demo only",
            "previous_close_ohlc": "Kotak quote fields" if live_quote and previous_close is not None else "Not returned",
            "vwap_volume_oi": "Kotak quote fields" if live_quote and (vwap is not None or volume is not None or open_interest is not None) else "Not returned",
            "support_resistance": "Not calculated — historical candles required",
            "kotak_neo": "Credentials ready — quote path used" if live_quote else ("Credentials ready — feed not verified" if kotak_status["configured"] else "Not configured"),
            "henry_hub": "Public reference available" if drivers["henry_hub_reference"] else "Unavailable",
            "usd_inr": "Public reference available" if drivers["usd_inr_reference"] else "Unavailable",
            "weather": "Forecast available" if drivers["us_gulf_weather"] else "Unavailable",
            "eia_storage": "Not connected", "news": "Not connected",
            "mcx_historical_candles": "Not available from Kotak historical API"
        }
    }

@app.get("/", response_class=HTMLResponse)
def home(): return HTMLResponse(PAGE)

@app.get("/api/health")
def health(): return {"ok":True,"app":"MCX Natural Gas Radar","demo_mode":True,"version":"0.4.0"}

@app.get("/api/snapshot")
def api_snapshot(): return snapshot()

@app.get("/api/kotak/status")
def kotak_status():
    """Safe readiness check; never returns credential values."""
    return connection_status()

def _safe_kotak_error(exc: Exception) -> dict:
    """Classify SDK failures without returning raw exception text or credentials."""
    response = getattr(exc, "response", None)
    status = getattr(exc, "status_code", None) or getattr(response, "status_code", None)
    code = getattr(exc, "code", None)
    name = type(exc).__name__
    # Use text only for classification; never return or log the raw value here.
    try:
        hint = str(exc).lower()
    except Exception:
        hint = ""
    if status == 429 or "rate limit" in hint or "too many requests" in hint:
        category, message = "rate_limited", "Kotak rate-limited the request. Wait before retrying."
    elif status in (401, 403) or "unauthorized" in hint or "forbidden" in hint:
        category, message = "auth_or_permission", "Kotak rejected access. Check API access, consumer key, and account permissions."
    elif "timeout" in name.lower() or "timed out" in hint or "timeout" in hint:
        category, message = "timeout", "The request timed out before Kotak completed the response. Check again later."
    elif "connection" in hint or "connection" in name.lower() or "failed to establish" in hint:
        category, message = "connection_error", "Could not establish a connection to Kotak's API; no successful response was received."
    elif status:
        category, message = "kotak_http_error", f"Kotak returned an HTTP {status} response."
    else:
        category, message = "sdk_error", "The Kotak SDK failed before a verified login response. See the private Render logs for the sanitized SDK event."
    result = {"category": category, "message": message, "exception_type": name}
    if isinstance(status, int):
        result["http_status"] = status
    if isinstance(code, (str, int)) and len(str(code)) <= 40:
        result["error_code"] = str(code)
    return result


@app.post("/api/kotak/test")
def kotak_test(request: Request):
    """Attempt one authenticated login, with a short cooldown and sanitized errors."""
    global _last_kotak_test
    status = connection_status()
    if not status["configured"]:
        raise HTTPException(status_code=409, detail="Kotak credentials are incomplete.")
    now = time.monotonic()
    if now - _last_kotak_test < 60:
        raise HTTPException(status_code=429, detail="Please wait 60 seconds between login tests.")
    _last_kotak_test = now
    try:
        client = create_authenticated_client()
        # Intentionally do not call order APIs or return client/session tokens.
        del client
        return {"ok": True, "authenticated": True, "mcx_quote_verified": False,
                "message": "Kotak authentication call completed. MCX instrument/quote and WebSocket feed still need separate verification."}
    except Exception as exc:
        detail = _safe_kotak_error(exc)
        return {"ok": False, "authenticated": False, "mcx_quote_verified": False,
                "code": detail["exception_type"], "diagnostic": detail,
                "message": "Kotak authentication test failed. " + detail["message"]}

@app.post("/api/kotak/mcx-test")
def kotak_mcx_test():
    """Resolve the Natural Gas futures chain and request one quote; never place orders."""
    global _last_kotak_test
    if not connection_status()["configured"]:
        raise HTTPException(status_code=409, detail="Kotak credentials are incomplete.")
    now = time.monotonic()
    if now - _last_kotak_test < 15:
        raise HTTPException(status_code=429, detail="Please wait 15 seconds before another MCX test.")
    _last_kotak_test = now
    try:
        client = create_authenticated_client()
        candidates = []
        # First try the futures-chain endpoint; underlying must match pSymbolName in the live scrip master.
        chain_error = None
        for underlying in ("NATURALGAS", "NATURAL GAS"):
            try:
                chain = client.option_chain(exchange="mcx_fo", underlying=underlying, instrument_type="fut")
                data = chain.get("data", chain) if isinstance(chain, dict) else {}
                futures = data.get("fut", []) if isinstance(data, dict) else []
                for item in futures if isinstance(futures, list) else []:
                    inst = item.get("inst", {}) if isinstance(item, dict) else {}
                    neo_symbol = inst.get("neoSymbol", "")
                    symbol = inst.get("symbol", "")
                    expiry = inst.get("expiryDt", "")
                    if isinstance(neo_symbol, str) and "|" in neo_symbol and neo_symbol.startswith("mcx_fo|"):
                        candidates.append((neo_symbol, symbol, expiry))
                if candidates:
                    break
            except Exception as exc:
                chain_error = type(exc).__name__
        # Reliable fallback: search the current MCX scrip master for futures, using its pSymbolName.
        if not candidates:
            try:
                rows = client.search_scrip(exchange_segment="mcx_fo", symbol="NATURALGAS", expiry="", option_type="FUT", strike_price="")
                for row in rows if isinstance(rows, list) else []:
                    token = row.get("pSymbol")
                    symbol = row.get("pTrdSymbol") or row.get("pSymbolName") or ""
                    expiry = row.get("pExpiryDate") or row.get("lExpiryDate") or ""
                    if token is not None and str(token).strip():
                        candidates.append((f"mcx_fo|{token}", symbol, str(expiry)))
            except Exception:
                pass
        if not candidates:
            return {"ok": False, "mcx_quote_verified": False,
                    "diagnostic": {"category": "no_contract_found", "chain_error": chain_error},
                    "message": "Kotak responded, but neither the futures chain nor the current MCX scrip master returned a Natural Gas futures contract. This does not prove a permission problem; the current symbol/market-data response needs inspection."}
        # Prefer the nearest expiry; support both DD-MMM-YYYY and ISO dates.
        def expiry_key(row):
            from datetime import datetime as _dt
            for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d%b%Y"):
                try: return _dt.strptime(row[2], fmt)
                except Exception: pass
            return _dt.max
        neo_symbol, symbol, expiry = sorted(candidates, key=expiry_key)[0]
        segment, token = neo_symbol.split("|", 1)
        response = client.quotes(instrument_tokens=[{"instrument_token": token, "exchange_segment": segment}], quote_type="all")
        rows = response if isinstance(response, list) else response.get("data", []) if isinstance(response, dict) else []
        if isinstance(rows, dict): rows = [rows]
        quote = rows[0] if rows and isinstance(rows[0], dict) else {}
        ltp = quote.get("ltp") or quote.get("last_traded_price")
        if not ltp:
            return {"ok": False, "mcx_quote_verified": False, "symbol": symbol or neo_symbol,
                    "message": "Natural Gas contract lookup succeeded, but Kotak did not return an LTP. Live quote access is not yet verified."}
        return {"ok": True, "mcx_quote_verified": True, "symbol": symbol or neo_symbol,
                "expiry": expiry, "ltp": str(ltp), "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": "Kotak returned a Natural Gas MCX futures quote. Dashboard demo figures remain labelled synthetic until live-feed integration is completed."}
    except HTTPException:
        raise
    except Exception as exc:
        detail = _safe_kotak_error(exc)
        return {"ok": False, "mcx_quote_verified": False, "code": detail["exception_type"],
                "diagnostic": detail,
                "message": "MCX contract/quote test failed. " + detail["message"]}

@app.get("/api/drivers")
def api_drivers():
    """Public reference drivers with source/time metadata; no trade recommendations."""
    return _global_drivers()


@app.get("/api/history/status")
def history_status():
    return {"status":"blocked_external_source_required",
            "message":"Kotak Neo historical-data documentation excludes MCX futures. Historical MCX candles and reliable backtesting require an authorized MCX historical-data provider.",
            "needed":["timestamp","contract","expiry","open","high","low","close","volume","open_interest"],
            "kotak_supported":False}
+f(gd.henry_hub_reference.price)+' / '+(gd.henry_hub_reference.symbol||'')):'Unavailable'],['USD/INR reference',gd.usd_inr_reference?f(gd.usd_inr_reference.price):'Unavailable'],['US Gulf weather',gd.us_gulf_weather?'3-day forecast available':'Unavailable'],['EIA storage','Not connected'],['MCX historical candles','Separate authorized source required']];$('drivers').innerHTML=gRows.map(([k,v])=>'<div><span>'+k+'</span><b>'+v+'</b></div>').join('');let span=(d.day_high!=null&&d.day_low!=null)?d.day_high-d.day_low:0;$('dot').style.left=(span>0?Math.max(0,Math.min(100,(d.price-d.day_low)/span*100)):50)+'%'}catch(e){document.getElementById('mode').textContent='API ERROR';document.getElementById('reason').textContent=e.message}}async function testMcx(){let el=document.getElementById('mcxresult'),b=document.querySelectorAll('.footbutton')[1];b.disabled=true;b.textContent='Checking MCX…';el.textContent='Looking up Natural Gas futures and requesting a quote…';try{let r=await fetch('/api/kotak/mcx-test',{method:'POST',cache:'no-store'});let d=await r.json();el.textContent=d.message+(d.symbol?'\\nContract: '+d.symbol:'')+(d.ltp?'\\nLive/last price: '+d.ltp:'')+(d.timestamp?'\\nChecked: '+d.timestamp:'')}catch(e){el.textContent='MCX quote test failed. Refresh and try again later.'}finally{b.disabled=false;b.textContent='Test MCX Natural Gas quote'}}async function testKotak(){let el=document.getElementById('testresult'),b=document.querySelector('.footbutton');b.disabled=true;b.textContent='Testing…';el.textContent='Checking Kotak authentication…';try{let r=await fetch('/api/kotak/test',{method:'POST',cache:'no-store'});let d=await r.json();el.textContent=d.message+(d.code?'\nCode: '+d.code:'');}catch(e){el.textContent='Test request failed. Please refresh and try again.'}finally{b.disabled=false;b.textContent='Test Kotak login'}}loadData();</script></body></html>"""


def get_live_mcx_quote():
    """Return a cached Kotak MCX Natural Gas quote; never place orders."""
    now = time.monotonic()
    cached = _quote_cache.get("data")
    if cached and now - _quote_cache.get("checked_at", 0) < _QUOTE_CACHE_SECONDS:
        return cached
    client = create_authenticated_client()
    candidates = []
    for underlying in ("NATURALGAS", "NATURAL GAS"):
        try:
            chain = client.option_chain(exchange="mcx_fo", underlying=underlying, instrument_type="fut")
            data = chain.get("data", chain) if isinstance(chain, dict) else {}
            futures = data.get("fut", []) if isinstance(data, dict) else []
            for item in futures if isinstance(futures, list) else []:
                inst = item.get("inst", {}) if isinstance(item, dict) else {}
                neo_symbol = inst.get("neoSymbol", "")
                symbol = inst.get("symbol", "")
                expiry = str(inst.get("expiryDt", ""))
                if isinstance(neo_symbol, str) and neo_symbol.startswith("mcx_fo|") and "|" in neo_symbol:
                    candidates.append((neo_symbol, symbol, expiry))
            if candidates:
                break
        except Exception:
            continue
    if not candidates:
        rows = client.search_scrip(exchange_segment="mcx_fo", symbol="NATURALGAS", expiry="", option_type="FUT", strike_price="")
        for row in rows if isinstance(rows, list) else []:
            token = row.get("pSymbol")
            symbol = row.get("pTrdSymbol") or row.get("pSymbolName") or ""
            expiry = row.get("pExpiryDate") or row.get("lExpiryDate") or ""
            if token is not None and str(token).strip():
                candidates.append((f"mcx_fo|{token}", symbol, str(expiry)))
    if not candidates:
        raise RuntimeError("No Natural Gas futures contract returned by Kotak.")
    def expiry_key(row):
        from datetime import datetime as _dt
        for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d%b%Y"):
            try:
                return _dt.strptime(row[2], fmt)
            except Exception:
                pass
        return _dt.max
    neo_symbol, symbol, expiry = sorted(candidates, key=expiry_key)[0]
    segment, token = neo_symbol.split("|", 1)
    response = client.quotes(instrument_tokens=[{"instrument_token": token, "exchange_segment": segment}], quote_type="all")
    rows = response if isinstance(response, list) else response.get("data", []) if isinstance(response, dict) else []
    if isinstance(rows, dict):
        rows = [rows]
    quote = rows[0] if rows and isinstance(rows[0], dict) else {}
    ltp = quote.get("ltp") or quote.get("last_traded_price")
    if ltp is None:
        raise RuntimeError("Kotak did not return a last traded price.")
    def number(value):
        try:
            return float(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None
    ohlc = quote.get("ohlc") if isinstance(quote.get("ohlc"), dict) else {}
    result = {"price": number(ltp), "contract": symbol or neo_symbol, "expiry": expiry,
              "timestamp_utc": datetime.now(timezone.utc).isoformat(), "live_quote": True,
              "previous_close": number(ohlc.get("close")), "day_open": number(ohlc.get("open")),
              "day_high": number(ohlc.get("high")), "day_low": number(ohlc.get("low")),
              "change": number(quote.get("change")), "change_pct": number(quote.get("per_change")),
              "volume": number(quote.get("last_volume")), "vwap": number(quote.get("avg_cost")),
              "open_interest": number(quote.get("open_interest") or quote.get("oi")),
              "oi_change": number(quote.get("oi_change"))}
    _quote_cache["checked_at"], _quote_cache["data"] = now, result
    return result


def _get_json(url: str, timeout: float = 4.0):
    """Fetch a public JSON endpoint with a short timeout; return None on failure."""
    import json
    from urllib.request import Request, urlopen
    try:
        req = Request(url, headers={"User-Agent": "MCX-Natural-Gas-Radar/1.0"})
        with urlopen(req, timeout=timeout) as response:
            if response.status != 200:
                return None
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return None


def _yahoo_last(symbol: str):
    """Best-effort public delayed reference quote; not an exchange-authoritative MCX feed."""
    import urllib.parse
    encoded = urllib.parse.quote(symbol, safe="")
    payload = _get_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?range=5d&interval=1d")
    try:
        result = payload["chart"]["result"][0]
        meta = result["meta"]
        quote = result["indicators"]["quote"][0]
        closes = [v for v in quote.get("close", []) if isinstance(v, (int, float))]
        if not closes:
            return None
        return {"symbol": symbol, "price": float(meta.get("regularMarketPrice", closes[-1])),
                "previous_close": float(meta.get("chartPreviousClose", closes[-2] if len(closes) > 1 else closes[-1])),
                "currency": meta.get("currency"),
                "timestamp": datetime.fromtimestamp(meta.get("regularMarketTime", time.time()), timezone.utc).isoformat(),
                "source": "Yahoo Finance chart endpoint; reference data, may be delayed"}
    except Exception:
        return None


def _global_drivers():
    """Fetch cached public reference drivers. These are context, not direct MCX signals."""
    now = time.monotonic()
    if _driver_cache["data"] and now - _driver_cache["checked_at"] < _DRIVER_CACHE_SECONDS:
        return _driver_cache["data"]
    henry = _yahoo_last("NG=F")
    usdinr = _yahoo_last("INR=X")
    weather = _get_json("https://api.open-meteo.com/v1/forecast?latitude=30.10&longitude=-91.10&daily=temperature_2m_mean,temperature_2m_min,temperature_2m_max&temperature_unit=fahrenheit&forecast_days=3&timezone=America%2FChicago")
    weather_summary = None
    try:
        daily = weather["daily"]
        weather_summary = {"location":"Henry Hub area, Louisiana","dates":daily["time"],
                           "mean_f":daily["temperature_2m_mean"],"min_f":daily["temperature_2m_min"],
                           "max_f":daily["temperature_2m_max"],"source":"Open-Meteo forecast API"}
    except Exception:
        pass
    result = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "henry_hub_reference":henry,"usd_inr_reference":usdinr,"us_gulf_weather":weather_summary,
              "eia_storage":{"status":"not_connected","note":"Official EIA weekly storage series not yet configured"},
              "mcx_historical":{"status":"unavailable_from_kotak_api","note":"Kotak Neo historical-data docs exclude MCX futures; an authorized historical source is required"}}
    _driver_cache["checked_at"], _driver_cache["data"] = now, result
    return result


def snapshot():
    now = datetime.now(timezone.utc).isoformat()
    demo_close = 263.70
    demo_price = round(demo_close + math.sin(datetime.now().minute / 8) * 1.8 - .4, 2)
    kotak_status = connection_status()
    live_quote = None
    if kotak_status["configured"]:
        try:
            live_quote = get_live_mcx_quote()
        except Exception:
            live_quote = None
    price = live_quote["price"] if live_quote else demo_price
    drivers = _global_drivers()
    # Live quote fields are shown only when actually returned by Kotak.
    previous_close = live_quote.get("previous_close") if live_quote else None
    change = live_quote.get("change") if live_quote else None
    change_pct = live_quote.get("change_pct") if live_quote else None
    day_high = live_quote.get("day_high") if live_quote else None
    day_low = live_quote.get("day_low") if live_quote else None
    volume = live_quote.get("volume") if live_quote and live_quote.get("volume") is not None else None
    vwap = live_quote.get("vwap") if live_quote else None
    open_interest = live_quote.get("open_interest") if live_quote else None
    oi_change = live_quote.get("oi_change") if live_quote else None
    return {
        "mode": "KOTAK LIVE QUOTE" if live_quote else "DEMO — SYNTHETIC DATA",
        "live_quote": bool(live_quote),
        "timestamp_utc": live_quote["timestamp_utc"] if live_quote else now,
        "contract": live_quote["contract"] if live_quote else "MCX Natural Gas Futures (demo placeholder)",
        "price": price,
        "previous_close": previous_close, "change": change, "change_pct": change_pct,
        "day_open": live_quote.get("day_open") if live_quote else None,
        "day_high": day_high, "day_low": day_low, "volume": volume,
        "open_interest": open_interest, "oi_change": oi_change, "vwap": vwap,
        "levels": {"status": "not_calculated", "support_1": None, "support_2": None, "resistance_1": None, "resistance_2": None},
        "signals": {
            "daily_bias": "WAIT FOR LIVE DATA",
            "intraday_setup": "No trade — demo mode",
            "overnight_gap": "Not forecast — historical validation required",
            "reason": "Kotak quote fields are shown only when returned by the broker. Support/resistance and trade signals are unavailable until verified MCX candles and a tested strategy are connected."
        },
        "global_drivers": drivers,
        "inputs": {
            "mcx_price": "Kotak quote connected" if live_quote else "Demo only",
            "previous_close_ohlc": "Kotak quote fields" if live_quote and previous_close is not None else "Not returned",
            "vwap_volume_oi": "Kotak quote fields" if live_quote and (vwap is not None or volume is not None or open_interest is not None) else "Not returned",
            "support_resistance": "Not calculated — historical candles required",
            "kotak_neo": "Credentials ready — quote path used" if live_quote else ("Credentials ready — feed not verified" if kotak_status["configured"] else "Not configured"),
            "henry_hub": "Public reference available" if drivers["henry_hub_reference"] else "Unavailable",
            "usd_inr": "Public reference available" if drivers["usd_inr_reference"] else "Unavailable",
            "weather": "Forecast available" if drivers["us_gulf_weather"] else "Unavailable",
            "eia_storage": "Not connected", "news": "Not connected",
            "mcx_historical_candles": "Not available from Kotak historical API"
        }
    }

@app.get("/", response_class=HTMLResponse)
def home(): return HTMLResponse(PAGE)

@app.get("/api/health")
def health(): return {"ok":True,"app":"MCX Natural Gas Radar","demo_mode":True,"version":"0.4.0"}

@app.get("/api/snapshot")
def api_snapshot(): return snapshot()

@app.get("/api/kotak/status")
def kotak_status():
    """Safe readiness check; never returns credential values."""
    return connection_status()

def _safe_kotak_error(exc: Exception) -> dict:
    """Classify SDK failures without returning raw exception text or credentials."""
    response = getattr(exc, "response", None)
    status = getattr(exc, "status_code", None) or getattr(response, "status_code", None)
    code = getattr(exc, "code", None)
    name = type(exc).__name__
    # Use text only for classification; never return or log the raw value here.
    try:
        hint = str(exc).lower()
    except Exception:
        hint = ""
    if status == 429 or "rate limit" in hint or "too many requests" in hint:
        category, message = "rate_limited", "Kotak rate-limited the request. Wait before retrying."
    elif status in (401, 403) or "unauthorized" in hint or "forbidden" in hint:
        category, message = "auth_or_permission", "Kotak rejected access. Check API access, consumer key, and account permissions."
    elif "timeout" in name.lower() or "timed out" in hint or "timeout" in hint:
        category, message = "timeout", "The request timed out before Kotak completed the response. Check again later."
    elif "connection" in hint or "connection" in name.lower() or "failed to establish" in hint:
        category, message = "connection_error", "Could not establish a connection to Kotak's API; no successful response was received."
    elif status:
        category, message = "kotak_http_error", f"Kotak returned an HTTP {status} response."
    else:
        category, message = "sdk_error", "The Kotak SDK failed before a verified login response. See the private Render logs for the sanitized SDK event."
    result = {"category": category, "message": message, "exception_type": name}
    if isinstance(status, int):
        result["http_status"] = status
    if isinstance(code, (str, int)) and len(str(code)) <= 40:
        result["error_code"] = str(code)
    return result


@app.post("/api/kotak/test")
def kotak_test(request: Request):
    """Attempt one authenticated login, with a short cooldown and sanitized errors."""
    global _last_kotak_test
    status = connection_status()
    if not status["configured"]:
        raise HTTPException(status_code=409, detail="Kotak credentials are incomplete.")
    now = time.monotonic()
    if now - _last_kotak_test < 60:
        raise HTTPException(status_code=429, detail="Please wait 60 seconds between login tests.")
    _last_kotak_test = now
    try:
        client = create_authenticated_client()
        # Intentionally do not call order APIs or return client/session tokens.
        del client
        return {"ok": True, "authenticated": True, "mcx_quote_verified": False,
                "message": "Kotak authentication call completed. MCX instrument/quote and WebSocket feed still need separate verification."}
    except Exception as exc:
        detail = _safe_kotak_error(exc)
        return {"ok": False, "authenticated": False, "mcx_quote_verified": False,
                "code": detail["exception_type"], "diagnostic": detail,
                "message": "Kotak authentication test failed. " + detail["message"]}

@app.post("/api/kotak/mcx-test")
def kotak_mcx_test():
    """Resolve the Natural Gas futures chain and request one quote; never place orders."""
    global _last_kotak_test
    if not connection_status()["configured"]:
        raise HTTPException(status_code=409, detail="Kotak credentials are incomplete.")
    now = time.monotonic()
    if now - _last_kotak_test < 15:
        raise HTTPException(status_code=429, detail="Please wait 15 seconds before another MCX test.")
    _last_kotak_test = now
    try:
        client = create_authenticated_client()
        candidates = []
        # First try the futures-chain endpoint; underlying must match pSymbolName in the live scrip master.
        chain_error = None
        for underlying in ("NATURALGAS", "NATURAL GAS"):
            try:
                chain = client.option_chain(exchange="mcx_fo", underlying=underlying, instrument_type="fut")
                data = chain.get("data", chain) if isinstance(chain, dict) else {}
                futures = data.get("fut", []) if isinstance(data, dict) else []
                for item in futures if isinstance(futures, list) else []:
                    inst = item.get("inst", {}) if isinstance(item, dict) else {}
                    neo_symbol = inst.get("neoSymbol", "")
                    symbol = inst.get("symbol", "")
                    expiry = inst.get("expiryDt", "")
                    if isinstance(neo_symbol, str) and "|" in neo_symbol and neo_symbol.startswith("mcx_fo|"):
                        candidates.append((neo_symbol, symbol, expiry))
                if candidates:
                    break
            except Exception as exc:
                chain_error = type(exc).__name__
        # Reliable fallback: search the current MCX scrip master for futures, using its pSymbolName.
        if not candidates:
            try:
                rows = client.search_scrip(exchange_segment="mcx_fo", symbol="NATURALGAS", expiry="", option_type="FUT", strike_price="")
                for row in rows if isinstance(rows, list) else []:
                    token = row.get("pSymbol")
                    symbol = row.get("pTrdSymbol") or row.get("pSymbolName") or ""
                    expiry = row.get("pExpiryDate") or row.get("lExpiryDate") or ""
                    if token is not None and str(token).strip():
                        candidates.append((f"mcx_fo|{token}", symbol, str(expiry)))
            except Exception:
                pass
        if not candidates:
            return {"ok": False, "mcx_quote_verified": False,
                    "diagnostic": {"category": "no_contract_found", "chain_error": chain_error},
                    "message": "Kotak responded, but neither the futures chain nor the current MCX scrip master returned a Natural Gas futures contract. This does not prove a permission problem; the current symbol/market-data response needs inspection."}
        # Prefer the nearest expiry; support both DD-MMM-YYYY and ISO dates.
        def expiry_key(row):
            from datetime import datetime as _dt
            for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d%b%Y"):
                try: return _dt.strptime(row[2], fmt)
                except Exception: pass
            return _dt.max
        neo_symbol, symbol, expiry = sorted(candidates, key=expiry_key)[0]
        segment, token = neo_symbol.split("|", 1)
        response = client.quotes(instrument_tokens=[{"instrument_token": token, "exchange_segment": segment}], quote_type="all")
        rows = response if isinstance(response, list) else response.get("data", []) if isinstance(response, dict) else []
        if isinstance(rows, dict): rows = [rows]
        quote = rows[0] if rows and isinstance(rows[0], dict) else {}
        ltp = quote.get("ltp") or quote.get("last_traded_price")
        if not ltp:
            return {"ok": False, "mcx_quote_verified": False, "symbol": symbol or neo_symbol,
                    "message": "Natural Gas contract lookup succeeded, but Kotak did not return an LTP. Live quote access is not yet verified."}
        return {"ok": True, "mcx_quote_verified": True, "symbol": symbol or neo_symbol,
                "expiry": expiry, "ltp": str(ltp), "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": "Kotak returned a Natural Gas MCX futures quote. Dashboard demo figures remain labelled synthetic until live-feed integration is completed."}
    except HTTPException:
        raise
    except Exception as exc:
        detail = _safe_kotak_error(exc)
        return {"ok": False, "mcx_quote_verified": False, "code": detail["exception_type"],
                "diagnostic": detail,
                "message": "MCX contract/quote test failed. " + detail["message"]}

@app.get("/api/drivers")
def api_drivers():
    """Public reference drivers with source/time metadata; no trade recommendations."""
    return _global_drivers()


@app.get("/api/history/status")
def history_status():
    return {"status":"blocked_external_source_required",
            "message":"Kotak Neo historical-data documentation excludes MCX futures. Historical MCX candles and reliable backtesting require an authorized MCX historical-data provider.",
            "needed":["timestamp","contract","expiry","open","high","low","close","volume","open_interest"],
            "kotak_supported":False}
