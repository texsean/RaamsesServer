# Raamses Server Status

> Last updated: 2026-07-20
> Repository: git@github.com:texsean/RaamsesServer.git
> Codebase root: `src/linux/rgs/`

This document describes the complete state of the Raamses Server project,
including its gateway, console, and testing infrastructure. Any agent
connecting to this server should read this document first to understand
the communication protocols and tooling available.

---

## 1. Raamses Server (Gateway)

The Raamses Gateway Server (`rgs`) is a TCP-based message routing server
that connects multiple devices/agents and routes commands between them.
It serves as the central hub of the Raamses multi-device agent network.

### 1.1 Architecture

```
┌──────────────────────────────────────────────────────────┐
│              Gateway Server (port 8765)                   │
│                                                           │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────────┐ │
│  │ SessionReg. │  │ MessageRouter│  │ StaleCleanup     │ │
│  │(O(1) lookup)│  │(classify+  │  │ Thread(30s)     │ │
│  │             │  │ dispatch)   │  │                  │ │
│  └──────┬──────┘  └──────┬──────┘  └──────────────────┘ │
│         │                │                                │
│  ┌──────┴────────────────┴─────────────────────────────┐ │
│  │           GatewayServer (TCP accept loop)           │ │
│  │   Each client -> daemon thread (_handle_client)     │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                           │
│  Log: gateway.log (file-based log tail)                  │
└──────────────────────────────────────────────────────────┘
```

**File locations:**
- Gateway server: `src/linux/rgs/server/gateway.py` (371 lines)
- Session registry: `src/linux/rgs/server/session_registry.py` (178 lines)
- Message router: `src/linux/rgs/server/message_router.py` (217 lines)
- Message envelope: `src/linux/rgs/messages/envelope.py` (45 lines)
- Package init: `src/linux/rgs/__init__.py`

### 1.2 Protocol Overview

The gateway speaks **plain-text line-delimited TCP** on port 8765.
Messages are single lines terminated by `\n`. The protocol supports two
classes of communication:

1. **Agent Communication** — Devices/agents register, heartbeat, send
   task updates, and receive commands.
2. **Console Communication** — The operator connects from a terminal
   to query status, list agents, and send targeted commands.

All messages use simple text-based commands — no JSON, no binary
formats. This keeps the protocol embeddable in any hardware with a
TCP stack.

### 1.3 Agent Communication (Gateway-Based)

Agents (CYD, E-Paper, Watch, Full desktop, etc.) connect via TCP,
register with the gateway, and then communicate using text commands.

#### 1.3.1 Registration

**Agent sends:**
```
REGISTER:<device_id>|<device_type>|<schema_version>[|<firmware_version>]
```

**Examples:**
```
REGISTER:cyd-001|cyd|1.0
REGISTER:watch-001|watch|1.0|2.1.3
```

**Gateway responds (on success):**
```
REGISTER_ACK:true|<server_iso_timestamp>|<schema_version>|rgs-gateway
```

**Example response:**
```
REGISTER_ACK:true|2026-07-20T14:30:00.123Z|1.0|rgs-gateway
```

**Session registry fields stored:**
- `device_id` — unique identifier (UUID recommended)
- `device_type` — one of: `cyd`, `full`, `epaper`, `watch`, `legacy`
- `schema_version` — protocol schema version (e.g., `"1.0"`)
- `firmware_version` — optional device firmware version
- `capabilities` — optional dict with screen/input/output/power
- `connection` — TCP socket handle
- `status` — `"active"` | `"paused"` | `"offline"`
- `current_task` — string description of current work
- `last_heartbeat` — ISO timestamp of last heartbeat
- `registered_at` — ISO timestamp of registration

#### 1.3.2 Heartbeats

**Agent sends (periodic):**
```
heartbeat
```
or simply:
```
PING
```

**Gateway responds:**
```
OK: heartbeat received
```

Heartbeats refresh the agent's liveness timer. If no heartbeat is
received within the `heartbeat_timeout` (default 90 seconds), the
gateway marks the agent as `"offline"` and eventually removes it
during the 30-second stale-agent cleanup cycle.

**Configuration:**
- Default timeout: 90 seconds
- Cleanup interval: 30 seconds (background thread)
- Configured in `GatewayServer.__init__(heartbeat_timeout=90)`

#### 1.3.3 Task Updates

Agents send progress updates using these prefixes:

| Prefix      | Meaning                    | Example                                     |
|-------------|----------------------------|---------------------------------------------|
| `task:`     | New task assigned/started  | `task: rendering dashboard`                 |
| `progress:` | Percentage progress        | `progress: 45% rendering`                   |
| `update:`   | General status update      | `update: rendering complete`                |
| `done:`     | Task completion            | `done: dashboard rendered`                  |
| `error:`    | Error report               | `error: screen timeout`                     |

**Gateway responds (for all):**
```
OK: task updated to '<description>'
```

#### 1.3.4 Commands from Gateway to Agent

The gateway routes commands to agents using slash commands typed by
the operator (see Console Communication below). Commands are delivered
via TCP in this format:

```
COMMAND:<device_id>:<raw_command>
```

**Example:**
```
COMMAND:cyd-001:/tell cyd-001 render dashboard
```

Commands are **dropped (not queued)** if the agent has moved on to a
different task or gone offline. This is the configured behavior to
ensure agents only execute relevant commands.

### 1.4 Console Communication (Gateway-Based)

The console (operator terminal) connects to the same TCP port and can
send both gateway-local commands and agent-targeted commands.

