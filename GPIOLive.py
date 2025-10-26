# GPIOLive.py — Seeed Studio XIAO ESP32S3 GPIOViewer v1.0.2
# Minimal, optimized core with live GPIO overlay + ESP Info tab.
# APIs: /api/pins, /api/info
# Only needs: boot.py (Wi-Fi) + this file. 

import uasyncio as asyncio, json, gc, os, time, sys
from machine import Pin

# ---------- PIN MAP ----------
D2GPIO = {
    0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6,
    6: 43, 7: 44, 8: 7, 9: 8, 10: 9,
}
ADC_D = {0, 1, 2, 3, 4, 5, 8, 9, 10}

# Overlay seed positions (% of image W/H)
PIN_OVERLAY = {
    0: {"x": 6.7, "y": 20.7}, 1: {"x": 6.9, "y": 32.2},
    2: {"x": 6.9, "y": 43.1}, 3: {"x": 6.7, "y": 54.6},
    4: {"x": 6.7, "y": 65.9}, 5: {"x": 6.9, "y": 77.0},
    6: {"x": 6.9, "y": 88.3}, 7: {"x": 91.9, "y": 88.3},
    8: {"x": 92.2, "y": 77.2}, 9: {"x": 91.9, "y": 66.2},
    10: {"x": 91.9, "y": 54.9},
}

# ---------- SETTINGS ----------
HTTP_PORT = 8080
POLL_MS   = 100
LED_PIN   = 21
VREF      = 3.30

# ---------- LED Breathing ----------
_pwm = None
def _try_led_pwm():
    global _pwm
    try:
        from machine import PWM
        _pwm = PWM(Pin(LED_PIN, Pin.OUT), freq=250)
    except:
        _pwm = None
_try_led_pwm()

async def _breathe():
    if not _pwm:
        return
    import math
    t = 0
    while True:
        try:
            _pwm.duty_u16(int((1 - (1 + math.cos(t/12)) / 2) * 65535))
            t += 1
        except:
            pass
        await asyncio.sleep_ms(30)

# ---------- CORE STATS ----------
START_MS = time.ticks_ms()
D_PINS   = tuple(sorted(D2GPIO.keys()))

def uptime_s():
    return time.ticks_diff(time.ticks_ms(), START_MS) // 1000

def cpu_freq_mhz():
    try:
        import machine
        return machine.freq() // 1_000_000
    except:
        return None

def cores_count():
    return 2  # ESP32-S3 dual core

def heap_info():
    gc.collect()
    return {'free': gc.mem_free(), 'alloc': gc.mem_alloc()}

def fs_info():
    try:
        s = os.statvfs('/')
        total = s[1] * s[2]
        free  = s[1] * s[3]
        return {'total': total, 'free': free, 'used': total - free}
    except:
        return None

def flash_size():
    try:
        import esp
        return esp.flash_size()
    except:
        return None

# ---------- NETWORK ----------
def network_info():
    """Return basic STA/AP info: ip, ssid, rssi, mac, gw, dns."""
    info = {'ip': None, 'netmask': None, 'gw': None, 'dns': None,
            'ssid': None, 'rssi': None, 'mac_sta': None, 'mac_ap': None}
    try:
        import network
        sta = network.WLAN(network.STA_IF)
        if sta and sta.active():
            try: ip, nm, gw, dns = sta.ifconfig(); info.update({'ip': ip, 'netmask': nm, 'gw': gw, 'dns': dns})
            except: pass
            try: info['ssid'] = sta.config('essid')
            except: pass
            try: info['rssi'] = sta.status('rssi')
            except: pass
            try:
                mac = sta.config('mac')
                if mac: info['mac_sta'] = '%02X:%02X:%02X:%02X:%02X:%02X' % tuple(mac)
            except: pass
        ap = network.WLAN(network.AP_IF)
        if ap and ap.active():
            try:
                mac = ap.config('mac')
                if mac: info['mac_ap'] = '%02X:%02X:%02X:%02X:%02X:%02X' % tuple(mac)
            except: pass
    except:
        pass
    return info

# ---------- BUILD INFO --------


