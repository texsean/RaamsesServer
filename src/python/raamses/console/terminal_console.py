#!/usr/bin/env python3
"""
Raamses Terminal Console (Primary Linux/Windows Console)

A powerful terminal-based interface, similar to the Hermes CLI experience.
Supports slash commands, live agent views, alerts, and device emulation.
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.text import Text
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
import threading
import time
from datetime import datetime

from ..client.device_client import DeviceClient
from ..messages.command import Command


class TerminalConsole:
    def __init__(self):
        self.console = Console()
        self.client: DeviceClient | None = None
        self.connected = False
        self.agent_status = "No data yet"
        self.alerts: list[str] = []
        self.log_lines: list[str] = []
        self.running = True

        self.session = PromptSession(
            history=FileHistory(".raamses_history"),
            message="raamses> "
        )

    def log(self, message: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_lines.append(f"[{ts}] {message}")
        if len(self.log_lines) > 20:
            self.log_lines.pop(0)

    def update_agent_view(self, status: str):
        self.agent_status = status

    def show_dashboard(self):
        """Render the main dashboard."""
        table = Table(title="RAAMSES Terminal Console", show_header=False)
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Status", "Connected" if self.connected else "Disconnected")
        table.add_row("Agent", self.agent_status)
        table.add_row("Alerts", str(len(self.alerts)))

        self.console.print(Panel(table, title="Overview", border_style="blue"))

        if self.alerts:
            alert_table = Table(title="Recent Alerts")
            alert_table.add_column("Alert")
            for a in self.alerts[-5:]:
                alert_table.add_row(a)
            self.console.print(alert_table)

        # Log
        if self.log_lines:
            log_text = "\n".join(self.log_lines[-8:])
            self.console.print(Panel(log_text, title="Event Log", border_style="dim"))

    def process_command(self, cmd: str):
        cmd = cmd.strip()
        if not cmd:
            return

        if cmd.startswith("/"):
            action = cmd[1:].lower()
            self.log(f"Command: {cmd}")

            if action in ["status", "approve", "reject", "refresh", "help"]:
                if self.client and self.connected:
                    command = Command(
                        command_id=str(int(time.time())),
                        action=action
                    )
                    # TODO: Send via client
                    self.log(f"Sent action: {action}")
                else:
                    self.log("Not connected to server")
            elif action == "connect":
                self.connect()
            elif action == "disconnect":
                self.disconnect()
            elif action == "quit":
                self.running = False
            else:
                self.log(f"Unknown command: {cmd}")
        else:
            self.log(f"Unknown input: {cmd}")

    def connect(self):
        if self.connected:
            return
        self.client = DeviceClient(device_type="terminal_console")
        if self.client.connect():
            self.connected = True
            self.log("Connected to Raamses Server")
        else:
            self.log("Failed to connect")

    def disconnect(self):
        if self.client:
            self.client.disconnect()
        self.connected = False
        self.log("Disconnected")

    def run(self):
        self.console.print(Panel.fit(
            "[bold cyan]RAAMSES Terminal Console[/bold cyan]\n"
            "Type /help for commands. /connect to start.",
            title="Welcome"
        ))

        while self.running:
            try:
                self.show_dashboard()
                user_input = self.session.prompt()
                self.process_command(user_input)
                self.console.clear()
            except (EOFError, KeyboardInterrupt):
                self.running = False

        self.console.print("\n[bold]Goodbye.[/bold]")


if __name__ == "__main__":
    TerminalConsole().run()