#### 1.4.1 Gateway-Local Commands

These execute on the gateway itself, not forwarded to any agent:

| Command      | Response                                                                 |
|--------------|--------------------------------------------------------------------------|
| `status`     | `Gateway active — N agents registered (M total)`                         |
| `ping`       | Same as `status`                                                         |
| `agents`     | List of connected agents with status, type, and task                     |
| `list`       | Same as `agents`                                                         |
| `list agents`| Same as `agents`                                                         |
| `quit`       | Stops the gateway                                                        |
| `exit`       | Same as `quit`                                                           |
| `register`   | Returns instruction to use `REGISTER:` prefix                            |
| `heartbeat`  | Returns info to use `/tell <id> heartbeat` for targeted heartbeats       |

**Example `agents` response:**
```
Connected agents (3):
  ● agent-cyd-01... type=cyd task='75% initialize monitoring'
  ◐ agent-full-02 type=full task='idle'
  ◐ agent-watch-03 type=watch task='waiting'
```

Legend: `●` = active, `◐` = paused/idle

#### 1.4.2 Agent-Targeted Commands (Slash Commands)

These commands target a specific agent and are delivered via TCP:

| Command              | Description              | Example                                        |
|----------------------|--------------------------|------------------------------------------------|
| `/cmd <id> <action>` | Send command to agent    | `/cmd cyd-001 render dashboard`                |
| `/tell <id> <msg>`   | Send message to agent    | `/tell cyd-001 status`                         |
| `/ask <id> <query>`  | Ask agent a question     | `/ask cyd-001 what is your battery level`      |
| `/pause <id>`        | Pause agent              | `/pause cyd-001`                               |
| `/resume <id>`       | Resume agent             | `/resume cyd-001`                              |
| `/stop <id>`         | Stop agent               | `/stop cyd-001`                                |
| `/restart <id>`      | Restart agent            | `/restart cyd-001`                             |
| `/approve <id>`      | Approve agent task       | `/approve cyd-001`                             |
| `/reject <id>`       | Reject agent task        | `/reject cyd-001`                              |
| `/ack <alert_id>`    | Acknowledge alert        | `/ack abc123`                                  |

**Response format:**
- Delivered: `[✓] DELIVERED — Command sent to <id> (current task: ...)`
- Dropped:  `[✗] DROPPED — Agent <id> not registered / offline / has moved on`
- Gateway:  `[→] EXECUTED — <result>`

#### 1.4.3 Agent-Update Messages

Device-initiated status messages that the gateway classifies and records:

| Pattern           | Type           | Example                                    |
|-------------------|----------------|--------------------------------------------|
| `update <msg>`    | agent_update   | `update: task complete`                    |
| `task <msg>`      | agent_update   | `task: rendering dashboard`                |
| `progress <msg>`  | agent_update   | `progress: 75% rendering`                  |
| `done <msg>`      | agent_update   | `done: dashboard rendered`                 |
| `error <msg>`     | agent_update   | `error: connection lost`                   |
| `alert <msg>`     | agent_update   | `alert: low battery`                       |

### 1.5 Message Router Classification

The `MessageRouter` class classifies every incoming message into one of
three types. Classification happens before dispatch:

```
classify(raw_input) -> (type, target_id, payload)
```

**Classification rules (applied in order):**

1. **Slash commands** — matches `/cmd`, `/tell`, `/ask`, `/pause`,
   `/resume`, `/stop`, `/restart`, `/approve`, `/reject`, `/ack`
   → returns `("agent_command", target_id, payload)`

2. **Gateway commands** — first word matches GATEWAY_COMMANDS set:
   `register`, `registerack`, `heartbeat`, `status`, `quit`, `exit`,
   `agents`, `list`, `help`, `about`, `connect`, `disconnect`, `mock`,
   `clear`, `cls`, `reset`, `ping`
   → returns `("gateway", None, text)`

3. **Agent update patterns** — matches `^(update|task|progress|done|error|alert)\s+(.*)`
   → returns `("agent_update", None, text)`

4. **Bare `/` prefix** — starts with `/` but no known handler
   → returns `("gateway", None, text)` (passthrough)

5. **Default** — anything else
   → returns `("gateway", None, text)` (passthrough)

**Route method returns:**
```python
{
    "type": "gateway" | "agent_command" | "agent_update",
    "status": "delivered" | "dropped" | "executed",
    "message": "human-readable description",
    "target": "device_id or None",
    "result": {"success": True, "sent": "..."}  # only for agent_command
}
```

### 1.6 Session Registry API

Thread-safe registry with O(1) connection lookup:

```python
from rgs.server.session_registry import SessionRegistry

registry = SessionRegistry(heartbeat_timeout=90)

# Register an agent (returns AgentSession)
session = registry.register(
    device_id="cyd-001",
    device_type="cyd",
    schema_version="1.0",
    firmware_version="2.1.3",
    capabilities={"screen": {"width": 320, "height": 240}},
    connection=tcp_socket_object,
)

# O(1) lookup by connection object
session = registry.get_session_by_connection(tcp_socket_object)

# Lookup by device_id
session = registry.get("cyd-001")

# Record heartbeat
success = registry.heartbeat("cyd-001")

# Record task update
success = registry.mark_task("cyd-001", "rendering dashboard")

# List active agents (active or paused)
active = registry.list_active()

# Remove stale agents (returns list of removed IDs)
removed = registry.remove_stale()

# Unregister (clean up + remove from connection index)
session = registry.unregister("cyd-001")

# Count total registered
total = registry.count()
```

