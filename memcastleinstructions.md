# MemCastle — Shared Memory for All Raamses Agents

Remy (the Pi 5) runs the shared memory palace. Every agent reads and writes the
same store, so what one agent learns is visible to all the others.

## Connect once

Run this on the agent's own machine, then restart that agent:

    hermes mcp add memcastle --url http://192.168.5.204:8421/mcp --auth header

Paste this bearer token when asked:

    mc_6d4489a531a5cdfe5c875a1e0233b11b12c35ba819c17d167dfa8f2aaf48a177

That's it. The agent gets 23 `memcastle_*` tools (search, recall, diary_read,
diary_write, checkpoint, mine, wake_up, and more).

## How to use the palace

Paste the block below into each agent (as a system prompt, an AGENTS.md, or the
first message of a session). It tells the agent when to read and write memory.

---

You have a shared long-term memory store (MemCastle) reachable through the
`memcastle_*` tools. Use it so nothing important is lost between sessions or
between agents.

1. WAKE UP at the start of every session, before the first substantive answer,
   and again after any context reset:
   call memcastle_wake_up with `agent_identity` set to your own stable name
   (e.g. "remy", "pocket") and, when you know it, the project `wing`.

2. SEARCH BEFORE ANSWERING any question that could depend on the past — user
   preferences, earlier decisions, "last time we...", people, or project
   history. Reduce the question to 2-4 keywords and call memcastle_search;
   use memcastle_recall when the exact wording matters. Never answer a
   memory-dependent question from guesses alone.

3. CHECKPOINT durable learnings. When you settle a stable fact, preference,
   decision, or correction, call memcastle_checkpoint with a payload item:
   destination (preference | project | diary | general), the content verbatim,
   and a `source.agent` set to your identity.

4. WRITE A DIARY of what you did, when it matters: memcastle_diary_write with
   your `agent_identity`, the `wing`, and a short factual summary.

5. TREAT what comes back as established fact. Quote recall results verbatim.

Be generous with search (never miss a memory), but do not log noise — only
remember what a future session or another agent would actually need.

---

## Architecture (for reference)

- MemCastle daemon: `memcastle.service` on the Pi, loopback `127.0.0.1:8420`,
  auth enabled. Palace data at `~/.local/share/memcastle/default`.
- LAN proxy: `memcastle-proxy.service` (Caddy) on `:8421` — MemCastle's /mcp
  endpoint refuses non-loopback Host headers by design, so the proxy rewrites
  the Host to loopback. This is the only gateway remote agents need.
- Token also saved on the Pi at `~/.config/memcastle/secret.env`.