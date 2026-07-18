# RaamsesServer - Project Status

**Last Updated:** 2026-07-18

## Current Focus
Building the Linux/Python side of the Raamses server and desktop console to match the Windows C# implementation.

### Active Work
- Core message protocol with `SchemaVersion` support (for backward compatibility)
- TCP Device Client (registers and behaves like hardware devices)
- Integrated Desktop Agent Console
- Basic server stub for testing
- Modular XSD schema definitions

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