### 1.7 Gateway Server Lifecycle

```python
from rgs.server.gateway import GatewayServer

# Create and start server
server = GatewayServer(
    host="0.0.0.0",
    port=8765,
    heartbeat_timeout=90,
)

server.start()  # Blocking: runs accept loop in calling thread

# Initialize router (wires handlers)
router = server.initialize_router()

# Access registry for monitoring/debugging
registry = server.registry
sessions = registry.list_active()

# Stop server (closes all connections, joins threads)
server.stop()
```

### 1.8 Logging

All gateway events are logged via Python's `logging` module to
`gateway.log`. Log format includes:

- Registration events with peer address
- Heartbeat timestamps
- Task updates
- Command delivery/drop decisions
- Stale agent cleanup
- Connection errors

Log file locations checked (in order):
1. `gateway.log` (project root)
2. `src/linux/rgs/console/../../gateway.log`
3. `/var/log/raamses/gateway.log`
4. `/var/log/raamses/debug.log`

### 1.9 Server Status Summary

| Feature                    | Status        | % Complete | Notes                          |
|----------------------------|---------------|------------|--------------------------------|
| TCP server accept loop     | COMPLETE      | 100%       | Thread-per-client, daemon      |
| Registration protocol      | COMPLETE      | 100%       | REGISTER + REGISTER_ACK        |
| Heartbeat system           | COMPLETE      | 100%       | Text "heartbeat" / "PING"      |
| Task update tracking       | COMPLETE      | 100%       | task:/progress:/update:/done:  |
| Message routing            | COMPLETE      | 100%       | Slash commands + gateway cmds  |
| Stale agent cleanup        | COMPLETE      | 100%       | Background thread, 30s interval|
| Session registry (O(1))    | COMPLETE      | 100%       | Reverse connection index       |
| Connection index update    | COMPLETE      | 100%       | On register/unregister/stale   |
| Logging to gateway.log     | COMPLETE      | 100%       | File tail + console            |
| Agent capabilities         | COMPLETE      | 100%       | Stored but not validated       |
| Schema version checking    | PARTIAL       | 40%        | Header exists, not enforced    |
| TLS support                | NOT STARTED   | 0%         | Plan: optional TLS on 8766     |
| Client certificates        | NOT STARTED   | 0%         | For agent auth                 |
| Bearer token auth          | NOT STARTED   | 0%         | For console auth               |
| Command queueing           | NOT STARTED   | 0%         | Currently drops if agent moved |
| Command retry logic        | NOT STARTED   | 0%         | Exponential backoff            |
| Pub/sub broadcast          | NOT STARTED   | 0%         | Broadcast to all agents        |
| File-based log parsing     | PARTIAL       | 60%        | RADAR reads gateway.log        |
| JSON envelope support      | IN PROGRESS   | 30%        | Message dataclasses exist      |
| Mock server (async)        | COMPLETE      | 100%       | Random commands/alerts         |
| Windows RGS port           | IN PROGRESS   | 40%        | XAML skeleton + core C++       |

---

## 2. Raamses Client Console

The Client Console is the main operator interface — a Rich-based
terminal dashboard for monitoring connected devices, viewing
communications, and sending commands. Three console variants exist,
ranging from mission-control to lightweight display modes.

### 2.1 Terminal Console (Full Dashboard)

The primary Linux operator console. A three-panel Rich dashboard with
interactive keyboard navigation.

**File:** `src/linux/rgs/console/terminal_console.py` (605 lines)

**Layout (3 sections):**

```
┌──────────────────────────────────────────────────────────────┐
│  Header: RAAMSES v2.0.0 [full] [Blink:ON]  uptime 3m 42s    │
│  Q=quit | UP/DOWN=select config | ENTER=apply | 1-5=select  │
├──────────────────┬───────────────────────────────────────────┤
│  Left Panel      │  Right Panel                              │
│  ┌────────────┐  │  ┌─────────────────────────────────────┐ │
│  │ Configuration│  │  │ Connected Devices (ASCII icons)     │ │
│  │ blink_mode   │  │  │ CYD-320  [●] ACTIVE  rendering     │ │
│  │ blink_interval│ │  │ FULL-1   [●] ACTIVE  dashboard      │ │
│  │ log_level    │  │  │ EPAPER-1 [◐] IDLE   waiting        │ │
│  │ gateway_port │  │  │ CYD-321  [●] ACTIVE  updating      │ │
│  │ heartbeat    │  │  │ FULL-2   [○] OFFLINE disconnected  │ │
│  │ max_agents   │  │  │                                      │ │
│  │ [Apply]      │  │  └─────────────────────────────────────┘ │
│  └──────────────┘  │  ┌─────────────────────────────────────┐ │
│  ┌────────────┐  │  │  Communication Log                    │ │
│  │ Log Files  │  │  │ [IN  ] CYD-320   | heartbeat          │ │
│  │ > debug.log│  │  │ [OUT ] AGENT     | /cmd dev-001 ...  │ │
│  │   app.log  │  │  │ [IN  ] FULL-1    | task: render...    │ │
│  │   server.log│ │  │                                      │ │
│  │   comm.log │  │  └─────────────────────────────────────┘ │
│  │   gw.log   │  │  ┌─────────────────────────────────────┐ │
│  └────────────┘  │  │  Active Log Tail (debug.log)         │ │
│                  │  │  072026_143000.123 _handle_reg ...   │ │
│  └────────────────┤  │  072026_143005.456 _heartbeat ...   │ │
│                    │  │  ...                                 │ │
│                    │  └─────────────────────────────────────┘ │
└──────────────────┴───────────────────────────────────────────┘
```

