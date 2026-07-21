#!/usr/bin/env python3
"""
RADAR — Raamses Agent Display And Reporter

Real-time dashboard module that connects to the RGS Gateway and displays
live agent status, device icons, communication log, and log tail.

Designed for Rich rendering (requires TTY terminal).
Usage: python3 -m rgs.console.radar [--host 127.0.0.1] [--port 8765]
"""
from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # src/linux/
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.layout import Layout

# ---------------------------------------------------------------------------
# ASCII device icons
# ---------------------------------------------------------------------------

DEVICE_ICONS: dict[str, str] = {
    "cyd": (
        " +----------+\n"
        " |  CYD     |\n"
        " | +--------+\n"
        " | |  [===] |\n"
        " | |  [===] |\n"
        " | +--------+\n"
        " +----------+\n"
        "    [====O]"),
    "full": (
        " +----------+\n"
        " | FULL     |\n"
        " | +--------+\n"
        " | |######  |\n"
        " | |######  |\n"
        " | +--------+\n"
        " +----------+\n"
        "    [====O]"),
    "epaper": (
        " +----------+\n"
        " | E-PAPER  |\n"
        " | +------+ |\n"
        " | |  ---  |\n"
        " | |  ---  |\n"
        " | |  ---  |\n"
        " | +------+ |\n"
        " +----------+"),
    "watch": (
        "  +-------+\n"
        "  |  WATCH |\n"
        "  | o---o  |\n"
        "  |        |\n"
        "  +-------+"),
}

# ---------------------------------------------------------------------------
# RADAR Console
# ---------------------------------------------------------------------------

