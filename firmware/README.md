# Raamses Display Device Firmware

ESP32 firmware for 5 display devices that monitor the Raamses gateway server.
Each device registers via HTTP, sends heartbeats, and displays real-time
gateway stats (CPU, RAM, agent count) and alert state.

## Devices

| Device | Hardware | Display | Input | Role |
|--------|----------|---------|-------|------|
| CYD | ESP32 + ILI9341 | 320x240 TFT | Touch | Desktop monitor |
| Cardputer | ESP32-S3 | 240x135 IPS | 56-key keyboard | Compose messages to agent |
| Core2 | ESP32 + M5Core2 | 320x240 LCD | Capacitive touch | Touch-button actions |
| StickC Plus2 | ESP32-PICO | 80x160 TFT | 2 buttons | Pocket monitor |
| Watchy 2.0 | ESP32 | 200x200 e-paper | 4 buttons | Ultra-low power wearable |

## Quick Start

### Prerequisites
- PlatformIO Core (`pip install platformio`)
- WiFi credentials as env vars:
  ```bash
  export WIFI_SSID="your_ssid"
  export WIFI_PASS="your_password"
  ```

### Build and Flash (per device)
```bash
cd firmware

# CYD
pio run -e cyd -t upload

# Cardputer
pio run -e cardputer -t upload

# Core2
pio run -e core2 -t upload

# StickC Plus2
pio run -e stickc -t upload

# Watchy 2.0
pio run -e watchy -t upload
```

### Serial Monitor
```bash
pio device monitor -e cyd    # or any env name
```

## Architecture

All devices share `src/RaamsesClient.h` — a single C++ class that handles:
- WiFi connection and reconnection
- Device registration (`POST /register`)
- Periodic heartbeat (`POST /heartbeat`)
- Stats fetching (`GET /stats`)
- Alert state tracking from heartbeat responses

Each device has its own `*_main.cpp` for display rendering and input handling.
The PlatformIO `platformio.ini` configures per-device build flags (screen size,
libraries, board definitions).

## Gateway Protocol

Devices communicate with the Raamses gateway over HTTP/JSON on port 8765:

```
POST /register    → { device_id, device_type, schema_version }
POST /heartbeat   → { device_id }
GET  /stats       → { cpu_temp_c, cpu_percent, mem_used_percent, agents_registered, ... }
POST /update      → { device_id, task, progress, alert }
```

The gateway returns `gateway_stats` in every register/heartbeat response.
If an agent has an active alert, the response includes `alert` and `alert_seq`.

## Configuration

Edit `platformio.ini` to change:
- `GATEWAY_IP` — your Raamses gateway IP (default: 192.168.6.230)
- `GATEWAY_PORT` — gateway port (default: 8765)
- `WIFI_SSID` / `WIFI_PASS` — WiFi credentials (via env vars)
- `HEARTBEAT_INTERVAL_MS` — heartbeat frequency (default: 15s)
- `DEVICE_ID` — unique device identifier

## File Layout

```
firmware/
├── platformio.ini          # PlatformIO config (5 environments)
├── README.md               # This file
└── src/
    ├── RaamsesClient.h     # Shared HTTP client + WiFi + state
    ├── cyd_main.cpp        # CYD 320x240 TFT monitor
    ├── cardputer_main.cpp  # Cardputer keyboard + display
    ├── core2_main.cpp      # Core2 touch + display
    ├── stickc_main.cpp     # StickC compact display
    └── watchy_main.cpp     # Watchy e-paper + deep sleep
```

## Testing Without Hardware

Use the Python device simulator to test the gateway without flashing firmware:
```bash
cd /home/pi/RaamsesServer
python3 src/linux/rgs/client/device_client.py cyd-001 cyd --demo
```

Or simulate an alert:
```bash
python3 sim_alert.py --trigger --device-id cyd-001
python3 sim_alert.py --list
```