**Controls:**
- `UP` / `DOWN` — Navigate configuration settings
- `ENTER` — Apply selected configuration (toggles blink_mode, etc.)
- `1`-`5` — Select log file to view in active tail
- `Q` or `quit` — Exit console

**Keyboard commands (single line):**
```
/help           Show help text
/connect        Connect FULL-1 device
/disconnect     Disconnect FULL-1 device
/blink [on|off] Toggle blink verification mode
/set <key> <val> Set configuration value (e.g., /set log_level debug)
/q              Quit
```

**Configuration settings:**
| Setting          | Values          | Default |
|------------------|-----------------|---------|
| blink_mode       | on / off        | on      |
| blink_interval   | Duration string | 2s      |
| log_level        | debug/info/warn | debug   |
| gateway_port     | Port number     | 8765    |
| heartbeat        | Duration string | 30s     |
| max_agents       | Integer         | 50      |

**Log files (editable list):**
- `debug.log` (active by default)
- `app.log`
- `server.log`
- `communication.log`
- `gateway.log`

Log format: `MMDDYY_HHMMSS.nnn<TAB>method_name<TAB>detail_string`

**How it works:**
1. Creates `logs/` directory in console source directory
2. Seeds `debug.log` with sample entries on first run
3. Runs Rich Live loop at 4Hz refresh rate
4. Reads log files on demand for active tail
5. Injects sample communication messages periodically
6. Blink mode cycles `O`/`@@` patterns on device icons

**Run it:**
```bash
python3 src/linux/rgs/console/terminal_console.py full   # Full dashboard
python3 src/linux/rgs/console/terminal_console.py cyd    # CYD mode
python3 src/linux/rgs/console/terminal_console.py epaper # E-Paper mode
```

**Status:** 100% complete. Runs as a standalone Rich Live dashboard.
Connects to gateway for live data, or runs in demo mode with injected
messages.

### 2.2 Server Console

A server-aware console that connects to the mock Raamses server via
TCP and displays live data from registered devices.

**File:** `src/linux/rgs/console/server_console.py` (402 lines)

**Architecture:**
- Connects to server TCP (default 127.0.0.1:9999)
- Auto-sends a `Register` message on connect
- Background thread receives messages from server
- Rich Live dashboard at 4Hz refresh

**Modes:**
| Mode      | Display                                    |
|-----------|--------------------------------------------|
| `full`    | 4-panel layout: overview, alerts, devices, event stream |
| `cyd`     | Single CYD-sized panel with status/alert   |
| `epaper`  | Single E-Paper-sized panel with status     |

**Protocol (JSON envelope per line):**
```json
{
    "header": {
        "message_id": "uuid",
        "timestamp": "ISO8601",
        "device_id": "",
        "schema_version": "1.0",
        "version": "1.0",
        "message_type": "Register|Alert|Command"
    },
    "payload": { ... }
}
```

**Console sends (on connect):**
```json
{
    "header": { "message_type": "Register", ... },
    "payload": {
        "device_id": "console-server-aware",
        "device_type": "console",
        "firmware_version": "1.0.0",
        "capabilities": { "screen": {...}, "input": {...} }
    }
}
```

**Console receives:**
- `RegisterAck` — Shows acceptance status in alerts
- `Command` — Shows in received commands list
- `Alert` — Shows with severity color (red/yellow/green)

**Commands:**
```
/connect      Connect to server (auto-connected by default)
/disconnect   Disconnect from server
/register     Send register message again
/clear-alerts Clear alert list
/quit         Exit console
```

**Run it:**
```bash
python3 src/linux/rgs/console/server_console.py full  # Default
python3 src/linux/rgs/console/server_console.py cyd
python3 src/linux/rgs/console/server_console.py epaper
```

**Status:** 90% complete.

**TODO:**
- ~~Auto-connect on startup~~ (DONE)
- Command input via prompt_toolkit (DONE but basic)
- Real-time device status from server registry (PARTIAL — pulls alerts/commands but not full device state from server)
- Send commands to server (NOT STARTED)
- Console-to-device command routing (NOT STARTED)

### 2.3 RADAR Console

RADAR = "Raamses Agent Display And Reporter" — A real-time dashboard
that connects directly to the gateway (port 8765) and displays live
agent status, device icons with blink verification, communication log,
and log tail.

**File:** `src/linux/rgs/console/radar.py` (367 lines)

**Architecture:**
- Queries gateway via TCP `agents` command every ~1 second
- Parses gateway response to build agent status dict
- Reads `gateway.log` for communication messages and live tail
- Displays ASCII device icons with blinking verification pulse
- Works in both TTY (Rich Live) and non-TTY (text mode) environments

**Dashboard sections (top to bottom):**

```
┌──────────────────────────────────────────────────────────────┐
│ RADAR — Gateway: 127.0.0.1:8765 | Agents: 3 (2 active) | ... │
├──────────────────────────────────────────────────────────────┤
│ ● CONNECTED AGENTS                                           │
│  +----------+   agent-cyd-01   [green]active[reset]  task=75%...│
│  |  CYD     |                                                  │
│  | +--------+                                                  │
│  | |  [@@] |       (blink @@ or O)                            │
│  | +--------+                                                  │
│  +----------+                                                  │
│                                                                │
│ ◆ COMM                                                         │
│  2026-07-20 14:30:00 INFO _handle_register ACCEPTED...        │
│  2026-07-20 14:30:05 INFO _handle_heartbeat heartbeat...      │
│                                                                │
│ ▸ TAIL — gateway.log                                          │
│  [30] INFO _handle_register ACCEPTED CYD-320                  │
│  [31] INFO _heartbeat Heartbeat from FULL-1                   │
└──────────────────────────────────────────────────────────────┘
```

