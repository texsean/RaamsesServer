#!/usr/bin/env python3
"""
rgs Terminal Console - htop Style (Primary Mode)

High-density, information-rich terminal dashboard inspired by htop.
Also supports CYD and E-Paper emulation modes.
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.layout import Layout
from rich.live import Live
from rich.bar import Bar
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from datetime import datetime
import sys


class HtopTerminalConsole:
    def __init__(self, mode: str = "full"):
        self.console = Console()
        self.mode = mode
        self.connected = False
        self.agent_status = "Running"
        self.token_total = 124830
        self.token_today = 18420
        self.sub_agents = 3
        self.alerts = []
        self.devices = []
        self.log = []
        self.running = True

        self.session = PromptSession(history=FileHistory(".rgs_history"))

    def log_event(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.append(f"[{ts}] {msg}")
        if len(self.log) > 15:
            self.log.pop(0)

    # ==================== FULL HTOP-STYLE MODE ====================
    def render_header(self):
        title = Text("rgs", style="bold cyan")
        status = Text("● Connected" if self.connected else "● Disconnected",
                      style="green" if self.connected else "red")
        return Panel(Text.assemble(title, "  v1.0.0  |  ", status),
                     style="blue", height=3)

    def render_overview(self):
        table = Table.grid(padding=(0, 2))
        table.add_column(style="cyan", justify="right")
        table.add_column(style="white")

        table.add_row("Agent Status", self.agent_status)
        table.add_row("Sub-Agents", str(self.sub_agents))
        table.add_row("Tokens (Total)", f"{self.token_total:,}")
        table.add_row("Tokens (Today)", f"{self.token_today:,}")

        return Panel(table, title="Overview", border_style="green")

    def render_alerts(self):
        if not self.alerts:
            content = Text("No recent alerts", style="dim")
        else:
            content = Text()
            for a in self.alerts[-5:]:
                color = "red" if a["severity"] == "critical" else "yellow"
                content.append(f"{a['message']}\n", style=color)
        return Panel(content, title="Alerts", border_style="red")

    def render_devices(self):
        if not self.devices:
            content = Text("No devices", style="dim")
        else:
            t = Table.grid()
            t.add_column("ID")
            t.add_column("Type")
            for d in self.devices[-6:]:
                t.add_row(d.get("id", "?"), d.get("type", "?"))
            content = t
        return Panel(content, title="Devices", border_style="magenta")

    def render_log(self):
        content = "\n".join(self.log[-7:]) if self.log else "No events"
        return Panel(content, title="Event Log", border_style="dim")

    def render_full(self):
        layout = Layout()
        layout.split_column(
            Layout(self.render_header(), size=3),
            Layout(name="main", ratio=5),
            Layout(self.render_log(), size=9),
        )
        layout["main"].split_row(
            Layout(self.render_overview(), ratio=2),
            Layout(self.render_alerts(), ratio=2),
            Layout(self.render_devices(), ratio=1),
        )
        return layout

    # ==================== CYD MODE ====================
    def render_cyd(self):
        content = Text()
        content.append("rgs CYD\n", style="bold cyan")
        content.append(f"Status: {self.agent_status}\n")
        content.append(f"Tokens: {self.token_total}\n")
        if self.alerts:
            content.append(f"Alert: {self.alerts[-1]['message']}\n", style="red")
        return Panel(content, title="CYD", border_style="green", width=42, height=16)

    # ==================== EPAPER MODE ====================
    def render_epaper(self):
        content = Text()
        content.append("rgs e-Paper\n", style="bold white")
        content.append(f"Agent: {self.agent_status}\n")
        content.append(f"Tok: {self.token_total}\n")
        return Panel(content, title="E-Paper", border_style="white", width=38, height=16)

    def render(self):
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
        self.log_event(f"> {cmd}")

        if cmd.startswith("/"):
            action = cmd[1:]
            if action == "connect":
                self.connected = True
                self.log_event("Connected to server")
            elif action == "disconnect":
                self.connected = False
            elif action == "quit":
                self.running = False
            else:
                self.log_event(f"Unknown: {action}")
        else:
            self.log_event(f"Unknown input: {cmd}")

    def run(self):
        self.console.print(f"[bold cyan]rgs Terminal Console[/bold cyan] — Mode: {self.mode}")
        self.console.print("Type /connect or /help\n")

        with Live(self.render(), refresh_per_second=4, screen=True) as live:
            while self.running:
                try:
                    live.update(self.render())
                    user_input = self.session.prompt()
                    self.process_command(user_input)
                except (EOFError, KeyboardInterrupt):
                    self.running = False

        self.console.print("\n[bold]Exiting rgs Console.[/bold]")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"
    HtopTerminalConsole(mode=mode).run()
