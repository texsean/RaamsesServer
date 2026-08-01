# RGS (Raamses Gateway Server) — Project Status

**Last Updated:** 2026-08-01

## Current Focus

Wrapping up the full Raamses product: Linux gateway server + device firmware for
all 5 display devices. The system is an agent monitoring platform — devices
connect to the gateway over WiFi (HTTP/JSON), display real-time agent stats,
and show alerts when agents need help.

## What's Done

### Linux Gateway Server (port 8765)
- TCP + HTTP dual-protocol message router
- Session registry (thread-safe, heartbeat tracking, stale detection)
- Message router (gateway-local vs agent-targeted dispatch)
- HTTP JSON endpoints: /register, /heartbeat, /update, /stats, /agents, /status, /verify, /report, /siteid
- Gateway stats (CPU, RAM, disk, temp, uptime — stdlib only, no psutil)
- Alert state in heartbeat/register responses ("Agent needs help")
- Trust-Verify (filesystem + git inspection)
- Report-Issue (log zip + mailto URL)
- Site-ID (unique UUID per installation)
- 158 tests passing (QA/tests/)

### LoRa Bridge
- Meshtastic + RangePi backends
- Binary protocol v1.1 (ALERT, ACK, CLEAR, HEARTBEAT, REGISTER, BUZZ)
- Mock mode when no radio connected
- Concurrent HTTP + LoRa operation

### Agent Bus (port 8787)
- Inter-agent messaging (register, send, inbox poll, ack)
- Auto-timeout (120s configurable)
- JSON logging per session
- Agents: Hermes, Orion, Codex, firmware pagers

### Device Firmware (PlatformIO)
- 5 ESP32 display devices, shared RaamsesClient.h library
- CYD — 320x240 TFT desktop monitor
- Cardputer — keyboard + display, can compose messages to agent
- Core2 — touch LCD with action buttons (refresh, alert, clear)
- StickC Plus2 — 80x160 pocket monitor
- Watchy 2.0 — e-paper, deep sleep, 5-min wake cycle

### Consoles & Dashboards
- RADAR dashboard (3-panel Rich, live gateway data)
- Terminal console (htop-style)
- Server console
- Monitor.py
- Sim device launcher (3 agents with staggered heartbeats)

### Windows Build (C++23)
- ConfigLoader, Logger, Verifier
- CMake multi-target build
- Platform-aware signal handling

## Repository Structure

```
RaamsesServer/
├── ProjectStatus/          # Status docs
├── firmware/               # ESP32 PlatformIO firmware (5 devices)
│   ├── platformio.ini      # 5 environments: cyd, cardputer, core2, stickc, watchy
│   ├── README.md
│   └── src/
│       ├── RaamsesClient.h # Shared WiFi + HTTP + state
│       ├── cyd_main.cpp
│       ├── cardputer_main.cpp
│       ├── core2_main.cpp
│       ├── stickc_main.cpp
│       └── watchy_main.cpp
├── firmware/rangepi/       # RangePi RP2040 MicroPython bridge
├── schemas/                # XSD protocol definitions
├── src/
│   ├── linux/
│   │   ├── rgs/             # Python package (gateway, console, client, lora, agentbus)
│   │   │   ├── server/      # GatewayServer, SessionRegistry, MessageRouter
│   │   │   ├── agentbus/    # Agent Bus (port 8787)
│   │   │   ├── lora/        # LoRa bridge (Meshtastic + RangePi)
│   │   │   ├── client/      # TCP device client + emulator
│   │   │   ├── console/     # RADAR, terminal, server consoles
│   │   │   ├── messages/    # Protocol message types
│   │   │   ├── verifier.py  # Trust-Verify
│   │   │   ├── report_issue.py
│   │   │   └── site_config.py
│   │   └── cpp/            # C++ verifier, core, logging
│   ├── windows/            # Windows C++ build
│   └── android/            # Android console app (Kotlin)
├── QA/
│   ├── tests/              # 158 passing pytest tests
│   └── console/
├── launch_gateway.py      # Single-command gateway launcher
├── launch_agentbus.py     # Agent Bus launcher
├── launch_devices.py      # Sim device launcher
├── daemon_gateway.py     # Daemonized gateway
├── run_radar.py          # RADAR dashboard launcher
├── sim_alert.py          # Alert trigger/clear test tool
└── gateway.log           # Runtime log
```

## Recent Commits
- feat: add Agent Bus — inter-agent messaging on port 8787
- feat: add gateway_stats to heartbeat/register responses + GET /stats endpoint
- feat: heartbeat/register responses include 'Agent needs help' alert
- feat: LoRa + HTTP concurrent gateway with Meshtastic bridge
- feat: Add Trust but Verify, User-Reported Issues, and SiteId to Linux side

## Hardware Inventory

| Device | Type | Transport | Status |
|--------|------|-----------|--------|
| CYD (Cheap Yellow Display) | ESP32 + 2.8" TFT | WiFi (HTTP) | Firmware ready |
| M5Stack Cardputer | ESP32-S3 + keyboard | WiFi (HTTP) | Firmware ready |
| M5Stack Core2 | ESP32 + 2" touch LCD | WiFi (HTTP) | Firmware ready |
| M5Stack StickC Plus2 | ESP32-PICO + 0.96" TFT | WiFi (HTTP) | Firmware ready |
| Watchy 2.0 | ESP32 + 1.28" e-paper | WiFi (HTTP) | Firmware ready |
| Meshtastic radio x2 | LoRa mesh | LoRa | Protocol ready, mock mode |
| RangePi dongle | RP2040 + LoRa | USB serial | Firmware + backend ready |

## Multi-Agent Strategy
- Do not lock to Hermes — agent-agnostic design
- Test with local Llama + OpenAI + Grok + Deepseek agents
- Agent Bus allows any agent to register and message
- Desktop Console is agent-agnostic