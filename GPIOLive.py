# GPIOLive.py — ESP32-S3 MicroPython
# Live GPIO + ADC viewer with compact UI + status bar

import uasyncio as asyncio
import gc, json
from machine import Pin, ADC
import network

# ---------------- Config ----------------
PORT = 8081
VREF = 3.3
SAMPLE_MS = 500

# Confirmed D→GPIO map (your jumper test)
D2GPIO = {
    0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6,
    6: 43,  # D6 UART
    7: 44,  # D7 UART
    8: 7,
    9: 8,
    10: 9,
}

# ADC-capable D pins (we show voltage on these)
ADC_D = {0, 1, 2, 3, 4, 5, 8, 9, 10}

# Overlay positions (percent of image)
PIN_OVERLAY = {
    0: {"x": 6.7, "y": 20.7}, 1: {"x": 6.9, "y": 32.2},
    2: {"x": 6.9, "y": 43.1}, 3: {"x": 6.7, "y": 54.6},
    4: {"x": 6.7, "y": 65.9}, 5: {"x": 6.9, "y": 77.0},
    6: {"x": 6.9, "y": 88.3}, 7: {"x": 91.9, "y": 88.3},
    8: {"x": 92.2, "y": 77.2}, 9: {"x": 91.9, "y": 66.2},
    10: {"x": 91.9, "y": 54.9},
}

# --------------- GPIO / ADC init ---------------
DIG = {}
for d, gpio in D2GPIO.items():
    if d in (6, 7):
        DIG[d] = None
    else:
        try:
            DIG[d] = Pin(gpio, Pin.IN, Pin.PULL_UP)
        except:
            DIG[d] = Pin(gpio, Pin.IN)

ADCs = {}
for d in ADC_D:
    try:
        ADCs[d] = ADC(Pin(D2GPIO[d]))
    except:
        pass


def _heap():
    gc.collect()
    return gc.mem_free()


def _digital_levels():
    out = {}
    for d in D2GPIO:
        if d in (6, 7):
            out["D%d" % d] = 0
        else:
            p = DIG[d]
            out["D%d" % d] = int(p.value()) if p else 0
    return out


def _adc_volts():
    out = {}
    for d, adc in ADCs.items():
        try:
            out["D%d" % d] = adc.read_u16() * VREF / 65535
        except:
            pass
    return out


# --------------- HTML ---------------

