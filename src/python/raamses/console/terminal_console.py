#!/usr/bin/env python3
"""
Raamses Terminal Console - Advanced ASCII TUI

Supports multiple display emulation modes:
- full     : htop-style rich dashboard
- cyd      : Small color LCD (320x240 style)
- epaper   : Monochrome e-paper style

Can be used as a real console or as a device emulator.
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.layout import Layout
from rich.live import Live
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from dataclasses import dataclass
from typing import Literal
import time
from datetime import datetime


DisplayMode = Literal["full", "cyd", "epaper"]


@dataclass
class DisplayProfile:
    name: str
    width: int
    height: int
    color: bool
    refresh_type: str


PROFILES = {
    "full": DisplayProfile("Full Desktop", 120, 40, True, "lcd"),
    "cyd": DisplayProfile("CYD 320x240", 40, 15, True, "lcd"),
    "epaper": DisplayProfile("E-Paper 296x128", 37, 16, False, "epaper"),
}


class AdvancedTerminalConsole:
    def __init__(self, mode: DisplayMode = "full"):
        self.console = Console()
        self.mode = mode
        self.profile = PROFILES[mode]
        self.connected = False
        self.agent_status = "Idle"
        self.token_total = 124830
        self.alerts = []
        self.log = []
        self.running = True

        self.session = PromptSession(history=FileHistory(".raamses_history"))

    def log_event(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.append(f"[{ts}] {msg}")
        if len(self.log) > 30:
            self.log.pop(0)

    def render_full(self):
        layout = Layout()
        layout.split_column(
            Layout(Panel(Text("RAAMSES Terminal Console", style="bold cyan"), style="blue"), size=3),
            Layout(name="main"),
            Layout(Panel("\n".join(self.log[-6:]), title="Event Log", border_style="dim"), size=8),
        )
        layout["main"].split_row(
            Layout(Panel(f"Agent Status: {self.agent_status}\nTokens: {self.token_total}", title="Overview")),
            Layout(Panel("No alerts" if not self.alerts else "\n".join(self.alerts[-4:]), title="Alerts", border_style="red")),
        )
        return layout

    def render_cyd(self):
        """Small CYD-style display"""
        content = Text()
        content.append("RAAMSES CYD\n", style="bold cyan")
        content.append(f"Status: {self.agent_status}\n")
        content.append(f"Tokens: {self.token_total}\n")
        if self.alerts:
            content.append(f"Alert: {self.alerts[-1]}\n", style="red")
        return Panel(content, title="CYD Emulation", border_style="green", width=42, height=17)

    def render_epaper(self):
        """Monochrome e-paper style"""
        content = Text()
        content.append("RAAMSES e-Paper\n", style="bold white")
        content.append(f"Agent: {self.agent_status}\n")
        content.append(f"Tok: {self.token_total}\n")
        return Panel(content, title="E-Paper", border_style="white", width=39, height=18)

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
                self.log_event("Connected")
            elif action == "disconnect":
                self.connected = False
            elif action == "mode":
                print("Modes: full | cyd | epaper")
            elif action == "quit":
                self.running = False
            else:
                self.log_event(f"Unknown command: {action}")
        else:
            self.log_event(f"Unknown: {cmd}")

    def run(self):
        self.console.print(f"[bold]Raamses Terminal Console[/bold] — Mode: {self.mode}")
        self.console.print("Type /help or /connect\n")

        with Live(self.render(), refresh_per_second=3, screen=True) as live:
            while self.running:
                try:
                    live.update(self.render())
                    user_input = self.session.prompt()
                    self.process_command(user_input)
                except (EOFError, KeyboardInterrupt):
                    self.running = False

        self.console.print("\n[bold]Exiting.[/bold]")


if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"
    AdvancedTerminalConsole(mode=mode).run()