class RADARConsole:
    """RADAR: Raamses Agent Display And Reporter — live dashboard."""

    def __init__(self, host="127.0.0.1", port=8765, log_path="") -> None:
        self.console = Console()
        self.host = host
        self.port = port
        self.log_path = log_path or self._find_gateway_log()

        # Connected agents from gateway session registry
        self.agents: dict[str, dict] = {}
        self._agent_lock = threading.Lock()

        # Communication log (real gateway messages)
        self.comm_log: list[str] = []
        self.comm_log_max = 100

        # Log tail
        self.log_tail: list[str] = []
        self._last_log_size = 0

        # Blink pulse
        self._blink_cycle = 0
        self._blink_states = ["  O  ", "  @@ ", "  O  ", "  @@ "]

        # Running state
        self.running = False

    def _find_gateway_log(self) -> str:
        """Try to find the gateway log file."""
        candidates = [
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "gateway.log"),
            os.path.join(os.path.dirname(__file__), "..", "..", "gateway.log"),
            "/var/log/raamses/gateway.log",
            "/var/log/raamses/debug.log",
        ]
        for c in candidates:
            c = os.path.normpath(c)
            if os.path.exists(c):
                return c
        # Default: project root
        return "gateway.log"

    # ------------------------------------------------------------------
    # Gateway connection
    # ------------------------------------------------------------------

    def _query_gateway(self) -> dict[str, dict]:
        """Send a gateway command to get agent status."""
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3.0)
            s.connect((self.host, self.port))
            # Send agents command
            s.sendall(b"agents\n")
            time.sleep(0.5)
            data = b""
            s.settimeout(1.0)  # Short timeout for reading response
            while True:
                try:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                except socket.timeout:
                    break
            s.close()
            text = data.decode("utf-8", errors="replace").strip()
            # Parse: "Gateway active — N agents registered (M total)"
            if text:
                return self._parse_status(text)
        except (OSError, ConnectionError, socket.timeout):
            pass
        return {}

    def _parse_status(self, text: str) -> dict[str, dict]:
        """Parse gateway status response into agent dict.
        
        Format:
          Connected agents (3):
            ● agent-cyd-01... type=cyd task='75% initialize monitoring'
            ◐ agent-full-02 type=full task='idle'
        """
        agents = {}
        lines = text.split("\n")
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("Connected agents"):
                continue
            if not stripped or stripped[0] not in ("\u25cf", "\u25d8", "●", "◐"):
                continue
            
            status = "active" if stripped[0] in ("\u25cf", "●") else "idle"
            
            # Remove leading bullet and whitespace
            after_bullet = stripped.lstrip("\u25cf\u25d8●◐ \t")
            
            # Split into tokens by whitespace
            tokens = after_bullet.split()
            if not tokens:
                continue
            
            # First token is device_id with trailing dots like "agent-cyd-01..."
            raw_id = tokens[0].rstrip(".")
            
            # Everything after device_id
            rest_tokens = tokens[1:]
            rest_text = " ".join(rest_tokens)
            
            # Extract task from "task='...'"
            task = "idle"
            if "task='" in rest_text:
                task = rest_text.split("task='")[1].split("'")[0]
            
            # Extract device_type from "type=foo"
            dev_type = "cyd"
            if "type=" in rest_text:
                dtype = rest_text.split("type=")[1].split()[0]
                dev_type = dtype.split(",")[0].rstrip(".,;")
            
            agents[raw_id] = {"status": status, "task": task, "type": dev_type}
        return agents

    def _read_gateway_log(self) -> list[str]:
        """Read the last N lines from the gateway log file."""
        try:
            with open(self.log_path, "r") as f:
                f.seek(0, 2)  # seek to end
                file_size = f.tell()
                if file_size == self._last_log_size:
                    return self.log_tail[-20:]  # unchanged
                f.seek(self._last_log_size)
                lines = f.readlines()
                self._last_log_size = file_size
                return [l.rstrip("\n") for l in lines[-30:]]
        except FileNotFoundError:
            return [f"(Log file not found: {self.log_path})"]

    def _read_comm_log(self) -> list[str]:
        """Parse gateway.log for COMM-type messages."""
        try:
            with open(self.log_path, "r") as f:
                lines = f.readlines()
            comm = []
            for line in lines[-50:]:
                line = line.strip()
                if "Registered" in line or "ACCEPTED" in line or "heartbeat" in line.lower():
                    comm.append(line)
                if "task" in line.lower():
                    comm.append(line)
            return comm[-20:]
        except FileNotFoundError:
            return []

    # ------------------------------------------------------------------
    # Renderers
    # ------------------------------------------------------------------

    def _render_header(self) -> Text:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        agent_count = len(self.agents)
        active_count = sum(1 for a in self.agents.values() if a["status"] == "active")
        return Text(
            f"  RADAR — Raamses Agent Display And Reporter  │  "
            f"Gateway: {self.host}:{self.port}  │  "
            f"Agents: {agent_count} ({active_count} active)  │  "
            f"{now}",
            style="bold cyan",
        )

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def render(self) -> Panel:
        """Render the full dashboard as a Rich Panel with plain text content."""
        self._blink_cycle += 1

        # Query real gateway data
        new_agents = self._query_gateway()
        if new_agents:
            with self._agent_lock:
                self.agents = new_agents

        # Build the text content
        header = self._render_header().plain
        agents_text = self._agent_icons_text()
        comm_lines = self._read_comm_log()[-8:]
        log_tail = self._read_gateway_log()[-8:]

        body = f"[bold green]● CONNECTED AGENTS[/]\n{agents_text}\n"
        body += f"\n[bold blue]◆ COMM[/]\n"
        body += "\n".join(comm_lines) if comm_lines else "\n[dim]No messages yet[/]\n"
        body += f"\n[bold yellow]▸ TAIL — {os.path.basename(self.log_path)}[/]\n"
        body += "\n".join(log_tail) if log_tail else "\n[dim]No log data[/]\n"

        return Panel(
            body,
            title=header,
            border_style="cyan",
            padding=(0, 1),
        )

    def _agent_icons_text(self) -> str:
        """Text version of agent icons."""
        lines = []
        blink = self._blink_states[self._blink_cycle % len(self._blink_states)]
        with self._agent_lock:
            agents = list(self.agents.items())
        if not agents:
            return "[dim]No agents connected[/]"
        for dev_id, info in agents[:6]:
            # Pick icon based on device type from agent dict
            dev_type = info.get("type", "cyd").lower()
            if dev_type not in DEVICE_ICONS:
                # Try partial match
                for key in DEVICE_ICONS:
                    if key in dev_type or dev_type in key:
                        dev_type = key
                        break
            icon = DEVICE_ICONS.get(dev_type, DEVICE_ICONS["cyd"])
            icon = icon.replace("  O  ", blink)
            status = info.get("status", "?")
            task = info.get("task", "idle")
            status_color = "green" if status == "active" else "yellow"
            lines.append(f"{icon}")
            lines.append(f"  {dev_id}  [{status_color}]{status}[reset]  task={task}")
            lines.append("")
        return "\n".join(lines)

    def _render_to_string(self) -> str:
        """Render the dashboard as a plain string (no TTY needed)."""
        from io import StringIO
        buf = StringIO()
        tmp_console = Console(file=buf, force_terminal=True, width=120, soft_wrap=True)
        panel = self.render()
        tmp_console.print(panel)
        return buf.getvalue()

    def run(self, interval: float = 1.0) -> None:
        """Run the RADAR dashboard in a Rich Live loop or text fallback."""
        self.running = True
        self._last_log_size = os.path.getsize(self.log_path) if os.path.exists(self.log_path) else 0

        try:
            if sys.stdout.isatty() and sys.stderr.isatty():
                # Interactive TTY — use Rich Live
                with Live(self.render(), console=self.console, refresh_per_second=2) as live:
                    while self.running:
                        live.update(self.render())
                        time.sleep(interval)
            else:
                # Non-TTY (pipe, file, background) — simple text redraw
                esc_clear = "\033[2J\033[H"
                while self.running:
                    output = self._render_to_string()
                    sys.stdout.write(esc_clear + output)
                    sys.stdout.flush()
                    time.sleep(interval)
        except KeyboardInterrupt:
            self.console.print("\n[RADAR] Stopped.")
        finally:
            self.running = False

    def stop(self) -> None:
        self.running = False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))

    parser = argparse.ArgumentParser(description="RADAR — Raamses Agent Display And Reporter")
    parser.add_argument("--host", default="127.0.0.1", help="Gateway host")
    parser.add_argument("--port", type=int, default=8765, help="Gateway port")
    parser.add_argument("--log", default="", help="Gateway log file path")
    parser.add_argument("--once", action="store_true", help="Show one snapshot and exit")
    args = parser.parse_args()

    console = RADARConsole(host=args.host, port=args.port, log_path=args.log)

    if args.once:
        console.render()
        console.console.print(console.render())
    else:
        console.run()


if __name__ == "__main__":
    main()
