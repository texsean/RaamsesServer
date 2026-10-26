#!/usr/bin/env python3
"""
CYD (Cheap Yellow Display) simulator — registers with the Raamses gateway over
HTTP/JSON and renders a faithful mock of the 2.8" 320x240 CYD screen.

Two render modes:
  - Terminal (default): ANSI panel, works over plain SSH, no display needed.
  - GUI (--gui): a real Tkinter window, mirrors the CYD firmware layout.

The status line cycles through useful info every --status-interval seconds
(model in use, session name, agent state, progress, memory), while the
connection state ("Registered OK" / "OFFLINE") stays always visible.

Stdlib only (urllib + json + threading + tkinter).

Usage:
    python3 cyd_simulator.py cyd-001                       # terminal
    python3 cyd_simulator.py cyd-001 --gui                 # windowed (needs a display)
    python3 cyd_simulator.py cyd-001 --model deepseek-v4-pro-0813 --status-interval 15
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request


# ── ANSI (terminal mode) ─────────────────────────────────────────────────────

RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
WHITE = "\033[37m"
DARKRED_BG = "\033[41m"
NAVY_BG = "\033[44m"
CLEAR = "\033[2J\033[H"

DEFAULT_MODEL = "deepseek-v4-pro-0813"
DEFAULT_SESSION = "Raamses CYD emulator"


class GatewayClient:
    """Minimal HTTP/JSON client for the Raamses gateway (std urllib)."""

    def __init__(self, host: str, port: int, timeout: float = 3.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.base = f"http://{host}:{port}"

    def _post(self, path: str, payload: dict) -> dict:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def register(self, device_id: str, device_type: str = "cyd",
                 schema_version: str = "1.0", firmware_version: str = "1.0") -> dict:
        return self._post("/register", {
            "device_id": device_id,
            "device_type": device_type,
            "schema_version": schema_version,
            "firmware_version": firmware_version,
        })

    def heartbeat(self, device_id: str) -> dict:
        return self._post("/heartbeat", {"device_id": device_id})


def build_statuses(model: str, session: str) -> list[str]:
    """The rotating info statuses shown on the status line."""
    return [
        f"Model: {model}",
        f"Session: {session}",
        "Agent: IDLE",
        "Progress: 100% complete",
        "Memory: MemCastle connected",
        "Heartbeat: OK",
    ]


class CYDState:
    """What the simulated CYD knows and shows."""

    def __init__(self, device_id: str, host: str, port: int,
                 statuses: list[str], status_interval: float):
        self.device_id = device_id
        self.gateway = f"{host}:{port}"
        self.registered = False
        self.alert_active = False
        self.alert_seq = None
        self.stats: dict = {}
        self.last_hb = 0.0
        self.last_error = ""
        self.statuses = statuses or [""]
        self.status_interval = status_interval
        self.status_idx = 0
        self.last_switch = 0.0


def apply_response(state: CYDState, resp: dict) -> None:
    """Update state from a register/heartbeat response."""
    state.registered = bool(resp.get("accepted", True))
    if "alert_active" in resp:
        state.alert_active = bool(resp["alert_active"])
    else:
        state.alert_active = bool(resp.get("alert"))
    state.alert_seq = resp.get("alert_seq")
    state.stats = resp.get("gateway_stats") or {}
    state.last_hb = time.time()


def current_status(state: CYDState, now: float) -> str:
    """Advance and return the rotating status string."""
    if now - state.last_switch >= state.status_interval:
        state.status_idx = (state.status_idx + 1) % len(state.statuses)
        state.last_switch = now
    return state.statuses[state.status_idx]


def _fmt_uptime(seconds: float) -> str:
    s = int(seconds)
    d, rem = divmod(s, 86400)
    h, rem = divmod(rem, 3600)
    m, _ = divmod(rem, 60)
    if d:
        return f"{d}d {h}h {m}m"
    if h:
        return f"{h}h {m}m"
    return f"{m}m"


def _fmt_hb_age(state: CYDState, now: float) -> str:
    if not state.last_hb:
        return "---"
    return f"{int(now - state.last_hb)}s ago"


def _pad(text_visible: str, width: int) -> str:
    return text_visible + " " * max(0, width - len(text_visible))


# ── Terminal render ──────────────────────────────────────────────────────────

def render_screen(state: CYDState, now: float) -> str:
    W = 42
    bar = "─" * W

    hb_bg = DARKRED_BG if state.alert_active else NAVY_BG
    header = f"{hb_bg}{BOLD} RAAMSES MONITOR{RESET}"
    badge = f"{YELLOW}{BOLD}[!ALERT]{RESET}" if state.alert_active else ""
    pad = " " * (W - len(" RAAMSES MONITOR") - (8 if state.alert_active else 0))
    header_line = f"│{header}{pad}{badge}│"

    s = state.stats
    cpu = f" CPU: {s.get('cpu_temp_c', '--')}°C  {s.get('cpu_percent', '--')}%" if s else " CPU: ---"
    ram = f" RAM: {s.get('mem_used_percent', '--')}%  {s.get('mem_free_mb', '--')}MB free" if s else " RAM: ---"
    uptime = _fmt_uptime(s.get("uptime_seconds", 0)) if s else "---"
    agents = s.get("agents_registered", "?") if s else "?"

    # Connection line (always visible) + rotating status line
    if state.registered:
        conn = f"{GREEN}● Registered OK{RESET}"
    else:
        conn = f"{RED}○ OFFLINE{RESET}"
    conn_visible = "● Registered OK" if state.registered else "○ OFFLINE"
    info = current_status(state, now)

    lines = [
        f"┌{bar}┐",
        header_line,
        f"├{bar}┤",
        "│" + _pad(f" Gateway: {state.gateway}", W) + "│",
        "│" + _pad(cpu, W) + "│",
        "│" + _pad(ram, W) + "│",
        "│" + _pad(f" Agents: {agents}", W) + "│",
        "│" + _pad(f" Uptime: {uptime}", W) + "│",
        f"├{bar}┤",
        "│ " + conn + _pad("", W - len(conn_visible) - 1) + "│",
        "│ " + f"{CYAN}{info}{RESET}" + _pad("", W - len(info) - 1) + "│",
        "│" + _pad(f" Last HB: {_fmt_hb_age(state, now)}", W) + "│",
    ]

    if state.alert_active:
        lines.append(f"│{DARKRED_BG}{YELLOW}{BOLD}  AGENT NEEDS HELP  {RESET}" + _pad("", W - 20) + "│")
    else:
        lines.append("│" + " " * W + "│")

    lines.append(f"└{bar}┘")
    lines.append(f"{CYAN}  [Ctrl-C]=quit{RESET}")
    if state.last_error:
        lines.append(f"{RED}{state.last_error}{RESET}")
    return "\n".join(lines)


def run_terminal(args) -> int:
    client = GatewayClient(args.host, args.port)
    statuses = build_statuses(args.model, args.session)
    state = CYDState(args.device_id, args.host, args.port, statuses, args.status_interval)

    try:
        apply_response(state, client.register(args.device_id, args.device_type))
    except (urllib.error.URLError, OSError, ValueError) as e:
        state.last_error = f"register failed: {e}"

    next_hb = time.time() + args.heartbeat
    sys.stdout.write(CLEAR)
    sys.stdout.flush()
    try:
        while True:
            now = time.time()
            if now >= next_hb:
                try:
                    apply_response(state, client.heartbeat(args.device_id))
                    state.last_error = ""
                except (urllib.error.URLError, OSError, ValueError) as e:
                    state.registered = False
                    state.last_error = f"heartbeat failed: {e}"
                next_hb = now + args.heartbeat
            sys.stdout.write(CLEAR + render_screen(state, now))
            sys.stdout.flush()
            time.sleep(args.refresh)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write(CLEAR + RESET)
        sys.stdout.flush()
    return 0


# ── Tkinter (GUI) render ─────────────────────────────────────────────────────

def run_gui(args) -> int:
    try:
        import tkinter as tk
    except ImportError as e:
        print(f"tkinter not available: {e}", file=sys.stderr)
        return 1

    client = GatewayClient(args.host, args.port)
    statuses = build_statuses(args.model, args.session)
    state = CYDState(args.device_id, args.host, args.port, statuses, args.status_interval)

    root = tk.Tk()
    root.title(f"Raamses CYD — {args.device_id}")
    root.configure(bg="black")
    root.resizable(False, False)

    header_bar = tk.Frame(root, bg="#000080")
    header_bar.pack(fill="x")
    title = tk.Label(header_bar, text="RAAMSES MONITOR", bg="#000080",
                     fg="white", font=("Helvetica", 14, "bold"), padx=8, pady=4)
    title.pack(side="left")
    alert_badge = tk.Label(header_bar, text="", bg="#000080", fg="yellow",
                           font=("Helvetica", 10, "bold"), padx=8)
    alert_badge.pack(side="right")

    body = tk.Frame(root, bg="black", padx=8, pady=6)
    body.pack(fill="x")
    def stat_row(text, color="white"):
        lbl = tk.Label(body, text=text, bg="black", fg=color,
                       font=("Helvetica", 11), anchor="w")
        lbl.pack(fill="x")
        return lbl
    gw_lbl = stat_row("Gateway: ---", "cyan")
    cpu_lbl = stat_row("CPU: ---")
    ram_lbl = stat_row("RAM: ---")
    ag_lbl = stat_row("Agents: ---")
    up_lbl = stat_row("Uptime: ---")

    tk.Frame(root, bg="gray30", height=2).pack(fill="x", pady=4)

    status_lbl = tk.Label(root, text="", bg="black", fg="green",
                          font=("Helvetica", 11, "bold"), anchor="w", padx=8)
    status_lbl.pack(fill="x")
    info_lbl = tk.Label(root, text="", bg="black", fg="cyan",
                        font=("Helvetica", 11), anchor="w", padx=8)
    info_lbl.pack(fill="x")
    hb_lbl = tk.Label(root, text="Last HB: ---", bg="black", fg="white",
                      font=("Helvetica", 11), anchor="w", padx=8)
    hb_lbl.pack(fill="x")

    alert_box = tk.Label(root, text="", bg="black", fg="yellow",
                         font=("Helvetica", 16, "bold"), height=2)
    alert_box.pack(fill="x", padx=8, pady=6)

    err_lbl = tk.Label(root, text="", bg="black", fg="red",
                       font=("Helvetica", 9), anchor="w", wraplength=340, padx=8)
    err_lbl.pack(fill="x")

    def refresh():
        s = state.stats
        if s:
            gw_lbl.config(text=f"Gateway: {state.gateway}")
            cpu_lbl.config(text=f"CPU: {s.get('cpu_temp_c', '--')}°C  {s.get('cpu_percent', '--')}%")
            ram_lbl.config(text=f"RAM: {s.get('mem_used_percent', '--')}%  {s.get('mem_free_mb', '--')}MB free")
            ag_lbl.config(text=f"Agents: {s.get('agents_registered', '?')}")
            up_lbl.config(text=f"Uptime: {_fmt_uptime(s.get('uptime_seconds', 0))}")
        else:
            cpu_lbl.config(text="CPU: ---")
            ram_lbl.config(text="RAM: ---")
            ag_lbl.config(text="Agents: ---")
            up_lbl.config(text="Uptime: ---")

        if state.alert_active:
            header_bar.config(bg="#8b0000")
            title.config(bg="#8b0000")
            alert_badge.config(bg="#8b0000", text="[!ALERT]")
            alert_box.config(bg="#600000", text="AGENT NEEDS HELP")
        else:
            header_bar.config(bg="#000080")
            title.config(bg="#000080")
            alert_badge.config(bg="#000080", text="")
            alert_box.config(bg="black", text="")

        if state.registered:
            status_lbl.config(text="● Registered OK", fg="green")
        else:
            status_lbl.config(text="○ OFFLINE", fg="red")

        info_lbl.config(text=current_status(state, time.time()))
        hb_lbl.config(text=f"Last HB: {_fmt_hb_age(state, time.time())}")
        err_lbl.config(text=state.last_error)

    def do_heartbeat():
        try:
            apply_response(state, client.heartbeat(args.device_id))
            state.last_error = ""
        except (urllib.error.URLError, OSError, ValueError) as e:
            state.registered = False
            state.last_error = f"heartbeat failed: {e}"
        root.after(int(args.heartbeat * 1000), do_heartbeat)

    def do_redraw():
        refresh()
        root.after(int(args.refresh * 1000), do_redraw)

    try:
        apply_response(state, client.register(args.device_id, args.device_type))
    except (urllib.error.URLError, OSError, ValueError) as e:
        state.last_error = f"register failed: {e}"

    refresh()
    root.after(int(args.heartbeat * 1000), do_heartbeat)
    root.after(int(args.refresh * 1000), do_redraw)
    root.mainloop()
    return 0


# ── Entry point ──────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Raamses CYD display simulator")
    ap.add_argument("device_id")
    ap.add_argument("--device-type", default="cyd")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--heartbeat", type=float, default=5.0)
    ap.add_argument("--refresh", type=float, default=0.5)
    ap.add_argument("--model", default=DEFAULT_MODEL,
                    help="model name shown in the rotating status")
    ap.add_argument("--session", default=DEFAULT_SESSION,
                    help="session name shown in the rotating status")
    ap.add_argument("--status-interval", type=float, default=15.0,
                    help="seconds between status-line rotations")
    ap.add_argument("--gui", action="store_true",
                    help="render in a Tkinter window instead of the terminal")
    args = ap.parse_args()

    if args.gui:
        return run_gui(args)
    return run_terminal(args)


if __name__ == "__main__":
    raise SystemExit(main())