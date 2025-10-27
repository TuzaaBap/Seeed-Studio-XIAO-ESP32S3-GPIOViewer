# Seeed Studio XIAO ESP32S3 GPIO Viewer

A MicroPython-based real-time GPIO monitor for the Seeed Studio XIAO ESP32S3 Sense.  
Displays live digital pin states (HIGH/LOW/TOUCH) through a local web interface using Thonny or any MicroPython environment.


## 🌐 Overview
This release introduces a **new, lightweight web dashboard** that lets you view GPIO states, system stats, and board diagnostics in real-time — right from your browser.

> 🧠 Ideal for debugging complex IoT systems such as relay drivers, sensors, or automation boards without requiring a serial console.

---

## 📸 Dashboard Preview For GPIOLive

<img width="1436" height="569" alt="image" src="https://github.com/user-attachments/assets/056cfeec-4807-45f5-8948-f568de167cf0" />

## 📸 Dashboard Preview For ESPInfo


<img width="2872" height="1618" alt="image" src="https://github.com/user-attachments/assets/2da62146-f776-4053-a1cc-a14b4d5922c6" />



---

## ✨ New in v1.0.2
### 🖤 Redesigned Dark Mode Interface
- Sleek, professional dark theme for better readability.  
- Responsive layout with adaptive contrast and smoother transitions.  
- Light/Dark mode toggle saved automatically in local storage.

### ⚙️ Expanded ESP Info Page
All critical system metrics are now displayed on one unified page:
| Category | Parameters |
|-----------|-------------|
| **Runtime** | CPU frequency, uptime |
| **Memory & Storage** | Heap used/total, FS usage %, Flash size, PSRAM |
| **Network** | IP, SSID, RSSI, MAC, Gateway, DNS |
| **Firmware & System** | Chip model, cores, MicroPython version, build info |

> Quick access to all debugging essentials — no serial monitor required.

### 💡 Improved GPIO Monitoring
- Live **analog and digital pin visualization**.
- ADC pins show **real-time voltage badges** (auto-scaled color gradient).  
- Green = LOW, Red = HIGH for digital pins.


---

## 🧠 How It Works
The firmware runs an async web server that:
- Reads all GPIO pins periodically
- Updates pin states in JSON
- Serves a responsive HTML dashboard at `http://<board-ip>:8080/`

---

## ⚡ Requirements
- Seeed Studio XIAO ESP32S3 Sense  
- MicroPython firmware ≥ 1.21  
- Thonny IDE  
- Wi-Fi credentials configured in `boot.py`

---

## 🚀 Setup
1. Flash MicroPython firmware to the board  
2. Open Thonny → copy project files (`boot.py`, `main.py`)  
3. Edit `boot.py` to match your Wi-Fi:
   ```python
   SSID = "Your_WiFi_SSID"
   PASSWORD = "Your_WiFi_Password" 
4. Run or reboot the board  
5. Visit the displayed IP in your browser (e.g., `http://192.168.1.4:8080/`)


---

⭐ **If you like this project, consider giving it a Star** to support future updates!  
---

## 📄 License
MIT License © 2025 [TuzaaBap](https://github.com/TuzaaBap)
