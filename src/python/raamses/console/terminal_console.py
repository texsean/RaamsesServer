#!/usr/bin/env python3
"""
Raamses Terminal Console - htop-style

Powerful terminal-based dashboard for monitoring and controlling agents.
Designed to feel like a "mission control" inside the terminal.
"""

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.text import Text
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
import threading
import time
from datetime import datetime


class HtopStyleConsole:
    def __init__(self):
        self.console = Console()
        self.layout = Layout()
        self._setup_layout()

        self.connected = False
        self.agent_status = "Idle"
        self.token_usage = {"total": 0, "today": 0, "last_hour": 0}
        self.alerts: list[dict] = []
        self.devices: list[dict] = []
        self.log_lines: list[str] = []

        self.running = True
        self.session = PromptSession(
            history=FileHistory(".raamses_history"),
            message="> "
        )

    def _setup_layout(self):
        self.layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main", ratio=3),
            Layout(name="bottom", size=8),
        )
        self.layout["main"].split_row(
            Layout(name="left", ratio=2),
            Layout(name="right", ratio=1),
        )

    def log(self, message: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_lines.append(f"[{ts}] {message}")
        if len(self.log_lines) > 12:
            self.log_lines.pop(0)

    def update_agent(self, status: str, tokens: dict = None):
        self.agent_status = status
        if tokens:
            self.token_usage.update(tokens)

    def add_alert(self, severity: str, message: str):
        self.alerts.append({"time": datetime.now(), "severity": severity, "message": message})
        if len(self.alerts) > 20:
            self.alerts.pop(0)

    def render_header(self) -> Panel:
        title = Text("RAAMSES Terminal Console", style="bold cyan")
        status = Text("● Connected" if self.connected else "● Disconnected",
                      style="green" if self.connected else "red")
        return Panel(Text.assemble(title, "  |  ", status),
                     style="blue", height=3)

    def render_agent_panel(self) -> Panel:
        table = Table.grid(padding=1)
        table.add_column(style="cyan", justify="right")
        table.add_column(style="white")

        table.add_row("Agent Status", self.agent_status)
        table.add_row("Tokens (Total)", str(self.token_usage.get("total", 0)))
        table.add_row("Tokens (Today)", str(self.token_usage.get("today", 0)))
        table.add_row("Tokens (Last Hour)", str(self.token_usage.get("last_hour", 0)))

        return Panel(table, title="Agent Overview", border_style="green")

    def render_alerts_panel(self) -> Panel:
        if not self.alerts:
            content = Text("No recent alerts", style="dim")
        else:
            content = Text()
            for a in self.alerts[-6:]:
                color = {"critical": "red", "error": "red", "warning": "yellow"}.get(a["severity"], "white")
                content.append(f"[{a['time'].strftime('%H:%M')}] ", style="dim")
                content.append(f"{a['message']}\n", style=color)

        return Panel(content, title="Alerts", border_style="red")

    def render_devices_panel(self) -> Panel:
        if not self.devices:
            content = Text("No devices connected", style="dim")
        else:
            table = Table.grid()
            table.add_column("Device")
            table.add_column("Type")
            for d in self.devices[-5:]:
                table.add_row(d.get("id", "?"), d.get("type", "?"))
            content = table

        return Panel(content, title="Connected Devices", border_style="magenta")

    def render_log(self) -> Panel:
        content = "\n".join(self.log_lines[-8:]) if self.log_lines else "No events yet"
        return Panel(content, title="Event Log", border_style="dim")

    def render(self) -> Layout:
        self.layout["header"].update(self.render_header())
        self.layout["left"].update(self.render_agent_panel())
        self.layout["right"].split_column(
            self.render_alerts_panel(),
            self.render_devices_panel()
        )
        self.layout["bottom"].update(self.render_log())
        return self.layout

    def process_command(self, cmd: str):
        cmd = cmd.strip().lower()
        if not cmd:
            return

        if cmd.startswith("/"):
            action = cmd[1:]
            self.log(f"Command: {cmd}")

            if action in ["status", "approve", "reject", "refresh"]:
                self.log(f"Action sent: {action}")
            elif action == "connect":
                self.connected = True
                self.log("Connected to server")
            elif action == "disconnect":
                self.connected = False
                self.log("Disconnected")
            elif action == "quit":
                self.running = False
            else:
                self.log(f"Unknown command: {cmd}")
        else:
            self.log(f"Unknown input: {cmd}")

    def run(self):
        self.console.print("[bold cyan]RAAMSES Terminal Console[/bold cyan] — htop style")
        self.console.print("Type /connect to start, /help for commands.\n")

        with Live(self.render(), refresh_per_second=4, screen=True) as live:
            while self.running:
                try:
                    live.update(self.render())
                    user_input = self.session.prompt()
                    self.process_command(user_input)
                except (EOFError, KeyboardInterrupt):
                    self.running = False

        self.console.print("\n[bold]Exiting Raamses Terminal Console.[/bold]")


if __name__ == "__main__":
    HtopStyleConsole().run()
