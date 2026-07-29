#!/usr/bin/env python3
"""
Raamses Terminal Console - Mission Control (Primary Linux Interface)

Three-sectioned dashboard:
  LEFT:  Server configuration (editable, Apply on change) + log file list
  RIGHT: Connected device icons (ASCII art) | Communication log | Active log tail
         (bottom third)

Log format: MMDDYY_HHMMSS.nnn<TAB>method_name<TAB>detail_string

Blink mode = device verification pulse (ON by default).
"""

from __future__ import annotations

import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.layout import Layout
from rich.live import Live
from rich.text import Text


# ---------------------------------------------------------------------------
# ASCII device icons
# ---------------------------------------------------------------------------

DEVICE_ICONS: dict[str, str] = {
    "CYD-320":   (
        " +----------+\n"
        " |  CYD-320 |\n"
        " | +--------+\n"
        " | |  ####  |\n"
        " | |  ####  |\n"
        " | +--------+\n"
        " +----------+\n"
        "    [====O]"),
    "FULL-1": (
        " +----------+\n"
        " | FULL-1   |\n"
        " | +--------+\n"
        " | |######  |\n"
        " | |######  |\n"
        " | +--------+\n"
        " +----------+\n"
        "    [====O]"),
    "EPAPER-1": (
        " +----------+\n"
        " | EPAPER-1 |\n"
        " | +------+ |\n"
        " | |  ---  |\n"
        " | |  ---  |\n"
        " | |  ---  |\n"
        " | +------+ |\n"
        " +----------+"),
    "CYD-321": (
        " +----------+\n"
        " | CYD-321  |\n"
        " | +--------+\n"
        " | |  ####  |\n"
        " | |  ####  |\n"
        " | +--------+\n"
        " +----------+\n"
        "    [====O]"),
    "FULL-2": (
        " +----------+\n"
        " | FULL-2   |\n"
        " | +--------+\n"
        " | |######  |\n"
        " | |######  |\n"
        " | +--------+\n"
        " +----------+\n"
        "    [====O]"),
}


# ---------------------------------------------------------------------------
# Console
# ---------------------------------------------------------------------------