def detect_chip_model():
    """Try to detect actual ESP variant from os.uname().machine."""
    try:
        u = os.uname()  # (sysname, nodename, release, version, machine)
        mach = getattr(u, 'machine', '').lower()
        if not mach:
            return "ESP32"
        if 's3' in mach:
            return "ESP32-S3"  
        if 's2' in mach:
            return "ESP32-S2"
        if 'c3' in mach:
            return "ESP32-C3"
        if 'esp32' in mach:
            return "ESP32"
        return mach.strip().upper()
    except Exception:
        return "ESP32"


def build_info():
    import sys
    impl = getattr(sys, 'implementation', None)
    ver  = None
    if impl and hasattr(impl, 'version'):
        try: ver = impl.version
        except: pass
    return {
        'micropython': getattr(sys, 'version', None),
        'platform': getattr(sys, 'platform', None),
        'build': ver,
    }

# ---------- GPIO / ADC ----------
_adc_map = {}
def _adc_for_gpio(gpio):
    from machine import ADC
    try:
        if gpio not in _adc_map:
            _adc_map[gpio] = ADC(Pin(gpio))
        return _adc_map[gpio]
    except:
        return None

def read_d_pin(d):
    """Return {'digital':0|1|None, 'adc':raw or None, 'volt':V or None}"""
    gpio = D2GPIO.get(d)
    if gpio is None:
        return {'digital': None, 'adc': None, 'volt': None}

    # Digital read
    dig = None
    try:
        dig = int(Pin(gpio, Pin.IN).value())
    except:
        pass

    # Analog read if applicable
    raw = volt = None
    if d in ADC_D:
        adc = _adc_for_gpio(gpio)
        if adc:
            try:
                raw = adc.read_u16()
                volt = raw / 65535 * VREF
            except:
                pass
    return {'digital': dig, 'adc': raw, 'volt': volt}

# ---------- optional pinmap.json ----------
def load_pinmap():
    try:
        with open("pinmap.json", "r") as f:
            return json.loads(f.read())
    except:
        return {}