**Device icons (4 built-in):**
- `cyd` — CYD 2.8" Color display (320x240)
- `full` — Full desktop display
- `epaper` — E-Paper display (200x200, 1-bit)
- `watch` — Smart Watch (120x120)

**Blink verification pulse:** Cycles `O` / `@@` on device icons
every ~750ms. This serves as a visual heartbeat to confirm agents
are still alive.

**Run it:**
```bash
# As module (preferred)
python3 -m rgs.console.radar --host 127.0.0.1 --port 8765

# With specific log file
python3 -m rgs.console.radar --log /var/log/raamses/gateway.log

# One-shot snapshot (no live mode)
python3 -m rgs.console.radar --once

# Inline run
python3 src/linux/rgs/console/radar.py --host 127.0.0.1 --port 8765
```

**Arguments:**
| Argument      | Default            | Description                      |
|---------------|--------------------|----------------------------------|
| `--host`      | 127.0.0.1          | Gateway server hostname          |
| `--port`      | 8765               | Gateway server port              |
| `--log`       | Auto-detect        | Path to gateway.log              |
| `--once`      | False              | Show one snapshot and exit       |

**Status:** 85% complete.

**TODO:**
- ~~Tty vs non-Tty detection~~ (DONE)
- ~~Gateway query via TCP `agents` command~~ (DONE)
- ~~Agent parsing from gateway response~~ (DONE)
- Log tail reading from gateway.log (DONE)
- Communication log from gateway.log (DONE)
- Rich table rendering for agents (PARTIAL — uses plain text with Rich markup)
- Keyboard commands to send to agents (NOT STARTED)
- Alert filtering/severity colors (PARTIAL — basic severity handling)
- Multi-gateway support (NOT STARTED)

### 2.4 Console Status Summary

| Feature                        | Status        | % Complete | Notes                           |
|--------------------------------|---------------|------------|---------------------------------|
| Terminal Console (full)        | COMPLETE      | 100%       | 3-panel Rich Live dashboard     |
| Terminal Console (cyd/epaper)  | COMPLETE      | 100%       | Single-panel fallback modes     |
| Keyboard navigation            | COMPLETE      | 100%       | UP/DOWN/ENTER, 1-5 log select   |
| Command input (/connect etc)   | COMPLETE      | 100%       | Single line commands            |
| Server Console (server-aware)  | IN PROGRESS   | 90%        | Connects, receives alerts       |
| RADAR Console                  | IN PROGRESS   | 85%        | Gateway query, icons, blink     |
| RADAR blink verification       | COMPLETE      | 100%       | 4-cycle blink pattern           |
| Device ASCII icons             | COMPLETE      | 100%       | 4 device types built-in         |
| Gateway log tail               | COMPLETE      | 100%       | Reads last 30 lines             |
| Communication log              | COMPLETE      | 100%       | Filters Registered/heartbeat    |
| Non-TTY text mode              | COMPLETE      | 100%       | Escape sequence clear + redraw  |
| Rich table rendering           | PARTIAL       | 60%        | Header + text body, not tables  |
| Agent keyboard commands        | NOT STARTED   | 0%         | RADAR needs send commands       |
| Alert severity coloring        | PARTIAL       | 40%        | Basic red/yellow/green          |
| Multi-gateway support          | NOT STARTED   | 0%         | Single gateway connection only  |

---

## 3. Testing Tools

The Raamses project includes a comprehensive testing infrastructure
for simulating devices, running integration tests, and monitoring
the gateway in real time.

### 3.1 Mock Raamses Server

An async TCP server for testing that simulates a Raamses gateway.
Unlike the real gateway, this server uses JSON envelopes and provides
randomized command dispatch and alert broadcasting.

**File:** `src/linux/rgs/server/mock_server.py` (284 lines)

**How it works:**
- Listens on TCP (default 127.0.0.1:9999)
- Accepts JSON lines (one JSON object per line)
- On Register: responds with RegisterAck (always accepts, tier="free")
- On Heartbeat: logs uptime/battery, occasionally dispatches commands
- Random alert broadcast every 5-15 seconds (30% chance on register,
  50% chance per heartbeat tick)
- Random command dispatch on heartbeat (15% chance)

**Alert templates (randomly selected):**
- Critical: High Temperature, Memory Critical, Security Alert
- Warning: Low Battery, Network Unstable, Disk Space
- Info: Firmware Update, Agent Status

**Command templates (randomly dispatched):**
- `capture_screenshot`
- `restart_agent`
- `run_diagnostic` (payload: "full")
- `update_firmware` (payload: "v1.2.0")
- `sync_clock`
- `run_task` (payload: "analyze_sensors")

**Run it:**
```bash
python3 src/linux/rgs/server/mock_server.py
# Default: 127.0.0.1:9999
```

**Status:** 100% complete. Fully functional test server.

### 3.2 Device Emulator

Async device simulator that connects to the mock server and behaves
like a real Raamses device (register, heartbeat, respond to commands).