class RaamsesConsole:
    """3-section terminal dashboard for Raamses gateway monitoring."""

    ESC = "\x1b"  # escape prefix for arrow-key sequences

    def __init__(self, mode: str = "full") -> None:
        self.console = Console()
        self.mode = mode
        self.running = False

        # ---- terminal dimensions (auto-updated each render) ----
        self.term_width = self.console.width
        self.term_height = self.console.height

        # ---- server configuration ----
        self.config: dict[str, str] = {
            "blink_mode": "on",
            "blink_interval": "2s",
            "log_level": "debug",
            "gateway_port": "8765",
            "heartbeat": "30s",
            "max_agents": "50",
        }
        self.config_order = list(self.config.keys())
        self.config_select_idx = 0

        # ---- log file list ----
        self.log_files = [
            "debug.log",
            "app.log",
            "server.log",
            "communication.log",
            "gateway.log",
        ]
        self.active_log = "debug.log"  # default
        self.log_select_idx = 0

        # ---- connected devices ----
        self.connected: dict[str, dict] = {
            "CYD-320":   {"status": "active",   "task": "idle"},
            "FULL-1":    {"status": "active",   "task": "rendering dashboard"},
            "EPAPER-1":  {"status": "idle",     "task": "waiting"},
            "CYD-321":   {"status": "active",   "task": "updating status"},
            "FULL-2":    {"status": "offline",  "task": "disconnected"},
        }

        # ---- communication log ----
        self.comm_log: list[str] = []
        self.comm_log_max = 150

        # ---- active log tail ----
        self.active_log_lines: list[str] = []
        self.log_tail_max = 80

        # ---- input ----
        self.user_input: Optional[str] = None
        self.input_lock = threading.Lock()

        # ---- blink pulse state (cycles every ~3 s) ----
        self._blink_cycle = 0
        self._blink_states = ["  O  ", "  @@ ", "  O  ", "  @@ "]

        # ---- stats ----
        self._msg_in = 0
        self._msg_out = 0
        self._start_time = time.time()

        # ---- helpers ----
        self._ensure_log_dir()
        self._seed_debug_log()

    # ------------------------------------------------------------------
    # Terminal size helpers
    # ------------------------------------------------------------------

    def _update_terminal_size(self) -> None:
        """Read current terminal dimensions. Called every render frame."""
        import shutil
        sz = shutil.get_terminal_size((80, 24))
        self.term_width = sz.columns
        self.term_height = sz.lines

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ensure_log_dir(self) -> None:
        base = os.path.dirname(os.path.abspath(__file__))
        self.log_dir = os.path.join(base, "logs")
        os.makedirs(self.log_dir, exist_ok=True)

    def _log_path(self, name: str) -> str:
        return os.path.join(self.log_dir, name)

    def _ts(self) -> str:
        """MMDDYY_HHMMSS.nnn"""
        now = datetime.now()
        ms = now.microsecond // 1000
        return now.strftime("%m%d%y_%H%M%S") + f".{ms:03d}"

    def _log_line(self, method: str, detail: str) -> str:
        return f"{self._ts()}\t{method}\t{detail}"

    def _seed_debug_log(self) -> None:
        """Write sample entries so the active log tail isn't blank."""
        path = self._log_path("debug.log")
        if os.path.exists(path):
            return
        lines = [
            ("_gateway_start", "Raamses Gateway listening on 0.0.0.0:8765"),
            ("_handle_register", "Accepted registration CYD-320 (type=cyd)"),
            ("_handle_register", "Accepted registration FULL-1 (type=full)"),
            ("_heartbeat", "Heartbeat from CYD-320"),
            ("_handle_comm", "REGISTER_ACK:true|2026-07-19T12:00:00Z|1.0|rgs-gateway"),
            ("_handle_comm", "PING from FULL-1"),
            ("_handle_comm", "TASK:rendering dashboard"),
            ("_handle_comm", "UPDATE:render complete"),
            ("_handle_comm", "Heartbeat from FULL-1"),
            ("_handle_register", "Accepted registration EPAPER-1 (type=epaper)"),
            ("_heartbeat", "Heartbeat from FULL-1"),
            ("_heartbeat", "Heartbeat from CYD-320"),
            ("_handle_comm", "REGISTER_ACK:true|2026-07-19T12:00:05Z|1.0|rgs-gateway"),
        ]
        with open(path, "w") as f:
            for m, d in lines:
                f.write(f"{self._log_line(m, d)}\n")

    def _read_log(self, name: str) -> list[str]:
        path = self._log_path(name)
        try:
            with open(path, "r") as f:
                lines = f.readlines()
            return [l.rstrip("\n") for l in lines[-self.log_tail_max:]]
        except FileNotFoundError:
            return [f"(File not found: {path})"]

    def _add_comm_msg(self, direction: str, label: str, detail: str) -> None:
        line = f"[{direction}] {label:<10s} | {detail}"
        self.comm_log.append(line)
        if len(self.comm_log) > self.comm_log_max:
            self.comm_log.pop(0)

    def _add_sample_comm(self) -> None:
        """Inject realistic incoming/outgoing messages periodically."""
        devices = list(self.connected.keys())
        agent_ids = ["dev-001", "dev-002", "dev-003"]
        msgs_in = [
            "REGISTER_ACK:true|2026-07-19T12:00:00Z|1.0",
            "heartbeat",
            "task: rendering dashboard",
            "status update: 45% battery",
            "update: task complete",
        ]
        msgs_out = [
            f"/cmd {agent_ids[0]} deploy",
            "HEARTBEAT: CYD-320",
            f"/tell {agent_ids[1]} status",
            "COMMAND: render_image",
        ]

        r = time.time() % 4
        if r < 1.5:
            label = devices[self._msg_in % len(devices)] if devices else "DISPLAY"
            self._add_comm_msg("IN  ", label, msgs_in[self._msg_in % len(msgs_in)])
            self._msg_in += 1
        elif r < 3:
            agent = agent_ids[self._msg_out % len(agent_ids)] if agent_ids else "dev-001"
            self._add_comm_msg("OUT ", "AGENT", msgs_out[self._msg_out % len(msgs_out)].format(agent))
            self._msg_out += 1

    # ------------------------------------------------------------------
    # Renderers
    # ------------------------------------------------------------------

    def _render_config_panel(self) -> Panel:
        """Left panel: Server configuration table."""
        # Dynamically size columns based on available width
        # Left panel gets ~1/3 of terminal width minus borders
        panel_width = max(30, self.term_width // 3 - 2)
        key_width = min(18, panel_width // 3)
        val_width = max(10, panel_width - key_width - 12)

        tbl = Table(box=None)
        tbl.add_column("Setting", style="cyan", width=key_width, justify="right")
        tbl.add_column("Value", style="white", max_width=val_width)
        tbl.add_column("", style="dim", max_width=8)

        blink_on = self.config["blink_mode"] == "on"
        blink_display = "ON  " if blink_on else "OFF "

        for i, key in enumerate(self.config_order):
            if key == "blink_mode":
                val = Text(blink_display, style="bold green" if blink_on else "red")
            elif i == self.config_select_idx:
                val = Text(self.config[key], style="bold yellow")
            else:
                val = Text(self.config[key])

            tbl.add_row(key, val, "[Apply]",
                        style="" if i == self.config_select_idx else "dim")

        return Panel(
            tbl,
            title="Server Configuration",
            subtitle="UP/DOWN=select  ENTER=apply",
            border_style="cyan",
        )

    def _render_log_list_panel(self) -> Panel:
        """Left panel: log file selector."""
        tbl = Table(box=None)
        tbl.add_column("", width=3)
        tbl.add_column("File", style="white")

        for i, name in enumerate(self.log_files):
            prefix = " > " if i == self.log_select_idx else "   "
            if i == self.log_select_idx:
                name_text = Text(name, style="bold yellow")
            else:
                name_text = Text(name)
            tbl.add_row(prefix, name_text)

        return Panel(
            tbl,
            title=f"Log Files  (active: {self.active_log})",
            subtitle="1-5=select file",
            border_style="dim",
        )

    def _render_device_icons(self) -> Panel:
        """Right-top: ASCII art icons for connected devices."""
        # Build device blocks as separate mini-panels stacked vertically
        block_lines: list[str] = []

        # Blink indicator
        blink_state = self._blink_states[self._blink_cycle % len(self._blink_states)]
        blink_on = self.config["blink_mode"] == "on"
        block_lines.append(f" [Blink: {blink_state if blink_on else 'OFF'}]  [{self._ts()}]")
        block_lines.append("")

        # Status helpers
        status_chars = {"active": "\u25cf", "idle": "\u25d0", "offline": "\u25cb"}
        status_color = {"active": "green", "idle": "yellow", "offline": "red"}

        # Determine how many device icon columns fit
        # Each icon block is ~14 chars wide + 2 spaces = 16
        right_panel_width = max(40, (self.term_width * 2) // 3 - 2)
        icon_cols = max(1, right_panel_width // 16)
        # Cap at number of devices
        icon_cols = min(icon_cols, len(self.connected))

        # Render devices in a grid
        devices_list = list(self.connected.items())
        for i, (name, info) in enumerate(devices_list):
            icon_ascii = DEVICE_ICONS.get(name, DEVICE_ICONS["CYD-320"])
            icon_lines = icon_ascii.split("\n")

            dot = status_chars.get(info["status"], "\u25cb")
            color = status_color.get(info["status"], "red")
            # Use Rich inline markup - Panel will auto-parse strings
            block_lines.append(f"  [bold {color}]{dot}[/] {name:<10s} {info['status'].upper():<8s} {info['task']}")
            # Print middle lines of icon
            for il in icon_lines[2:6]:
                block_lines.append(f"    {il[3:]}")

            # Add blank line between rows of icons (not after last in row or last overall)
            if (i + 1) % icon_cols == 0 and i < len(devices_list) - 1:
                block_lines.append("")

        return Panel(
            "\n".join(block_lines),  # plain str so Panel auto-parses markup
            title="Connected Devices",
            border_style="green",
        )

    def _render_comm_log(self) -> Panel:
        """Right-middle: raw communication messages."""
        # Adapt number of visible comm lines to terminal height
        # Right column has 3 sections; comm gets roughly 1/3 of the main area
        # Main area height = term_height - 3 (header) - 2 (borders)
        main_height = max(8, self.term_height - 5)
        comm_lines = max(5, main_height // 3 - 2)

        if not self.comm_log:
            content = Text("(no communication yet)", style="dim")
        else:
            content = Text()
            for entry in self.comm_log[-comm_lines:]:
                if entry.startswith("[IN  ]"):
                    content.append(entry + "\n", style="green")
                elif entry.startswith("[OUT ]"):
                    content.append(entry + "\n", style="yellow")
                else:
                    content.append(entry + "\n")

        return Panel(
            content,
            title=f"Communication  ({self._msg_in} in / {self._msg_out} out)",
            border_style="blue",
        )

    def _render_active_log(self) -> Panel:
        """Right-bottom (1/3): tailing the selected log file."""
        self.active_log_lines = self._read_log(self.active_log)

        # Adapt visible log lines to terminal height
        main_height = max(8, self.term_height - 5)
        log_lines = max(5, main_height // 3 - 2)
        visible_lines = self.active_log_lines[-log_lines:]

        content = Text()
        for line in visible_lines:
            parts = line.split("\t", 2)
            if len(parts) == 3:
                ts, method, detail = parts
                content.append(ts + "\t", style="dim cyan")
                content.append(method + "\t", style="yellow")
                content.append(detail + "\n")
            else:
                content.append(line + "\n", style="dim")

        return Panel(
            content,
            title=f"Active Log: {self.active_log}  (bottom-{self.log_tail_max})",
            border_style="dim",
        )

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def render_full(self) -> Layout:
        """Full dashboard: left=config+logfile | right=devices|comm|active-log."""
        # Update terminal dimensions for this frame
        self._update_terminal_size()

        layout = Layout(name="root")

        # Top row: header
        now = datetime.now()
        elapsed = int(time.time() - self._start_time)
        mins, secs = divmod(elapsed, 60)

        blink_text = "ON" if self.config["blink_mode"] == "on" else "OFF"
        blink_style = "green" if blink_text == "ON" else "red"

        header = Panel(
            Text.assemble(
                Text("RAAMSES  ", style="bold cyan"),
                Text("v2.0.0", style="dim blue"),
                Text(f" [{self.mode}]", style="dim"),
                Text(f" [Blink:{blink_text}]", style=blink_style),
                Text(f"  {self.term_width}x{self.term_height}", style="dim"),
                Text("  "),
                Text(f"up {mins}m {secs}s", style="dim"),
            ),
            border_style="cyan",
            subtitle=Text("  Q=quit  |  UP/DOWN=select config  |  ENTER=apply  |  1-5=select log", style="dim"),
            height=3,
        )
        layout.split_column(
            Layout(header, size=3),
            Layout(name="main", ratio=1),
        )

        # Main area split left / right — ratio adapts to width
        # On narrow terminals, give more space to the right panel
        if self.term_width < 100:
            left_ratio = 1
            right_ratio = 2
        else:
            left_ratio = 2
            right_ratio = 3

        layout["main"].split_row(
            Layout(name="left", ratio=left_ratio),
            Layout(name="right", ratio=right_ratio),
        )

        # Left column: config + log files
        layout["left"].split_column(
            Layout(self._render_config_panel(), ratio=3),
            Layout(self._render_log_list_panel(), ratio=1),
        )

        # Right column: devices + comm + active log
        # Ratios adapt to terminal height
        if self.term_height < 20:
            # Very short terminal — minimize devices, give more to logs
            layout["right"].split_column(
                Layout(self._render_device_icons(), ratio=1),
                Layout(self._render_comm_log(), ratio=2),
                Layout(self._render_active_log(), ratio=2),
            )
        else:
            layout["right"].split_column(
                Layout(self._render_device_icons(), ratio=2),
                Layout(self._render_comm_log(), ratio=2),
                Layout(self._render_active_log(), ratio=1),
            )

        return layout

    def render(self) -> Layout:
        if self.mode == "full":
            return self.render_full()
        # cyd / epaper: simplified single-panel fallback
        return Layout(self._render_config_panel(), name="full")

    # ------------------------------------------------------------------
    # Command handling
    # ------------------------------------------------------------------

    def process_command(self, cmd: str) -> None:
        cmd = cmd.strip()
        if not cmd:
            return

        if cmd.lower() in ("q", "quit"):
            self.running = False
            return

        if cmd.lower() == "help":
            self.console.print(
                "\nCommands:\n"
                "  /help          - Show this help\n"
                "  /connect       - Connect a display\n"
                "  /disconnect    - Disconnect FULL-1\n"
                "  /blink [on|off]- Toggle Blink mode\n"
                "  /set <k> <v>   - Set config key\n"
                "  /q             - Quit\n"
                "\n"
                "Arrow keys: UP/DOWN to select config, ENTER to apply\n"
                "Keys 1-5: select log file\n"
            )
            return

        if cmd.lower().startswith("/connect"):
            self.connected["FULL-1"]["status"] = "active"
            self._add_sample_comm()
            return

        if cmd.lower().startswith("/disconnect"):
            self.connected["FULL-1"]["status"] = "offline"
            self._add_sample_comm()
            return

        if cmd.lower() == "/blink":
            cur = self.config["blink_mode"]
            self.config["blink_mode"] = "off" if cur == "on" else "on"
            self.console.print(f"  [Blink] {'ON' if self.config['blink_mode'] == 'on' else 'OFF'}")
            return

        if cmd.lower().startswith("/blink "):
            val = cmd[7:].strip().lower()
            self.config["blink_mode"] = "on" if val in ("on", "enable", "true", "yes") else "off"
            self.console.print(f"  [Blink] {self.config['blink_mode']}")
            return

        if cmd.lower().startswith("/set "):
            parts = cmd[5:].strip().split(None, 1)
            if len(parts) == 2:
                key, val = parts
                if key in self.config:
                    old = self.config[key]
                    self.config[key] = val
                    self.console.print(f"  Config: {key} = {old} -> {val}")
                else:
                    self.console.print(f"  Unknown setting: {key}")
            return

        self.console.print(f"  Unknown: {cmd} (type /help)")

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------

    def _input_thread(self) -> None:
        """Background thread: reads stdin for keyboard input."""
        while self.running:
            try:
                data = sys.stdin.read(1)
                if data:
                    with self.input_lock:
                        self.user_input = data
            except (OSError, IOError):
                time.sleep(0.1)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Start the terminal dashboard."""
        self.console.print("[bold cyan]RAAMSES Terminal Console v2.0[/bold cyan]  Mode: [bold]{mode}[/bold]".format(mode=self.mode))
        self.console.print("Loading dashboard...\n")

        # Start input thread
        self.running = True
        t = threading.Thread(target=self._input_thread, daemon=True)
        t.start()

        # Signal handler for terminal resize
        try:
            def _on_resize(sig, frame):
                pass
            signal.signal(signal.SIGWINCH, _on_resize)
        except (OSError, ValueError):
            pass

        with Live(self.render(), refresh_per_second=4, screen=True) as live:
            last_tick = time.time()

            while self.running:
                # Periodic updates
                now = time.time()
                if now - last_tick >= 2.0:
                    self._add_sample_comm()
                    self._blink_cycle += 1
                    last_tick = now

                # Refresh display
                live.update(self.render())

                # Check for user input
                with self.input_lock:
                    data = self.user_input
                    self.user_input = None

                if data:
                    # Handle escape sequences
                    if data == self.ESC:
                        try:
                            data = self.ESC + sys.stdin.read(2)
                        except (OSError, IOError):
                            data = self.ESC

                    if data == self.ESC + "[A":
                        # UP
                        if self.config_select_idx > 0:
                            self.config_select_idx -= 1
                        else:
                            self.config_select_idx = len(self.config_order) - 1

                    elif data == self.ESC + "[B":
                        # DOWN
                        if self.config_select_idx < len(self.config_order) - 1:
                            self.config_select_idx += 1
                        else:
                            self.config_select_idx = 0

                    elif data == "\n" or data == "\r":
                        # ENTER: apply selected config
                        key = self.config_order[self.config_select_idx]
                        if key == "blink_mode":
                            self.config[key] = "off" if self.config[key] == "on" else "on"
                        self.console.print(f"  Applied: {key} = {self.config[key]}")

                    elif data.lower() in ("q", "quit"):
                        self.running = False

                    else:
                        # Regular command (single character, e.g. "1" for log files)
                        if data.isdigit() and 1 <= int(data) <= len(self.log_files):
                            self.log_select_idx = int(data) - 1
                            self.active_log = self.log_files[self.log_select_idx]
                            self.active_log_lines = self._read_log(self.active_log)
                        else:
                            self.process_command(data)

                time.sleep(0.05)

        self.console.print("\n[bold]Shutting down Raamses Console.[/bold]\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"
    RaamsesConsole(mode=mode).run()
