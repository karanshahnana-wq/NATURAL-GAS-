from datetime import datetime, timezone
from pathlib import Path
import os, math, time, logging

# Kotak SDK REST errors may include account identifiers and request payloads.
# Disable its raw request logger; expose only our sanitized diagnostics.
logging.getLogger("neo_api_client.rest").disabled = True
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from kotak_connection import connection_status, create_authenticated_client
from candle_engine import start_collector, get_status as candle_status, get_candles
from x_radar import router as x_radar_router

app = FastAPI(title="MCX Natural Gas Radar", version="0.4.0")
app.include_router(x_radar_router)
DEMO_MODE = os.getenv("RADAR_DEMO_MODE", "true").lower() == "true"
_last_kotak_test = 0.0
_quote_cache = {"checked_at": 0.0, "data": None}
_QUOTE_CACHE_SECONDS = 20
_driver_cache = {"checked_at": 0.0, "data": None}
_DRIVER_CACHE_SECONDS = 600
_eia_cache = {"checked_at": 0.0, "data": None}
_EIA_CACHE_SECONDS = 21600  # EIA weekly storage: refresh at most every 6 hours
_kotak_client_cache = {"created_at": 0.0, "client": None}
_KOTAK_CLIENT_CACHE_SECONDS = 480

PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MCX Natural Gas Radar</title><style>
:root{color-scheme:dark;--bg:#0a1020;--p:#111b2e;--line:#263650;--t:#e8eef8;--m:#9cacc4;--a:#7dd3fc;--g:#34d399;--r:#fb7185;--y:#fbbf24}*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at top right,#172b49,#0a1020 48%);color:var(--t);font:15px/1.5 system-ui,Segoe UI,sans-serif}.top{padding:24px max(20px,calc((100vw - 1200px)/2));border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center;gap:16px}.eyebrow{font-size:11px;letter-spacing:1.5px;color:var(--a);font-weight:800}h1{font-size:clamp(25px,4vw,38px);margin:5px 0;letter-spacing:-1px}h2{font-size:19px;margin:0 0 12px}p{color:var(--m)}.muted{color:var(--m);font-size:13px}.pill{border:1px solid var(--y);color:var(--y);padding:6px 10px;border-radius:99px;font-size:11px;font-weight:800}button{background:var(--a);color:#07111f;border:0;border-radius:9px;padding:10px 14px;font-weight:800;cursor:pointer}.actions{display:flex;align-items:center;gap:10px}main{max-width:1200px;margin:auto;padding:20px}.notice{background:#2a2110;border:1px solid #8a6720;color:#f9e6b0;padding:12px 15px;border-radius:12px;margin-bottom:16px}.grid{display:grid;grid-template-columns:1.1fr 1fr;gap:15px}.panel{background:linear-gradient(145deg,#111b2e,#0d1729);border:1px solid var(--line);border-radius:16px;padding:20px;min-width:0}.label{font-size:11px;letter-spacing:1.3px;color:var(--a);font-weight:800}.price{font-size:clamp(38px,6vw,58px);font-weight:850;letter-spacing:-2px;margin:8px 0}.change{font-weight:800}.positive{color:var(--g)}.negative{color:var(--r)}.mini{display:grid;grid-template-columns:repeat(4,1fr);gap:9px;margin-top:20px}.mini div{background:#0a1425;border:1px solid var(--line);border-radius:9px;padding:10px}.mini span{display:block;color:var(--m);font-size:12px}.mini b{display:block;margin-top:5px}.range{height:5px;background:linear-gradient(90deg,var(--r),#64748b,var(--g));border-radius:5px;margin:24px 0 8px;position:relative}.range i{position:absolute;left:50%;top:-4px;width:13px;height:13px;border:3px solid var(--a);background:white;border-radius:50%}.range-labels{display:flex;justify-content:space-between;color:var(--m);font-size:12px}.three{display:grid;grid-template-columns:repeat(3,1fr);gap:15px;margin:15px 0}.value{font-size:18px;font-weight:800;margin:12px 0}.three p{min-height:45px}.foot{border-top:1px solid var(--line);padding-top:10px;color:var(--a);font-size:12px}.levels div,.inputs div{display:flex;justify-content:space-between;gap:10px;padding:11px 0;border-bottom:1px solid var(--line)}.levels div:last-child,.inputs div:last-child{border:0}.levels span,.inputs span{color:var(--m);font-size:12px}.current{background:#18304a;padding-left:8px!important;padding-right:8px!important;border-radius:8px}.readiness .inputs{margin-top:8px}.readiness .inputs b{font-size:12px;text-align:right}.readiness .ok{color:var(--g)}.readiness p{margin-top:18px}.testresult{margin-top:12px;white-space:pre-wrap;overflow-wrap:anywhere;color:var(--a);font-size:13px}.footbutton{margin-top:10px}footer{text-align:center;color:var(--m);font-size:12px;padding:22px}@media(max-width:760px){.top{align-items:flex-start;flex-direction:column;padding:20px}.actions{width:100%;justify-content:space-between}main{padding:12px}.grid,.three{grid-template-columns:1fr}.mini{grid-template-columns:repeat(2,1fr)}.panel{padding:16px}.three p{min-height:0}}
.x-controls{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:10px;margin:12px 0}.x-controls select{min-width:0;width:100%;background:#0a1425;color:var(--t);border:1px solid var(--line);border-radius:8px;padding:10px}.x-timeline-wrap{max-width:760px;min-width:0;border:1px solid var(--line);border-radius:10px;padding:12px;overflow:hidden}.x-timeline-wrap iframe{max-width:100%!important}.x-card-title{font-weight:700;margin-bottom:10px;overflow-wrap:anywhere}.x-sources{margin-top:12px;border:1px solid var(--line);border-radius:9px;padding:12px}.x-sources summary{cursor:pointer;font-weight:700}.x-sources #xRadarAccounts>div{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;padding:10px 0;border-bottom:1px solid var(--line)}.x-sources .market-outlook-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:14px 0}.outlook-tile{min-width:0;background:#0a1425;border:1px solid var(--line);border-radius:10px;padding:13px}.outlook-tile span,.outlook-tile small{display:block;color:var(--m);font-size:12px}.outlook-tile b{display:block;font-size:clamp(16px,2.5vw,23px);margin:7px 0;overflow-wrap:anywhere}.outlook-tile small{overflow-wrap:anywhere}.table-scroll{width:100%;overflow-x:auto}.news-impact-table{width:100%;border-collapse:collapse;font-size:13px;min-width:680px}.news-impact-table th,.news-impact-table td{text-align:left;vertical-align:top;padding:11px 9px;border-bottom:1px solid var(--line)}.news-impact-table th{color:var(--a);font-size:11px;text-transform:uppercase;letter-spacing:.5px}.news-impact-table td a{color:var(--a);text-decoration:none}.x-sources{border:1px solid var(--line);border-radius:9px;padding:12px}.x-sources summary{cursor:pointer;font-weight:700}.x-sources #xRadarAccounts>div{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;padding:10px 0;border-bottom:1px solid var(--line)}.x-sources #xRadarAccounts span{overflow-wrap:anywhere}.x-sources a{font-size:13px;text-decoration:none;color:var(--a)}@media(max-width:700px){.market-outlook-grid{grid-template-columns:1fr}.outlook-tile{padding:11px}}</style></head><body><header class="top"><div><div class="eyebrow">MARKET INTELLIGENCE WORKSPACE</div><h1>MCX Natural Gas Radar</h1><p style="margin:0">Daily direction · Intraday plan · Overnight gap research</p></div><div class="actions"><span id="mode" class="pill">LOADING</span><button onclick="loadData()">Refresh</button></div></header><main><div class="notice" id="notice"><b>Live quote integration:</b> main price is sourced from Kotak when available. VWAP, volume, open interest, levels and signals remain demo until separately connected.</div><section class="grid"><article class="panel"><div class="label" id="priceLabel">Natural Gas futures · Kotak quote</div><div class="price" id="price">—</div><div><span id="change" class="change">Change unavailable</span> <span class="muted">· Broker-reported previous close </span><b id="prev">Not connected</b></div><div class="muted" style="margin-top:6px">Contract <b id="contract">—</b> · Expiry <b id="expiry">—</b></div><div class="muted">Updated <span id="updated">—</span> · Quote age <b id="quoteAge">—</b></div><div class="range"><i id="dot"></i></div><div class="range-labels"><span>Low <b id="low">Not connected</b></span><span>High <b id="high">Not connected</b></span></div><div class="mini"><div><span>VWAP · broker quote when available</span><b id="vwap">—</b></div><div><span id="volumeLabel">Volume · broker quote when available</span><b id="volume">—</b></div><div><span>OI · broker quote when available</span><b id="oi">—</b></div><div><span>OI change · broker quote when available</span><b id="oichange">—</b></div></div></article><article class="panel"><div class="label">MARKET CONTEXT · NOT A VALIDATED SIGNAL</div><div class="value" id="bias">WAIT FOR LIVE DATA</div><p id="contextSummary" class="muted">Waiting for verified inputs.</p><p id="reason">Loading snapshot…</p><h2 style="margin-top:22px">Intraday reference levels <span class="muted" id="levelMethod">· unavailable</span></h2><div class="levels"><div><span>Resistance 2</span><b id="r2">—</b></div><div><span>Resistance 1</span><b id="r1">—</b></div><div class="current"><span>Current price</span><b id="lp">—</b></div><div><span>Support 1</span><b id="s1">—</b></div><div><span>Support 2</span><b id="s2">—</b></div></div></article></section><h2 style="margin-top:25px">Three separate decisions</h2><section class="three"><article class="panel"><div class="label">01 · DAILY DIRECTION</div><div class="value" id="daily">Waiting for validated data</div><p>Trend, volatility, levels, global gas move and scheduled catalysts.</p><div class="foot">Bullish / bearish / neutral + invalidation</div></article><article class="panel"><div class="label">02 · INTRADAY ENTRY / EXIT</div><div class="value" id="intra">No trade in demo mode</div><p>Trigger, stop, targets and no-trade conditions before entry.</p><div class="foot">Setup + risk levels</div></article><article class="panel"><div class="label">03 · OVERNIGHT OPENING GAP</div><div class="value" id="overnight">Estimate unavailable</div><p id="overnightDetail">Next MCX open versus prior close. Any proxy is unvalidated and low confidence.</p><div class="foot">Point estimate · range · gap · data timestamp</div></article></section><section class="panel" style="margin-top:15px"><div class="label">KOTAK OPTIONS CHAIN · READ ONLY</div><h2 style="margin-top:8px">Options positioning</h2><p class="muted">Only broker-returned option rows are shown. PCR is not a standalone buy/sell signal.</p><div id="optionsSummary" class="inputs"><div><span>Status</span><b>Checking Kotak options feed…</b></div></div><div id="optionsMessage" class="muted" style="margin-top:10px">No option values should be assumed until the feed schema is verified.</div></section><section class="grid"><article class="panel"><h2>Data connections</h2><div id="inputs" class="inputs"></div><h2 style="margin-top:18px">Global reference drivers</h2><p class="muted">Public reference feeds may be delayed; contextual only, not direct MCX signals.</p><div id="drivers" class="inputs"></div><h2 style="margin-top:18px">10-factor gas assessment</h2><p class="muted">Only verified available inputs contribute to context. Missing feeds remain unavailable.</p><div id="factors" class="inputs"></div><h2 style="margin-top:18px">Market headlines</h2><div id="headlines" class="inputs"></div><h2 style="margin-top:18px">Connection diagnostics</h2><p>This makes one login attempt. It will not place orders or return your credentials.</p><button class="footbutton" onclick="testKotak()">Test Kotak login</button><div id="testresult" class="testresult" role="status"></div><button class="footbutton" onclick="testMcx()">Test MCX Natural Gas quote</button><div id="mcxresult" class="testresult" role="status"></div><button class="footbutton" onclick="testQuoteFields()">Inspect Kotak quote fields</button><div id="fieldresult" class="testresult" role="status"></div></article><article class="panel readiness"><div class="label">SYSTEM READINESS</div><h2>What is verified today</h2><div class="inputs"><div><span>MCX futures quote</span><b class="ok">Connected when Kotak responds</b></div><div><span>Reference market feeds</span><b>Check live status below</b></div><div><span>Support / resistance</span><b>Requires historical candles</b></div><div><span>Trading signals</span><b>Not validated — no trade advice</b></div></div><p class="muted">The radar will only promote a signal after the required data is available and the strategy is tested against historical MCX futures data.</p></article></section><section class="panel" style="margin-top:15px"><div class="label">LIVE-CANDLE MOVEMENT OUTLOOK</div><h2 style="margin-top:8px">Natural Gas short-term forecast</h2><p class="muted">Rule-based estimate from verified Kotak 5-minute candles only. Not a guaranteed prediction.</p><div id="forecastPanel" class="inputs"><div><span>Forecast</span><b>Loading…</b></div></div><p id="forecastWarning" class="muted" style="margin-top:10px">Waiting for verified candles.</p></section><section class="panel" style="margin-top:15px"><div class="label">VERIFIED-CANDLE INDICATORS · DESCRIPTIVE ONLY</div><h2 style="margin-top:8px">Technical indicator status</h2><p class="muted">Calculated only from stored Kotak SFeed candles. No synthetic data and no trade signal.</p><div id="indicatorPanel" class="inputs"><div><span>Indicator engine</span><b>Loading…</b></div></div></section><section class="panel" id="xRadarPanel" style="margin-top:15px"><div class="label">LIVE PRICE + NEWS IMPACT</div><h2 style="margin-top:8px">Natural Gas Market Outlook</h2><p class="muted">Current MCX quote plus recent public gas news. Headline impact is a preliminary keyword classification, not a validated prediction.</p><div class="market-outlook-grid"><div class="outlook-tile"><span>Current MCX price</span><b id="outlookPrice">Checking Kotak…</b><small id="outlookContract">Waiting for live quote</small></div><div class="outlook-tile"><span>MCX change</span><b id="outlookChange">—</b><small id="outlookTimestamp">Quote timestamp unavailable</small></div><div class="outlook-tile"><span>News bias</span><b id="newsBias">Analysing…</b><small id="newsConfidence">Waiting for headlines</small></div></div><div id="outlookSummary" class="notice" style="margin-top:12px">Loading price and news. No forecast without verified data.</div><h2 style="margin-top:20px">News impact table</h2><div class="table-scroll"><table class="news-impact-table"><thead><tr><th>Time / source</th><th>Headline</th><th>Possible gas impact</th><th>Reason / caveat</th></tr></thead><tbody id="newsImpactRows"><tr><td colspan="4">Loading headlines…</td></tr></tbody></table></div><p class="muted" id="outlookMethod" style="margin-top:12px">Loading data coverage…</p><details class="x-sources" style="margin-top:12px"><summary>20 X sources — collection status</summary><p class="muted">The watchlist is configured, but actual post text is not currently retrieved into the backend. X embeds alone do not provide dependable post text for analysis, so this engine will not pretend it analysed those posts.</p><div id="xRadarAccounts" class="inputs"></div></details></section>
<footer>MCX Natural Gas Radar · responsive starter · no order placement</footer></main><script>async function loadOptions(){const el=document.getElementById('optionsSummary'),msg=document.getElementById('optionsMessage');try{const r=await fetch('/api/kotak/options',{cache:'no-store'});if(!r.ok)throw Error('HTTP '+r.status);const d=await r.json(),f=v=>v==null?'Unavailable':Number(v).toLocaleString('en-IN',{maximumFractionDigits:2});const top=a=>Array.isArray(a)&&a.length?a.slice(0,3).map(x=>f(x.strike)+' (OI '+f(x.oi)+')').join(' · '):'Unavailable';const rows=[['Feed status',d.status||'Unavailable'],['Parsed option rows',d.options_rows_parsed==null?'Unavailable':d.options_rows_parsed],['Call open interest',f(d.call_oi)],['Put open interest',f(d.put_oi)],['PCR · OI',f(d.pcr_oi)],['Call volume',f(d.call_volume)],['Put volume',f(d.put_volume)],['PCR · volume',f(d.pcr_volume)],['Highest call OI strikes',top(d.top_call_oi_strikes)],['Highest put OI strikes',top(d.top_put_oi_strikes)],['IV fields',d.iv_available?'Present':'Unavailable'],['OI-change fields',d.oi_change_available?'Present':'Unavailable'],['Checked (UTC)',d.checked_at_utc||'Not available']];el.innerHTML=rows.map(([k,v])=>'<div><span>'+k+'</span><b>'+v+'</b></div>').join('');msg.textContent=(d.message||'No additional feed details')+' Source: '+(d.source||'Kotak Neo')+'. Synthetic data: '+(d.synthetic===false?'No':'not confirmed')+'.';}catch(e){el.innerHTML='<div><span>Feed status</span><b>Unavailable</b></div>';msg.textContent='Options feed could not be read. No PCR or strike levels are inferred.'}}async function loadForecast(){const el=document.getElementById('forecastPanel'),w=document.getElementById('forecastWarning');try{const r=await fetch('/api/forecast',{cache:'no-store'});const d=await r.json();const rows=[['Direction',d.direction||'Unavailable'],['Horizon',d.horizon||'Next 30–60 minutes'],['Confidence',d.confidence_label||'Unavailable'],['Trend score',d.score==null?'Unavailable':d.score],['Latest close',d.latest_close==null?'Unavailable':Number(d.latest_close).toLocaleString('en-IN')],['EMA 9 / EMA 21',d.ema_9==null||d.ema_21==null?'Insufficient candles':Number(d.ema_9).toFixed(2)+' / '+Number(d.ema_21).toFixed(2)],['RSI 14',d.rsi_14==null?'Unavailable':d.rsi_14],['ATR 14',d.atr_14==null?'Unavailable':d.atr_14],['Verified candles',d.candle_count||0],['Invalidation',d.invalidation||'Unavailable']];el.innerHTML=rows.map(([k,v])=>'<div><span>'+k+'</span><b>'+v+'</b></div>').join('');w.textContent=d.warning||'No forecast available.'}catch(e){el.innerHTML='<div><span>Forecast</span><b>Unavailable</b></div>';w.textContent='Forecast endpoint unavailable; no direction fabricated.'}}async function loadIndicators(){let el=document.getElementById('indicatorPanel');try{let r=await fetch('/api/indicators?interval=5m&limit=300',{cache:'no-store'});let d=await r.json();const f=v=>v==null?'Unavailable':Number(v).toLocaleString('en-IN',{maximumFractionDigits:2});el.innerHTML=[['Status',d.status||'Unavailable'],['Verified candles',d.count==null?'0':d.count],['Latest close',f(d.latest_close)],['EMA 9',f(d.ema_9)],['EMA 21',f(d.ema_21)],['RSI 14',f(d.rsi_14)],['ATR 14',f(d.atr_14)],['Latest candle UTC',d.latest_candle_utc||'Not available']].map(x=>'<div><span>'+x[0]+'</span><b>'+x[1]+'</b></div>').join('')+(d.warning?'<p class="muted">'+d.warning+'</p>':'')+(d.message?'<p class="muted">'+d.message+'</p>':'')}catch(e){el.textContent='Indicator status unavailable; the app may be redeploying.'}}async function loadData(){try{let r=await fetch('/api/snapshot',{cache:'no-store'});if(!r.ok)throw Error('API '+r.status);let d=await r.json(),f=v=>v==null?'—':Number(v).toLocaleString('en-IN',{maximumFractionDigits:2}),$=id=>document.getElementById(id);$('mode').textContent=d.mode;$('priceLabel').textContent=d.live_quote?'Natural Gas futures · Kotak quote':'Natural Gas futures · live quote unavailable';$('notice').innerHTML=d.live_quote?'<b>Kotak quote connected:</b> Main price and any OHLC, change, VWAP or volume fields shown come from Kotak when returned. Global drivers are contextual; trading signals and support/resistance are not validated.':'<b>Live quote unavailable:</b> no synthetic price is displayed. Refresh after the Kotak connection is restored.';$('price').textContent='₹'+f(d.price);$('prev').textContent=d.previous_close==null?'Not connected':'₹'+f(d.previous_close);$('change').textContent=d.change==null?'Change unavailable':(d.change>=0?'+':'')+'₹'+f(d.change)+' ('+(d.change_pct>=0?'+':'')+f(d.change_pct)+'%)';$('change').className='change '+(d.change==null?'':(d.change>=0?'positive':'negative'));$('contract').textContent=d.live_quote?(d.contract||'Natural Gas futures'):'Demo placeholder';$('expiry').textContent=d.live_quote?(d.expiry||'Not returned'):'—';const quoteMs=Date.parse(d.timestamp_utc||'');const quoteAge=Number.isFinite(quoteMs)?Math.max(0,Math.floor((Date.now()-quoteMs)/1000)):null;$('quoteAge').textContent=d.live_quote?(quoteAge==null?'Unknown':quoteAge+' sec'):'Demo';$('updated').textContent=(d.live_quote?'Kotak quote · ':'Demo snapshot · ')+new Date(d.timestamp_utc).toLocaleTimeString();$('low').textContent=d.day_low==null?'Not connected':'₹'+f(d.day_low);$('high').textContent=d.day_high==null?'Not connected':'₹'+f(d.day_high);$('vwap').textContent=d.vwap==null?'Unavailable':'₹'+f(d.vwap);$('volumeLabel').textContent=d.volume_kind==='last_trade'?'Last traded quantity/volume · broker field':'Volume · broker field';$('volume').textContent=d.volume==null?'Unavailable':f(d.volume);$('oi').textContent=d.open_interest==null?'Unavailable':f(d.open_interest);$('oichange').textContent=d.oi_change==null?'Unavailable':f(d.oi_change);$('bias').textContent=d.context?d.context.label:d.signals.daily_bias;$('contextSummary').textContent=d.context?d.context.warning:d.signals.reason;$('daily').textContent=d.signals.daily_bias;$('intra').textContent=d.signals.intraday_setup;$('overnight').textContent=d.signals.overnight_gap;const oe=d.opening_estimate||{};$('overnightDetail').textContent=oe.point_estimate!=null?('Estimate ₹'+f(oe.point_estimate)+' · range ₹'+f(oe.range_low)+'–₹'+f(oe.range_high)+' · gap '+(oe.estimated_gap_rupees>=0?'+':'')+'₹'+f(oe.estimated_gap_rupees)+' ('+f(oe.estimated_gap_pct)+'%) · '+(oe.confidence||'LOW')+' · '+(oe.method||'')):(oe.method||'No reliable numeric estimate: required reference data unavailable.');$('reason').textContent=d.signals.reason;$('lp').textContent='₹'+f(d.price);$('levelMethod').textContent=d.levels&&d.levels.method?'· '+d.levels.method:'· unavailable';for(let k of ['r1','r2','s1','s2'])$(k).textContent=d.levels&&d.levels[{r1:'resistance_1',r2:'resistance_2',s1:'support_1',s2:'support_2'}[k]]!=null?'₹'+f(d.levels[{r1:'resistance_1',r2:'resistance_2',s1:'support_1',s2:'support_2'}[k]]):'Unavailable';$('inputs').innerHTML=Object.entries(d.inputs).map(([k,v])=>'<div><span>'+k.replaceAll('_',' ')+'</span><b>'+v+'</b></div>').join('');const gd=d.global_drivers||{};const rows=[['Henry Hub reference',gd.henry_hub_reference?('USD '+f(gd.henry_hub_reference.price)+' ('+(gd.henry_hub_reference.source||'reference feed')+')'):'Unavailable'],['US Gulf weather',gd.us_gulf_weather?'3-day forecast available':'Unavailable'],['EIA storage · weekly',gd.eia_storage&&gd.eia_storage.status==='connected'?(gd.eia_storage.value_bcf+' Bcf · report '+gd.eia_storage.period): (gd.eia_storage?gd.eia_storage.note||gd.eia_storage.status:'Unavailable')],['Crude oil reference',gd.crude_oil_reference?('USD '+f(gd.crude_oil_reference.price)+' ('+(gd.crude_oil_reference.change_pct>=0?'+':'')+f(gd.crude_oil_reference.change_pct)+'%)'):'Unavailable'],['USD/INR reference',gd.usd_inr_reference?('₹'+f(gd.usd_inr_reference.price)+' ('+(gd.usd_inr_reference.change_pct>=0?'+':'')+f(gd.usd_inr_reference.change_pct)+'%)'):'Unavailable'],['Weekly storage change',gd.eia_storage&&gd.eia_storage.weekly_change_bcf!=null?((gd.eia_storage.weekly_change_bcf>0?'+':'')+gd.eia_storage.weekly_change_bcf+' Bcf vs prior report'):'Not available'],['Storage consensus / surprise',gd.eia_storage&&gd.eia_storage.consensus_bcf!=null?('Consensus '+gd.eia_storage.consensus_bcf+' Bcf · surprise '+gd.eia_storage.surprise_bcf+' Bcf'):'Consensus feed not connected · no surprise calculated'],['Best bid',d.best_bid==null?'Unavailable':'₹'+f(d.best_bid)+' · qty '+f(d.best_bid_qty)],['Best ask',d.best_ask==null?'Unavailable':'₹'+f(d.best_ask)+' · qty '+f(d.best_ask_qty)],['Lower circuit',d.circuit_lower==null?'Not returned':'₹'+f(d.circuit_lower)],['Upper circuit',d.circuit_upper==null?'Not returned':'₹'+f(d.circuit_upper)],['52-week low / high',d.week52_low==null&&d.week52_high==null?'Not returned':f(d.week52_low)+' / '+f(d.week52_high)],['MCX historical candles','Authorized source required']];$('drivers').innerHTML=rows.map(([k,v])=>'<div><span>'+k+'</span><b>'+v+'</b></div>').join('');const fa=d.factor_assessment||{},ff=Array.isArray(fa.factors)?fa.factors:[];$('factors').innerHTML='<div><span>Overall context</span><b>'+ (fa.label||'Unavailable')+'</b></div><div><span>Factors available</span><b>'+(fa.available_factors??0)+' / '+(fa.total_factors??10)+'</b></div>'+ff.map(x=>'<div><span>'+x.factor+' · '+(x.status||'unknown')+'</span><b>'+x.direction+' · weight '+x.weight+'</b></div>').join('')+'<p class=\"muted\">'+(fa.warning||'No factor assessment available.')+'</p>';const news=gd.news&&gd.news.items?gd.news.items:[];$('headlines').innerHTML=news.length?news.map(n=>'<div><span>'+n.published+'</span><b><a style="color:var(--a)" target="_blank" rel="noopener" href="'+n.url+'">'+n.title+'</a></b></div>').join(''):'<div><span>News feed</span><b>Unavailable from service</b></div>';let span=(d.day_high!=null&&d.day_low!=null)?d.day_high-d.day_low:0;$('dot').style.left=(span>0?Math.max(0,Math.min(100,(d.price-d.day_low)/span*100)):50)+'%'}catch(e){document.getElementById('mode').textContent='API ERROR';document.getElementById('reason').textContent=e.message}finally{loadIndicators()}}async function testMcx(){let el=document.getElementById('mcxresult'),b=document.querySelectorAll('.footbutton')[1];b.disabled=true;b.textContent='Checking MCX…';el.textContent='Looking up Natural Gas futures and requesting a quote…';try{let r=await fetch('/api/kotak/mcx-test',{method:'POST',cache:'no-store'});let d=await r.json();el.textContent=(d.message||'Quote test completed')+(d.symbol?'\nContract: '+d.symbol:'')+(d.ltp?'\nLive/last price: '+d.ltp:'')+(d.timestamp?'\nChecked: '+d.timestamp:'')}catch(e){el.textContent='MCX quote test failed. Refresh and try again later.'}finally{b.disabled=false;b.textContent='Test MCX Natural Gas quote'}}async function testQuoteFields(){let el=document.getElementById('fieldresult');el.textContent='Inspecting safe field metadata…';try{let r=await fetch('/api/kotak/quote-diagnostics',{cache:'no-store'});let d=await r.json();el.textContent=JSON.stringify(d,null,2)}catch(e){el.textContent='Quote diagnostics unavailable; try again after refresh.'}}async function testKotak(){let el=document.getElementById('testresult'),b=document.querySelector('.footbutton');b.disabled=true;b.textContent='Testing…';el.textContent='Checking Kotak authentication…';try{let r=await fetch('/api/kotak/test',{method:'POST',cache:'no-store'});let d=await r.json();el.textContent=d.message+(d.code?'\nCode: '+d.code:'');}catch(e){el.textContent='Test request failed. Please refresh and try again.'}finally{b.disabled=false;b.textContent='Test Kotak login'}}function loadXWidgets(){if(window.twttr&&window.twttr.widgets){window.twttr.widgets.load(document.getElementById('xRadarTimeline'));return}if(document.getElementById('twitter-widget-script'))return;const sc=document.createElement('script');sc.id='twitter-widget-script';sc.src='https://platform.twitter.com/widgets.js';sc.async=true;sc.charset='utf-8';sc.onload=()=>{if(window.twttr&&window.twttr.widgets)window.twttr.widgets.load(document.getElementById('xRadarTimeline'))};sc.onerror=()=>{const st=document.getElementById('xRadarStatus');if(st)st.textContent='X timeline widget could not load; try account profile links.'};document.head.appendChild(sc)}let xRadarData=null;function renderXTimeline(){const select=document.getElementById('xRadarSelect'),wrap=document.getElementById('xRadarTimeline');if(!xRadarData||!select.value){wrap.innerHTML='<p class="muted">No account selected.</p>';return}const a=(xRadarData.accounts||[]).find(v=>v.handle===select.value);if(!a){wrap.innerHTML='<p class="muted">Account unavailable.</p>';return}wrap.replaceChildren();const title=document.createElement('div');title.className='x-card-title';title.textContent='@'+a.handle+' · '+a.focus;const timeline=document.createElement('a');timeline.className='twitter-timeline';timeline.href=a.profile_url;timeline.setAttribute('data-height','520');timeline.setAttribute('data-theme','dark');timeline.setAttribute('data-chrome','noheader nofooter noborders transparent');timeline.textContent='Posts by @'+a.handle;const fallback=document.createElement('p');fallback.className='muted';const profile=document.createElement('a');profile.href=a.profile_url;profile.target='_blank';profile.rel='noopener noreferrer';profile.textContent='Open profile on X';profile.style.color='var(--a)';fallback.append(profile);wrap.append(title,timeline,fallback);loadXWidgets()}function scoreHeadline(item){const t=((item.title||'')+' '+(item.category||'')).toLowerCase(),bull=['cold','colder','heating demand','freeze','outage','disruption','storage draw','production falls','supply cut'],bear=['warm','warmer','mild weather','storage build','injection','production rises','record production','supply rises','demand falls','exports fall','feedgas drops'];let score=0,why=[];for(const k of bull)if(t.includes(k)){score+=2;why.push(k+' may support prices')}for(const k of bear)if(t.includes(k)){score-=2;why.push(k+' may pressure prices')}return {score,why:[...new Set(why)]}}async function loadXRadar(){const method=document.getElementById('outlookMethod'),rows=document.getElementById('newsImpactRows');try{const [nr,sr,fr]=await Promise.all([fetch('/api/x-radar',{cache:'no-store'}),fetch('/api/snapshot',{cache:'no-store'}),fetch('/api/forecast',{cache:'no-store'})]);if(!nr.ok)throw Error('News feed HTTP '+nr.status);const data=await nr.json(),snap=sr.ok?await sr.json():{},forecast=fr.ok?await fr.json():{},q=snap.price;document.getElementById('outlookPrice').textContent=q==null?'Unavailable — Kotak quote missing':'₹'+Number(q).toLocaleString('en-IN',{maximumFractionDigits:2});document.getElementById('outlookContract').textContent=snap.contract||snap.mode||'MCX Natural Gas futures';document.getElementById('outlookChange').textContent=snap.change_pct==null?'Unavailable':(snap.change_pct>0?'+':'')+Number(snap.change_pct).toFixed(2)+'%';document.getElementById('outlookTimestamp').textContent=snap.timestamp_utc?'Quote UTC: '+new Date(snap.timestamp_utc).toLocaleString():'Quote timestamp unavailable';const items=((data.news||{}).items||[]).map(x=>({...x,...scoreHeadline(x)})),total=items.reduce((n,x)=>n+x.score,0),pos=items.filter(x=>x.score>0).length,neg=items.filter(x=>x.score<0).length,bias=total>=3?'Bullish news bias':total<=-3?'Bearish news bias':'Mixed / unclear';document.getElementById('newsBias').textContent=(forecast.direction||'')+' · '+bias;document.getElementById('newsConfidence').textContent=(forecast.confidence_label||'Technical confidence unavailable')+' · '+items.length+' headlines ('+pos+' bullish / '+neg+' bearish);document.getElementById('outlookSummary').textContent=(snap.change_pct==null?'Current MCX change unavailable.':snap.change_pct>0?'MCX quote is up '+Number(snap.change_pct).toFixed(2)+'%.':snap.change_pct<0?'MCX quote is down '+Math.abs(Number(snap.change_pct)).toFixed(2)+'%.':'MCX quote is unchanged.')+' Technical model: '+(forecast.direction||'unavailable')+'. News scan: '+bias+'. '+(forecast.warning||'Technical estimate unavailable.')+' Actual X post text is not yet included.';rows.replaceChildren();for(const it of items){const tr=document.createElement('tr'),time=document.createElement('td'),headline=document.createElement('td'),impact=document.createElement('td'),reason=document.createElement('td'),a=document.createElement('a');time.textContent=(it.published||'Time unavailable').replace('T',' ').slice(0,16)+' · '+(it.source||'News');a.href=it.url;a.target='_blank';a.rel='noopener noreferrer';a.textContent=it.title||'Untitled headline';headline.append(a);impact.textContent=it.score>0?'Potentially bullish':it.score<0?'Potentially bearish':'Unclear / neutral';reason.textContent=it.why.length?it.why.join('; '):'Headline alone does not establish a clear gas impact.';tr.append(time,headline,impact,reason);rows.append(tr)}if(!items.length)rows.innerHTML='<tr><td colspan="4">No recent news available; no forecast generated.</td></tr>';const ac=document.getElementById('xRadarAccounts');ac.replaceChildren();for(const x of data.accounts||[]){const row=document.createElement('div'),label=document.createElement('span'),right=document.createElement('b'),a=document.createElement('a');label.textContent='@'+x.handle+' · '+x.focus;a.href=x.profile_url;a.target='_blank';a.rel='noopener noreferrer';a.textContent='Open on X';right.append(a);row.append(label,right);ac.append(row)}method.textContent='News: public Google News RSS · '+(data.checked_at_utc?new Date(data.checked_at_utc).toLocaleTimeString():'time unavailable')+'. MCX price: Kotak only. X posts are not yet included.'}catch(e){method.textContent='Analysis refresh failed: '+e.message;rows.innerHTML='<tr><td colspan="4">News or snapshot unavailable. No prediction fabricated.</td></tr>';document.getElementById('outlookSummary').textContent='Could not refresh current price and news. Retry when data feeds recover.'}}setInterval(loadXRadar,300000);loadXRadar();loadData();loadOptions();loadForecast();setInterval(loadForecast,30000);setInterval(loadData,30000);setInterval(loadOptions,30000);</script></body></html>"""


def _get_kotak_client():
    """Reuse an authenticated session briefly instead of re-login on every refresh."""
    now = time.monotonic()
    client = _kotak_client_cache.get("client")
    if client is not None and now - _kotak_client_cache.get("created_at", 0) < _KOTAK_CLIENT_CACHE_SECONDS:
        return client
    client = create_authenticated_client()
    _kotak_client_cache["created_at"] = now
    _kotak_client_cache["client"] = client
    return client


def get_live_mcx_quote():
    """Return a cached Kotak MCX Natural Gas quote; never place orders."""
    now = time.monotonic()
    cached = _quote_cache.get("data")
    if cached and now - _quote_cache.get("checked_at", 0) < _QUOTE_CACHE_SECONDS:
        return cached
    client = _get_kotak_client()
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
        try: return float(value) if value not in (None, "") else None
        except (TypeError, ValueError): return None
    ohlc = quote.get("ohlc") if isinstance(quote.get("ohlc"), dict) else {}
    # Kotak "all" quotes can carry depth, circuit limits and 52-week fields too.
    # Normalize only values actually returned; never fabricate missing market data.
    depth = quote.get("depth") if isinstance(quote.get("depth"), dict) else {}
    buy_rows = depth.get("buy") or quote.get("buy") or []
    sell_rows = depth.get("sell") or quote.get("sell") or []
    best_bid = buy_rows[0] if isinstance(buy_rows, list) and buy_rows and isinstance(buy_rows[0], dict) else {}
    best_ask = sell_rows[0] if isinstance(sell_rows, list) and sell_rows and isinstance(sell_rows[0], dict) else {}
    # Treat zero/missing broker fields as unavailable; zero is not a valid LTP/depth/VWAP reading.
    def positive_or_none(value):
        parsed = number(value)
        return parsed if parsed is not None and parsed > 0 else None
    # Kotak SDK/API versions expose some fields under different documented names.
    # Preserve the raw broker value and normalize aliases; never calculate/fabricate volume or OI.
    raw_volume = quote.get("volume")
    volume_kind = "total" if raw_volume not in (None, "") else "last_trade"
    if raw_volume in (None, ""):
        raw_volume = quote.get("total_volume") or quote.get("total_traded_volume") or quote.get("last_volume")
    raw_oi = quote.get("open_interest")
    if raw_oi in (None, ""):
        raw_oi = quote.get("open_int")
    if raw_oi in (None, ""):
        raw_oi = quote.get("oi")
    raw_vwap = quote.get("avg_cost")
    if raw_vwap in (None, ""):
        raw_vwap = quote.get("average_price") or quote.get("average_traded_price") or quote.get("avg_price")
    raw_oi_change = quote.get("oi_change")
    if raw_oi_change in (None, ""):
        raw_oi_change = quote.get("open_int_change") or quote.get("change_in_oi")
    result = {"price": positive_or_none(ltp), "contract": symbol or neo_symbol, "expiry": expiry,
              "exchange_segment": segment, "instrument_token": token,
              "timestamp_utc": datetime.now(timezone.utc).isoformat(), "live_quote": True,
              "quote_fields_present": sorted(str(k) for k in quote.keys() if isinstance(k, str)),
              "previous_close": number(ohlc.get("close")), "day_open": number(ohlc.get("open")),
              "day_high": number(ohlc.get("high")), "day_low": number(ohlc.get("low")),
              "change": number(quote.get("change")), "change_pct": number(quote.get("per_change")),
              "volume": number(raw_volume), "volume_kind": volume_kind, "vwap": positive_or_none(raw_vwap),
              "open_interest": number(raw_oi), "oi_change": number(raw_oi_change),
              "best_bid": positive_or_none(best_bid.get("price") or best_bid.get("p")), "best_bid_qty": positive_or_none(best_bid.get("quantity") or best_bid.get("qty") or best_bid.get("q")),
              "best_ask": positive_or_none(best_ask.get("price") or best_ask.get("p")), "best_ask_qty": positive_or_none(best_ask.get("quantity") or best_ask.get("qty") or best_ask.get("q")),
              "circuit_lower": number(quote.get("lower_circuit") or quote.get("lowerCircuitLimit") or quote.get("lower_circuit_limit")),
              "circuit_upper": number(quote.get("upper_circuit") or quote.get("upperCircuitLimit") or quote.get("upper_circuit_limit")),
              "week52_low": number(quote.get("52w_low") or quote.get("low_52_week") or quote.get("low52")),
              "week52_high": number(quote.get("52w_high") or quote.get("high_52_week") or quote.get("high52"))}
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
        last_close = float(closes[-1])
        prior_close = float(closes[-2]) if len(closes) > 1 else float(meta.get("chartPreviousClose", last_close))
        change_pct = ((last_close / prior_close) - 1) * 100 if prior_close else None
        return {"symbol": symbol, "price": float(meta.get("regularMarketPrice", last_close)),
                "previous_close": float(meta.get("chartPreviousClose", prior_close)),
                "change_pct": change_pct,
                "currency": meta.get("currency"),
                "timestamp": datetime.fromtimestamp(meta.get("regularMarketTime", time.time()), timezone.utc).isoformat(),
                "source": "Yahoo Finance chart endpoint; reference data, may be delayed"}
    except Exception:
        return None


def _eia_storage():
    """Fetch EIA's weekly storage series; cache it because the report updates weekly."""
    now = time.monotonic()
    cached = _eia_cache.get("data")
    if cached and now - _eia_cache.get("checked_at", 0) < _EIA_CACHE_SECONDS:
        return cached
    key = os.getenv("EIA_API_KEY", "").strip()
    if not key:
        result = {"status":"api_key_required","release_frequency":"weekly",
                  "note":"EIA storage is weekly, not an intraday feed. Add EIA_API_KEY in Render to load official observations."}
        _eia_cache.update(checked_at=now, data=result)
        return result
    import urllib.parse
    params = urllib.parse.urlencode({
        "api_key": key, "frequency":"weekly", "data[0]":"value",
        "facets[series][]":"NW2_EPG0_SWO_R48_BCF",
        "sort[0][column]":"period", "sort[0][direction]":"desc",
        "offset":"0", "length":"3"
    })
    payload = _get_json("https://api.eia.gov/v2/natural-gas/stor/wkly/data/?"+params, timeout=6)
    try:
        rows = payload["response"]["data"]
        if not rows:
            result = {"status":"empty","release_frequency":"weekly","note":"EIA returned no storage observations."}
        else:
            latest = rows[0]
            previous = rows[1] if len(rows)>1 else None
            latest_value = float(latest["value"]) if latest.get("value") is not None else None
            previous_value = float(previous["value"]) if previous and previous.get("value") is not None else None
            result = {"status":"connected","release_frequency":"weekly",
                "series":"Lower 48 working gas in underground storage","period":latest.get("period"),
                "value_bcf":latest_value,"previous_period":previous.get("period") if previous else None,
                "previous_value_bcf":previous_value,
                "weekly_change_bcf":round(latest_value-previous_value, 2) if latest_value is not None and previous_value is not None else None,
                "consensus_bcf":None,"surprise_bcf":None,
                "consensus_status":"not_connected",
                "note":"Consensus is not connected, so no storage-surprise value is calculated. Use the report date and weekly change; do not treat this as live intraday data.",
                "source":"U.S. EIA API v2","checked_at_utc":datetime.now(timezone.utc).isoformat()}
    except Exception:
        result = {"status":"feed_unavailable","release_frequency":"weekly",
                  "note":"EIA endpoint did not return the expected series; verify API key and series access."}
    _eia_cache.update(checked_at=now, data=result)
    return result


def _news_headlines():
    """Read a small set of current natural-gas headlines from a public RSS feed."""
    from urllib.request import Request, urlopen
    import xml.etree.ElementTree as ET
    url = "https://news.google.com/rss/search?q=natural+gas+LNG+storage+weather+when:7d&hl=en-US&gl=US&ceid=US:en"
    try:
        req = Request(url, headers={"User-Agent":"MCX-Natural-Gas-Radar/1.0"})
        with urlopen(req, timeout=5) as response:
            root = ET.fromstring(response.read())
        items = []
        for item in root.findall("./channel/item")[:6]:
            items.append({"title":item.findtext("title","").strip(),
                          "published":item.findtext("pubDate",""),
                          "url":item.findtext("link",""),
                          "source":"Google News RSS"})
        return {"status":"connected" if items else "empty","items":items,
                "checked_at_utc":datetime.now(timezone.utc).isoformat()}
    except Exception:
        return {"status":"feed_unavailable","items":[],"note":"Public news RSS could not be reached from the service."}


def _global_drivers():
    """Fetch cached public reference drivers. These are context, not direct MCX signals."""
    now = time.monotonic()
    if _driver_cache["data"] and now - _driver_cache["checked_at"] < _DRIVER_CACHE_SECONDS:
        return _driver_cache["data"]
    henry = _yahoo_last("NG=F")
    crude = _yahoo_last("CL=F")
    usd_inr = _yahoo_last("INR=X")
    weather = _get_json("https://api.open-meteo.com/v1/forecast?latitude=30.10&longitude=-91.10&daily=temperature_2m_mean,temperature_2m_min,temperature_2m_max&temperature_unit=fahrenheit&forecast_days=3&timezone=America%2FChicago")
    weather_summary = None
    try:
        daily = weather["daily"]
        weather_summary = {"location":"Henry Hub area, Louisiana","dates":daily["time"],
                           "mean_f":daily["temperature_2m_mean"],"min_f":daily["temperature_2m_min"],
                           "max_f":daily["temperature_2m_max"],"source":"Open-Meteo forecast API"}
    except Exception:
        pass
    eia = _eia_storage()
    news = _news_headlines()
    result = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "henry_hub_reference":henry,"us_gulf_weather":weather_summary,
              "eia_storage":eia,"news":news,
              "mcx_historical":{"status":"unavailable_from_kotak_api","note":"Kotak Neo historical-data docs exclude MCX futures; use an authorized MCX historical-data provider for research-grade candles."}}
    _driver_cache["checked_at"], _driver_cache["data"] = now, result
    return result


def _factor_assessment(live_quote, drivers):
    """Expose the full ten-factor framework while scoring only evidence-backed inputs."""
    factors = []

    def add(name, direction, weight, evidence, source, available=True, status=None):
        factors.append({
            "factor": name,
            "direction": direction if available else "unavailable",
            "weight": float(weight) if available else 0.0,
            "evidence": evidence,
            "source": source,
            "available": bool(available),
            "status": status or ("available" if available else "not_connected"),
        })

    # 1. MCX session price action: a quote is context, not a trend by itself.
    opened = live_quote.get("day_open") if live_quote else None
    price = live_quote.get("price") if live_quote else None
    if isinstance(opened, (int, float)) and isinstance(price, (int, float)) and opened > 0:
        pct = (price / opened - 1) * 100
        direction = "bullish" if pct > 0.15 else "bearish" if pct < -0.15 else "neutral"
        add("MCX price vs session open", direction, 2 if direction != "neutral" else 0,
            f"Price {price:.2f}; open {opened:.2f}; {pct:+.2f}%",
            "Kotak Neo quote")
    else:
        add("MCX price vs session open", "unavailable", 0,
            "A verified price and session open are both required", "Kotak Neo", False)

    # 2. Henry Hub reference price. Public reference may be delayed.
    hh = drivers.get("henry_hub_reference") if isinstance(drivers, dict) else None
    if hh and isinstance(hh.get("change_pct"), (int, float)):
        v = float(hh["change_pct"])
        direction = "bullish" if v > 0.25 else "bearish" if v < -0.25 else "neutral"
        add("Henry Hub reference move", direction, 1 if direction != "neutral" else 0,
            f"Reference move {v:+.2f}%; check timestamp and contract context",
            hh.get("source", "Public reference feed"))
    else:
        add("Henry Hub reference move", "unavailable", 0,
            "No verified current reference quote", "Public reference feed", False)

    # 3. EIA storage. Do not manufacture a surprise without verified consensus/seasonal norm.
    eia = drivers.get("eia_storage") if isinstance(drivers, dict) else None
    if eia and eia.get("status") == "connected" and isinstance(eia.get("weekly_change_bcf"), (int, float)):
        add("EIA weekly storage", "context_only", 0,
            f"Report period {eia.get('period')}; weekly change {eia['weekly_change_bcf']:+.1f} Bcf; consensus/seasonal benchmark not connected",
            eia.get("source", "U.S. EIA"), True, "context_only")
    else:
        add("EIA weekly storage", "unavailable", 0,
            "Official current series unavailable; no storage surprise inferred", "U.S. EIA", False)

    # 4. Weather proxy; Gulf-area minimum temperature is not a full US HDD/CDD model.
    weather = drivers.get("us_gulf_weather") if isinstance(drivers, dict) else None
    mins = [v for v in (weather or {}).get("min_f", []) if isinstance(v, (int, float))]
    if len(mins) >= 2:
        delta = mins[-1] - mins[0]
        direction = "bullish" if delta <= -8 else "bearish" if delta >= 8 else "neutral"
        add("US Gulf weather proxy", direction, 0.5 if direction != "neutral" else 0,
            f"Three-day minimum-temperature change {delta:+.1f}°F; regional proxy only",
            weather.get("source", "Open-Meteo"), True, "low_relevance_proxy")
    else:
        add("US Gulf weather proxy", "unavailable", 0,
            "Forecast temperature series unavailable or incomplete", "Open-Meteo", False)

    # 5–9. These require dedicated, timestamped source integrations.
    add("LNG exports and terminal flows", "unavailable", 0,
        "No verified current LNG feed connected; no directional assumption", "LNG terminal/export feed", False)
    add("US dry gas production", "unavailable", 0,
        "No verified current production observation connected", "EIA / authorized production feed", False)
    add("Pipeline flows and outages", "unavailable", 0,
        "No verified pipeline nominations, flows, or outage feed connected", "Pipeline operator / authorized feed", False)
    add("US demand and power burn", "unavailable", 0,
        "No verified demand/power-burn series connected", "EIA / authorized demand feed", False)
    add("CFTC positioning and seasonality", "unavailable", 0,
        "Positioning and historical seasonal percentile are not connected; no estimate fabricated", "CFTC / verified historical dataset", False)

    # 10. Technical trend from genuine stored Kotak SFeed candles only.
    try:
        candle_result = get_candles(interval="5m", limit=30)
        closes = [float(c["close"]) for c in candle_result.get("candles", [])
                  if isinstance(c.get("close"), (int, float)) and c["close"] > 0]
    except Exception:
        closes = []
    if len(closes) >= 21:
        def ema(values, period):
            alpha = 2 / (period + 1)
            value = values[0]
            for item in values[1:]:
                value = alpha * item + (1 - alpha) * value
            return value
        ema9, ema21 = ema(closes[-min(len(closes), 27):], 9), ema(closes[-min(len(closes), 63):], 21)
        last = closes[-1]
        direction = "bullish" if last > ema9 > ema21 else "bearish" if last < ema9 < ema21 else "neutral"
        add("MCX verified 5-minute technical trend", direction, 1 if direction != "neutral" else 0,
            f"Last close {last:.2f}; EMA9 {ema9:.2f}; EMA21 {ema21:.2f}; {len(closes)} stored candles",
            "Kotak Neo SFeed stored candles", True, "descriptive_not_backtested")
    else:
        add("MCX verified 5-minute technical trend", "unavailable", 0,
            f"Need at least 21 genuine stored 5-minute closes; found {len(closes)}",
            "Kotak Neo SFeed stored candles", False)

    directional = [f for f in factors if f["available"] and f["weight"] > 0
                   and f["direction"] in ("bullish", "bearish", "neutral")]
    score = round(sum(f["weight"] if f["direction"] == "bullish"
                      else -f["weight"] if f["direction"] == "bearish" else 0
                      for f in directional), 2)
    total_weight = round(sum(f["weight"] for f in directional), 2)
    label = "WAIT — insufficient verified directional inputs"
    if total_weight >= 2 and score >= 1.5:
        label = "Bullish context — not a trade signal"
    elif total_weight >= 2 and score <= -1.5:
        label = "Bearish context — not a trade signal"
    return {
        "status": "context_only" if total_weight else "insufficient_data",
        "label": label,
        "score": score,
        "available_weight": total_weight,
        "available_factors": sum(1 for f in factors if f["available"]),
        "total_factors": 10,
        "factors": factors,
        "warning": "Ten-factor checklist is visible, but only verified inputs contribute to context. Missing feeds are not guessed. This is not a backtested MCX entry/exit strategy.",
    }

def snapshot():
    now = datetime.now(timezone.utc).isoformat()
    kotak_status = connection_status()
    live_quote = None
    if kotak_status["configured"]:
        try:
            live_quote = get_live_mcx_quote()
        except Exception:
            live_quote = None
    price = live_quote["price"] if live_quote else None
    drivers = _global_drivers()
    factor_assessment = _factor_assessment(live_quote, drivers)
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
    # Transparent intraday pivots use only broker-returned session OHLC. They are not historical S/R.
    levels = {"status":"not_calculated","method":None,"pivot":None,"support_1":None,"support_2":None,"resistance_1":None,"resistance_2":None}
    if live_quote and all(isinstance(live_quote.get(k),(int,float)) for k in ("day_high","day_low","previous_close")):
        h, l, prev = live_quote["day_high"], live_quote["day_low"], live_quote["previous_close"]
        pivot = (h+l+prev)/3
        levels = {"status":"calculated_from_broker_ohlc","method":"Classic floor pivots from quote OHLC; provisional intraday reference",
                  "pivot":round(pivot,2),"support_1":round(2*pivot-h,2),"support_2":round(pivot-(h-l),2),
                  "resistance_1":round(2*pivot-l,2),"resistance_2":round(pivot+(h-l),2)}
    # A descriptive context score only; not a tested entry/exit strategy.
    context = {"status":"insufficient_data","score":None,"label":"WAIT — insufficient verified inputs",
               "factors":[],"warning":"Context score is descriptive only, not a validated trading signal."}
    if live_quote and isinstance(live_quote.get("day_open"),(int,float)) and isinstance(live_quote.get("price"),(int,float)):
        score = 1 if live_quote["price"] > live_quote["day_open"] else (-1 if live_quote["price"] < live_quote["day_open"] else 0)
        factors = [{"name":"MCX price vs broker session open","direction":"bullish" if score>0 else "bearish" if score<0 else "neutral","score":score}]
        hh = drivers.get("henry_hub_reference")
        if hh and isinstance(hh.get("change_pct"),(int,float)):
            hs = 1 if hh["change_pct"] > 0.25 else (-1 if hh["change_pct"] < -0.25 else 0)
            factors.append({"name":"Henry Hub reference move","direction":"bullish" if hs>0 else "bearish" if hs<0 else "neutral","score":hs})
            score += hs
        context = {"status":"context_only","score":score,"label":"Bullish context" if score>0 else "Bearish context" if score<0 else "Mixed / neutral context",
                   "factors":factors,"warning":"Not a validated strategy. Do not trade from this score alone."}
    # A numeric opening estimate is shown only when both a broker-reported MCX prior close
    # and a public Henry Hub reference move are available. It is an unvalidated 1:1 percentage proxy.
    hh = drivers.get("henry_hub_reference") if isinstance(drivers, dict) else None
    opening_estimate = None
    if live_quote and previous_close and previous_close > 0 and hh and isinstance(hh.get("change_pct"), (int, float)):
        proxy_pct = max(-5.0, min(5.0, float(hh["change_pct"])))
        estimate = round(previous_close * (1 + proxy_pct / 100), 2)
        band_pct = max(0.5, min(2.0, abs(proxy_pct) * 0.75 + 0.5))
        opening_estimate = {"status":"unvalidated_proxy", "point_estimate":estimate,
            "range_low":round(estimate * (1-band_pct/100),2), "range_high":round(estimate * (1+band_pct/100),2),
            "prior_mcx_close":round(previous_close,2), "estimated_gap_rupees":round(estimate-previous_close,2),
            "estimated_gap_pct":round(proxy_pct,2), "reference_change_pct":round(float(hh["change_pct"]),2),
            "reference_source":hh.get("source","public reference"), "reference_timestamp":hh.get("timestamp"),
            "timestamp_utc":datetime.now(timezone.utc).isoformat(), "confidence":"LOW — uncalibrated proxy",
            "method":"Applies Henry Hub percentage move 1:1 to prior MCX close; not calibrated against MCX opening history."}
    else:
        opening_estimate = {"status":"unavailable", "point_estimate":None, "range_low":None, "range_high":None,
            "prior_mcx_close":previous_close, "estimated_gap_rupees":None, "estimated_gap_pct":None,
            "timestamp_utc":datetime.now(timezone.utc).isoformat(), "confidence":"NOT ESTIMATED",
            "method":"Requires a broker-reported MCX prior close and a fresh Henry Hub reference move; no number is fabricated."}
    return {
        "mode": "KOTAK LIVE QUOTE" if live_quote else "WAIT — NO LIVE QUOTE",
        "live_quote": bool(live_quote),
        "timestamp_utc": live_quote["timestamp_utc"] if live_quote else now,
        "contract": live_quote["contract"] if live_quote else "No verified contract",
        "price": price,
        "previous_close": previous_close, "change": change, "change_pct": change_pct,
        "day_open": live_quote.get("day_open") if live_quote else None,
        "day_high": day_high, "day_low": day_low, "volume": volume, "volume_kind": live_quote.get("volume_kind") if live_quote else None,
        "open_interest": open_interest, "oi_change": oi_change, "vwap": vwap,
        "best_bid": live_quote.get("best_bid") if live_quote else None,
        "best_bid_qty": live_quote.get("best_bid_qty") if live_quote else None,
        "best_ask": live_quote.get("best_ask") if live_quote else None,
        "best_ask_qty": live_quote.get("best_ask_qty") if live_quote else None,
        "circuit_lower": live_quote.get("circuit_lower") if live_quote else None,
        "circuit_upper": live_quote.get("circuit_upper") if live_quote else None,
        "week52_low": live_quote.get("week52_low") if live_quote else None,
        "week52_high": live_quote.get("week52_high") if live_quote else None,
        "levels": levels,
        "context": context,
        "signals": {
            "daily_bias": (context["label"] + " · context only") if live_quote else "WAIT FOR LIVE DATA",
            "intraday_setup": "No trade — strategy not validated",
            "overnight_gap": ("₹" + str(opening_estimate["point_estimate"]) + " proxy · LOW confidence" if opening_estimate.get("point_estimate") is not None else "Estimate unavailable — reference data required"),
            "reason": "Kotak quote fields are shown only when returned by the broker. Support/resistance and trade signals are unavailable until verified MCX candles and a tested strategy are connected."
        },
        "global_drivers": drivers,
        "factor_assessment": factor_assessment,
        "opening_estimate": opening_estimate,
        "inputs": {
            "mcx_price": "Kotak quote connected" if live_quote else "Live quote unavailable — no synthetic price",
            "previous_close_ohlc": "Kotak quote fields" if live_quote and previous_close is not None else "Not returned",
            "vwap_volume_oi": "Kotak quote fields" if live_quote and (vwap is not None or volume is not None or open_interest is not None) else "Not returned",
            "support_resistance": "Not calculated — historical candles required",
            "kotak_neo": "Credentials ready — quote path used" if live_quote else ("Credentials ready — feed not verified" if kotak_status["configured"] else "Not configured"),
            "henry_hub": "Public reference available" if drivers["henry_hub_reference"] else "Unavailable",
            "weather": "Forecast available" if drivers["us_gulf_weather"] else "Unavailable",
            "eia_storage": drivers.get("eia_storage",{}).get("status","unavailable"), "news": drivers.get("news",{}).get("status","unavailable"),
            "mcx_historical_candles": "Authorized external source required"
        }
    }

@app.get("/", response_class=HTMLResponse)
def home(): return HTMLResponse(PAGE)

@app.get("/api/health")
def health():
    """Report actual runtime readiness instead of a permanently hard-coded demo flag."""
    status = connection_status()
    live = False
    quote_age_seconds = None
    try:
        cached = _quote_cache.get("data")
        if cached and cached.get("live_quote"):
            quote_age_seconds = max(0, int(time.time() - datetime.fromisoformat(
                cached["timestamp_utc"].replace("Z", "+00:00")).timestamp()))
            live = quote_age_seconds <= 120
    except Exception:
        quote_age_seconds = None
    candles = candle_status()
    return {
        "ok": True, "app": "MCX Natural Gas Radar", "version": "0.5.0",
        "demo_mode": not live, "kotak_configured": bool(status.get("configured")),
        "sdk_available": bool(status.get("sdk_available")),
        "live_quote_cached": bool(live), "quote_age_seconds": quote_age_seconds,
        "candle_collector_status": candles.get("status"),
        "candle_connected": bool(candles.get("connected")),
        "timestamp_utc": datetime.now(timezone.utc).isoformat()
    }

@app.get("/api/snapshot")
def api_snapshot(): return snapshot()

@app.get("/api/kotak/quote-diagnostics")
def kotak_quote_diagnostics():
    """Safe field-level diagnostics for the latest broker quote; never returns credentials or raw payload."""
    status = connection_status()
    if not status.get("configured"):
        return {"status": "not_configured", "message": "Kotak credentials are not configured."}
    try:
        quote = get_live_mcx_quote()
        present = quote.get("quote_fields_present", [])
        expected = {
            "ltp": ["ltp", "last_traded_price"],
            "volume": ["volume", "total_volume", "total_traded_volume", "last_volume"],
            "vwap": ["avg_cost", "average_price", "average_traded_price", "avg_price"],
            "open_interest": ["open_interest", "open_int", "oi"],
            "oi_change": ["oi_change", "open_int_change", "change_in_oi"],
            "depth": ["depth", "buy", "sell"]
        }
        fields = {}
        for label, aliases in expected.items():
            found = [name for name in aliases if name in present]
            normalized = {"ltp":"price", "volume":"volume", "vwap":"vwap",
                          "open_interest":"open_interest", "oi_change":"oi_change"}
            if label == "depth":
                mapped_available = quote.get("best_bid") is not None or quote.get("best_ask") is not None
            else:
                mapped_available = quote.get(normalized.get(label, "price")) is not None
            fields[label] = {"present_aliases": found,
                             "mapped_value_available": mapped_available}
        return {"status": "connected", "contract": quote.get("contract"), "expiry": quote.get("expiry"),
                "timestamp_utc": quote.get("timestamp_utc"), "field_diagnostics": fields,
                "quote_field_names": present,
                "note": "Only field names and normalized availability are returned; no credentials or raw response."}
    except Exception as exc:
        detail = _safe_kotak_error(exc)
        return {"status": "unavailable", "diagnostic": detail,
                "note": "No quote field metadata available until Kotak returns a quote."}

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
    if "totp is not registered" in hint or "totp not registered" in hint:
        category, message = "totp_not_registered", "Kotak says API TOTP is not registered. Register/enable API TOTP in Kotak Neo, then save that exact setup key in Render as NEO_TOTP_SECRET."
    elif "rejected the generated totp" in hint or "invalid totp" in hint:
        category, message = "invalid_totp", "Kotak rejected the generated TOTP. Check that Render's NEO_TOTP_SECRET is the current API setup key, not a six-digit code, and confirm the registered mobile/UCC."
    elif "rejected mpin validation" in hint:
        category, message = "mpin_rejected", "Kotak rejected MPIN validation. Verify NEO_MPIN in Render and confirm API login is enabled."
    elif status == 429 or "rate limit" in hint or "too many requests" in hint:
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
                "quote_fields": sorted(str(k) for k in quote.keys() if isinstance(k, str)),
                "available_fields": {
                    "volume": any(quote.get(k) not in (None, "") for k in ("volume","total_volume","total_traded_volume","last_volume")),
                    "vwap": any(quote.get(k) not in (None, "") for k in ("avg_cost","average_price","average_traded_price","avg_price")),
                    "open_interest": any(quote.get(k) not in (None, "") for k in ("open_interest","open_int","oi")),
                    "oi_change": any(quote.get(k) not in (None, "") for k in ("oi_change","open_int_change","change_in_oi")),
                    "depth": any(quote.get(k) not in (None, "") for k in ("depth","buy","sell"))
                },
                "message": "Kotak returned a Natural Gas MCX futures quote. Field availability is listed without exposing the raw response."}
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



_options_cache = {"checked_at": 0.0, "data": None}

@app.get("/api/kotak/options")
def api_kotak_options():
    """Read-only options-chain summary using Kotak Neo's documented response schema."""
    now = time.monotonic()
    cached = _options_cache.get("data")
    if cached and now - _options_cache.get("checked_at", 0) < 30:
        return cached
    try:
        client = _get_kotak_client()
        # Kotak Neo documents instrument_type="option" and returns separate
        # data.call / data.put arrays; "opt" and data.options are not the API schema.
        response = client.option_chain(
            exchange="mcx_fo",
            underlying="NATURALGAS",
            instrument_type="option",
            count=40,
        )
        if not isinstance(response, dict) or response.get("error") or response.get("errors"):
            result = {
                "status": "unavailable", "source": "Kotak Neo", "synthetic": False,
                "message": "Kotak did not return a usable options-chain response.",
                "diagnostics": ["broker_error_or_unexpected_response"],
            }
        else:
            data = response.get("data", response)
            if not isinstance(data, dict):
                data = {}
            raw_calls = data.get("call", [])
            raw_puts = data.get("put", [])
            if not isinstance(raw_calls, list):
                raw_calls = []
            if not isinstance(raw_puts, list):
                raw_puts = []

            def num(value):
                # Broker numeric fields sometimes arrive as formatted strings (e.g. "6,91,250").
                # Normalize separators without treating arbitrary text as a number.
                try:
                    if value is not None and value != "":
                        if isinstance(value, bool):
                            return None
                        if isinstance(value, str):
                            value = value.strip().replace(",", "").replace(" ", "")
                            if value.endswith("%"):
                                value = value[:-1]
                        parsed = float(value)
                        return parsed if math.isfinite(parsed) else None
                except (TypeError, ValueError, OverflowError):
                    pass
                return None

            def nested_value(obj, names):
                """Find a named numeric market field, including broker wrappers like {'openInterest': {'current': 123}}."""
                wanted = {str(name).lower().replace("_", "").replace("-", "") for name in names}
                preferred = ("current", "cur", "value", "currentvalue", "currentoi", "openinterest", "openint", "oi", "qty", "quantity")

                def normalized(key):
                    return str(key).lower().replace("_", "").replace("-", "").replace(" ", "")

                def numeric_leaf(value):
                    parsed = num(value)
                    if parsed is not None:
                        return parsed
                    if isinstance(value, dict):
                        # Prefer explicitly current/latest values over previous/change fields.
                        for key in preferred:
                            for actual_key, child in value.items():
                                if normalized(actual_key) == key:
                                    found = numeric_leaf(child)
                                    if found is not None:
                                        return found
                        for child in value.values():
                            found = numeric_leaf(child)
                            if found is not None:
                                return found
                    elif isinstance(value, list):
                        for child in value:
                            found = numeric_leaf(child)
                            if found is not None:
                                return found
                    return None

                if isinstance(obj, dict):
                    for key, value in obj.items():
                        if normalized(key) in wanted:
                            found = numeric_leaf(value)
                            if found is not None:
                                return found
                    for value in obj.values():
                        found = nested_value(value, names)
                        if found is not None:
                            return found
                elif isinstance(obj, list):
                    for value in obj:
                        found = nested_value(value, names)
                        if found is not None:
                            return found
                return None

            def parse_leg(row, option_type):
                if not isinstance(row, dict):
                    return None
                inst = row.get("instrument", row.get("inst", {}))
                quote = row.get("quote", {})
                oi_data = row.get("openInterest", row.get("open_interest", row.get("oi", {})))
                if not isinstance(inst, dict):
                    inst = {}
                if not isinstance(quote, dict):
                    quote = {}
                if not isinstance(oi_data, dict):
                    oi_data = {}
                strike = num(inst.get("strikePrice", inst.get("strike_price", inst.get("strike"))))
                if strike is None:
                    strike = nested_value(row, ("strikePrice", "strike_price", "strike", "strikeRate"))
                oi = num(oi_data.get("current", oi_data.get("cur", oi_data.get("oi", row.get("open_interest", row.get("oi"))))))
                if oi is None:
                    oi = nested_value(row, ("openInterest", "open_interest", "oi", "openInt", "open_int", "opnInterest"))
                volume = num(quote.get("volume", quote.get("vol", row.get("volume", row.get("vol")))))
                if volume is None:
                    volume = nested_value(row, ("volume", "vol", "tradedVolume", "tradeVolume"))
                iv = num(row.get("iv", quote.get("iv", inst.get("iv"))))
                if iv is None:
                    iv = nested_value(row, ("iv", "impliedVolatility", "implied_volatility"))
                oi_change = num(oi_data.get("change", oi_data.get("chg", oi_data.get("oi_change", row.get("oi_change")))))
                if oi_change is None:
                    oi_change = nested_value(row, ("oiChange", "oi_change", "changeInOI", "changeinopeninterest"))
                return {
                    "type": option_type,
                    "strike": strike,
                    "oi": oi,
                    "volume": volume,
                    "iv": iv,
                    "oi_change": oi_change,
                }

            calls = [x for x in (parse_leg(row, "CE") for row in raw_calls) if x is not None]
            puts = [x for x in (parse_leg(row, "PE") for row in raw_puts) if x is not None]

            def total(rows, key):
                values = [x[key] for x in rows if x[key] is not None]
                return sum(values) if values else None

            call_oi = total(calls, "oi")
            put_oi = total(puts, "oi")
            call_vol = total(calls, "volume")
            put_vol = total(puts, "volume")

            def top_strikes(rows):
                known = [x for x in rows if x["strike"] is not None and x["oi"] is not None]
                known.sort(key=lambda x: x["oi"], reverse=True)
                return [{"strike": x["strike"], "oi": x["oi"]} for x in known[:5]]

            parsed_count = len(calls) + len(puts)
            def safe_keys(rows):
                keys = set()
                for row in rows[:3]:
                    if isinstance(row, dict):
                        keys.update(str(k)[:80] for k in row.keys())
                        for container_key in ("instrument", "inst", "quote", "openInterest", "open_interest", "oi"):
                            child = row.get(container_key)
                            if isinstance(child, dict):
                                keys.update(f"{container_key}.{str(k)[:60]}" for k in child.keys())
                return sorted(keys)[:80]
            field_coverage = {
                "call_strike": sum(x["strike"] is not None for x in calls),
                "put_strike": sum(x["strike"] is not None for x in puts),
                "call_oi": sum(x["oi"] is not None for x in calls),
                "put_oi": sum(x["oi"] is not None for x in puts),
                "call_volume": sum(x["volume"] is not None for x in calls),
                "put_volume": sum(x["volume"] is not None for x in puts),
                "iv": sum(x["iv"] is not None for x in calls + puts),
                "oi_change": sum(x["oi_change"] is not None for x in calls + puts),
            }
            result = {
                "status": "connected" if parsed_count else "schema_unverified",
                "source": "Kotak Neo", "underlying": "NATURALGAS",
                "checked_at_utc": datetime.now(timezone.utc).isoformat(),
                "options_rows_parsed": parsed_count, "synthetic": False,
                "diagnostics": {
                    "response_data_keys": sorted(str(k)[:80] for k in data.keys())[:80],
                    "call_row_keys_sample": safe_keys(raw_calls),
                    "put_row_keys_sample": safe_keys(raw_puts),
                    "field_coverage": field_coverage,
                },
                "call_oi": call_oi, "put_oi": put_oi,
                "pcr_oi": round(put_oi / call_oi, 4) if call_oi not in (None, 0) and put_oi is not None else None,
                "call_volume": call_vol, "put_volume": put_vol,
                "pcr_volume": round(put_vol / call_vol, 4) if call_vol not in (None, 0) and put_vol is not None else None,
                "top_call_oi_strikes": top_strikes(calls),
                "top_put_oi_strikes": top_strikes(puts),
                "iv_available": any(x["iv"] is not None for x in calls + puts),
                "oi_change_available": any(x["oi_change"] is not None for x in calls + puts),
                "expiry": (data.get("common_data") or {}).get("expiryDt") if isinstance(data.get("common_data"), dict) else None,
                "message": (
                    "Parsed using Kotak Neo's documented call/put, instrument, quote and openInterest fields."
                    if parsed_count else
                    "Kotak responded, but no call/put rows were returned for NATURALGAS. PCR and strike levels remain unavailable."
                ),
            }
        _options_cache.update(checked_at=now, data=result)
        return result
    except Exception as exc:
        result = {
            "status": "unavailable", "source": "Kotak Neo", "synthetic": False,
            "error_type": type(exc).__name__,
            "message": "Options data is unavailable. No PCR or options signal has been fabricated.",
        }
        _options_cache.update(checked_at=now, data=result)
        return result

@app.get("/api/forecast")
def api_forecast():
    """Transparent short-horizon direction estimate from verified, fresh MCX candles only."""
    feed = candle_status()
    candles = get_candles(interval="5m", limit=300).get("candles", [])
    candles = [c for c in candles if all(isinstance(c.get(k), (int, float)) for k in ("open", "high", "low", "close"))]
    # Never publish a directional estimate from old candles just because the database
    # still contains enough history. A connected socket alone is not proof of fresh ticks.
    if not feed.get("data_fresh"):
        return {"status":"stale_or_disconnected","direction":"WAIT — live MCX feed is not fresh",
                "confidence_label":"Unavailable","score":None,"candle_count":len(candles),
                "horizon":"Next 30–60 minutes","synthetic":False,
                "latest_candle_utc":candles[-1].get("updated_utc") if candles else None,
                "feed_status":feed.get("status"),"last_tick_utc":feed.get("last_tick_utc"),
                "tick_age_seconds":feed.get("tick_age_seconds"),
                "warning":"No directional estimate while verified MCX ticks are stale or disconnected. Refresh after the broker feed resumes."}
    if len(candles) < 30:
        return {"status":"insufficient_data","direction":"WAIT — insufficient verified candles",
                "confidence_label":"Unavailable","score":None,"candle_count":len(candles),
                "horizon":"Next 30–60 minutes","synthetic":False,
                "warning":"Need at least 30 real 5-minute Kotak candles. No forecast is issued from demo data."}
    closes=[float(c["close"]) for c in candles]; highs=[float(c["high"]) for c in candles]; lows=[float(c["low"]) for c in candles]
    def ema(values, period):
        alpha=2/(period+1); out=sum(values[:period])/period
        for v in values[period:]: out=alpha*v+(1-alpha)*out
        return out
    e9,e21=ema(closes,9),ema(closes,21)
    changes=[closes[i]-closes[i-1] for i in range(1,len(closes))]
    gains=[max(v,0) for v in changes[-14:]]; losses=[max(-v,0) for v in changes[-14:]]
    ag,al=sum(gains)/14,sum(losses)/14
    rsi=100 if al==0 and ag>0 else 50 if al==0 else 100-(100/(1+ag/al))
    trs=[max(highs[i]-lows[i],abs(highs[i]-closes[i-1]),abs(lows[i]-closes[i-1])) for i in range(1,len(candles))]
    atr=sum(trs[-14:])/14
    momentum=closes[-1]-closes[-6]; score=0
    score += 1 if e9>e21 else -1 if e9<e21 else 0
    score += 1 if closes[-1]>e9 else -1 if closes[-1]<e9 else 0
    score += 1 if rsi>=55 else -1 if rsi<=45 else 0
    score += 1 if momentum>0 else -1 if momentum<0 else 0
    direction="BULLISH BIAS" if score>=2 else "BEARISH BIAS" if score<=-2 else "SIDEWAYS / MIXED"
    confidence="MODERATE" if abs(score)>=3 and len(candles)>=60 else "LOW"
    invalidation=round(closes[-1]-atr,2) if score>=2 else round(closes[-1]+atr,2) if score<=-2 else "Wait for breakout"
    return {"status":"rule_based_estimate","direction":direction,"horizon":"Next 30–60 minutes",
            "confidence_label":confidence,"score":score,"latest_close":round(closes[-1],2),
            "ema_9":round(e9,2),"ema_21":round(e21,2),"rsi_14":round(rsi,2),
            "atr_14":round(atr,2),"candle_count":len(candles),"invalidation":invalidation,
            "latest_candle_utc":candles[-1].get("updated_utc"),"synthetic":False,
            "warning":"Unvalidated heuristic, not a calibrated probability or proven strategy. Directional context only; avoid entries if data is stale."}

@app.on_event("startup")
def start_live_candle_collection():
    """Start live tick collection when Kotak credentials are configured."""
    status = connection_status()
    if status.get("configured") and status.get("sdk_available"):
        start_collector(create_authenticated_client, get_live_mcx_quote)


@app.get("/api/candles/status")
def api_candles_status():
    return candle_status()


@app.get("/api/candles")
def api_candles(interval: str = "5m", limit: int = 300):
    try:
        return get_candles(interval=interval, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/indicators")
def api_indicators(interval: str = "5m", limit: int = 300):
    """Calculate transparent technical indicators only from stored real Kotak candles."""
    if interval not in ("1m", "5m", "15m", "1h"):
        raise HTTPException(status_code=400, detail="interval must be one of: 1m, 5m, 15m, 1h")
    candles = get_candles(interval=interval, limit=max(limit, 60)).get("candles", [])
    if not candles:
        return {"status": "insufficient_data", "interval": interval, "count": 0,
                "source": "Kotak Neo SFeed live ticks", "synthetic": False,
                "message": "No verified live candles stored yet; indicators are not calculated."}
    closes = [float(c["close"]) for c in candles]
    highs = [float(c["high"]) for c in candles]
    lows = [float(c["low"]) for c in candles]
    def ema(values, period):
        if len(values) < period:
            return None
        alpha = 2.0 / (period + 1)
        result = sum(values[:period]) / period
        for value in values[period:]:
            result = alpha * value + (1-alpha) * result
        return round(result, 4)
    rsi = None
    if len(closes) >= 15:
        changes = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        gains = [max(v, 0.0) for v in changes[-14:]]
        losses = [max(-v, 0.0) for v in changes[-14:]]
        avg_gain, avg_loss = sum(gains)/14, sum(losses)/14
        rsi = 100.0 if avg_loss == 0 and avg_gain > 0 else (50.0 if avg_loss == 0 else round(100-(100/(1+avg_gain/avg_loss)), 2))
    atr = None
    if len(candles) >= 15:
        true_ranges = []
        for i in range(1, len(candles)):
            true_ranges.append(max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])))
        atr = round(sum(true_ranges[-14:])/14, 4)
    enough = len(closes) >= 21
    return {
        "status": "calculated" if enough else "partial_data",
        "interval": interval, "count": len(candles), "latest_candle_utc": candles[-1].get("updated_utc"),
        "latest_close": closes[-1], "ema_9": ema(closes, 9), "ema_21": ema(closes, 21),
        "rsi_14": rsi, "atr_14": atr,
        "source": "Kotak Neo SFeed live ticks", "synthetic": False,
        "warning": "Indicators are descriptive only; they are not a tested entry/exit strategy."
    }

@app.get("/api/history/status")
def history_status():
    return {"status":"blocked_external_source_required",
            "message":"Kotak Neo historical-data documentation excludes MCX futures. Historical MCX candles and reliable backtesting require an authorized MCX historical-data provider.",
            "needed":["timestamp","contract","expiry","open","high","low","close","volume","open_interest"],
            "kotak_supported":False}