def page_html():
    overlay_json = json.dumps(PIN_OVERLAY)
    adc_list_json = json.dumps(sorted(list(ADC_D)))

    html = (
        "<!doctype html><html><head><meta charset='utf-8'/>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'/>"
        "<title>Seeed Studio XIAO ESP32S3 GPIO Pin Monitoring</title>"
        "<style>"
       ' /* ---- color system (light/dark) ---- */'
        ":root{"
        " --bg:#ffffff; --text:#111;"
        " --topbar-bg:rgba(255,255,255,.92); --topbar-br:#e6e7eb;"
        " --pill-bg:#f2f4f7; --pill-text:#111;"
        " --section-bg:#f3f4f6;"       '/* panel background */'
        " --card-bg:#ffffff;"          '/* tile background */'
        " --card-br:rgba(0,0,0,.10);"  '/* tile/panel borders */'
        " --adc-bg:#777; --hole-hi:#d94134; --hole-lo:#2e9e5f;"
        "}"
        "[data-theme='dark']{"
        " --bg:#0b1222; --text:#e5e7eb;"
        " --topbar-bg:rgba(11,18,34,.92); --topbar-br:#1f2a3d;"
        " --pill-bg:#0f1a2e; --pill-text:#e5e7eb;"
        " --section-bg:#0f172a;"
        " --card-bg:#152238;"          '/* brighter than section so cards pop */'
        " --card-br:#27344b;"
        " --adc-bg:#505965;"
        "}"
        '/* ---- layout ---- */'
        "html,body{margin:0;padding:0;background:var(--bg);color:var(--text);font-family:Roboto,Arial,Helvetica,sans-serif}"
        ".topbar{position:sticky;top:0;z-index:10;background:var(--topbar-bg);backdrop-filter:saturate(180%) blur(6px);border-bottom:1px solid var(--topbar-br)}"
        ".topin{max-width:980px;margin:0 auto;padding:8px 12px;display:flex;flex-direction:column;align-items:center;gap:8px}"
        ".title{font-weight:800;font-size:18px;text-align:center}"
        ".pills{display:flex;gap:12px;align-items:center;flex-wrap:wrap;justify-content:center}"
        ".pill{font-weight:700;font-size:12px;padding:6px 10px;border-radius:999px;background:var(--pill-bg);color:var(--pill-text);border:1px solid var(--card-br)}"
        ".pill .lab{opacity:.7;margin-right:6px}"
        ".pill select{border:none;background:transparent;font:inherit;outline:none;cursor:pointer;color:var(--pill-text)}"
        ".tab{display:inline-flex;border-radius:999px;overflow:hidden;border:1px solid var(--topbar-br);background:var(--pill-bg)}"
        ".tab button{padding:6px 10px;font-weight:700;font-size:12px;border:none;background:transparent;cursor:pointer;color:var(--pill-text)}"
        ".tab button.act{background:#e5e7eb;color:#111}"
        "[data-theme='dark'] .tab button.act{background:#22314a;color:#e5e7eb}"
        ".wrap{max-width:980px;margin:0 auto 18px;padding:0 10px}"
        ".board{position:relative;width:clamp(240px,48vw,360px);margin:12px auto 0}"
        ".board img{width:100%;display:block;user-select:none;pointer-events:none}"
        ".hole{position:absolute;width:23.6px;height:23.6px;margin:-11.8px 0 0 -11.8px;border-radius:50%;display:flex;align-items:center;justify-content:center;transition:background-color .25s ease,transform .08s ease;border:2px solid rgba(0,0,0,.18);box-shadow:0 1px 2px rgba(0,0,0,.15) inset}"
        ".hole.lo{background:var(--hole-lo)}.hole.hi{background:var(--hole-hi)}.hole.na{background:#bdbdbd}"
        ".lbl{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);font-size:9px;font-weight:700;color:#fff;text-shadow:0 1px 1px rgba(0,0,0,.25)}"
        ".adc{position:absolute;bottom:-6px;left:50%;transform:translateX(-50%);font-size:9px;font-weight:700;padding:1px 4px;border-radius:8px;color:#fff;background:var(--adc-bg);min-width:30px;text-align:center}"
        ".theme{position:fixed;top:10px;right:10px;z-index:20;background:var(--pill-bg);color:var(--pill-text);border:1px solid var(--card-br);border-radius:999px;padding:6px 10px;font-weight:700;display:flex;align-items:center;gap:6px;cursor:pointer}"
        ".theme .ic{font-size:14px;line-height:1}"
        ".section{background:var(--section-bg);border:1px solid var(--card-br);border-radius:14px;padding:12px;margin-top:10px}"
        ".section>h3{margin:0 0 8px 0;font-size:14px;opacity:.9}"
        ".cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}"
        ".card{background:var(--card-bg);color:var(--pill-text);border-radius:12px;padding:10px;border:1px solid var(--card-br);box-shadow:0 1px 0 rgba(0,0,0,.04)}"
        ".kv{display:grid;grid-template-columns:160px 1fr;gap:8px;margin-top:10px}"
        ".muted{opacity:.7}"
        "</style></head><body>"

        "<button id='theme' class='theme' title='Toggle theme'><span id='themeIc' class='ic'>🌙</span><span id='themeTxt'>Dark</span></button>"

        "<div class='topbar'><div class='topin'>"
          "<div class='title'>Seeed Studio XIAO ESP32S3 GPIO Pin Monitoring</div>"
          "<div class='pills'>"
            "<div class='pill'><span class='lab'>IP</span><span id='ip'>—</span></div>"
            "<div class='pill'><span class='lab'>Uptime</span><span id='uptime'>0:00</span></div>"
            "<div class='pill'><span class='lab'>Heap</span><span id='heap'>—</span></div>"
            "<div class='pill'><span class='lab'>Refresh</span>"
              "<select id='rate'><option value='250'>250 ms</option>"
              "<option value='500' selected>500 ms</option>"
              "<option value='1000'>1 s</option><option value='2000'>2 s</option></select>"
            "</div>"
            "<div class='tab'><button id='tabG' class='act'>GPIO Live</button><button id='tabI'>ESP Info</button></div>"
          "</div>"
        "</div></div>"

        "<div class='wrap'>"
          "<div id='viewG'>"
            "<div class='board'>"
              "<img id='board' src='/board.jpg' onerror=\"this.onerror=null;this.src='https://raw.githubusercontent.com/TuzaaBap/Seeed-Studio-XIAO-ESP32S3-GPIOViewer/main/assets/XIAO-ESP32-S3.png'\">"
              "<div id='overlay'></div>"
            "</div>"
            "<small class='muted' style='display:block;text-align:center;margin-top:6px'>Green = LOW, Red = HIGH. ADC pins show voltage.</small>"
          "</div>"

          "<div id='viewI' style='display:none'>"
            "<div class='section'><h3>Runtime &amp; Timers</h3><div class='cards' id='secRT'></div></div>"
            "<div class='section'><h3>Memory &amp; Storage</h3><div class='cards' id='secMEM'></div></div>"
            "<div class='section'><h3>Network &amp; Connectivity</h3><div class='cards' id='secNET'></div></div>"
            "<div class='section'><h3>Firmware &amp; System Info</h3><div class='kv' id='secFW'></div></div>"
          "</div>"
        "</div>"

        "<script>"
        "/* theme bootstrap */"
        "(function(){try{var key='theme', saved=localStorage.getItem(key), prefers=window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';"
        "var t=saved||prefers;document.documentElement.setAttribute('data-theme',t);"
        "var ic=document.getElementById('themeIc'),tx=document.getElementById('themeTxt');"
        "function setUI(x){if(!ic||!tx)return;if(x==='dark'){ic.textContent='🌙';tx.textContent='Dark';}else{ic.textContent='☀️';tx.textContent='Light';}}"
        "setUI(t);document.getElementById('theme').onclick=function(){var cur=(document.documentElement.getAttribute('data-theme')==='dark')?'dark':'light';"
        "var nxt=(cur==='dark')?'light':'dark';document.documentElement.setAttribute('data-theme',nxt);localStorage.setItem(key,nxt);setUI(nxt);};}catch(_){}})();"

        "/* tabs */"
        "var tabG=document.getElementById('tabG'),tabI=document.getElementById('tabI');"
        "var viewG=document.getElementById('viewG'),viewI=document.getElementById('viewI');"
        "function showG(){tabG.classList.add('act');tabI.classList.remove('act');viewG.style.display='';viewI.style.display='none';localStorage.setItem('view','gpio');}"
        "function showI(){tabI.classList.add('act');tabG.classList.remove('act');viewI.style.display='';viewG.style.display='none';localStorage.setItem('view','info');}"
        "tabG.onclick=showG;tabI.onclick=showI;(function(){var v=localStorage.getItem('view');if(v==='info')showI();})();"

        "/* constants */"
        "const MAP="+overlay_json+";const ADC_D="+adc_list_json+";const NA_PINS=new Set([6,7]);"
        "const overlay=document.getElementById('overlay');const ipEl=document.getElementById('ip');const heapEl=document.getElementById('heap');"
        "const uptimeEl=document.getElementById('uptime');const rateSel=document.getElementById('rate');"
        "ipEl.textContent=location.host||(location.hostname+(location.port?':'+location.port:''));"

        "/* uptime ticker */"
        "let bootEpochMs=null;"
        "function setUptimeBase(u){if(u!=null&&bootEpochMs==null){bootEpochMs=Date.now()-(u*1000);}}"
        "function currentUptime(){if(bootEpochMs==null)return '—';var sec=((Date.now()-bootEpochMs)/1000)|0;var h=(sec/3600)|0,m=((sec%3600)/60)|0,s=sec%60;"
        "return (h>0?((''+h).padStart(2,'0')+':'):'')+(''+m).padStart(2,'0')+':'+(''+s).padStart(2,'0');}"
        "function tickUptime(){if(bootEpochMs==null)return;var sec=((Date.now()-bootEpochMs)/1000)|0;var h=(sec/3600)|0,m=((sec%3600)/60)|0,s=sec%60;"
        "uptimeEl.textContent=(h>0?(h*60+m):m)+':'+(''+s).padStart(2,'0');var uc=document.getElementById('upCard');if(uc){uc.textContent=currentUptime();}}"
        "setInterval(tickUptime,1000);"

        "/* build GPIO dots */"
        "for(const k of Object.keys(MAP)){const d=Number(k),p=MAP[k];const el=document.createElement('div');el.className='hole lo';el.dataset.d=d;"
        "el.style.left=p.x+'%';el.style.top=p.y+'%';const lbl=document.createElement('div');lbl.className='lbl';lbl.textContent='D'+d;el.appendChild(lbl);"
        "const adc=document.createElement('div');adc.className='adc';adc.textContent='';el.appendChild(adc);overlay.appendChild(el);}"

        "/* helpers */"
        "function fmtB(b){if(b==null)return '—';var kb=b/1024,mb=kb/1024;return (mb>=1?(mb.toFixed(2)+' MB'):(kb.toFixed(0)+' KB'));}"
        "function fmtBytes(b){if(b==null||!isFinite(b))return '—';var kb=b/1024,mb=kb/1024,gb=mb/1024;if(gb>=1)return gb.toFixed(2)+' GB';if(mb>=1)return mb.toFixed(2)+' MB';if(kb>=1)return kb.toFixed(0)+' KB';return b+' B';}"
        "function fmtPct(p){if(p==null||!isFinite(p))return '—';return (Math.round(p*10)/10)+'%';}"
        "function badgeColor(v){if(v==null)return getComputedStyle(document.documentElement).getPropertyValue('--adc-bg')||'#777';var t=Math.max(0,Math.min(1,v/3.3));var hue=120*(1-t);var light=35+45*t;return 'hsl('+hue+'deg 90% '+light+'%)';}"
        "function avg(arr){if(!arr||!arr.length)return null;var s=0;for(var i=0;i<arr.length;i++)s+=arr[i];return s/arr.length;}"
        "function rel(ms){if(!ms)return '—';var d=Date.now()-ms;if(d<0)d=0;var s=Math.floor(d/1000);if(s<1)return 'just now';if(s<60)return s+'s ago';var m=Math.floor(s/60);if(m<60)return m+'m ago';var h=Math.floor(m/60);return h+'h ago';}"
        "let lastADC={};"

        "function applyADC(adc){lastADC=adc||{};for(const el of overlay.children){const d=Number(el.dataset.d);const badge=el.querySelector('.adc');const v=lastADC['D'+d];"
        "if(v==null){badge.textContent='';badge.style.background='var(--adc-bg)';}else{badge.textContent=v.toFixed(2)+' V';badge.style.background=badgeColor(v);}}}"
        "function applyLevels(levels){for(const el of overlay.children){const d=Number(el.dataset.d);if(NA_PINS.has(d)){el.className='hole na';continue;}const v=lastADC['D'+d];"
        "if(v!=null){el.className='hole '+(v>=2.0?'hi':'lo');continue;}const bit=(levels&&('D'+d in levels))?levels['D'+d]:0;el.className='hole '+(bit?'hi':'lo');}}"

        "/* GPIO polling */"
        "let timer=null;"
        "async function pollGPIO(){try{const pr=await fetch('/api/pins',{cache:'no-store'});const pins=await pr.json();"
        "const ir=await fetch('/api/info',{cache:'no-store'});const info=await ir.json();"
        "if(info&&info.heap)heapEl.textContent=fmtB(info.heap.free);if(info&&info.ip)ipEl.textContent=info.ip;if(info&&info.uptime_s!=null)setUptimeBase(info.uptime_s);"
        "const adcv={};for(const d of pins.order){const v=pins.values[d];if(v&&v.volt!=null)adcv['D'+d]=v.volt;}applyADC(adcv);"
        "const levels={};for(const d of pins.order){const v=pins.values[d];levels['D'+d]=(v&&v.digital===1)?1:0;}applyLevels(levels);}catch(_){}}"
        "function startGPIO(iv){if(timer)clearInterval(timer);timer=setInterval(pollGPIO,iv);pollGPIO();}"
        "startGPIO(parseInt(rateSel.value,10));rateSel.addEventListener('change',function(){startGPIO(parseInt(rateSel.value,10));});"

        "/* ESP Info polling + link status */"
        "const secRT=document.getElementById('secRT');const secMEM=document.getElementById('secMEM');const secNET=document.getElementById('secNET');const secFW=document.getElementById('secFW');"
        "function card(label,value){return '<div class=\\'card\\'><div class=\\'muted\\'>'+(label||'')+'</div><b>'+(value==null?'—':value)+'</b></div>';}"
        "let lastOkMs=0, failCount=0, rttSamples=[];"
        "function updateLinkUI(){var link=document.getElementById('linkState');var last=document.getElementById('lastUpd');var rtt=document.getElementById('rttAvg');"
        "if(!link||!last||!rtt)return; var ok=(failCount<3); link.textContent=ok?'Connected':'Disconnected'; last.textContent=rel(lastOkMs);"
        "var a=avg(rttSamples); rtt.textContent=(a==null)?'—':(Math.round(a)+' ms');}"
        "setInterval(updateLinkUI,1000);"

        "async function pollInfo(){"
        " try{"
        "   var t0=Date.now();"
        "   const r=await fetch('/api/info',{cache:'no-store'});"
        "   const d=await r.json();"
        "   var dt=Date.now()-t0; rttSamples.push(dt); if(rttSamples.length>5) rttSamples.shift();"
        "   lastOkMs=Date.now(); failCount=0;"
        "   if(d&&d.uptime_s!=null) setUptimeBase(d.uptime_s);"
        "   var heapUsed=(d.heap_used!=null)?d.heap_used:(d.heap&&d.heap.alloc);"
        "   var heapFree=(d.heap_free!=null)?d.heap_free:(d.heap&&d.heap.free);"
        "   var heapTotal=(d.heap_total!=null)?d.heap_total:((heapUsed!=null&&heapFree!=null)?(heapUsed+heapFree):null);"
        "   var fsUsed=(d.fs_used!=null)?d.fs_used:(d.fs&&d.fs.used);"
        "   var fsTotal=(d.fs_total!=null)?d.fs_total:(d.fs&&d.fs.total);"
        "   var fsPct=(fsUsed!=null&&fsTotal)?(fsUsed/fsTotal*100):null;"
        "   var flashSize=(d.flash_size!=null)?d.flash_size:null;"
        "   var flashPct=(flashSize&&fsUsed!=null)?(fsUsed/flashSize*100):null;"

        "   secRT.innerHTML=["
        "     card('CPU', (d.cpu_freq_mhz!=null?d.cpu_freq_mhz+' MHz':'—')),"
        "     card('Uptime', '<span id=\\'upCard\\'>'+currentUptime()+'</span>')"
        "   ].join('');"

        "   secMEM.innerHTML=["
        "     card('Heap Used/Total', (fmtBytes(heapUsed)+' / '+fmtBytes(heapTotal))),"
        "     card('FS Used/Total', (fmtBytes(fsUsed)+' / '+fmtBytes(fsTotal))),"
        "     card('FS Usage %', fmtPct(fsPct)),"
        "     card('PSRAM', ((d.psram_used!=null?fmtBytes(d.psram_used):'—')+' / '+(d.psram_total!=null?fmtBytes(d.psram_total):'—'))),"
        "     card('Flash Size', fmtBytes(flashSize)),"
        "     card('Flash Usage %', fmtPct(flashPct))"
        "   ].join('');"

        "   secNET.innerHTML=["
        "     card('IP', (d.ip||'—')),"
        "     card('SSID', d.ssid),"
        "     card('RSSI', (d.rssi!=null?d.rssi+' dBm':'—')),"
        "     card('MAC (STA)', d.mac_sta||d.mac),"
        "     card('Netmask', d.netmask),"
        "     card('Gateway', d.gw),"
        "     card('DNS', d.dns)"
        "   ].join('');"

        "   var fw=(d.firmware||{}); var build=(fw.build&&fw.build.join)?fw.build.join('.'):(fw.build||'—');"
        "   secFW.innerHTML=["
        "     '<div class=\\'muted\\'>Chip Model</div><div>'+(d.chip_model||'ESP32-S3')+'</div>',"
        "     '<div class=\\'muted\\'>Chip Revision</div><div>'+(d.chip_revision!=null?d.chip_revision:'—')+'</div>',"
        "     '<div class=\\'muted\\'>Cores</div><div>'+(d.cores!=null?d.cores:'2')+'</div>',"
        "     '<div class=\\'muted\\'>Link</div><div id=\\'linkState\\'>—</div>',"
        "     '<div class=\\'muted\\'>Last Update</div><div id=\\'lastUpd\\'>—</div>',"
        "     '<div class=\\'muted\\'>RTT (avg)</div><div id=\\'rttAvg\\'>—</div>',"
        "     '<div class=\\'muted\\'>Board</div><div>'+(d.board||'—')+'</div>',"
        "     '<div class=\\'muted\\'>MicroPython</div><div>'+(fw.micropython||'—')+'</div>',"
        "     '<div class=\\'muted\\'>Build</div><div>'+build+'</div>'"
        "   ].join('');"
        "   updateLinkUI();"
        " }catch(_){ failCount++; if(failCount>50) failCount=50; updateLinkUI(); }"
        "}"
        "setInterval(pollInfo,1500);pollInfo();"
        "</script></body></html>"
    )
    return html

