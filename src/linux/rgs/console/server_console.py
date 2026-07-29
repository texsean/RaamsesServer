#!/usr/bin/env python3
"""
Raamses Terminal Console - Server-Aware Edition

Live dashboard that connects to a Raamses server and displays
device status, alerts, and commands in real-time.

Usage:
    python terminal_console.py --host 127.0.0.1 --port 9999
    python terminal_console.py                    # defaults to 127.0.0.1:9999
    python terminal_console.py full|cyd|epaper    # mode selection
"""

import json
import uuid
import threading
import time
from datetime import datetime, timezone
from typing import Optional
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.layout import Layout
from rich.live import Live
from rich.bar import Bar
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory


class ServerConnection:
    """Manages TCP connection to the Raamses server."""

    def __init__(self, host: str = "127.0.0.1", port: int = 9999):
        self.host = host
        self.port = port
        self.connected = False
        self.reader = None
        self.writer = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._devices = {}
        self._alerts = []
        self._received_commands = []

    @property
    def devices(self):
        return self._devices

    @property
    def alerts(self):
        return self._alerts

    @property
    def received_commands(self):
        return self._received_commands

    def connect(self):
        """Connect to the server in a background thread."""
        import socket
        try:
            self.writer = socket.create_connection((self.host, self.port), timeout=5)
            self.writer.setblocking(True)
            self.reader = self.writer.makefile('r')
            self.connected = True
            self._running = True
            self._thread = threading.Thread(target=self._receive_loop, daemon=True)
            self._thread.start()
            return True
        except Exception:
            return False

    def disconnect(self):
        self._running = False
        if self.writer:
            try:
                self.writer.close()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=2)

    def send(self, msg_type: str, payload: dict):
        if self.writer and self.connected:
            envelope = {
                "header": {
                    "message_id": str(uuid.uuid4()),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "device_id": "",
                    "schema_version": "1.0",
                    "version": "1.0",
                    "message_type": msg_type,
                },
                "payload": payload,
            }
            try:
                line = json.dumps(envelope) + "\n"
                self.writer.sendall(line.encode("utf-8"))
            except Exception:
                pass

    def _receive_loop(self):
        while self._running:
            try:
                line = self.reader.readline()
                if not line:
                    break
                text = line.strip()
                if not text:
                    continue
                try:
                    msg = json.loads(text)
                except json.JSONDecodeError:
                    continue
                msg_type = msg.get("header", {}).get("message_type", "")
                payload = msg.get("payload", {})
                ts = datetime.now().strftime("%H:%M:%S")

                if msg_type == "RegisterAck":
                    ack = payload.get("accepted", False)
                    device_id = payload.get("device_id", "unknown")
                    tier = payload.get("assigned_tier", "?")
                    self._add_alert("info", "Server",
                                    f"RegisterAck: {'accepted' if ack else 'rejected'}"
                                    f" tier={tier}")
                elif msg_type == "Command":
                    cmd_id = payload.get("command_id", "?")[:8]
                    action = payload.get("action", "?")
                    self._received_commands.append((ts, action, cmd_id))
                    if len(self._received_commands) > 20:
                        self._received_commands.pop(0)
                    self._add_alert("info", "Command",
                                    f"Received: {action} (id={cmd_id})")
                elif msg_type == "Alert":
                    severity = payload.get("severity", "?")
                    title = payload.get("title", "?")
                    message = payload.get("message", "?")
                    self._add_alert(severity, title, message)
                else:
                    print(f"[Console] <- {msg_type}", flush=True)

            except Exception:
                break

    def _add_alert(self, severity: str, title: str, message: str):
        entry = {
            "severity": severity,
            "title": title,
            "message": message,
            "time": datetime.now().strftime("%H:%M:%S"),
        }
        self._alerts.append(entry)
        if len(self._alerts) > 30:
            self._alerts.pop(0)


