#!/usr/bin/env python3
"""
RGS Device Client — TCP client that connects to the gateway server.

Tests the full pipeline:
  1. REGISTER → RegisterAck
  2. Heartbeat loop
  3. Listen for commands from the server
  4. Send task updates

Usage:
    python device_client.py <device_id> <device_type> [--host localhost] [--port 8765]

Examples:
    python device_client.py dev-001 cyd
    python device_client.py agent-003 full --port 9000
"""

from __future__ import annotations

import argparse
import logging
import socket
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("device_client")


class DeviceClient:
    """TCP device client that speaks the RGS protocol."""

    def __init__(
        self,
        device_id: str,
        device_type: str,
        host: str = "127.0.0.1",
        port: int = 8765,
        schema_version: str = "1.0",
        firmware: Optional[str] = None,
        heartbeat_interval: float = 10.0,
    ) -> None:
        self.device_id = device_id
        self.device_type = device_type
        self.host = host
        self.port = port
        self.schema_version = schema_version
        self.firmware = firmware
        self.heartbeat_interval = heartbeat_interval

        self._sock: Optional[socket.socket] = None
        self._running = False
        self._recv_thread: Optional[threading.Thread] = None
        self._hb_thread: Optional[threading.Thread] = None

        # Session state
        self.registered = False
        self.current_task: Optional[str] = None

    # ── Connection ────────────────────────────────────────────────────────

    def connect(self) -> None:
        """Open TCP connection to gateway server."""
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(5.0)
        log.info("Connecting to %s:%d ...", self.host, self.port)
        self._sock.connect((self.host, self.port))
        self._sock.settimeout(None)  # blocking after connect
        log.info("Connected to %s:%d", self.host, self.port)

    def disconnect(self) -> None:
        """Close the connection and stop all threads."""
        self._running = False
        if self._recv_thread and self._recv_thread.is_alive():
            self._recv_thread.join(timeout=2)
        if self._hb_thread and self._hb_thread.is_alive():
            self._hb_thread.join(timeout=2)
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        log.info("Disconnected")

    # ── Sending ───────────────────────────────────────────────────────────

    def send(self, text: str) -> None:
        """Send a line to the gateway server."""
        if self._sock is None:
            return
        try:
            self._sock.sendall(f"{text}\n".encode("utf-8"))
            log.info("SENT: %s", text[:120])
        except (OSError, ConnectionError) as e:
            log.error("Send failed: %s", e)
            self._running = False

    def send_register(self) -> None:
        """Send REGISTER message."""
        parts = [
            self.device_id,
            self.device_type,
            self.schema_version,
        ]
        if self.firmware:
            parts.append(self.firmware)
        msg = "REGISTER:" + "|".join(parts)
        self.send(msg)

    def send_heartbeat(self) -> None:
        """Send heartbeat."""
        self.send("heartbeat")

    def send_task(self, task: str) -> None:
        """Send task update."""
        self.current_task = task
        self.send(f"task: {task}")

    def send_progress(self, pct: int, detail: str = "") -> None:
        """Send progress update."""
        self.send(f"progress: {pct}% {detail}")

    def send_done(self, result: str) -> None:
        """Send completion."""
        self.send(f"done: {result}")

    def send_error(self, msg: str) -> None:
        """Send error report."""
        self.send(f"error: {msg}")

    # ── Receiving ─────────────────────────────────────────────────────────

    def _recv_loop(self) -> None:
        """Background thread: read responses from server."""
        buf = b""
        while self._running:
            try:
                data = self._sock.recv(4096)
                if not data:
                    log.info("Server closed connection")
                    self._running = False
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    text = line.decode("utf-8", errors="replace").strip()
                    if not text:
                        continue
                    self._handle_server_response(text)
            except (OSError, ConnectionError, UnicodeDecodeError):
                log.error("Receive error")
                self._running = False
                break

    def _handle_server_response(self, text: str) -> None:
        """Process a single line from the server."""
        log.info("RECV: %s", text[:200])

        if text.startswith("REGISTER_ACK:"):
            self.registered = True
            ack_parts = text.replace("REGISTER_ACK:", "").split("|")
            if len(ack_parts) >= 2:
                accepted = ack_parts[0]
                log.info("Registered: %s (accepted=%s)", self.device_id, accepted)

        elif text.lower().startswith("task:") or text.lower().startswith("update:"):
            # Server asking us to do something
            cmd = text.lower()
            if cmd.startswith("task:"):
                task_text = text.split(":", 1)[1].strip()
                log.info("Server assigned task: %s", task_text)
                self.current_task = task_text
                # Echo back confirmation
                self.send(f"progress: 0% started: {task_text}")

        elif text.lower().startswith("progress:") or text.lower().startswith("update:"):
            log.info("Server update: %s", text)

    # ── Heartbeat thread ──────────────────────────────────────────────────

    def _heartbeat_loop(self) -> None:
        """Background thread: periodic heartbeats."""
        while self._running:
            time.sleep(self.heartbeat_interval)
            if self._running:
                self.send_heartbeat()

    # ── Full startup ──────────────────────────────────────────────────────

    def start(self) -> None:
        """Connect, register, and start heartbeat loop."""
        self._running = True
        self.connect()
        self.send_register()

        # Start threads
        self._recv_thread = threading.Thread(
            target=self._recv_loop, daemon=True, name="recv"
        )
        self._recv_thread.start()

        self._hb_thread = threading.Thread(
            target=self._heartbeat_loop, daemon=True, name="heartbeat"
        )
        self._hb_thread.start()

        log.info(
            "Device client running: id=%s type=%s hb_interval=%ds",
            self.device_id,
            self.device_type,
            self.heartbeat_interval,
        )

    def run_demo(self, cycle_seconds: int = 8) -> None:
        """Run a demo workload cycle until interrupted."""
        try:
            self.start()
            time.sleep(1.5)  # wait for registration

            # Demo: simulate a task
            tasks = [
                "initialize monitoring",
                "collect metrics",
                "analyze data",
                "generate report",
            ]

            for task in tasks:
                if not self._running:
                    break
                log.info(">>> Starting task: %s", task)
                self.send_task(task)

                # Simulate work
                for pct in range(0, 101, 25):
                    if not self._running:
                        break
                    time.sleep(cycle_seconds * 0.25)
                    self.send_progress(pct, task)

                if self._running:
                    self.send_done(f"completed: {task}")

            log.info("Demo workload finished. Press Ctrl+C to exit.")

        except KeyboardInterrupt:
            log.info("Interrupted by user")
        finally:
            self.disconnect()


# ── Entry point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RGS Device TCP Client")
    parser.add_argument("device_id", help="Unique device identifier")
    parser.add_argument(
        "device_type",
        choices=["cyd", "full", "epaper"],
        help="Device type (matches gateway device_type)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Gateway host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Gateway port (default: 8765)")
    parser.add_argument("--schema", default="1.0", help="Schema version (default: 1.0)")
    parser.add_argument("--firmware", default=None, help="Firmware version (optional)")
    parser.add_argument(
        "--heartbeat", type=float, default=10.0, help="Heartbeat interval in seconds (default: 10)"
    )
    parser.add_argument(
        "--demo", action="store_true", help="Run demo workload cycle"
    )

    args = parser.parse_args()

    client = DeviceClient(
        device_id=args.device_id,
        device_type=args.device_type,
        host=args.host,
        port=args.port,
        schema_version=args.schema,
        firmware=args.firmware,
        heartbeat_interval=args.heartbeat,
    )

    if args.demo:
        client.run_demo()
    else:
        client.start()
        log.info("Connected. Type Ctrl+C to disconnect.")
        try:
            while client._running:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            client.disconnect()
