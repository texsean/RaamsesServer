#!/usr/bin/env python3
"""
Mock Raamses Server - TCP-based Raamses protocol server for testing.

Accepts device connections, handles Register/RegisterAck,
Heartbeat, Command dispatch, and Alert broadcasting.
Message format: JSON per line (one JSON object per line, terminated by \\n)
"""

import asyncio
import json
import uuid
import random
from datetime import datetime, timezone
from typing import Dict, Optional
import sys


class RaamsesDevice:
    """Represents a connected device in the mock server."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.reader = reader
        self.writer = writer
        self.device_id: Optional[str] = None
        self.device_type: Optional[str] = None
        self.schema_version: str = "1.0"
        self.registered = False
        self.uptime = 0
        self.register_time: Optional[datetime] = None

    async def send(self, data: dict):
        """Send a JSON message to the device."""
        if self.writer and not self.writer.is_closing():
            line = json.dumps(data) + "\n"
            self.writer.write(line.encode("utf-8"))
            await self.writer.drain()

    def close(self):
        if self.writer and not self.writer.is_closing():
            self.writer.close()


class MockRaamsesServer:
    """Mock Raamses server that handles device registration, heartbeats, commands, and alerts."""

    DEVICE_TYPES = ["cyd", "epaper", "watch", "legacy"]
    ALERT_TEMPLATES = [
        {"severity": "critical", "title": "High Temperature",
         "message": "Device CPU temp exceeded 85C threshold"},
        {"severity": "warning", "title": "Low Battery",
         "message": "Device battery at 15% - charging required"},
        {"severity": "info", "title": "Firmware Update",
         "message": "New firmware v1.2.0 available for your device"},
        {"severity": "warning", "title": "Network Unstable",
         "message": "Signal strength fluctuating - connection may drop"},
        {"severity": "critical", "title": "Memory Critical",
         "message": "Free memory below 5% - immediate action needed"},
        {"severity": "info", "title": "Agent Status",
         "message": "Sub-agent completed task successfully"},
        {"severity": "warning", "title": "Disk Space",
         "message": "Storage usage at 90% - cleanup recommended"},
        {"severity": "critical", "title": "Security Alert",
         "message": "Unauthorized access attempt detected on device"},
    ]
    COMMAND_TEMPLATES = [
        {"action": "capture_screenshot", "payload": None},
        {"action": "restart_agent", "payload": None},
        {"action": "run_diagnostic", "payload": "full"},
        {"action": "update_firmware", "payload": "v1.2.0"},
        {"action": "sync_clock", "payload": None},
        {"action": "run_task", "payload": "analyze_sensors"},
    ]

    def __init__(self, host: str = "127.0.0.1", port: int = 9999):
        self.host = host
        self.port = port
        self.devices: Dict[str, RaamsesDevice] = {}
        self.running = False
        self._server: Optional[asyncio.Server] = None
        self._heartbeat_counter = 0

    def _make_envelope(self, device_id: str, message_type: str, payload: dict) -> dict:
        return {
            "header": {
                "message_id": str(uuid.uuid4()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "device_id": device_id,
                "schema_version": "1.0",
                "version": "1.0",
                "message_type": message_type,
            },
            "payload": payload,
        }

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle a single connected device."""
        device = RaamsesDevice(reader, writer)
        peer = writer.get_extra_info("peername")
        print(f"[SERVER] New connection from {peer}", flush=True)

        # Start heartbeat tracker
        self._heartbeat_counter += 1
        hb_task = asyncio.create_task(self._track_heartbeat(device, self._heartbeat_counter))

        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                text = line.decode("utf-8").strip()
                if not text:
                    continue

                try:
                    msg = json.loads(text)
                except json.JSONDecodeError:
                    print(f"[SERVER] Invalid JSON from {device.device_id or peer}: {text[:80]}", flush=True)
                    continue

                msg_type = msg.get("header", {}).get("message_type", "")
                device_id = msg.get("header", {}).get("device_id", "")

                print(f"[SERVER] <- {msg_type} from {device_id or peer}", flush=True)

                if msg_type == "Register":
                    await self._handle_register(device, msg)
                elif msg_type == "Heartbeat":
                    await self._handle_heartbeat(device, msg)
                elif msg_type == "CommandResult":
                    print(f"[SERVER] <- CommandResult: {msg.get('payload', {})}", flush=True)
                elif msg_type == "RegisterAck":
                    print(f"[SERVER] <- RegisterAck (from emulator self-register)", flush=True)
                else:
                    print(f"[SERVER] <- Unknown: {msg_type}", flush=True)

        except asyncio.CancelledError:
            pass
        except ConnectionResetError:
            print(f"[SERVER] Connection reset for {device.device_id or peer}", flush=True)
        except Exception as e:
            print(f"[SERVER] Error handling {device.device_id or peer}: {e}", flush=True)
        finally:
            hb_task.cancel()
            try:
                await hb_task
            except asyncio.CancelledError:
                pass
            did = device.device_id
            if did:
                self.devices.pop(did, None)
            device.registered = False
            device.close()
            print(f"[SERVER] Device disconnected: {did}", flush=True)

    async def _handle_register(self, device: RaamsesDevice, msg: dict):
        """Handle Register message, respond with RegisterAck."""
        payload = msg.get("payload", {})
        device_id = payload.get("device_id", str(uuid.uuid4()))
        device_type = payload.get("device_type", "unknown")
        schema_version = payload.get("schema_version", "1.0")
        firmware = payload.get("firmware_version")
        caps = payload.get("capabilities", {})

        device.device_id = device_id
        device.device_type = device_type
        device.schema_version = schema_version
        device.registered = True
        device.register_time = datetime.now(timezone.utc)
        if device_id:
            self.devices[device_id] = device

        # Accept registration
        ack = self._make_envelope(
            device_id, "RegisterAck", {
                "accepted": True,
                "server_time": datetime.now(timezone.utc).isoformat(),
                "schema_version": "1.0",
                "assigned_tier": "free",
            }
        )
        await device.send(ack)
        print(f"[SERVER] [REGISTER] {device_id} ({device_type}) tier=free schema={schema_version}", flush=True)

        # Optionally send an alert right away
        if random.random() < 0.3:
            await self._broadcast_alert(device_id, "info", "Welcome",
                                        f"Device {device_type} registered successfully")

    async def _handle_heartbeat(self, device: RaamsesDevice, msg: dict):
        """Handle Heartbeat message."""
        payload = msg.get("payload", {})
        uptime = payload.get("uptime_seconds", 0)
        battery = payload.get("battery_percent")
        device.uptime = uptime
        device_id = device.device_id or "unknown"
        print(f"[SERVER] [HEARTBEAT] {device_id} uptime={uptime}s"
              f"{' battery=' + str(battery) + '%' if battery else ''}", flush=True)

        # Occasionally dispatch commands
        if random.random() < 0.15 and device_id != "unknown":
            await self._dispatch_command(device_id)

    async def _dispatch_command(self, device_id: str):
        """Send a random command to a device."""
        device = self.devices.get(device_id)
        if not device:
            return
        cmd_template = random.choice(self.COMMAND_TEMPLATES)
        cmd = self._make_envelope(
            device_id, "Command", {
                "command_id": str(uuid.uuid4()),
                "action": cmd_template["action"],
                "payload": cmd_template["payload"],
            }
        )
        await device.send(cmd)
        print(f"[SERVER] [COMMAND] -> {device_id}: {cmd_template['action']}", flush=True)

    async def _broadcast_alert(self, device_id: str, severity: str, title: str, message: str):
        """Send an alert to a specific device."""
        device = self.devices.get(device_id)
        if not device:
            return
        alert = self._make_envelope(
            device_id, "Alert", {
                "severity": severity,
                "title": title,
                "message": message,
                "requires_ack": severity in ("critical", "warning"),
            }
        )
        await device.send(alert)

    async def _track_heartbeat(self, device: RaamsesDevice, counter: int):
        """Periodically send alerts and commands to a registered device."""
        try:
            while True:
                await asyncio.sleep(random.randint(5, 15))
                if device.device_id not in self.devices:
                    break

                # Randomly send an alert
                if random.random() < 0.5 and device.device_id:
                    tmpl = random.choice(self.ALERT_TEMPLATES)
                    await self._broadcast_alert(
                        device.device_id, tmpl["severity"], tmpl["title"], tmpl["message"]
                    )
        except asyncio.CancelledError:
            pass

    async def run(self):
        """Start the mock server."""
        self._server = await asyncio.start_server(
            self.handle_client, self.host, self.port
        )
        addr = self._server.sockets[0].getsockname()
        self.running = True
        print(f"\n{'='*60}", flush=True)
        print(f"  MOCK RAAMSES SERVER RUNNING", flush=True)
        print(f"  {addr[0]}:{addr[1]}", flush=True)
        print(f"{'='*60}\n", flush=True)

        async with self._server:
            await self._server.serve_forever()

    async def stop(self):
        self.running = False
        if self._server:
            self._server.close()
            await self._server.wait_closed()


async def main():
    server = MockRaamsesServer(host="127.0.0.1", port=9999)
    try:
        await server.run()
    except KeyboardInterrupt:
        print("\n[SERVER] Shutting down...", flush=True)
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
