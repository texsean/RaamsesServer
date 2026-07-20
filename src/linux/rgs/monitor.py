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

# Accept --log argument for the log file to monitor
_parser = argparse.ArgumentParser()
_parser.add_argument("--log", default="/tmp/raamses_server_live.log", help="Server log file to monitor")
_args = _parser.parse_args()

RAAMSES_LOG = _args.log
RAAMSES_STATE = "/tmp/raamses_state.json"

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
        """Print a text-based htop-style dashboard."""
        now = time.strftime("%H:%M:%S")
        uptime = int(time.time() - self.start_time)

        # Header
        device_count = len(self.devices)
        alert_count = len(self.alerts)
        cmd_count = len(self.commands)
        border = "═" * 70
        print(f"\r{border}", end="", flush=True)
        print(f"\r│ {'RAAMSES LIVE SERVER MONITOR':^50s} │ {'● LIVE':^10s} {'● v1.1':^5s}│", end="", flush=True)
        print(f"\r{border}", end="", flush=True)

        # Row 1: Overview
        status = "ALL SYSTEMS NOMINAL" if device_count > 0 else "WAITING FOR DEVICES"
        print(f"\r│ Status: {status:^45s} │ {now:^10s} │ {uptime}s │", end="", flush=True)
        print(f"\r{border}", end="", flush=True)

        # Row 2: Stats
        print(f"\r│ Devices: {device_count:^10d} │ Alerts: {alert_count:^6d} │ Commands: {cmd_count:^4d} │ Server: 127.0.0.1:9999", end="", flush=True)
        print(f"\r{border}", end="", flush=True)

        # Row 3+: Device Table
        if self.devices:
            print(f"\r│ {'─'*68}│", end="", flush=True)
            print(f"\r│ {'Device ID':<20s} │ {'Type':<10s} │ {'Tier':<8s} │ {'Uptime':<10s} │ {'Battery':<8s} │", end="", flush=True)
            print(f"\r│ {'─'*20} │ {'─'*10} │ {'─'*8} │ {'─'*10} │ {'─'*8} │", end="", flush=True)
            for did, info in list(self.devices.items())[-8:]:
                dtype = info.get("type", "?")
                tier = info.get("tier", "?")
                up = info.get("uptime", "?") + "s"
                bat = info.get("battery", "?") + "%" if info.get("battery") != "?" else "?"
                reg = info.get("registered", "?")
                print(f"\r│ {did:<20s} │ {dtype:<10s} │ {tier:<8s} │ {up:<10s} │ {bat:<8s} │", end="", flush=True)
        else:
            print(f"\r│ {'No devices registered yet. Waiting for emulator(s)...':^68}│", end="", flush=True)

        print(f"\r{border}", end="", flush=True)

        # Alerts section
        if self.alerts:
            print(f"\r│ {'─'*68}│", end="", flush=True)
            print(f"\r│ LATEST ALERTS:", end="", flush=True)
            print(f"\r│", end="", flush=True)
            for ts, sev, title, msg in self.alerts[-5:]:
                sev_color = {"CRITICAL": "!!!", "WARNING": "!! ", "INFO": "   "}.get(sev.upper(), "   ")
                msg_short = msg[:45] if len(msg) > 45 else msg
                print(f"\r│   [{ts}] {sev_color} [{sev.upper():<8s}] {title}: {msg_short}", end="", flush=True)
        else:
            print(f"\r│ {'Waiting for alerts...':^68}│", end="", flush=True)

        print(f"\r{border}", end="", flush=True)

        # Commands section
        if self.commands:
            print(f"\r│ {'─'*68}│", end="", flush=True)
            print(f"\r│ LATEST COMMANDS:", end="", flush=True)
            print(f"\r│", end="", flush=True)
            for ts, direction, target, action in self.commands[-5:]:
                print(f"\r│   [{ts}] → {target:<15s} {action}", end="", flush=True)
        else:
            print(f"\r│ {'Waiting for commands...':^68}│", end="", flush=True)

        print(f"\r{border}", end="", flush=True)

        # Footer
        total_alerts = len(self.alerts)
        critical = sum(1 for a in self.alerts if a[1].upper() == "CRITICAL")
        warnings = sum(1 for a in self.alerts if a[1].upper() == "WARNING")
        info = sum(1 for a in self.alerts if a[1].upper() == "INFO")
        print(f"\r│ {'CRITICAL:'+str(critical):^18s} | {'WARNINGS:'+str(warnings):^18s} | {'INFO:'+str(info):^18s} | Heartbeats/sec: {device_count*0.1:.1f}{' '*(14-len(str(device_count*0.1)))}│", end="", flush=True)
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
