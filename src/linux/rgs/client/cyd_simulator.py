#!/usr/bin/env python3
"""
CYD (Cheap Yellow Display) simulator.

Renders the 2.8" 320x240 CYD screen live in the terminal and drives the device
lifecycle against the Raamses gateway over HTTP/JSON (the transport the real
ESP32 firmware uses): register -> heartbeat -> read gateway_stats + alert state
-> redraw.

Stdlib only (urllib + json + threading). Works over plain SSH, no X display.

Usage:
    python3 cyd_simulator.py cyd-001 [--host 127.0.0.1] [--port 8765]
                                      [--heartbeat 5] [--refresh 0.5]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone


# ── ANSI ---------------------------------------------------------------------

RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
WHITE = "\033[37m"
DARKRED_BG = "\033[41m"          # red background
NAVY_BG = "\033[44m"             # blue background
CLEAR = "\033[2J\033[H"          # clear screen + cursor home


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

    def _get(self, path: str) -> dict:
        req = urllib.request.Request(f"{self.base}{path}")
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

    def stats(self) -> dict:
        return self._get("/stats")


class CYDState:
    """What the simulated CYD knows and shows."""

    def __init__(self, device_id: str, host: str, port: int):
        self.device_id = device_id
        self.gateway = f"{host}:{port}"
        self.registered = False
        self.alert_active = False
        self.alert_seq = None
        self.stats: dict = {}
        self.last_hb = 0.0
        self.last_error = ""


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


def render_screen(state: CYDState, now: float) -> str:
    """Build the CYD 320x240-style screen as a boxed terminal panel."""
    W = 42  # inner width
    bar = "─" * W

    # Header bar (color reflects alert state)
    hb_bg = DARKRED_BG if state.alert_active else NAVY_BG
    header = f"{hb_bg}{BOLD} RAAMSES MONITOR{RESET}"
    badge = f"{YELLOW}{BOLD}[!ALERT]{RESET}" if state.alert_active else ""
    header_line = f"│{header}{' ' * (W - len(' RAAMSES MONITOR') - (len('[!ALERT]') if state.alert_active else 0))}{badge}│"

    s = state.stats
    uptime = _fmt_uptime(s.get("uptime_seconds", 0)) if s else "---"
    cpu_line = (
        f" CPU: {s.get('cpu_temp_c', '--')}°C  {s.get('cpu_percent', '--')}%"
        if s else " CPU: ---"
    )
    ram_line = (
        f" RAM: {s.get('mem_used_percent', '--')}%  {s.get('mem_free_mb', '--')}MB free"
        if s else " RAM: ---"
    )
    agents = s.get("agents_registered", "?") if s else "?"

    status = "Registered OK" if state.registered else "OFFLINE"
    status_color = GREEN if state.registered else RED
    status_line = f" Status: {status_color}{status}{RESET}"
    hb_line = f" Last HB: {_fmt_hb_age(state, now)}"

    lines = [
        f"┌{bar}┐",
        header_line,
        f"├{bar}┤",
        f"│ Gateway: {state.gateway}".ljust(W + 1) + "│",
        f"│{cpu_line}".ljust(W + 1) + "│",
        f"│{ram_line}".ljust(W + 1) + "│",
        f"│ Agents: {agents}".ljust(W + 1) + "│",
        f"│ Uptime: {uptime}".ljust(W + 1) + "│",
        f"├{bar}┤",
        f"│{status_line}".ljust(W + 9) + "│",
        f"│{hb_line}".ljust(W + 1) + "│",
    ]

    # Alert box (bottom of screen)
    if state.alert_active:
        alert_box = f"│{DARKRED_BG}{YELLOW}{BOLD}  AGENT NEEDS HELP  {RESET}"
        lines.append(alert_box.ljust(W + 19) + "│")
    else:
        lines.append(f"│{' ' * W}│")

    lines.append(f"└{bar}┘")
    lines.append(f"{CYAN}  [q]=quit  [Ctrl-C]=quit{RESET}")
    if state.last_error:
        lines.append(f"{RED}{state.last_error}{RESET}")

    return "\\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Raamses CYD display simulator")
    ap.add_argument("device_id")
    ap.add_argument("--device-type", default="cyd")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--heartbeat", type=float, default=5.0,
                    help="heartbeat interval in seconds")
    ap.add_argument("--refresh", type=float, default=0.5,
                    help="screen redraw interval in seconds")
    args = ap.parse_args()

    client = GatewayClient(args.host, args.port)
    state = CYDState(args.device_id, args.host, args.port)

    def apply_response(resp: dict):
        """Update state from a register/heartbeat response."""
        state.registered = bool(resp.get("accepted", True))
        # Alert may be signalled as a string field ("alert") or a bool.
        if "alert" in resp and resp["alert"]:
            state.alert_active = True
        elif resp.get("alert_active") is False:
            state.alert_active = False
        state.alert_seq = resp.get("alert_seq")
        if "gateway_stats" in resp:
            state.stats = resp["gateway_stats"]
        else:
            state.stats = {}
        state.last_hb = time.time()

    # Initial register
    try:
        apply_response(client.register(args.device_id, args.device_type))
    except (urllib.error.URLError, OSError, ValueError) as e:
        state.last_error = f"register failed: {e}"

    next_hb = time.time() + args.heartbeat
    print(CLEAR, end="", flush=True)
    try:
        while True:
            now = time.time()

            # Heartbeat on cadence
            if now >= next_hb:
                try:
                    apply_response(client.heartbeat(args.device_id))
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


if __name__ == "__main__":
    raise SystemExit(main())