def page_html():
    overlay_json = json.dumps(PIN_OVERLAY)
    adc_list_json = json.dumps(sorted(list(ADC_D)))

    html = (
        "<!doctype html><html><head><meta charset='utf-8'/>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'/>"
        "<title>Seeed Studio ESP 32 S3 GPIO Pin Monitoring</title>"
        "<style>"
        "html,body{margin:0;padding:0;background:#fff;font-family:Roboto,Arial;}"
        "/* top bar centered */"
        ".topbar{position:sticky;top:0;z-index:10;background:rgba(255,255,255,.92);"
        "backdrop-filter:saturate(180%) blur(6px);border-bottom:1px solid #eee;}"
        ".topin{max-width:980px;margin:0 auto;padding:8px 12px;"
        "display:flex;flex-direction:column;align-items:center;gap:8px;}"
        ".title{font-weight:800;font-size:18px;color:#111;text-align:center;}"
        ".pills{display:flex;gap:12px;align-items:center;flex-wrap:wrap;justify-content:center;}"
        ".pill{font-weight:700;font-size:12px;padding:6px 10px;border-radius:999px;background:#f2f4f7;color:#111}"
        ".pill .lab{color:#6b7280;margin-right:6px}"
        ".pill select{border:none;background:transparent;font:inherit;outline:none;cursor:pointer}"

        ".wrap{max-width:980px;margin:0 auto 18px;padding:0 10px}"
        ".board{position:relative;width:clamp(240px,48vw,360px);margin:12px auto 0}"
        ".board img{width:100%;display:block;user-select:none;pointer-events:none}"

        "/* your (smaller) dots; keep alignment intact */"
        ".hole{position:absolute;width:23.6px;height:23.6px;margin:-11.8px 0 0 -11.8px;"
        "border-radius:50%;display:flex;align-items:center;justify-content:center;"
        "transition:background-color .25s ease,transform .08s ease;"
        "border:2px solid rgba(0,0,0,.18);box-shadow:0 1px 2px rgba(0,0,0,.15) inset;}"
        ".hole.lo{background:#2e9e5f;}.hole.hi{background:#d94134;}.hole.na{background:#bdbdbd;}"

        ".lbl{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);"
        "font-size:9px;font-weight:700;color:#fff;text-shadow:0 1px 1px rgba(0,0,0,.25);}"
        ".adc{position:absolute;bottom:-6px;left:50%;transform:translateX(-50%);"
        "font-size:9px;font-weight:700;padding:1px 4px;border-radius:8px;color:#fff;"
        "background:#777;min-width:30px;text-align:center}"
        "</style></head><body>"

        "<div class='topbar'><div class='topin'>"
          "<div class='title'>Seeed Studio ESP 32 S3 GPIO Pin Monitoring</div>"
          "<div class='pills'>"
            "<div class='pill'><span class='lab'>IP</span><span id='ip'>—</span></div>"
            "<div class='pill'><span class='lab'>Uptime</span><span id='uptime'>0:00</span></div>"
            "<div class='pill'><span class='lab'>Heap</span><span id='heap'>—</span></div>"
            "<div class='pill'><span class='lab'>Refresh</span>"
              "<select id='rate'><option value='250'>250 ms</option>"
              "<option value='500' selected>500 ms</option>"
              "<option value='1000'>1 s</option><option value='2000'>2 s</option></select>"
            "</div>"
          "</div>"
        "</div></div>"

        "<div class='wrap'>"
          "<div class='board'>"
            "<img src='https://raw.githubusercontent.com/TuzaaBap/Seeed-Studio-XIAO-ESP32S3-GPIOViewer/refs/heads/main/assets/XIAO-ESP32-S3.png'/>"
            "<div id='overlay'></div>"
          "</div>"
        "</div>"

        "<script>"
        "const MAP="+overlay_json+";"
        "const ADC_D="+adc_list_json+";"
        "const NA_PINS=new Set([6,7]);"
        "const overlay=document.getElementById('overlay');"
        "const ipEl=document.getElementById('ip');"
        "const heapEl=document.getElementById('heap');"
        "const uptimeEl=document.getElementById('uptime');"
        "const rateSel=document.getElementById('rate');"

        "ipEl.textContent=location.host||(location.hostname+(location.port?':'+location.port:''));"

        "/* build dots */"
        "for(const k of Object.keys(MAP)){const d=Number(k),p=MAP[k];"
          "const el=document.createElement('div');el.className='hole lo';el.dataset.d=d;"
          "el.style.left=p.x+'%';el.style.top=p.y+'%';"
          "const lbl=document.createElement('div');lbl.className='lbl';lbl.textContent='D'+d;el.appendChild(lbl);"
          "const adc=document.createElement('div');adc.className='adc';adc.textContent='';el.appendChild(adc);"
          "overlay.appendChild(el);"
        "}"

       "/* helpers */"
        "function fmtHeap(bytes){"
          "if(bytes==null)return '—';"
          "const kb=bytes/1024, mb=kb/1024;"
          "return (mb>=1? (mb.toFixed(2)+' MB') : (kb.toFixed(0)+' KB'));"
        "}"
        "function badgeColor(v){if(v==null)return'#777';"
          "const t=Math.max(0,Math.min(1,v/3.3));const hue=120*(1-t);const light=35+45*t;"
          "return `hsl(${hue}deg 90% ${light}%)`;}"
        "let lastADC={};"

        "function applyADC(adc){lastADC=adc||{};"
          "for(const el of overlay.children){const d=Number(el.dataset.d);"
            "const badge=el.querySelector('.adc');const v=lastADC['D'+d];"
            "if(v==null){badge.textContent='';badge.style.background='#777';}"
            "else{badge.textContent=v.toFixed(2)+' V';badge.style.background=badgeColor(v);} "
          "}"
        "}"

        "function applyLevels(levels){for(const el of overlay.children){const d=Number(el.dataset.d);"
          "if(NA_PINS.has(d)){el.className='hole na';continue;}"
          "const v=lastADC['D'+d];if(v!=null){el.className='hole '+(v>=2.0?'hi':'lo');continue;}"
          "const bit=(levels&&('D'+d in levels))?levels['D'+d]:0;el.className='hole '+(bit?'hi':'lo');}}"

        "/* uptime */"
        "const t0=Date.now();setInterval(()=>{const s=Math.floor((Date.now()-t0)/1000);"
          "const m=Math.floor(s/60),ss=s%60;uptimeEl.textContent=`${m}:${ss.toString().padStart(2,'0')}`;},1000);"

        "/* data loop */"
        "let timer=null;"
        "async function poll(){try{const r=await fetch('/data',{cache:'no-store'});"
          "const o=await r.json();"
          "if(o.heap!=null)heapEl.textContent=fmtHeap(o.heap);"
          "if(o.adcv)applyADC(o.adcv);if(o.levels)applyLevels(o.levels);"
        "}catch(_){}}"
        "function startFetch(iv){if(timer)clearInterval(timer);timer=setInterval(poll,iv);poll();}"

        "if('EventSource'in window){const es=new EventSource('/events');"
          "es.onmessage=(e)=>{try{const o=JSON.parse(e.data);"
            "if(o.heap!=null)heapEl.textContent=fmtHeap(o.heap);"
            "if(o.adcv)applyADC(o.adcv);if(o.levels)applyLevels(o.levels);}catch(_){}};"
          "startFetch(5000);"
        "}else{startFetch(parseInt(rateSel.value,10));}"

        "rateSel.addEventListener('change',()=>startFetch(parseInt(rateSel.value,10)));"
        "</script></body></html>"
    )
    return html
