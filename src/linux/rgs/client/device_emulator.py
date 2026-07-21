#!/usr/bin/env python3
"""
Raamses Device Emulator Client - connects to a Raamses server and
simulates a real device by registering, sending heartbeats, and
responding to commands.

Usage:
    python device_emulator.py --host 127.0.0.1 --port 9999 \
        --device-type cyd --device-id "cyd-001"
"""

import asyncio
import json
import uuid
import argparse
import sys
import random
import os
from datetime import datetime, timezone, timedelta

# Ensure the rgs package is importable.
# device_emulator.py lives at src/linux/rgs/client/device_emulator.py;
# sys.path needs src/linux/ so that `from rgs.server.mock_server` resolves.
_rgs_parent = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/linux/
if _rgs_parent not in sys.path:
    sys.path.insert(0, _rgs_parent)


# Device profiles (from device_emulator.py)
DEVICE_PROFILES = {
    "cyd": {
        "name": "CYD 2.8\" Color",
        "device_type": "cyd",
        "schema_version": "1.0",
        "capabilities": {
            "screen": {"width": 320, "height": 240, "color_depth": 16, "refresh_type": "lcd"},
            "input": {"has_touch": True, "has_buttons": False},
            "output": {"has_vibration": False},
            "power": {"has_battery": False},
        },
        "battery": None,
        "max_uptime": 999999,
    },
    "epaper": {
        "name": "E-Paper 200x200 1-bit",
        "device_type": "epaper",
        "schema_version": "1.0",
        "capabilities": {
            "screen": {"width": 200, "height": 200, "color_depth": 1, "refresh_type": "epaper"},
            "input": {"has_buttons": True, "button_count": 2},
            "output": {"has_vibration": False},
            "power": {"has_battery": True},
        },
        "battery": 78,
        "max_uptime": 999999,
    },
    "watch": {
        "name": "Smart Watch (Small)",
        "device_type": "watch",
        "schema_version": "1.0",
        "capabilities": {
            "screen": {"width": 120, "height": 120, "color_depth": 16},
            "input": {"has_buttons": True, "button_count": 1},
            "output": {"has_vibration": True},
            "power": {"has_battery": True},
        },
        "battery": 45,
        "max_uptime": 999999,
    },
    "legacy": {
        "name": "Old Limited Device",
        "device_type": "legacy",
        "schema_version": "1.0",
        "capabilities": {
            "screen": {"width": 128, "height": 64, "color_depth": 1},
            "input": {"has_buttons": True, "button_count": 3},
            "output": {},
            "power": {"has_battery": True},
        },
        "battery": 23,
        "max_uptime": 999999,
    },
}


