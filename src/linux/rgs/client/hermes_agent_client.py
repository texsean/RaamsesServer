#!/usr/bin/env python3
"""
Hermes Agent Monitor Client

Connects to the Raamses Gateway as a registered agent and bridges
messages between the gateway and the Hermes AI agent.

When a message comes in from the gateway (from a device or another agent),
it writes it to a named pipe (FIFO) that Hermes can read from.
When Hermes wants to send a reply, it writes to the gateway via this client.

Usage:
    python hermes_agent_client.py --device-id hermes-agent-01 --device-type hermes

The agent registers, heartbeats, and listens for incoming commands.
Messages from the gateway are printed to stdout and logged.
"""

from __future__ import annotations

import argparse
import logging
import os
import socket
import sys
import threading
import time
import json
from datetime import datetime, timezone
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("hermes-agent")

# FIFO paths for Hermes <-> Gateway bridge
HERMES_RX_FIFO = "/tmp/raamses_hermes_rx"   # Gateway -> Hermes (agent reads from here)
HERMES_TX_FIFO = "/tmp/raamses_hermes_tx"   # Hermes -> Gateway (agent writes to here)


class HermesAgentClient:
    """TCP client that connects to the gateway as a Hermes agent."""

    def __init__(
        self,
        device_id: str = "hermes-agent-01",
        device_type: str = "hermes",
        host: str = "127.0.0.1",
        port: int = 8765,
        schema_version: str = "1.0",
        heartbeat_interval: float = 10.0,
    ) -> None:
        self.device_id = device_id
        self.device_type = device_type
        self.host = host
        self.port = port
        self.schema_version = schema_version
        self.heartbeat_interval = heartbeat_interval

        self._sock: Optional[socket.socket] = None
        self._running = False
        self._recv_thread: Optional[threading.Thread] = None
        self._hb_thread: Optional[threading.Thread] = None
        self._fifo_thread: Optional[threading.Thread] = None
        self.registered = False

    # ── Connection ────────────────────────────────────────────────────────

    def connect(self) -> bool:
        """Connect to gateway server."""
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.settimeout(5.0)
            log.info("Connecting to gateway %s:%d ...", self.host, self.port)
            self._sock.connect((self.host, self.port))
            self._sock.settimeout(None)
            log.info("Connected to gateway!")
            return True
        except (OSError, ConnectionError) as e:
            log.error("Connection failed: %s", e)
            return False

    def disconnect(self) -> None:
        self._running = False
        for t in [self._recv_thread, self._hb_thread, self._fifo_thread]:
            if t and t.is_alive():
                t.join(timeout=2)
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        log.info("Disconnected from gateway")

    def send(self, text: str) -> None:
        if self._sock is None:
            return
        try:
            self._sock.sendall(f"{text}\n".encode("utf-8"))
            log.info("SENT: %s", text[:200])
        except (OSError, ConnectionError) as e:
            log.error("Send failed: %s", e)
            self._running = False

    def send_register(self) -> None:
        msg = f"REGISTER:{self.device_id}|{self.device_type}|{self.schema_version}|hermes-agent-v1"
        self.send(msg)

    def send_heartbeat(self) -> None:
        self.send("heartbeat")

    def send_task(self, task: str) -> None:
        self.send(f"task: {task}")

    def send_chat(self, message: str) -> None:
        """Send a chat message that the gateway will route."""
        self.send(f"task: {message}")

    def send_done(self, result: str) -> None:
        self.send(f"done: {result}")

    # ── Receiving ─────────────────────────────────────────────────────────

    def _recv_loop(self) -> None:
        """Background thread: read responses from gateway."""
        buf = b""
        while self._running:
            try:
                data = self._sock.recv(4096)
                if not data:
                    log.info("Gateway closed connection")
                    self._running = False
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    text = line.decode("utf-8", errors="replace").strip()
                    if not text:
                        continue
                    self._handle_gateway_message(text)
            except (OSError, ConnectionError, UnicodeDecodeError):
                log.error("Receive error")
                self._running = False
                break

    def _handle_gateway_message(self, text: str) -> None:
        """Process a message from the gateway."""
        log.info("RECV: %s", text[:300])

        # Print prominently for Hermes to see
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"\n{'='*60}")
        print(f"[{timestamp}] GATEWAY MESSAGE:")
        print(f"  {text}")
        print(f"{'='*60}\n", flush=True)

        if text.startswith("REGISTER_ACK:"):
            self.registered = True
            ack_parts = text.replace("REGISTER_ACK:", "").split("|")
            if len(ack_parts) >= 2:
                accepted = ack_parts[0]
                log.info("Registered: %s (accepted=%s)", self.device_id, accepted)

        elif text.startswith("COMMAND:"):
            # Gateway is sending us a command to execute
            # Format: COMMAND:<device_id>:<raw_command>
            parts = text.split(":", 2)
            if len(parts) >= 3:
                source = parts[1]
                command = parts[2]
                log.info("Command from %s: %s", source, command)
                # Write to FIFO for Hermes to read
                self._write_to_rx_fifo(source, command)
                # Auto-respond with acknowledgment
                self.send_task(f"acknowledged: {command}")

        elif text.lower().startswith("task:") or text.lower().startswith("update:"):
            # Server assigning a task or sending update
            task_text = text.split(":", 1)[1].strip()
            log.info("Gateway task/update: %s", task_text)
            self._write_to_rx_fifo("gateway", task_text)

        elif text.startswith("["):
            # Router response like [✓] delivered — ...
            log.info("Router response: %s", text)

        else:
            # Unknown message — log it
            log.info("Unknown message: %s", text)
            self._write_to_rx_fifo("gateway", text)

    def _write_to_rx_fifo(self, source: str, message: str) -> None:
        """Write incoming message to the RX FIFO for Hermes to read."""
        entry = json.dumps({
            "source": source,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        try:
            with open(HERMES_RX_FIFO, "w") as f:
                f.write(entry + "\n")
        except (OSError, FileNotFoundError):
            # FIFO not created yet — that's OK
            pass

    # ── FIFO TX loop (Hermes -> Gateway) ────────────────────────────────

    def _fifo_tx_loop(self) -> None:
        """Background thread: read from TX FIFO and send to gateway."""
        while self._running:
            try:
                with open(HERMES_TX_FIFO, "r") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                            msg_type = entry.get("type", "task")
                            message = entry.get("message", "")
                            if msg_type == "task":
                                self.send_task(message)
                            elif msg_type == "done":
                                self.send_done(message)
                            elif msg_type == "heartbeat":
                                self.send_heartbeat()
                            elif msg_type == "chat":
                                self.send_chat(message)
                            else:
                                self.send(message)
                        except json.JSONDecodeError:
                            # Plain text — send as task
                            self.send_task(line)
            except (OSError, FileNotFoundError):
                time.sleep(1)

    # ── Heartbeat ────────────────────────────────────────────────────────

    def _heartbeat_loop(self) -> None:
        while self._running:
            time.sleep(self.heartbeat_interval)
            if self._running:
                self.send_heartbeat()

    # ── Startup ──────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Connect, register, start all loops."""
        if not self.connect():
            return False

        self._running = True
        self.send_register()

        # Wait for registration ack
        time.sleep(1)

        if not self.registered:
            log.warning("No registration ack yet, continuing anyway...")

        # Start recv loop
        self._recv_thread = threading.Thread(
            target=self._recv_loop, daemon=True, name="recv"
        )
        self._recv_thread.start()

        # Start heartbeat loop
        self._hb_thread = threading.Thread(
            target=self._heartbeat_loop, daemon=True, name="heartbeat"
        )
        self._hb_thread.start()

        # Start FIFO TX loop (Hermes -> Gateway)
        self._fifo_thread = threading.Thread(
            target=self._fifo_tx_loop, daemon=True, name="fifo-tx"
        )
        self._fifo_thread.start()

        log.info("Hermes Agent Client started (id=%s, type=%s)", self.device_id, self.device_type)
        return True

    def run_forever(self) -> None:
        """Block until stopped."""
        try:
            while self._running:
                time.sleep(0.5)
        except KeyboardInterrupt:
            log.info("Shutting down...")
            self.disconnect()


def setup_fifos():
    """Create FIFOs if they don't exist."""
    for fifo in [HERMES_RX_FIFO, HERMES_TX_FIFO]:
        if not os.path.exists(fifo):
            try:
                os.mkfifo(fifo)
                log.info("Created FIFO: %s", fifo)
            except OSError as e:
                log.warning("Failed to create FIFO %s: %s", fifo, e)


def main():
    parser = argparse.ArgumentParser(description="Hermes Agent Monitor Client")
    parser.add_argument("--device-id", default="hermes-agent-01", help="Agent device ID")
    parser.add_argument("--device-type", default="hermes", help="Agent device type")
    parser.add_argument("--host", default="127.0.0.1", help="Gateway host")
    parser.add_argument("--port", type=int, default=8765, help="Gateway port")
    parser.add_argument("--heartbeat", type=float, default=10.0, help="Heartbeat interval (seconds)")
    args = parser.parse_args()

    # Set up FIFOs for Hermes <-> Gateway bridge
    setup_fifos()

    client = HermesAgentClient(
        device_id=args.device_id,
        device_type=args.device_type,
        host=args.host,
        port=args.port,
        heartbeat_interval=args.heartbeat,
    )

    if not client.start():
        log.error("Failed to start — is the gateway running on %s:%d?", args.host, args.port)
        sys.exit(1)

    # Print banner
    print(f"\n{'='*60}")
    print(f"  HERMES AGENT MONITOR")
    print(f"  ID: {args.device_id}")
    print(f"  Gateway: {args.host}:{args.port}")
    print(f"  RX FIFO: {HERMES_RX_FIFO}")
    print(f"  TX FIFO: {HERMES_TX_FIFO}")
    print(f"{'='*60}\n", flush=True)

    client.run_forever()


if __name__ == "__main__":
    main()