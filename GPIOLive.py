# GPIOLive.py — ESP32-S3 Live GPIO + ADC + SSE
# Final version — no % formatting issues, safe on MicroPython 1.22+

import uasyncio as asyncio
import json, gc
from machine import Pin, ADC
import network

PORT = 8081
VREF = 3.3

D2GPIO = {
    0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6,
    6: 43,          # D6  -> GPIO43 (UART TX)
    7: 44,           # D7  -> GPIO7  (<<< FIXED; was 44)
    8:   7,           # D8  -> GPIO8
    9: 8,           # D9  -> GPIO9
    10: 9        # D10 -> GPIO10
}
ADC_D = {0, 1, 2, 3, 4, 5, 8, 9, 10}
PIN_OVERLAY = {
    0: {"x": 6.7, "y": 20.7}, 1: {"x": 6.9, "y": 32.2},
    2: {"x": 6.9, "y": 43.1}, 3: {"x": 6.7, "y": 54.6},
    4: {"x": 6.7, "y": 65.9}, 5: {"x": 6.9, "y": 77.0},
    6: {"x": 6.9, "y": 88.3}, 7: {"x": 91.9, "y": 88.3},
    8: {"x": 92.2, "y": 77.2}, 9: {"x": 91.9, "y": 66.2},
    10: {"x": 91.9, "y": 54.9},
}

# Safe pin init
try:
    PINS = {d: Pin(D2GPIO[d], Pin.IN, Pin.PULL_DOWN) for d in D2GPIO}
except AttributeError:
    PINS = {d: Pin(D2GPIO[d], Pin.IN) for d in D2GPIO}

ADCS = {}
for d in ADC_D:
    try:
        ADCS[d] = ADC(Pin(D2GPIO[d]))
    except Exception:
        pass

def _heap(): return gc.mem_free()
def _levels(): return {f"D{d}": int(PINS[d].value()) for d in D2GPIO}
def _adcv():
    out = {}
    for d, adc in ADCS.items():
        try:
            raw = adc.read_u16()
            v = (raw / 65535.0) * VREF
            out[f"D{d}"] = round(v, 3)
        except Exception:
            out[f"D{d}"] = None
    for d in (6, 7):
        out.setdefault(f"D{d}", None)
    return out

