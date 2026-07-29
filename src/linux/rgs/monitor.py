#!/usr/bin/env python3
"""
Raamses Live Server Monitor - reads server log and displays live dashboard.

This shows the htop-style dashboard you'd see in the full terminal console,
pulled from live server activity.
"""

import json
import time
import os
import sys
import signal
import argparse
import re

# Accept --log and --port arguments for flexibility
_parser = argparse.ArgumentParser(description="Raamses Live Server Monitor")
_parser.add_argument("--log", default="/tmp/raamses_server_live.log", help="Server log file to monitor")
_parser.add_argument("--server-port", type=int, default=8765, help="Gateway server port (display only)")
_args = _parser.parse_args()

RAAMSES_LOG = _args.log
RAAMSES_STATE = "/tmp/raamses_state.json"
SERVER_PORT = _args.server_port

class LiveMonitor:
    def __init__(self):
        self.devices = {}
        self.alerts = []
        self.commands = []
        self.running = True
        self.start_time = time.time()

    def parse_log_line(self, line):
        line = line.strip()
        # Strip ANSI escape codes before parsing
        line = re.sub(r'\x1b\[[0-9;]*m', '', line)
        line = line.strip()
        if "[SERVER] [REGISTER]" in line:
            # Parse: [REGISTER] cyd-001 (cyd) tier=free schema=1.0
            parts = line.split("[REGISTER] ")[1]
            tokens = parts.split()
            device_id = tokens[0]
            device_type = tokens[1].strip("()")
            tier = "?"
            schema = "1.0"
            for i, t in enumerate(tokens):
                if t.startswith("tier="): tier = t.split("=")[1]
                if t.startswith("schema="): schema = t.split("=")[1]
            self.devices[device_id] = {
                "type": device_type,
                "tier": tier,
                "schema": schema,
                "registered": time.strftime("%H:%M:%S"),
            }
        elif "[SERVER] [HEARTBEAT]" in line:
            parts = line.split("[HEARTBEAT] ")[1]
            device_id = parts.split(" ")[0]
            rest = parts[len(device_id)+1:]
            uptime = "?"
            battery = "?"
            if "uptime=" in rest:
                uptime = rest.split("uptime=")[1].split()[0]
            if "battery=" in rest:
                battery = rest.split("battery=")[1].split("%")[0]
            if device_id in self.devices:
                self.devices[device_id]["uptime"] = uptime
                self.devices[device_id]["battery"] = battery
        elif "[SERVER] [COMMAND]" in line:
            parts = line.split("[COMMAND] ")[1]
            direction = parts.split(":")[0]
            target = parts.split(":")[1].split()[0]
            action = ":".join(parts.split(":")[1:]).split()[0].strip()
            self.commands.append((time.strftime("%H:%M:%S"), direction, target, action))
        elif "[EMULATOR] [ALERT]" in line:
            # Parse: [ALERT] [INFO] Agent Status: Sub-agent completed...
            try:
                bracket = line.index("[ALERT]")
                rest = line[bracket+7:].strip()
                severity = rest.split("[")[1].split("]")[0]
                rest2 = rest[rest.index("]")+1:].strip()
                title = rest2.split(":")[0]
                message = rest2[rest2.index(":")+1:].strip()
                self.alerts.append((time.strftime("%H:%M:%S"), severity, title, message))
            except (ValueError, IndexError):
                pass
        elif "[EMULATOR] [HEARTBEAT]" in line:
            pass  # Already handled by server heartbeat parsing
        elif "[EMULATOR] [COMMAND]" in line:
            pass  # Already handled by server command parsing
        elif "[SERVER] <- Register from " in line:
            parts = line.split("from ")[1]
            device_id = parts.strip()
            self.devices[device_id] = self.devices.get(device_id, {})
            if "registered" not in self.devices[device_id]:
                self.devices[device_id]["registered"] = time.strftime("%H:%M:%S")

    def save_state(self):
        """Save current state for console to read."""
        state = {
            "devices": self.devices,
            "alerts": self.alerts[-50:],
            "commands": self.commands[-50:],
            "uptime": int(time.time() - self.start_time),
        }
        tmp = RAAMSES_STATE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f)
        os.rename(tmp, RAAMSES_STATE)

    def update(self):
        """Read new lines from server log."""
        if not os.path.exists(RAAMSES_LOG):
            return
        try:
            with open(RAAMSES_LOG, "r") as f:
                f.seek(0, 2)  # EOF
                size = f.tell()
            if not hasattr(self, "_pos"):
                self._pos = 0  # Start from beginning on first read
            with open(RAAMSES_LOG, "r") as f:
                f.seek(self._pos)
                for line in f:
                    self.parse_log_line(line)
                self._pos = f.tell()
        except Exception:
            pass
        self.save_state()

    def display_dashboard(self):
        """Print a text-based htop-style dashboard. Adapts to terminal size."""
        # Get terminal dimensions
        import shutil
        sz = shutil.get_terminal_size((80, 24))
        term_w = sz.columns
        term_h = sz.lines

        now = time.strftime("%H:%M:%S")
        uptime = int(time.time() - self.start_time)

        # Header
        device_count = len(self.devices)
        alert_count = len(self.alerts)
        cmd_count = len(self.commands)

        # Inner width = terminal width (content rows are │...│ = term_w chars)
        # Content area inside borders = term_w - 2 (subtract left │ and right │)
        inner_w = max(40, term_w)
        border = "═" * inner_w

        # How many device/alert/command rows fit
        # Reserve: 2 header borders, 2 status borders, 2 stats borders, 1 device header,
        # 1 alerts header, 1 commands header, 1 footer border = ~10 lines overhead
        avail_rows = max(3, term_h - 12)
        device_rows = min(avail_rows // 3, 8) if self.devices else 0
        alert_rows = min(avail_rows // 3, 5) if self.alerts else 0
        cmd_rows = min(avail_rows // 3, 5) if self.commands else 0

        print(f"\r{border}", end="", flush=True)
        title_str = "RAAMSES LIVE SERVER MONITOR"
        live_str = "● LIVE"
        ver_str = "● v1.1"
        # Center title in available space
        left_pad = (inner_w - len(title_str) - len(live_str) - len(ver_str) - 4) // 2
        print(f"\r│ {title_str:^{max(0,left_pad)}s} │ {live_str}  {ver_str}│", end="", flush=True)
        print(f"\r{border}", end="", flush=True)

        # Row 1: Overview — 3 columns
        # Line format: │ col1 │ col2 │ col3 │
        # Total = 1+1+col1+1+1+col2+1+1+col3+1+1 = col1+col2+col3+10
        status = "ALL SYSTEMS NOMINAL" if device_count > 0 else "WAITING FOR DEVICES"
        status_field = f"Status: {status}"
        time_field = f"{now}"
        uptime_field = f"{uptime}s"
        avail_3 = inner_w - 10  # 10 = 4 separator positions * 2 + 2 borders
        col1_w = avail_3 // 3
        col2_w = max(len(time_field), avail_3 // 4)
        col3_w = avail_3 - col1_w - col2_w
        # Truncate fields to their column width
        status_field = status_field[:col1_w]
        time_field = time_field[:col2_w]
        uptime_field = uptime_field[:col3_w]
        print(f"\r│ {status_field:<{col1_w}s} │ {time_field:<{col2_w}s} │ {uptime_field:>{col3_w}s} │", end="", flush=True)
        print(f"\r{border}", end="", flush=True)

        # Row 2: Stats — 4 columns
        # Line format: │ col1 │ col2 │ col3 │ col4 │
        # Total = col1+col2+col3+col4 + 12 (5 separators * 2 + 2 borders)
        stats1 = f"Devices: {device_count}"
        stats2 = f"Alerts: {alert_count}"
        stats3 = f"Commands: {cmd_count}"
        stats4 = f"Server: 127.0.0.1:{SERVER_PORT}"
        avail_4 = inner_w - 12
        s1_w = max(len(stats1), min(12, avail_4 // 4))
        s2_w = max(len(stats2), min(10, avail_4 // 4))
        s3_w = max(len(stats3), min(12, avail_4 // 4))
        s4_w = avail_4 - s1_w - s2_w - s3_w
        # Truncate fields to column width
        stats1 = stats1[:s1_w]
        stats2 = stats2[:s2_w]
        stats3 = stats3[:s3_w]
        stats4 = stats4[:s4_w]
        print(f"\r│ {stats1:<{s1_w}s} │ {stats2:<{s2_w}s} │ {stats3:<{s3_w}s} │ {stats4:<{s4_w}s} │", end="", flush=True)
        print(f"\r{border}", end="", flush=True)

        # Row 3+: Device Table — 5 columns
        # Line format: │ col1 │ col2 │ col3 │ col4 │ col5 │
        # Total = col1+col2+col3+col4+col5 + 14 (6 separators * 2 + 2 borders)
        if self.devices:
            print(f"\r│ {'─'*(inner_w-2)}│", end="", flush=True)
            avail_5 = inner_w - 14
            id_w = max(8, min(20, avail_5 // 5))
            type_w = max(4, min(10, avail_5 // 5))
            tier_w = max(4, min(8, avail_5 // 5))
            up_w = max(4, min(10, avail_5 // 5))
            bat_w = avail_5 - id_w - type_w - tier_w - up_w
            bat_w = max(4, bat_w)
            # Truncate header fields
            hdr_id = "Device ID"[:id_w]
            hdr_type = "Type"[:type_w]
            hdr_tier = "Tier"[:tier_w]
            hdr_up = "Uptime"[:up_w]
            hdr_bat = "Battery"[:bat_w]
            print(f"\r│ {hdr_id:<{id_w}s} │ {hdr_type:<{type_w}s} │ {hdr_tier:<{tier_w}s} │ {hdr_up:<{up_w}s} │ {hdr_bat:<{bat_w}s} │", end="", flush=True)
            print(f"\r│ {'─'*id_w} │ {'─'*type_w} │ {'─'*tier_w} │ {'─'*up_w} │ {'─'*bat_w} │", end="", flush=True)
            for did, info in list(self.devices.items())[-device_rows:]:
                dtype = info.get("type", "?")
                tier = info.get("tier", "?")
                up = info.get("uptime", "?") + "s"
                bat = info.get("battery", "?") + "%" if info.get("battery") != "?" else "?"
                # Truncate all fields to their column width
                did = did[:id_w]
                dtype = dtype[:type_w]
                tier = tier[:tier_w]
                up = up[:up_w]
                bat = bat[:bat_w]
                print(f"\r│ {did:<{id_w}s} │ {dtype:<{type_w}s} │ {tier:<{tier_w}s} │ {up:<{up_w}s} │ {bat:<{bat_w}s} │", end="", flush=True)
        else:
            no_dev = "No devices registered yet. Waiting for emulator(s)..."
            print(f"\r│ {no_dev:^{inner_w-2}s}│", end="", flush=True)

        print(f"\r{border}", end="", flush=True)

        # Alerts section
        if self.alerts:
            print(f"\r│ {'─'*(inner_w-2)}│", end="", flush=True)
            print(f"\r│ LATEST ALERTS:", end="", flush=True)
            print(f"\r│", end="", flush=True)
            for ts, sev, title, msg in self.alerts[-alert_rows:]:
                sev_color = {"CRITICAL": "!!!", "WARNING": "!! ", "INFO": "   "}.get(sev.upper(), "   ")
                # Truncate message to fit terminal width
                msg_max = inner_w - 25
                msg_short = msg[:msg_max] if len(msg) > msg_max else msg
                print(f"\r│   [{ts}] {sev_color} [{sev.upper():<8s}] {title}: {msg_short}", end="", flush=True)
        else:
            print(f"\r│ {'Waiting for alerts...':^{inner_w-2}s}│", end="", flush=True)

        print(f"\r{border}", end="", flush=True)

        # Commands section
        if self.commands:
            print(f"\r│ {'─'*(inner_w-2)}│", end="", flush=True)
            print(f"\r│ LATEST COMMANDS:", end="", flush=True)
            print(f"\r│", end="", flush=True)
            for ts, direction, target, action in self.commands[-cmd_rows:]:
                # Truncate action to fit
                action_max = inner_w - 30
                action_short = action[:action_max] if len(action) > action_max else action
                target_short = target[:15]
                print(f"\r│   [{ts}] → {target_short:<15s} {action_short}", end="", flush=True)
        else:
            print(f"\r│ {'Waiting for commands...':^{inner_w-2}s}│", end="", flush=True)

        print(f"\r{border}", end="", flush=True)

        # Footer — 4 columns
        # Line format: │ col1 │ col2 │ col3 │ col4 │
        # Total = col1+col2+col3+col4 + 12 (5 separators * 2 + 2 borders)
        total_alerts = len(self.alerts)
        critical = sum(1 for a in self.alerts if a[1].upper() == "CRITICAL")
        warnings = sum(1 for a in self.alerts if a[1].upper() == "WARNING")
        info = sum(1 for a in self.alerts if a[1].upper() == "INFO")
        hb = f"Heartbeats/sec: {device_count*0.1:.1f}"
        avail_f = inner_w - 12
        f1 = f"CRITICAL:{str(critical)}"
        f2 = f"WARNINGS:{str(warnings)}"
        f3 = f"INFO:{str(info)}"
        f1_w = max(len(f1), min(12, avail_f // 4))
        f2_w = max(len(f2), min(12, avail_f // 4))
        f3_w = max(len(f3), min(10, avail_f // 4))
        f4_w = avail_f - f1_w - f2_w - f3_w
        # Truncate fields to column width
        f1 = f1[:f1_w]
        f2 = f2[:f2_w]
        f3 = f3[:f3_w]
        hb = hb[:f4_w]
        print(f"\r│ {f1:<{f1_w}s} │ {f2:<{f2_w}s} │ {f3:<{f3_w}s} │ {hb:<{f4_w}s} │", end="", flush=True)
        print(f"\r{border}", end="", flush=True)


def save_server_log():
    """Redirect server output to log file."""
    # This is called by the launcher wrapper
    pass


def main():
    monitor = LiveMonitor()

    # Create signal handler for clean exit
    def handle_signal(sig, frame):
        monitor.running = False
        print("\n\n[Monitor] Stopped.")
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    print("=" * 70)
    print("  RAAMSES LIVE SERVER MONITOR")
    print("  Reading from", RAAMSES_LOG)
    print("  Press Ctrl+C to stop")
    print("=" * 70)

    # Wait for log file to exist
    while not os.path.exists(RAAMSES_LOG):
        time.sleep(0.5)

    while monitor.running:
        monitor.update()
        monitor.display_dashboard()
        time.sleep(1)


if __name__ == "__main__":
    main()
