# Gateway Routing — Message Classification & Delivery

**Created:** 2026-07-19

## Architecture

The rgs gateway receives messages from two sources:
- **Connected devices/agents** (TCP/WS connections from CYD, Android, other gateways)
- **Operators** (via the Android console or terminal)

Every incoming message is classified into one of two types:

### Type 1: Gateway Communication
Direct protocol or administrative commands that should be executed immediately on the server itself.

**Examples:** `register`, `heartbeat`, `status`, `quit`, protocol messages

**Behavior:** Execute locally, as if the operator typed it directly into the gateway.
No routing, no queuing. Fire and forget.

### Type 2: Agent-Targeted Commands
Commands directed at a specific registered agent (identified by `device_id`).

**Examples:** `/cmd <agent_id> <action>`, `/tell`, `/ask`, `/pause`, `/resume`, `/stop`

**Behavior:**
1. Look up the target agent by `device_id` in the session registry
2. Check if the agent is still active and hasn't moved past this command
3. **If the agent is available:** dispatch the command and wait for response
4. **If the agent has moved on:** drop the command and log it

### Race Condition Handling

When an agent-targeted command arrives but the agent has already moved on to other work:

**Action: DROP AND LOG**

- The command is not queued, not retried, not forwarded
- A log entry is written: `DROPPED: command=<cmd> to agent=<id> — agent moved to task=<latest_task>`
- The operator receives a brief response if they sent it interactively: "Agent X has moved on (latest: Y)"

### Session Registry

A simple in-memory mapping maintained by the gateway:

```
AgentSession {
    device_id: str          # registered UUID
    status: str             # "active" | "paused" | "offline"
    last_heartbeat: datetime
    current_task: str       # what the agent is currently working on
    task_assigned_at: datetime
    connection: object      # TCP/WS connection handle
}
```

Agents register themselves and update `current_task` as they work. The gateway tracks this state.

## Implementation

- `src/linux/rgs/server/gateway.py` — main gateway server
- `src/linux/rgs/server/session_registry.py` — agent session tracking
- `src/linux/rgs/server/message_router.py` — classification and dispatch logic
