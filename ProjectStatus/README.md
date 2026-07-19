# RaamsesServer - Project Status

**Last Updated:** 2026-07-18

## Current Focus
Building the Linux/Python side of the Raamses server and desktop console to match the Windows C# implementation.

### Active Work
- Core message protocol with `SchemaVersion` support (for backward compatibility)
- TCP Device Client (registers and behaves like hardware devices)
- Integrated Desktop Agent Console
- **Gateway Server** (new — TCP message router with classification & delivery)
- **Session Registry** (thread-safe agent tracking with heartbeat detection)
- **Message Router** (classifies commands as gateway-local vs agent-targeted)
- Modular XSD schema definitions
- Basic server stub for testing

### Gateway Routing Design (2026-07-19)
- **Type 1: Gateway Communication** — direct protocol/admin commands execute locally on the server (e.g., `register`, `heartbeat`, `status`)
- **Type 2: Agent-Targeted Commands** — routed to specific agent via `device_id` (e.g., `/cmd <id> <action>`, `/tell`, `/ask`, `/pause`, `/resume`)
- **Race handling:** If an agent has moved on to a different task, the command is **dropped and logged** (not queued)
- Full design documented in `ProjectStatus/gateway-routing.md`

### Key Design Decisions
- Never infer capabilities from model names
- Missing fields = unsupported
- Public `device_id` must be random UUID
- All booleans as `true`/`false`
- Timestamps in ISO 8601 UTC
- Authentication outside the XML payload

### Multi-Agent Strategy
- Do **not** lock to Hermes
- Test with local Llama + OpenAI + Grok + Deepseek agents
- Desktop Console should be agent-agnostic

## Repository Structure (Target)

```
RaamsesServer/
├── ProjectStatus/          # This folder - status, plans, decisions
├── schemas/                # XSD definitions
├── src/
│   └── python/
│       └── raamses/
│           ├── messages/   # Protocol layer
│           ├── client/     # TCP device client
│           ├── console/    # Desktop Agent Console
│           └── server/     # Server implementation
├── docs/
└── tests/
```

## Recent Commits
- Initial Python protocol work + Desktop Console integration
- README status updates

---
*Only the user and Hermes are currently working in this repo.*