# ---------- HTML Page ----------
def page_html():
    overlay_json = json.dumps(PIN_OVERLAY)
    adc_list_json = json.dumps(sorted(list(ADC_D)))

    html = r"""<!doctype html><html><head><meta charset='utf-8'/>
<meta name='viewport' content='width=device-width,initial-scale=1'/>
<title>ESP32-S3 Live GPIO + ADC</title>
<style>
html,body{margin:0;padding:0;background:#fff;font-family:Roboto,Arial;}
.title{font-weight:600;text-align:center;margin:18px 0 6px 0;}
.board{position:relative;width:min(92vw,680px);margin:0 auto;}
.board img{width:100%;display:block;}

/* Pin dots */
.hole{
  position:absolute;width:41px;height:41px;margin:-20.5px 0 0 -20.5px;
  border-radius:50%;
  display:flex;align-items:center;justify-content:center;
  transition:background-color .25s ease, transform .08s ease;
  border:3px solid rgba(0,0,0,.18);
  box-shadow:0 1px 2px rgba(0,0,0,.15) inset;
}

/* LOW = solid green, HIGH = solid red, UART = grey */
.hole.lo{ background:#2e9e5f; }
.hole.hi{ background:#d94134; }
.hole.na{ background:#bdbdbd; }

.lbl{
  position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
  font-size:12px;font-weight:700;color:#fff;text-shadow:0 1px 1px rgba(0,0,0,.25);
}

.adc{
  position:absolute;bottom:-8px;left:50%;transform:translateX(-50%);
  font-size:10px;font-weight:700;padding:2px 5px;border-radius:9px;color:#fff;
  background:#777;min-width:34px;text-align:center;
}
</style>
</head><body>
<div class='title'>ESP32-S3 Live GPIO + ADC Monitor</div>
<div class='board'>
  <img src='https://raw.githubusercontent.com/thelastoutpostworkshop/microcontroller_devkit/refs/heads/main/gpio_viewer_1_5/devboards_images/XIAO-ESP32-S3.png'/>
  <div id='overlay'></div>
</div>

<script>
const MAP = """ + overlay_json + r""";
const ADC_D = """ + adc_list_json + r""";
const NA_PINS = new Set([6,7]); // D6, D7 = UART (grey)
const overlay = document.getElementById('overlay');

/* Build dots */
for (const k of Object.keys(MAP)) {
  const d = Number(k), p = MAP[k];
  const el = document.createElement('div');
  el.className = 'hole lo';                // default
  el.dataset.d = d;
  el.style.left = p.x + '%';
  el.style.top  = p.y + '%';

  const lbl = document.createElement('div');
  lbl.className = 'lbl'; lbl.textContent = 'D' + d;
  el.appendChild(lbl);

  const adc = document.createElement('div');
  adc.className = 'adc'; adc.textContent = '';
  el.appendChild(adc);

  overlay.appendChild(el);
}

/* Color helper for ADC badge (green→red with voltage) */
function badgeColor(v){
  if (v == null) return '#777';
  const t = Math.max(0, Math.min(1, v/3.3));     // 0..1
  const hue = 120*(1 - t);                       // 120→0 (green→red)
  const light = 35 + 45*t;                       // brighter as voltage rises
  return `hsl(${hue}deg 90% ${light}%)`;
}

/* Apply ADC numbers + derive hi/lo from ADC when present */
let lastADC = {};  // keep latest adcv to use for hi/lo
function applyADC(adc){
  lastADC = adc || {};
  for (const el of overlay.children) {
    const d = Number(el.dataset.d);
    const badge = el.querySelector('.adc');
    const v = lastADC['D'+d];

    if (v == null) {
      badge.textContent = '';
      badge.style.background = '#777';
    } else {
      badge.textContent = v.toFixed(2) + ' V';
      badge.style.background = badgeColor(v);
    }
  }
}

/* Apply levels; prefer ADC-derived hi/lo when available */
function applyLevels(levels){
  for (const el of overlay.children) {
    const d = Number(el.dataset.d);
    if (NA_PINS.has(d)) { el.className = 'hole na'; continue; }

    // Prefer ADC voltage to decide HIGH/LOW
    const v = lastADC['D'+d];
    if (v != null) {
      el.className = 'hole ' + (v >= 2.0 ? 'hi' : 'lo'); // tweak threshold if you want
      continue;
    }
    // Fallback to digital level
    const bit = (levels && (('D'+d) in levels)) ? levels['D'+d] : 0;
    el.className = 'hole ' + (bit ? 'hi' : 'lo');
  }
}

/* Live updates via SSE (fallback to fetch) */
function start(){
  if ('EventSource' in window) {
    const es = new EventSource('/events');
    es.onmessage = (e)=>{
      try{
        const o = JSON.parse(e.data);
        if (o.adcv)   applyADC(o.adcv);
        if (o.levels) applyLevels(o.levels);
      }catch(_){}
    };
  } else {
    async function tick(){
      try{
        const r = await fetch('/data',{cache:'no-store'});
        const o = await r.json();
        if (o.adcv)   applyADC(o.adcv);
        if (o.levels) applyLevels(o.levels);
      }catch(_){}
    }
    setInterval(tick, 500); tick();
  }
}
start();
</script>
</body></html>"""
    return html
# ---------- HTTP ----------
async def _send_ok(w, body, ctype="text/html; charset=utf-8"):
    hdr = "HTTP/1.1 200 OK\r\nContent-Type: %s\r\nCache-Control: no-cache\r\nConnection: close\r\n\r\n" % ctype
    await w.awrite(hdr)
    await w.awrite(body)

async def _send_json(w, obj):
    await _send_ok(w, json.dumps(obj), "application/json")

async def _send_404(w):
    await w.awrite("HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n")

# ---------- SSE ----------
async def _send_sse(w):
    hdr = "HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nCache-Control: no-cache\r\nConnection: keep-alive\r\n\r\n"
    await w.awrite(hdr)
    try:
        while True:
            data = {"levels": _levels(), "adcv": _adcv()}
            await w.awrite("data: " + json.dumps(data) + "\n\n")
            await asyncio.sleep_ms(500)
    except Exception:
        pass

# ---------- Router ----------
async def handle(r, w):
    line = await r.readline()
    if not line:
        await w.aclose(); return
    try:
        method, path, _ = line.decode().split(" ", 2)
    except:
        await w.aclose(); return
    while True:
        h = await r.readline()
        if not h or h == b"\r\n":
            break
    if path in ("/", "/index.html"):
        await _send_ok(w, page_html())
    elif path == "/data":
        await _send_json(w, {"levels": _levels(), "adcv": _adcv(), "heap": _heap()})
    elif path == "/events":
        await _send_sse(w)
    else:
        await _send_404(w)
    await w.aclose()

# ---------- Main ----------
async def main():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    ip = wlan.ifconfig()[0] if wlan.isconnected() else "0.0.0.0"
    print("GPIO Viewer → http://%s:%d/" % (ip, PORT))
    server = await asyncio.start_server(handle, "0.0.0.0", PORT)
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        server.close()
        await server.wait_closed()

try:
    asyncio.run(main())
finally:
    asyncio.new_event_loop()