class DeviceEmulator:
    """Simulates a Raamses device that connects to a server."""

    def __init__(self, device_id: str, device_type: str, host: str, port: int):
        self.device_id = device_id
        self.host = host
        self.port = port
        self.profile = DEVICE_PROFILES.get(device_type, DEVICE_PROFILES["cyd"])
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.uptime = 0
        self.running = False
        self.received_commands = []
        self.received_alerts = []
        self.registered = False
        self._connected_event = asyncio.Event()

    async def connect(self):
        """Connect to the Raamses server."""
        print(f"\n[EMULATOR] Connecting to {self.host}:{self.port} ...", flush=True)
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        print(f"[EMULATOR] Connected!", flush=True)
        self._connected_event.set()

    def _make_envelope(self, message_type: str, payload: dict) -> dict:
        return {
            "header": {
                "message_id": str(uuid.uuid4()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "device_id": self.device_id,
                "schema_version": "1.0",
                "version": "1.0",
                "message_type": message_type,
            },
            "payload": payload,
        }

    async def register(self):
        """Send a Register message and wait for RegisterAck."""
        reg = self._make_envelope("Register", {
            "device_id": self.device_id,
            "schema_version": self.profile["schema_version"],
            "device_type": self.profile["device_type"],
            "firmware_version": "1.0.0",
            "capabilities": self.profile["capabilities"],
        })
        await self._send(reg)
        print(f"[EMULATOR] [REGISTER] Sent for {self.device_id} ({self.profile['name']})", flush=True)

        # Wait for RegisterAck (read until we get one)
        ack = await self._read_until_type("RegisterAck", timeout=5)
        if ack:
            self.registered = True
            resp = ack.get("payload", {})
            print(f"[EMULATOR] [REGISTER] Accepted: tier={resp.get('assigned_tier', '?')}"
                  f" server_time={resp.get('server_time', '?')[:19]}", flush=True)
        else:
            print("[EMULATOR] [REGISTER] No ack received", flush=True)

    async def send_heartbeat(self):
        """Send a single heartbeat."""
        hb = self._make_envelope("Heartbeat", {
            "uptime_seconds": self.uptime,
            "battery_percent": self.profile["battery"],
            "signal_strength": random.randint(40, 95),
            "free_memory_kb": random.randint(50000, 200000),
        })
        await self._send(hb)
        print(f"[EMULATOR] [HEARTBEAT] uptime={self.uptime}s"
              f"{' battery=' + str(self.profile['battery']) + '%' if self.profile['battery'] is not None else ''}",
              flush=True)

    async def handle_command(self, msg: dict):
        """Process an incoming command and send a CommandResult."""
        payload = msg.get("payload", {})
        cmd_id = payload.get("command_id", "unknown")
        action = payload.get("action", "unknown")
        self.received_commands.append((action, cmd_id))
        print(f"[EMULATOR] [COMMAND] <- {action} (id={cmd_id[:8]})", flush=True)

        # Simulate command execution
        success = random.random() > 0.1  # 90% success rate
        result = self._make_envelope("CommandResult", {
            "command_id": cmd_id,
            "success": success,
            "message": f"Command '{action}' completed" if success else "Command failed",
        })
        await self._send(result)

    async def handle_alert(self, msg: dict):
        """Process an incoming alert."""
        payload = msg.get("payload", {})
        severity = payload.get("severity", "?")
        title = payload.get("title", "?")
        message = payload.get("message", "?")
        self.received_alerts.append((severity, title, message))
        color = {"critical": "\033[91m", "warning": "\033[93m", "info": "\033[92m"}.get(severity, "")
        reset = "\033[0m"
        print(f"[EMULATOR] {color}[ALERT] [{severity.upper()}] {title}: {message}{reset}", flush=True)

    async def run(self):
        """Main loop: connect, register, send heartbeats, handle incoming messages."""
        hb_task: asyncio.Task | None = None
        recv_task: asyncio.Task | None = None
        connected = False
        try:
            await self.connect()
            connected = True
            await self.register()

            # Start heartbeat sender and message receiver
            hb_task = asyncio.create_task(self._heartbeat_loop())
            recv_task = asyncio.create_task(self._receive_loop())

            # Update uptime
            try:
                while self.running:
                    await asyncio.sleep(1)
                    self.uptime += 1
            except asyncio.CancelledError:
                pass
        except ConnectionRefusedError:
            print("[EMULATOR] Connection refused. Is the server running?", flush=True)
        except Exception as e:
            print(f"[EMULATOR] Error: {e}", flush=True)
        finally:
            if hb_task:
                hb_task.cancel()
                try:
                    await hb_task
                except asyncio.CancelledError:
                    pass
            if recv_task:
                recv_task.cancel()
                try:
                    await recv_task
                except asyncio.CancelledError:
                    pass
            if connected and self.writer:
                self.writer.close()
            print(f"[EMULATOR] Disconnected ({len(self.received_commands)} commands, "
                  f"{len(self.received_alerts)} alerts received)", flush=True)

    async def _heartbeat_loop(self):
        """Send heartbeats periodically."""
        try:
            while self.running:
                await asyncio.sleep(random.randint(5, 10))
                if self.registered:
                    await self.send_heartbeat()
        except asyncio.CancelledError:
            pass

    async def _receive_loop(self):
        """Read messages from the server."""
        try:
            while self.running:
                line = await self.reader.readline()
                if not line:
                    break
                text = line.decode("utf-8").strip()
                if not text:
                    continue
                try:
                    msg = json.loads(text)
                except json.JSONDecodeError:
                    continue
                msg_type = msg.get("header", {}).get("message_type", "")
                if msg_type == "Command":
                    await self.handle_command(msg)
                elif msg_type == "Alert":
                    await self.handle_alert(msg)
                else:
                    print(f"[EMULATOR] <- Unhandled: {msg_type}", flush=True)
        except asyncio.CancelledError:
            pass

    async def _send(self, msg: dict):
        """Send a JSON message to the server."""
        if self.writer and not self.writer.is_closing():
            line = json.dumps(msg) + "\n"
            self.writer.write(line.encode("utf-8"))
            await self.writer.drain()

    async def _read_until_type(self, msg_type: str, timeout: float = 5.0) -> dict | None:
        """Read messages until we find one of the specified type."""
        deadline = asyncio.get_event_loop().time() + timeout
        try:
            while asyncio.get_event_loop().time() < deadline:
                line = await asyncio.wait_for(self.reader.readline(), timeout=0.5)
                if not line:
                    return None
                text = line.decode("utf-8").strip()
                if not text:
                    continue
                try:
                    msg = json.loads(text)
                    if msg.get("header", {}).get("message_type") == msg_type:
                        return msg
                except json.JSONDecodeError:
                    continue
        except asyncio.TimeoutError:
            pass
        return None


async def main():
    parser = argparse.ArgumentParser(description="Raamses Device Emulator")
    parser.add_argument("--host", default="127.0.0.1", help="Server host")
    parser.add_argument("--port", type=int, default=9999, help="Server port")
    parser.add_argument("--device-id", default=None, help="Device ID (random if not specified)")
    parser.add_argument("--device-type", default="cyd",
                        choices=list(DEVICE_PROFILES.keys()), help="Device type")
    args = parser.parse_args()

    device_id = args.device_id or f"emulator-{uuid.uuid4().hex[:8]}"
    print(f"{'='*60}", flush=True)
    print(f"  RAAMSES DEVICE EMULATOR", flush=True)
    print(f"  ID: {device_id}", flush=True)
    print(f"  Type: {args.device_type}", flush=True)
    print(f"  Target: {args.host}:{args.port}", flush=True)
    print(f"{'='*60}\n", flush=True)

    emulator = DeviceEmulator(
        device_id=device_id,
        device_type=args.device_type,
        host=args.host,
        port=args.port,
    )
    emulator.running = True

    try:
        await emulator.run()
    except KeyboardInterrupt:
        emulator.running = False
        print("\n[EMULATOR] Stopped by user", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
