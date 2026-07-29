# LoRa + HTTP Concurrent Gateway — Status

**Date:** 2026-07-29
**Status:** Implementation complete, 59 tests passing

## What Was Built

The Raamses gateway now supports concurrent HTTP (WiFi) and LoRa (Meshtastic) transport. When a RangePi is detected on the server, the gateway uses both LoRa and WiFi HTTP concurrently — LoRa-compatible displays can still receive alerts even when they don't have WiFi.

### New Files

| File | Purpose |
|------|---------|
| `src/linux/rgs/lora/__init__.py` | LoRa module exports |
| `src/linux/rgs/lora/protocol.py` | Binary protocol encode/decode (6 command types) |
| `src/linux/rgs/lora/bridge.py` | LoRaBridge — Meshtastic radio interface, listener, ALERT/CLEAR broadcaster |
| `scripts/setup_lora_channel.py` | Configure "raamses" secondary channel on Meshtastic radio |
| `launch_gateway.py` | Single-command launcher for HTTP+LoRa concurrent gateway |
| `QA/tests/test_lora_protocol.py` | 35 tests — protocol encode/decode, edge cases, anti-replay |
| `QA/tests/test_lora_bridge.py` | 24 tests — bridge mock mode, packet handling, registry transport fields |

### Modified Files

| File | Changes |
|------|---------|
| `src/linux/rgs/server/gateway.py` | Added `enable_lora`, `lora_serial_port`, `lora_tcp_host` params; LoRa bridge lifecycle; alert/clear LoRa broadcast on HTTP /update; transport/node_id in /agents and /register |
| `src/linux/rgs/server/session_registry.py` | Added `transport`, `node_id`, `alert_active`, `alert_seq` fields; `get_by_node_id()`, `list_by_transport()`, `set_alert()`, `clear_alert()`, `get_alert_state()`, `list_alerted()` methods |

## Architecture

```
    ┌──────────────────────────────────────────────┐
    │              GatewayServer                     │
    │  ┌─────────────┐    ┌──────────────────┐      │
    │  │ TCP+HTTP    │    │   LoRaBridge      │      │
    │  │ (port 8765) │    │  (Meshtastic)     │      │
    │  │             │    │                  │      │
    │  │ WiFi devices │    │ LoRa devices     │      │
    │  │ HTTP POST   │    │ port 256         │      │
    │  └──────┬──────┘    └────────┬─────────┘      │
    │         │                    │                │
    │         └─── SessionRegistry ─┘                │
    │              (shared, thread-safe)             │
    └──────────────────────────────────────────────┘
```

### LoRa Protocol (v1.1 from RAAMSES_LORA_PROTOCOL.md)

Wire format: `[cmd:1][len:1][payload:N]` on Meshtastic PRIVATE_APP port 256.

| Cmd | Code | Direction | Purpose |
|-----|------|-----------|---------|
| ALERT | 0x01 | Bridge → Nodes | Agent needs help (count + seq) |
| ACK | 0x02 | Node → Bridge | Acknowledge ALERT receipt |
| CLEAR | 0x03 | Bridge → Nodes | Alert resolved (same seq as ALERT) |
| HEARTBEAT | 0x04 | Node → Bridge | Keepalive every 30s (node_id + status) |
| REGISTER | 0x05 | Node → Bridge | Device registration on boot |
| BUZZ | 0x06 | Bridge → Node | Test buzzer/LED |

### Alert Flow

1. HTTP device sends `POST /update` with `{"alert": "agent needs help"}`
2. Gateway broadcasts ALERT(count, seq) on LoRa channel
3. LoRa-only nodes receive ALERT, flash LED, show screen
4. When HTTP device sends update without alert (or with `alert_clear`):
   - Gateway broadcasts CLEAR(count, same_seq) on LoRa
   - LoRa nodes dismiss the alert

### Bridge Mode (WiFi + LoRa Relay)

WiFi-connected bridges relay LoRa packets to the HTTP gateway:
- REGISTER on LoRa → `POST /register` with `"source":"lora_relay"`
- HEARTBEAT on LoRa → `POST /heartbeat` with `"source":"lora_relay"`

This means the gateway sees ALL devices — WiFi direct via HTTP, LoRa nodes via bridge relay.

### Mock Mode

When no Meshtastic radio is connected, the bridge runs in mock mode:
- Logs what it would send/receive
- Gateway still serves HTTP clients normally
- LoRa broadcasts are logged but not transmitted

## Launch Commands

```bash
# HTTP only (no LoRa)
python3 launch_gateway.py

# HTTP + LoRa (auto-detect serial)
python3 launch_gateway.py --lora

# HTTP + LoRa (specific serial port)
python3 launch_gateway.py --lora --lora-serial /dev/ttyUSB0

# HTTP + LoRa (TCP-connected radio)
python3 launch_gateway.py --lora --lora-tcp 192.168.1.100
```

## Test Results

```
59 passed in 0.06s
```

- 35 protocol tests (encode/decode all 6 commands, edge cases, anti-replay)
- 24 bridge/registry tests (mock mode, packet handling, transport fields, alert tracking)

## Dependencies

- `meshtastic` (v2.7.11) — already installed on this Pi
- `pyserial` (v3.5) — already installed
- No new dependencies required

## Next Steps

1. Connect a Meshtastic radio (Heltec v3 or similar) via USB
2. Run `python3 scripts/setup_lora_channel.py` to configure the "raamses" channel
3. Flash console firmware (from RaamsesMesh repo) to LoRa display devices
4. Launch with `python3 launch_gateway.py --lora`
5. Test end-to-end: HTTP alert → LoRa ALERT broadcast → device LED flash