# --------------- HTTP helpers ---------------
async def _send(writer, status, ctype, body):
    hdr = "HTTP/1.1 %s\r\nContent-Type: %s\r\nCache-Control: no-store\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % (
        status, ctype, len(body)
    )
    await writer.awrite(hdr.encode() + body)


async def _send_json(writer, obj):
    await _send(writer, "200 OK", "application/json", json.dumps(obj).encode())


async def _send_html(writer, html_str):
    await _send(writer, "200 OK", "text/html; charset=utf-8", html_str.encode())


async def _send_404(writer):
    await _send(writer, "404 Not Found", "text/plain", b"404")


# --------------- SSE ---------------
async def sse_stream(writer):
    await writer.awrite(
        b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n"
    )
    try:
        while True:
            data = {"heap": _heap(), "levels": _digital_levels(), "adcv": _adc_volts()}
            await writer.awrite("data: %s\n\n" % json.dumps(data))
            await asyncio.sleep_ms(SAMPLE_MS)
    except:
        pass


# --------------- Router ---------------
async def handle(reader, writer):
    try:
        line = await reader.readline()
        if not line:
            await writer.aclose()
            return
        try:
            method, path, _ = line.decode().split(" ", 2)
        except:
            await writer.aclose()
            return
        # skip headers
        while True:
            h = await reader.readline()
            if not h or h == b"\r\n":
                break

        if method == "GET" and (path == "/" or path.startswith("/index.html")):
            await _send_html(writer, page_html())
        elif method == "GET" and path == "/data":
            await _send_json(writer, {"heap": _heap(), "levels": _digital_levels(), "adcv": _adc_volts()})
        elif method == "GET" and path == "/events":
            await sse_stream(writer)
        else:
            await _send_404(writer)
    except:
        try:
            await _send_404(writer)
        except:
            pass
    finally:
        try:
            await writer.aclose()
        except:
            pass


# --------------- Main ---------------
async def main():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    ip = wlan.ifconfig()[0] if wlan.isconnected() else "0.0.0.0"
    print("GPIO Viewer -> http://%s:%d/" % (ip, PORT))
    server = await asyncio.start_server(handle, "0.0.0.0", PORT)
    async with server:
        await server.wait_closed()


try:
    asyncio.run(main())
finally:
    asyncio.new_event_loop()