**File:** `src/linux/rgs/client/device_emulator.py` (324 lines)

**Device profiles (4 built-in):**
| Profile  | Type   | Screen    | Battery | Features                    |
|----------|--------|-----------|---------|-----------------------------|
| `cyd`    | cyd    | 320x240   | None    | Touch, 16-bit color LCD     |
| `epaper` | epaper | 200x200   | 78%     | 2 buttons, 1-bit, battery   |
| `watch`  | watch  | 120x120   | 45%     | 1 button, vibration, battery|
| `legacy` | legacy | 128x64    | 23%     | 3 buttons, 1-bit, battery   |

**Behavior:**
- Connects to mock server on specified port
- Sends JSON Register with capabilities
- Sends random heartbeats every 5-10 seconds
- Responds to Commands with 90% success rate
- Displays alerts with color coding (red=critical, yellow=warning, green=info)

**Run it:**
```bash
python3 src/linux/rgs/client/device_emulator.py \
    --host 127.0.0.1 --port 9999 \
    --device-type cyd --device-id cyd-001

python3 src/linux/rgs/client/device_emulator.py \
    --device-type epaper --device-id epaper-002
```

**Arguments:**
| Argument        | Default     | Description                      |
|-----------------|-------------|----------------------------------|
| `--host`        | 127.0.0.1   | Server hostname                  |
| `--port`        | 9999        | Server port                      |
| `--device-id`   | random UUID | Device identifier                |
| `--device-type` | cyd         | One of: cyd, epaper, watch, legacy |

**Status:** 100% complete. Fully functional emulator.

### 3.3 Device Client (Gateway TCP)

A synchronous TCP client for the **real** gateway server (port 8765).
Used for testing the gateway protocol directly without the mock server.

**File:** `src/linux/rgs/client/device_client.py` (304 lines)

**Protocol (plain text, line-delimited):**
```
REGISTER:<device_id>|<device_type>|<schema_version>[|<firmware>]
heartbeat
task: <description>
progress: <percentage>% <detail>
done: <result>
error: <message>
```

**Run it (interactive mode):**
```bash
python3 src/linux/rgs/client/device_client.py dev-001 cyd --port 8765
```

**Run it (demo mode):**
```bash
python3 src/linux/rgs/client/device_client.py dev-001 cyd --port 8765 --demo
# Runs a 4-task cycle: initialize -> collect -> analyze -> report
# with progress updates every 25%
```

**Demo workload cycle:**
```
1. task: initialize monitoring
2. progress: 0% started -> 25% -> 50% -> 75% -> 100% done
3. task: collect metrics
4. progress: 0% -> 25% -> 50% -> 75% -> 100% done
5. task: analyze data
6. task: generate report
```

**Arguments:**
| Argument        | Default    | Description                          |
|-----------------|------------|--------------------------------------|
| `device_id`     | required   | Device identifier                    |
| `device_type`   | required   | One of: cyd, full, epaper            |
| `--host`        | 127.0.0.1  | Gateway hostname                     |
| `--port`        | 8765       | Gateway port                         |
| `--schema`      | 1.0        | Schema version                       |
| `--firmware`    | None       | Firmware version (optional)          |
| `--heartbeat`   | 10.0       | Heartbeat interval in seconds        |
| `--demo`        | False      | Run demo workload cycle              |

**Status:** 100% complete.

### 3.4 Live Server Monitor

A terminal-based htop-style dashboard that reads the mock server's
log file and displays live device status, alerts, and commands.

**File:** `src/linux/rgs/monitor.py` (239 lines)

**How it works:**
- Reads mock server log file line by line (appends only)
- Parses log entries for REGISTER, HEARTBEAT, COMMAND, ALERT events
- Builds device state dict with uptime, battery, tier
- Saves state to `/tmp/raamses_state.json` (for other tools to read)
- Renders htop-style dashboard at 1Hz refresh

**Dashboard display:**
```
════════════════════════════════════════════════════════════════
│              RAAMSES LIVE SERVER MONITOR              ● LIVE  v1.1│
════════════════════════════════════════════════════════════════
│ Status: ALL SYSTEMS NOMINAL             14:30:05 │  42s │
════════════════════════════════════════════════════════════════
│ Devices:          3 │ Alerts:          2 │ Commands:    5 │ Server: 127.0.0.1:9999
════════════════════════════════════════════════════════════════
│ Device ID          │ Type     │ Tier   │ Uptime     │ Battery   │
│ ───────────────────── │ ─────────── │ ─ ─ ─ ─ ─ ─ │ ─ ─ ─ ─ ─ ─ │ ─ ─ ─ ─ ─ ─ │
│ cyd-001            │ cyd      │ free   │ 42s        │ ?%        │
│ epaper-001         │ epaper   │ free   │ 35s        │ 78%       │
│ watch-001          │ watch    │ free   │ 28s        │ 45%       │
════════════════════════════════════════════════════════════════
│ LATEST ALERTS:
│   [14:30:02] !! [WARNING] Network Unstable: Signal strength...
│   [14:30:01] !!! [CRITICAL] High Temperature: Device CPU t...
════════════════════════════════════════════════════════════════
│ LATEST COMMANDS:
│   [14:30:05] → cyd-001            run_task
│   [14:30:03] → epaper-001         capture_screenshot
════════════════════════════════════════════════════════════════
│ CRITICAL:1         | WARNINGS:1         | INFO:0         | Heartbeats/sec: 0.1   │
════════════════════════════════════════════════════════════════
```

