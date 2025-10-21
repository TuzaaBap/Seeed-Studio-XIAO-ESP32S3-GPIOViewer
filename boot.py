# boot.py — Wi-Fi setup for ESP32-S3 Live GPIO Runner

import network, machine, time

# ==== CONFIG ====
SSID = "Airtel_riyal"
PASS = "Euuu@1713"

def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("Connecting to Wi-Fi:", SSID)
        wlan.connect(SSID, PASS)
        timeout = 20
        while not wlan.isconnected() and timeout > 0:
            print(".", end="")
            time.sleep(1)
            timeout -= 1
    print("\nWi-Fi: UP" if wlan.isconnected() else "Wi-Fi: FAILED")
    if wlan.isconnected():
        print("IP:", wlan.ifconfig()[0])

try:
    connect_wifi()
except Exception as e:
    print("Wi-Fi error:", e)