class ServerAwareConsole:
    """Htop-style console that pulls live data from a Raamses server."""

    def __init__(self, mode: str = "full", host: str = "127.0.0.1", port: int = 9999):
        self.console = Console()
        self.mode = mode
        self.connected = False
        self.host = host
        self.port = port
        self.agent_status = "Offline"
        self.token_total = 0
        self.token_today = 0
        self.sub_agents = 0
        self._server: Optional[ServerConnection] = None
        self._live: Optional[Live] = None
        self.running = True
        self.session = PromptSession(history=FileHistory(".raamses_history"))
        self.start_time = time.time()
        self._last_heartbeat = 0
        self.register_sent = False

        # Terminal dimensions (updated each frame)
        import shutil
        sz = shutil.get_terminal_size((80, 24))
        self.term_width = sz.columns
        self.term_height = sz.lines

    def _update_terminal_size(self) -> None:
        """Read current terminal dimensions."""
        import shutil
        sz = shutil.get_terminal_size((80, 24))
        self.term_width = sz.columns
        self.term_height = sz.lines

    def _connect_to_server(self):
        if not self.connected:
            print(f"\n[Console] Connecting to {self.host}:{self.port} ...", flush=True)
            self._server = ServerConnection(self.host, self.port)
            if self._server.connect():
                self.connected = True
                self.agent_status = "Online"
                print("[Console] Connected to server!", flush=True)
                # Auto-send a Register on connect
                self._send_register()

    def _send_register(self):
        self._server.send("Register", {
            "device_id": "console-server-aware",
            "schema_version": "1.0",
            "device_type": "console",
            "firmware_version": "1.0.0",
            "capabilities": {
                "screen": {"width": 1920, "height": 1080, "color_depth": 24},
                "input": {"has_touch": False, "has_keyboard": True},
                "output": {},
                "power": {},
            },
        })
        self.console.print("[cyan]Register sent to server[/cyan]")

    def log_event(self, msg: str):
        self._server._add_alert("info", "Console", msg)

    # ==================== RENDERING ====================
    def render_header(self):
        title = Text("RAAMSES SERVER CONSOLE", style="bold cyan")
        if self.connected and self._server:
            device_count = len(self._server.devices)
            status = Text(f"● Connected | {device_count} devices", style="green bold")
        else:
            status = Text("● Disconnected", style="red bold")
        return Panel(Text.assemble(title, "  v1.1 |  ", status),
                     style="blue", height=3)

    def render_overview(self):
        table = Table.grid(padding=(0, 2))
        table.add_column(style="cyan", justify="right")
        table.add_column(style="white")

        # Gather live data from server
        device_count = 0
        device_list = []
        alert_count = 0
        command_count = 0
        if self._server:
            device_count = len(self._server.devices)
            device_list = list(self._server.devices.values())
            alert_count = len(self._server.alerts)
            command_count = len(self._server.received_commands)

        table.add_row("Agent Status", self.agent_status)
        table.add_row("Devices Online", str(device_count))
        table.add_row("Alerts Received", str(alert_count))
        table.add_row("Commands Rcvd", str(command_count))
        table.add_row("Uptime", f"{int(time.time() - self.start_time)}s")

        return Panel(table, title="Server Stats", border_style="green")

    def render_alerts(self):
        # Adapt number of alerts shown to terminal height
        max_alerts = max(4, self.term_height // 4)
        if not self._server or not self._server.alerts:
            content = Text("No alerts", style="dim")
        else:
            content = Text()
            for a in self._server.alerts[-max_alerts:]:
                color = {"critical": "red", "warning": "yellow", "info": "green"}.get(
                    a.get("severity", ""), "white")
                sev = a.get("severity", "?").upper()
                content.append(f"[{a.get('time', '?')}] ", style="dim")
                content.append(f"[{sev}] ", style=color)
                content.append(f"{a.get('title', '?')}: ", style=color)
                content.append(f"{a.get('message', '')[:40]}\n", style=color)
        return Panel(content, title="Live Alerts", border_style="red")

    def render_devices(self):
        if not self._server or not self._server.devices:
            content = Text("No registered devices", style="dim")
        else:
            t = Table.grid()
            t.add_column("ID", style="cyan")
            t.add_column("Type", style="magenta")
            t.add_column("Reg Time", style="dim")
            for did, info in list(self._server.devices.items())[-5:]:
                reg = info.get("register_time", "?")
                if isinstance(reg, datetime):
                    reg = reg.strftime("%H:%M:%S")
                else:
                    reg = str(reg)[:10] if reg else "?"
                t.add_row(did[:20], str(info.get("device_type", "?")), str(reg))
            content = t
        return Panel(content, title="Registered Devices", border_style="magenta")

    def render_commands(self):
        if not self._server or not self._server.received_commands:
            content = Text("No commands received", style="dim")
        else:
            content = Text()
            for ts, action, cmd_id in self._server.received_commands[-5:]:
                content.append(f"[{ts}] ", style="dim")
                content.append(f"{action} ", style="cyan")
                content.append(f"({cmd_id})\n", style="dim")
        return Panel(content, title="Commands (Console)", border_style="blue")

    def render_log(self):
        lines = []
        if self._server:
            for a in self._server.alerts[-5:]:
                sev = a.get("severity", "?").upper()
                lines.append(f"[{a.get('time', '?')}] [{sev}] {a.get('title', '?')}: "
                             f"{a.get('message', '')[:50]}")
        content = "\n".join(lines) if lines else "No events yet..."
        return Panel(content, title="Event Stream", border_style="dim")

    def render_full(self):
        layout = Layout()
        # Adapt log height to terminal height
        log_h = max(5, min(12, self.term_height // 3))
        layout.split_column(
            Layout(self.render_header(), size=3),
            Layout(name="main", ratio=5),
            Layout(self.render_log(), size=log_h),
        )
        # Adapt column ratios to width
        if self.term_width < 80:
            layout["main"].split_row(
                Layout(self.render_overview(), ratio=1),
                Layout(self.render_alerts(), ratio=2),
                Layout(self.render_devices(), ratio=1),
            )
        else:
            layout["main"].split_row(
                Layout(self.render_overview(), ratio=2),
                Layout(self.render_alerts(), ratio=3),
                Layout(self.render_devices(), ratio=2),
            )
        return layout

    def render_cyd(self):
        content = Text()
        content.append("RAAMSES CYD\n", style="bold cyan")
        content.append(f"Status: {self.agent_status}\n")
        content.append(f"Devices: {len(self._server.devices) if self._server else 0}\n")
        if self._server and self._server.alerts:
            last = self._server.alerts[-1]
            content.append(f"Alert: {last.get('message', '?')[:30]}\n", style="red")
        # Adapt width to terminal — cap at terminal width but keep minimum
        panel_w = min(42, max(30, self.term_width - 2))
        return Panel(content, title="CYD", border_style="green", width=panel_w, height=16)

    def render_epaper(self):
        content = Text()
        content.append("RAAMSES e-Paper\n", style="bold white")
        content.append(f"Status: {self.agent_status}\n")
        content.append(f"Dev: {len(self._server.devices) if self._server else 0}\n")
        panel_w = min(38, max(28, self.term_width - 2))
        return Panel(content, title="E-Paper", border_style="white", width=panel_w, height=16)

    def render(self):
        self._update_terminal_size()
        if self.mode == "full":
            return self.render_full()
        elif self.mode == "cyd":
            return self.render_cyd()
        else:
            return self.render_epaper()

    def process_command(self, cmd: str):
        cmd = cmd.strip().lower()
        if not cmd:
            return

        if cmd.startswith("/"):
            action = cmd[1:]
            if action == "connect":
                if not self.connected:
                    self._connect_to_server()
            elif action == "disconnect":
                self.connected = False
                if self._server:
                    self._server.disconnect()
                self.agent_status = "Offline"
                self.log_event("Disconnected")
            elif action == "register":
                self._send_register()
            elif action == "clear-alerts":
                if self._server:
                    self._server._alerts.clear()
                self.log_event("Alerts cleared")
            elif action == "quit" or action == "exit":
                self.running = False
            else:
                self.log_event(f"Unknown: {action}")
        else:
            self.log_event(f"Input: {cmd}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Raamses Server Console")
    parser.add_argument("mode", nargs="?", default="full",
                        choices=["full", "cyd", "epaper"])
    parser.add_argument("--host", default="127.0.0.1", help="Server host")
    parser.add_argument("--port", type=int, default=9999, help="Server port")
    args = parser.parse_args()

    console = ServerAwareConsole(mode=args.mode, host=args.host, port=args.port)
    console.console.print(f"[bold cyan]RAAMSES Server Console[/bold cyan] — Mode: {args.mode}\n")
    console.console.print(f"Target: {args.host}:{args.port}")
    console.console.print("Type /connect to connect, or wait for auto-connect\n")

    # Auto-connect
    console._connect_to_server()

    with Live(console.render(), refresh_per_second=4, screen=True) as live:
        console._live = live
        while console.running:
            try:
                live.update(console.render())
                user_input = console.session.prompt()
                console.process_command(user_input)
            except (EOFError, KeyboardInterrupt):
                console.running = False
            except Exception as e:
                console.console.print(f"[red]Error: {e}[/red]")

    if console._server:
        console._server.disconnect()
    console.console.print("\n[bold]Exiting Raamses Server Console.[/bold]")


if __name__ == "__main__":
    main()
