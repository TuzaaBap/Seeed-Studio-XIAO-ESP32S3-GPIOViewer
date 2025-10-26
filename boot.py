# boot.py — Wi-Fi setup for ESP32 / ESP32-S3 (MicroPython)

import network, time

# ====== CONFIG ======
SSID = "Your_WiFi_SSID"          # <-- set me
PASSWORD = "Your_WiFi_Password"  # <-- set me

# Optional: set a hostname (shows on router / mDNS helpers)
HOSTNAME = "gpio-live"

# Optional: STATIC IP (uncomment to use)
# STATIC_IP = ("192.168.1.50", "255.255.255.0", "192.168.1.1", "192.168.1.1")

# Total seconds to try before giving up (boot continues even if Wi-Fi fails)
CONNECT_TIMEOUT_S = 20


def connect_wifi():
    # Disable AP to save power / avoid confusion
    try:
        ap = network.WLAN(network.AP_IF)
        ap.active(False)
    except:
        pass

    sta = network.WLAN(network.STA_IF)
    if not sta.active():
        sta.active(True)

    # Hostname (supported on newer MicroPython builds)
    try:
        if HOSTNAME:
            sta.config(dhcp_hostname=HOSTNAME)
    except:
        pass

    # Optional static IP
    try:
        if "STATIC_IP" in globals() and STATIC_IP:
            sta.ifconfig(STATIC_IP)
    except:
        pass

    if sta.isconnected():
        ip, nm, gw, dns = sta.ifconfig()
        print("Wi-Fi already connected:", ip)
        return sta

    print("Connecting to Wi-Fi:", SSID)
    try:
        sta.connect(SSID, PASSWORD)
    except Exception as e:
        print("connect() error:", e)

    t0 = time.ticks_ms()
    while not sta.isconnected() and time.ticks_diff(time.ticks_ms(), t0) < CONNECT_TIMEOUT_S * 1000:
        print(".", end="")
        time.sleep(1)

    print()  # newline after dots

    if sta.isconnected():
        ip, nm, gw, dns = sta.ifconfig()
        print("Wi-Fi: UP  IP:", ip, "GW:", gw, "DNS:", dns)
    else:
        print("Wi-Fi: FAILED (timeout)")
    return sta


try:
    connect_wifi()
except Exception as e:
    print("Wi-Fi error:", e)
