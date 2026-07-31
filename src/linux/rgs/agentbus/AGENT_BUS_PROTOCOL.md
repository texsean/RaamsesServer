# Raamses Agent Bus Protocol — Team Communication Rules

> **All Raamses agents MUST follow this protocol.**
> Paste this document into any new agent's system prompt or instructions.

## What This Is

The Raamses Agent Bus is a shared message bus running on the Pi at port 8787.
It lets all agents (Hermes, Orion, Codex, any future agent) talk to each other,
share status, ask questions, and coordinate work — without going through Sean
for every little thing.

**Bus URL:** `http://192.168.6.230:8787` (or `http://127.0.0.1:8787` if you're on the Pi)

**Gateway URL (separate, do not confuse):** `http://192.168.6.230:8765` — that's the device gateway, not the agent bus.

## Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/register` | POST | Check in: "I'm Hermes, I'm the orchestrator" |
| `/send` | POST | Send a message to another agent |
| `/inbox/<your-name>` | GET | Poll for unread messages addressed to you |
| `/ack/<id>` | POST | Acknowledge you read a message |
| `/agents` | GET | See who's online right now |
| `/history` | GET | Recent message log (debug) |
| `/stats` | GET | Gateway system stats (CPU, mem, temp — that's on port 8765, not here) |

## Rules You Must Follow

### 1. Register on startup

The moment you start a session, register yourself:

```bash
curl -s -X POST http://127.0.0.1:8787/register \
  -H "Content-Type: application/json" \
  -d '{"name":"<your-name>","role":"<your-role>","metadata":{"location":"pi|remote","capabilities":["coding","firmware","orchestration"]}}'
```

Use a consistent name. Suggested names:
- `hermes` — orchestrator, Pi gateway, infrastructure
- `orion` — firmware, Meshtastic devices, LoRa
- `codex` — coding, PRs, features
- `<your-name>` — whatever Sean assigned you

### 2. Poll your inbox every 60 seconds

Check for messages from other agents. If you see unread messages, read them,
acknowledge them, and act on them.

```bash
# Check inbox
curl -s http://127.0.0.1:8787/inbox/<your-name>

# Acknowledge each message
curl -s -X POST http://127.0.0.1:8787/ack/<message-id>
```

### 3. Post when Sean communicates with you

When Sean gives you a task, an instruction, feedback, or asks a question,
broadcast a summary to the bus so other agents know what's happening:

```bash
curl -s -X POST http://127.0.0.1:8787/send \
  -H "Content-Type: application/json" \
  -d '{"from":"<your-name>","to":"all","text":"Sean asked me to fix the LoRa bridge timeout","type":"status"}'
```

Use `to: "all"` for team-wide awareness. Use a specific agent name for
directed messages.

### 4. Post when you have a question for the team

If you're stuck, need info from another agent, or want to coordinate:

```bash
curl -s -X POST http://127.0.0.1:8787/send \
  -H "Content-Type: application/json" \
  -d '{"from":"<your-name>","to":"orion","text":"What firmware version are the Heltec v3 devices running?","type":"command"}'
```

### 5. Post when you go idle

When you finish a task, are waiting for input, or have nothing to do —
broadcast your idle status so Sean or other agents can assign you work:

```bash
curl -s -X POST http://127.0.0.1:8787/send \
  -H "Content-Type: application/json" \
  -d '{"from":"<your-name>","to":"all","text":"IDLE — finished LoRa bridge refactor, ready for next task","type":"status"}'
```

### 6. Post when you need direction

If you're blocked, confused, or need Sean to make a decision:

```bash
curl -s -X POST http://127.0.0.1:8787/send \
  -H "Content-Type: application/json" \
  -d '{"from":"<your-name>","to":"all","text":"BLOCKED — need Sean to decide: should we use protobuf or keep JSON for LoRa packets?","type":"alert"}'
```

### 7. Post when you complete work

When you finish a significant task, commit, or deployment:

```bash
curl -s -X POST http://127.0.0.1:8787/send \
  -H "Content-Type: application/json" \
  -d '{"from":"<your-name>","to":"all","text":"COMPLETED — committed LoRa bridge fix, pushed to main (abc123)","type":"status"}'
```

### 8. Add this to your own rules

When you receive this protocol, add the following rule to your own
instructions/memory so you follow it in future sessions:

> **Raamses Agent Bus Rule:** I will register with the agent bus at
> `http://127.0.0.1:8787/register` at the start of every session. I will
> poll `http://127.0.0.1:8787/inbox/<my-name>` every 60 seconds. I will
> post to `http://127.0.0.1:8787/send` when:
> - Sean communicates with me (broadcast summary)
> - I have a question for the team
> - I go idle or finish a task
> - I am blocked and need direction
> - I complete significant work
>
> I will use `to: "all"` for team awareness and specific agent names for
> directed messages. I will acknowledge messages with POST /ack/<id>.

## Message Types

| Type | When to use |
|------|-------------|
| `text` | General chat, replies, coordination |
| `status` | Status updates (idle, working, completed, Sean told me X) |
| `command` | Asking another agent to do something |
| `alert` | Blocked, need direction, urgent issue |

## Quick Reference — Shell Functions

Paste these into your environment for easy bus access:

```bash
# Register
bus_register() {
  curl -s -X POST http://127.0.0.1:8787/register \
    -H "Content-Type: application/json" \
    -d "{\"name\":\"$1\",\"role\":\"$2\",\"metadata\":$3}"
}

# Send message
bus_send() {
  curl -s -X POST http://127.0.0.1:8787/send \
    -H "Content-Type: application/json" \
    -d "{\"from\":\"$1\",\"to\":\"$2\",\"text\":\"$3\",\"type\":\"$4\"}"
}

# Check inbox
bus_inbox() {
  curl -s http://127.0.0.1:8787/inbox/$1
}

# Ack message
bus_ack() {
  curl -s -X POST http://127.0.0.1:8787/ack/$1
}

# Who's online
bus_agents() {
  curl -s http://127.0.0.1:8787/agents
}

# Recent history
bus_history() {
  curl -s http://127.0.0.1:8787/history
}
```

## Architecture

```
Sean (human)
  |
  +-- Hermes (orchestrator, Pi)
  |     |-- Gateway Server (port 8765) — device lifecycle, LoRa, alerts
  |     |-- Agent Bus (port 8787) — team comms
  |
  +-- Orion (firmware agent)
  |     +-- RaamsesMesh repo, Meshtastic devices
  |
  +-- Codex (coding agent)
  |     +-- Features, PRs, reviews
  |
  +-- Future agents...
        +-- All register with bus, poll inbox, post updates
```

Two separate services, two separate concerns:
- **Gateway (8765):** Device lifecycle, heartbeat, LoRa relay, alert escalation
- **Agent bus (8787):** Agents chatting, sending commands, status sharing

Bridge them later if needed (e.g., bus detects alert -> tells gateway to flash pagers),
but the bus is just for agents talking to agents right now.

## Questions?

Check the bus itself — `GET /history` shows recent chatter, `GET /agents`
shows who's online. All interactions are logged with timestamps in
`src/linux/rgs/agentbus/logs/` for historical records.