# ---------- HTTP server (optimized) ----------


async def _serve(reader, writer):
    try:
        # ---- request line ----
        line = await reader.readline()
        if not line:
            await writer.aclose()
            return
        try:
            parts = line.decode().split(' ')
            method, path = parts[0], parts[1]
        except Exception:
            method, path = 'GET', '/'

        # ---- consume headers ----
        while True:
            h = await reader.readline()
            if not h or h == b'\r\n':
                break

        # ---- responder ----
        def send(status='200 OK', ctype='text/html', body=b''):
            try:
                writer.write(b'HTTP/1.1 ' + status.encode() + b'\r\n')
                writer.write(b'Content-Type: ' + ctype.encode() + b'\r\n')
                writer.write(b'Cache-Control: no-store\r\n')
                writer.write(b'Connection: close\r\n')
                writer.write(b'Content-Length: ' + str(len(body)).encode() + b'\r\n\r\n')
                if body:
                    writer.write(body)
            except:
                pass

        # ---- routes ----
        if path == '/' or path.startswith('/index') or path == '/info':
            send(body=page_html().encode())

        elif path.startswith('/board.jpg'):
            # optional local board image
            try:
                with open('board.jpg', 'rb') as f:
                    send(ctype='image/jpeg', body=f.read())
            except Exception:
                send('404 Not Found', 'text/plain', b'Missing board.jpg')

        elif path.startswith('/api/pins'):
            # live GPIO snapshot only
            vals = {d: read_d_pin(d) for d in D_PINS}
            body = json.dumps({'order': list(D_PINS), 'values': vals}).encode()
            send('200 OK', 'application/json', body)

        elif path.startswith('/api/info'):
            # ---- Build payload for ESP Info + top pills ----
            try:
                ni = network_info()
            except Exception:
                ni = {}

            heap = heap_info()
            fs   = fs_info()
            flsz = flash_size()

            # Heap
            heap_used  = heap.get('alloc') if heap else None
            heap_free  = heap.get('free')  if heap else None
            heap_total = (heap_used + heap_free) if (heap_used is not None and heap_free is not None) else None

            # FS (robust percentage; works when used==0 and avoids div/0)
            fs_used  = fs['used']  if fs else None
            fs_total = fs['total'] if fs else None
            fs_pct = None
            if fs_total not in (None, 0) and fs_used is not None:
                fs_pct = round((fs_used / fs_total) * 100, 1)

            payload = {
                # Runtime & Timers
                'ip': ni.get('ip'),
                'cpu_freq_mhz': cpu_freq_mhz(),
                'uptime_s': uptime_s(),

                # Memory & Storage
                'heap': heap,
                'flash_size': flsz,
                'fs': fs,
                'heap_used': heap_used,
                'heap_total': heap_total,
                'heap_free': heap_free,
                'fs_used': fs_used,
                'fs_total': fs_total,
                'fs_used_pct': fs_pct,
                'psram_total': 8 * 1024 * 1024,
                'psram_used': None,

                # Network & Connectivity
                'ssid': ni.get('ssid'),
                'rssi': ni.get('rssi'),
                'mac_sta': ni.get('mac_sta'),
                'netmask': ni.get('netmask'),
                'gw': ni.get('gw'),
                'dns': ni.get('dns'),

                # Firmware & System Info
                'firmware': build_info(),
                'board': sys.platform,
                'cores': cores_count(),
                'chip_model': detect_chip_model(),
                'chip_revision': 2,

                # Extras used by UI
                'order': list(D_PINS),
                'pinmap': load_pinmap() or None,
            }
            send('200 OK', 'application/json', json.dumps(payload).encode())

        else:
            send('404 Not Found', 'text/plain', b'Not Found')

        await writer.drain()

    except Exception as e:
        try:
            writer.write(b'HTTP/1.1 500\r\nContent-Type: text/plain\r\n\r\n' + str(e).encode())
            await writer.drain()
        except:
            pass
    finally:
        try:
            await writer.aclose()
        except:
            pass

# ---------- Main Run ----------
async def run():
    await asyncio.start_server(_serve, '0.0.0.0', HTTP_PORT)
    print('[GPIOLive] v1.0.2 listening on port', HTTP_PORT)
    asyncio.create_task(_breathe())
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass

try:
    asyncio.run(run())
except Exception as e:
    print('run() exited:', e)           
