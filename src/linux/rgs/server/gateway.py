"""Raamses Gateway Server — TCP message router.

Accepts TCP connections from registered devices/agents, classifies incoming
messages, and routes them to the appropriate handler:

  - Gateway-local commands execute immediately on this server
  - Agent-targeted commands are dispatched to the correct agent connection
  - Agent updates (heartbeats, task status) are recorded in the session registry

Commands are dropped (not queued) when an agent has moved on.
"""

from __future__ import annotations

import logging
import socket
import threading
from datetime import datetime, timezone
from typing import Optional

from rgs.server.session_registry import SessionRegistry
from rgs.server.message_router import MessageRouter

logger = logging.getLogger(__name__)


class GatewayServer:
    """TCP gateway server that routes messages to agents.

    Parameters:
        host: Bind address (default "0.0.0.0")
        port: TCP port (default 8765)
        heartbeat_timeout: Seconds before an agent is considered stale (default 90)
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8765,
        heartbeat_timeout: int = 90,
    ) -> None:
        self._host = host
        self._port = port
        self._server_socket: Optional[socket.socket] = None
        self._running = False
        self._threads: list[threading.Thread] = []
        self._lock = threading.Lock()

        self._registry = SessionRegistry(heartbeat_timeout=heartbeat_timeout)
        self._router: Optional[MessageRouter] = None
        self._connections: dict[str, socket.socket] = {}  # device_id -> socket

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the gateway server."""
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind((self._host, self._port))
        self._server_socket.listen(50)
        self._server_socket.settimeout(1.0)  # allow checking _running flag
        self._running = True

        logger.info("Raamses Gateway listening on %s:%d", self._host, self._port)
        print(f"[Gateway] Listening on {self._host}:{self._port}")

        # Main accept loop runs in the calling thread
        while self._running:
            try:
                conn, addr = self._server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            thread = threading.Thread(
                target=self._handle_client,
                args=(conn, addr),
                daemon=True,
                name=f"client-{addr[0]}:{addr[1]}",
            )
            thread.start()
            with self._lock:
                self._threads.append(thread)

    def stop(self) -> None:
        """Stop the gateway server and close all connections."""
        self._running = False
        if self._server_socket:
            try:
                self._server_socket.close()
            except OSError:
                pass

        # Close all client connections
        with self._lock:
            for device_id, conn in list(self._connections.items()):
                try:
                    conn.close()
                except OSError:
                    pass
            self._connections.clear()

        # Wait for worker threads
        for t in self._threads:
            t.join(timeout=2)
        self._threads.clear()

        logger.info("Raamses Gateway stopped")

    # ── Configuration ──────────────────────────────────────────────────────

    def initialize_router(self) -> MessageRouter:
        """Create and return the message router, wiring in the handlers.

        Must be called after start() and before accepting traffic.
        """
        self._router = MessageRouter(
            registry=self._registry,
            execute_gateway=self._execute_gateway_command,
            deliver_to_agent=self._deliver_to_agent_connection,
        )
        return self._router

    # ── Handlers ───────────────────────────────────────────────────────────

    def _execute_gateway_command(self, command: str) -> str:
        """Execute a gateway-local command.

        This is the handler for Type 1 (gateway communication) messages.
        Returns a status string.
        """
        cmd = command.strip().lower()

        if cmd in ("status", "ping"):
            active = len(self._registry.list_active())
            total = self._registry.count()
            return f"Gateway active — {active} agents registered ({total} total)"

        if cmd in ("quit", "exit"):
            self.stop()
            return "Gateway shutting down"

        if cmd.startswith("agents") or cmd in ("list", "agents"):
            sessions = self._registry.list_active()
            lines = [f"Connected agents ({len(sessions)}):"]
            for s in sessions:
                status_icon = "●" if s.status == "active" else "◐"
                task = s.current_task or "(idle)"
                lines.append(
                    f"  {status_icon} {s.device_id[:12]}... "
                    f"type={s.device_type} "
                    f"task='{task}'"
                )
            return "\n".join(lines)

        if cmd.startswith("register"):
            return "Register requires device details — handled by session registry"

        if cmd.startswith("heartbeat"):
            return "Heartbeat received — use /tell <id> heartbeat for targeted"

        # Unknown gateway command — log and return info
        logger.info("Gateway command (not implemented): %s", cmd)
        return f"Command '{cmd}' accepted (no handler yet)"

    def _deliver_to_agent_connection(
        self, device_id: str, session: object, raw_command: str
    ) -> dict:
        """Deliver a command to an agent's TCP connection.

        If the connection is closed, returns success=False (triggers drop).
        """
        session_obj: SessionRegistry.AgentSession = session  # type: ignore[assignment]
        conn = session_obj.connection

        if conn is None:
            # No connection attached — agent may have disconnected
            logger.warning("Agent %s has no connection — cannot deliver command",
                           device_id)
            return {"success": False, "error": "no connection"}

        try:
            # Send the command over TCP
            message = f"COMMAND:{device_id}:{raw_command}\n".encode("utf-8")
            conn.sendall(message)
            return {"success": True, "sent": message.decode("utf-8")}
        except (OSError, BrokenPipeError) as e:
            logger.warning("Failed to deliver to agent %s: %s", device_id, e)
            session_obj.status = "offline"
            return {"success": False, "error": str(e)}

    # ── Client Handler ─────────────────────────────────────────────────────

    def _handle_client(self, conn: socket.socket, addr: tuple) -> None:
        """Handle a single connected client's message stream.

        Reads lines until the client disconnects or sends a register message.
        """
        device_id = f"client-{addr[0]}:{addr[1]}"
        buf = b""

        try:
            while self._running:
                data = conn.recv(4096)
                if not data:
                    break  # client disconnected

                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    text = line.decode("utf-8", errors="replace").strip()
                    if not text:
                        continue

                    self._process_incoming(device_id, text, conn)

        except (OSError, ConnectionError) as e:
            logger.info("Client %s:%d disconnected: %s", addr[0], addr[1], e)
        finally:
            # Clean up session on disconnect
            self._registry.unregister(device_id)
            with self._lock:
                self._connections.pop(device_id, None)
            try:
                conn.close()
            except OSError:
                pass

    def _process_incoming(self, device_id: str, text: str, conn: socket.socket) -> None:
        """Process a single incoming message from a client."""

        # Check if this is a register message
        if text.startswith("REGISTER:"):
            self._handle_register(device_id, text, conn)
            return

        # Look up the session by connection (not by raw device_id)
        session = self._registry.get_session_by_connection(conn)

        # Gateway-local commands work for ALL clients (status, agents, ping, quit)
        if text.lower().strip() in ("status", "ping"):
            self._send_to_client(conn, self._execute_gateway_command(text.lower().strip()))
            return
        if text.lower().strip() in ("agents", "list", "list agents"):
            self._send_to_client(conn, self._execute_gateway_command("agents"))
            return

        if session is None:
            # Unregistered client — log and respond
            logger.info("Unregistered client %s sent: %s", device_id[:20], text[:100])
            self._send_to_client(
                conn,
                "INFO: unregistered client. Send 'REGISTER:<details>' first."
            )
            return

        # This is a registered agent — process by its actual device_id
        actual_id = session.device_id

        # Check if this is a heartbeat from a registered agent
        if text.lower().startswith("heartbeat") or text == "PING":
            if self._registry.heartbeat(actual_id):
                self._send_to_client(conn, "OK: heartbeat received")
            return

        # Check for agent task update
        if text.lower().startswith(("task:", "update:", "progress:")):
            task_text = text.split(":", 1)[1].strip() if ":" in text else text
            self._registry.mark_task(actual_id, task_text)
            self._send_to_client(conn, f"OK: task updated to '{task_text}'")
            return

        # Route through the message router
        if self._router:
            result = self._router.route(text)
            response = self._format_response(result, actual_id)
            self._send_to_client(conn, response)

    def _handle_register(self, device_id: str, text: str, conn: socket.socket) -> None:
        """Parse and handle a REGISTER message."""
        # Format: REGISTER:<device_id>|<device_type>|<schema_version>[|<firmware>]
        parts = text.replace("REGISTER:", "").split("|")
        if len(parts) < 3:
            self._send_to_client(conn, "ERROR: REGISTER format: REGISTER:<device_id>|<type>|<schema>[|<firmware>]")
            return

        dev_id = parts[0].strip()
        dev_type = parts[1].strip()
        schema_ver = parts[2].strip()
        firmware = parts[3].strip() if len(parts) > 3 else None

        session = self._registry.register(dev_id, dev_type, schema_ver, firmware)
        session.connection = conn

        with self._lock:
            self._connections[dev_id] = conn

        ack = (
            f"REGISTER_ACK:true|{datetime.now(timezone.utc).isoformat()}|"
            f"{schema_ver}|rgs-gateway"
        )
        self._send_to_client(conn, ack)
        logger.info("Registration accepted: %s (type=%s, fw=%s)",
                     dev_id, dev_type, firmware)

    # ── I/O Helpers ────────────────────────────────────────────────────────

    def _send_to_client(self, conn: socket.socket, text: str) -> None:
        """Send a response to a connected client."""
        try:
            conn.sendall(f"{text}\n".encode("utf-8"))
        except (OSError, BrokenPipeError):
            pass

    def _format_response(self, result: dict, target: str) -> str:
        """Format a router result dict into a human-readable string."""
        status = result.get("status", "unknown")
        message = result.get("message", "")
        msg_type = result.get("type", "gateway")

        status_icon = "✓" if status == "delivered" else "✗" if status == "dropped" else "→"
        return f"[{status_icon.upper()}] {status} — {message}"

    # ── Accessors ──────────────────────────────────────────────────────────

    @property
    def registry(self) -> SessionRegistry:
        """Access the session registry for monitoring/debugging."""
        return self._registry

    @property
    def port(self) -> int:
        return self._port