**Run it:**
```bash
python3 src/linux/rgs/monitor.py --log /tmp/raamses_server_live.log --server-port 9999
```

**Arguments:**
| Argument       | Default                      | Description                   |
|----------------|------------------------------|-------------------------------|
| `--log`        | /tmp/raamses_server_live.log | Server log file to monitor    |
| `--server-port`| 8765                         | Gateway server port (display) |

**State file:** `/tmp/raamses_state.json`
- Saved by monitor for console tools to read
- Contains devices dict, alerts list, commands list, uptime
- Written atomically (tmp file + rename)

**Status:** 100% complete.

### 3.5 Integration Test

Automated test that starts the mock server, connects an emulator,
and verifies the full communication pipeline.

**File:** `src/linux/rgs/tests/test_integration.py` (54 lines)

**Test procedure:**
1. Start MockRaamsesServer on port 19999
2. Wait 1 second for server binding
3. Start DeviceEmulator (cyd-001) connecting to same server
4. Run for 20 seconds
5. Stop emulator and server
6. Report results

**Test results (pass criteria):**
- Emulator connects and registers (RegisterAck received)
- Emulator receives at least 1 command
- Emulator receives at least 1 alert
- Server receives heartbeats from emulator
- Server receives CommandResult responses

**Run it:**
```bash
python3 src/linux/rgs/tests/test_integration.py
```

**Status:** 100% complete. Runs and passes successfully.

### 3.6 Test Launcher Script

Bash script that orchestrates the full test environment: starts
the mock server, device emulators, and optional monitor dashboard.

**File:** `startRaamsesTest.sh` (456 lines)

**How it works:**
1. Validates required files exist
2. Cleans up port conflicts (kills existing processes on target port)
3. Starts mock server (port 9999) with log file
4. Starts device emulators (one per specified type)
5. Optionally starts monitor dashboard
6. Follows log output in real-time
7. Displays status stats (server status, emulator count, log stats)
8. Auto-shutdown on timeout

**Usage:**
```bash
./startRaamsesTest.sh
# Default: 3 emulators (cyd, epaper, watch), no timeout

./startRaamsesTest.sh --devicetype=cyd --devicetype=watch
# Single device types specified

./startRaamsesTest.sh --devicetype=cyd --monitor -t 60s --log ./test.log
# With monitor dashboard, 60-second timeout, custom log

./startRaamsesTest.sh --devicetype=DesktopFull
# Monitor dashboard (DesktopFull = --monitor)
```

**Arguments:**
| Argument           | Description                                    |
|--------------------|------------------------------------------------|
| `--devicetype=<t>` | Device type to emulate (repeatable). cyd, epaper, watch, legacy, DesktopFull |
| `-t, --timeout=<d>`| Run duration then shutdown. Format: 20s, 5m, 2h |
| `--log=<path>`     | Log output file (default: /tmp/raamses_test_<date>.log) |
| `--monitor`        | Launch live dashboard (implies DesktopFull)    |
| `--no-log`         | Suppress log display after launch              |
| `-h, --help`       | Show help text                                 |

**Process management:**
- Tracks all PIDs for cleanup
- Kills existing processes on port before starting
- Cleanup on EXIT (signal handling)
- Timeout timer for auto-shutdown

**Status:** 100% complete.

### 3.7 Launcher (Async)

Python-based launcher for the mock server and emulators.
More flexible than the bash script for programmatic use.

**File:** `src/linux/rgs/launcher.py` (121 lines)

**Run it:**
```bash
python3 src/linux/rgs/launcher.py                          # Server only
python3 src/linux/rgs/launcher.py --emulators cyd epaper  # Server + 2 emulators
python3 src/linux/rgs/launcher.py --emulators cyd=cyd-001 watch:watch-01  # Custom IDs
```

**Arguments:**
| Argument        | Default     | Description                    |
|-----------------|-------------|--------------------------------|
| `--host`        | 127.0.0.1   | Server hostname                |
| `--port`        | 9999        | Server port                    |
| `--emulators`   | []          | Device types to emulate        |

**Status:** 100% complete.

### 3.8 Test Tools Status Summary

| Tool                       | File                                            | Status  | % Complete |
|----------------------------|-------------------------------------------------|---------|------------|
| Mock Raamses Server        | src/linux/rgs/server/mock_server.py             | COMPLETE| 100%       |
| Device Emulator            | src/linux/rgs/client/device_emulator.py         | COMPLETE| 100%       |
| Device Client (Gateway)    | src/linux/rgs/client/device_client.py           | COMPLETE| 100%       |
| Live Server Monitor        | src/linux/rgs/monitor.py                        | COMPLETE| 100%       |
| Integration Test           | src/linux/rgs/tests/test_integration.py         | COMPLETE| 100%       |
| Test Launcher Script       | startRaamsesTest.sh                             | COMPLETE| 100%       |
| Async Launcher             | src/linux/rgs/launcher.py                       | COMPLETE| 100%       |

---

## 4. Quick Start Reference

### For agents connecting to the server:

1. **Connect via TCP** to `127.0.0.1:8765` (gateway) or `127.0.0.1:9999` (mock)

2. **Register:**
   ```
   REGISTER:<device_id>|<device_type>|<schema_version>
   ```
   Example: `REGISTER:cyd-001|cyd|1.0`

3. **Heartbeat:**
   ```
   heartbeat
   ```
   or:
   ```
   PING
   ```

