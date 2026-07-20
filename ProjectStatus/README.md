# RGS (Raamses Gateway Server) — Project Status

**Last Updated:** 2026-07-19

## Current Focus

Cross-platform gateway server (Linux + Windows) with terminal/Android console for monitoring AI agents connected to the Raamses protocol.

### Active Work
- Gateway Server TCP router (port 8765) with classification & delivery
- Session Registry (thread-safe agent tracking, heartbeat detection)
- Message Router (gateway-local vs agent-targeted dispatch)
- Terminal Console (htop-style dashboard — 3-sectioned: config, devices, logs)
- Modular XSD schema definitions
- Python package renamed `raamses` → `rgs` (internal paths only; classes preserved)

### Gateway Routing Design (2026-07-19)
- **Type 1: Gateway Communication** — direct protocol/admin commands execute locally (e.g., `register`, `heartbeat`, `status`)
- **Type 2: Agent-Targeted Commands** — routed to specific agent via `device_id` (e.g., `/cmd <id> <action>`, `/tell`, `/ask`, `/pause`, `/resume`)
- **Race handling:** If agent has moved on, command is **dropped and logged** (not queued)

### Key Design Decisions
- Never infer capabilities from model names
- Missing fields = unsupported
- Public `device_id` must be random UUID generated at onboarding
- All booleans as `true`/`false`
- Timestamps in ISO 8601 UTC
- Authentication outside the protocol payload (TLS + client certs / bearer tokens)

### Multi-Agent Strategy
- Do **not** lock to Hermes
- Test with local Llama + OpenAI + Grok + Deepseek agents
- Desktop Console should be agent-agnostic

## Repository Structure

```
rgsServer/
├── ProjectStatus/          # This folder - status, plans, decisions
├── schemas/                # XSD protocol definitions
├── src/
│   ├── linux/
│   │   ├── rgs/            # Python package (gateway, console, messages)
│   │   │   ├── server/     # GatewayServer, SessionRegistry, MessageRouter
│   │   │   ├── messages/   # Protocol message types
│   │   │   ├── client/     # TCP device client / emulator
│   │   │   └── console/    # Terminal dashboard (Rich-based)
│   │   └── cpp/            # C++ verifier, core, logging
│   ├── windows/            # Windows C++ build (planned)
│   └── android/            # Android console app (Kotlin/Jetpack Compose)
├── QA/
│   ├── tests/              # pytest unit tests (37 passing)
│   ├── emulator/           # Verifier emulator (Python)
│   └── console/            # Legacy console copy
└── .github/workflows/      # CI (Android build)
```

### Python Import Paths
```python
from rgs.server.gateway import RGsGatewayServer
from rgs.server.session_registry import SessionRegistry
from rgs.messages.envelope import RaamsesMessage
from rgs.console.terminal_console import RaamsesConsole
```
Set `PYTHONPATH=src/linux` or install as editable package.

## Recent Commits
- feat(console): 3-section mission control dashboard (config, devices, logs)
- refactor: Rename 'raamses' package to 'rgs', restructure src/
- feat(cpp): Improve Verifier with methodology placeholders
- Add gateway server: TCP router, session registry, and message classifier

---
*Only the user and Hermes are currently working in this repo.*