4. **Task updates:**
   ```
   task: <description>
   progress: <percentage>% <detail>
   done: <result>
   error: <message>
   ```

5. **For console operators:** connect to `127.0.0.1:8765` and use:
   - `status` / `agents` / `list` for server info
   - `/cmd <id> <action>` to target specific agents

### For running tests:

```bash
# Quick integration test (20 seconds)
python3 src/linux/rgs/tests/test_integration.py

# Full test with emulators and monitor
./startRaamsesTest.sh --monitor -t 60s

# Just the server + emulator
python3 src/linux/rgs/launcher.py --emulators cyd
```

### For the console:

```bash
# Full terminal console (Rich dashboard)
python3 src/linux/rgs/console/terminal_console.py full

# Server-aware console (connects to mock server)
python3 src/linux/rgs/console/server_console.py full

# RADAR (connects to gateway, shows agent icons)
python3 -m rgs.console.radar --host 127.0.0.1 --port 8765
```

---

## 5. File Index

### Gateway Server
| Path                                    | Lines | Description                     |
|-----------------------------------------|-------|---------------------------------|
| src/linux/rgs/server/gateway.py         | 371   | Main TCP gateway server         |
| src/linux/rgs/server/session_registry.py| 178   | Agent session tracking          |
| src/linux/rgs/server/message_router.py  | 217   | Message classification/routing  |
| src/linux/rgs/server/mock_server.py     | 284   | Async mock server for testing   |

### Message Types
| Path                                        | Lines | Description                     |
|---------------------------------------------|-------|---------------------------------|
| src/linux/rgs/messages/envelope.py          | 45    | RaamsesMessage header/payload   |
| src/linux/rgs/messages/register.py          | 55    | Register/RegisterAck types      |
| src/linux/rgs/messages/command.py           | 28    | Command/CommandResult types     |
| src/linux/rgs/messages/heartbeat.py         | 16    | Heartbeat type                  |
| src/linux/rgs/messages/alert.py             | 19    | Alert type                      |
| src/linux/rgs/messages/agent_update.py      | 28    | AgentUpdate/TokenUsage types    |

### Consoles
| Path                                        | Lines | Description                     |
|---------------------------------------------|-------|---------------------------------|
| src/linux/rgs/console/terminal_console.py   | 605   | Full 3-panel Rich dashboard     |
| src/linux/rgs/console/server_console.py     | 402   | Server-aware Rich dashboard     |
| src/linux/rgs/console/radar.py              | 367   | RADAR: agent display/monitor    |

### Clients
| Path                                        | Lines | Description                     |
|---------------------------------------------|-------|---------------------------------|
| src/linux/rgs/client/device_client.py       | 304   | TCP client for gateway testing  |
| src/linux/rgs/client/device_emulator.py     | 324   | Async device emulator           |

### Testing
| Path                                        | Lines | Description                     |
|---------------------------------------------|-------|---------------------------------|
| src/linux/rgs/tests/test_integration.py     | 54    | Integration test                |
| src/linux/rgs/launcher.py                   | 121   | Async launcher                  |
| src/linux/rgs/monitor.py                    | 239   | Live server monitor             |
| startRaamsesTest.sh                         | 456   | Bash test launcher              |

### Package
| Path                            | Lines | Description                     |
|---------------------------------|-------|---------------------------------|
| src/linux/rgs/__init__.py       | 56    | Package init with lazy imports  |
| src/linux/rgs/messages/__init__.py | 15 | Message type exports            |

---

## 6. Open Tasks

### Server
- [ ] TLS support on port 8766 (0%)
- [ ] Client certificate authentication for agents (0%)
- [ ] Bearer token authentication for console (0%)
- [ ] Command queueing when agent moved on (0%)
- [ ] Schema version enforcement (40% — header exists, not checked)
- [ ] Pub/sub broadcast to all agents (0%)
- [ ] Windows RGS port completion (40% — XAML skeleton exists)

### Consoles
- [ ] RADAR keyboard commands to send to agents (0%)
- [ ] Server Console real-time device state from registry (60%)
- [ ] Server Console command routing to devices (0%)
- [ ] Multi-gateway support in RADAR (0%)

### Testing
- [ ] Automated test suite with pytest (0%)
- [ ] Coverage reporting (0%)
- [ ] Test fixture cleanup (partial — mock server cleanup works)

---

## 7. Known Issues

1. **Mock server uses JSON envelopes but gateway uses plain text.**
   The mock server (port 9999) and real gateway (port 8765) use
   different protocols. The device emulator works with the mock
   server. The device client works with the gateway. These need
   unification or separate emulators for each.

2. **Console devices not connected to live gateway data.**
   The terminal_console.py reads from local log files only. It
   does not connect to the gateway for real-time device status.
   The RADAR console does query the gateway, but only for agent
   list/status, not individual device details.

3. **No unified test for gateway protocol.**
   test_integration.py tests the mock server + emulator. There
   is no equivalent test for the real gateway + device_client.

4. **Log file path discovery is fragile.**
   Multiple components try to find gateway.log using hardcoded
   relative paths. A config file or CLI argument would be more
   robust.

---

## 8. Dependencies

### Core (required)
- Python 3.9+
- No external packages needed for gateway server

### Consoles (Rich dashboard)
- `rich` — terminal UI library
- `prompt_toolkit` — command input (server_console only)

### Optional
- `pytest` — for test suite (not yet configured)
- `pytest-timeout` — for test timeouts

### To install:
```bash
pip install rich prompt_toolkit pytest
```

---

*End of status document.*
