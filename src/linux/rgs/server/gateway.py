"""Raamses Gateway Server — TCP + HTTP message router.

Accepts TCP connections from registered devices/agents, classifies incoming
messages, and routes them to the appropriate handler:

  - TCP text messages: REGISTER:id|type|schema, heartbeat, task: ..., progress: ...
  - HTTP JSON messages: POST /register, /heartbeat, /update with JSON payloads
  - Gateway-local commands execute immediately on this server
  - Agent-targeted commands are dispatched to the correct agent connection
  - Agent updates (heartbeats, task status) are recorded in the session registry

Commands are dropped (not queued) when an agent has moved on.
"""

from __future__ import annotations

import json
import logging
import os
import re
import socket
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from rgs.server.session_registry import SessionRegistry
from rgs.server.message_router import MessageRouter
from rgs.verifier import TrustVerifier
from rgs.report_issue import report_issue
from rgs.site_config import get_site_id

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
        enable_lora: bool = False,
        lora_serial_port: Optional[str] = None,
        lora_tcp_host: Optional[str] = None,
        lora_backend: str = "meshtastic",
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
        self._stale_check_interval = 30  # seconds between stale-agent checks
        self._cleanup_thread: Optional[threading.Thread] = None

        # Trust but Verify engine
        self._verifier = TrustVerifier(project_root=Path(__file__).resolve().parent.parent.parent.parent.parent)

        # LoRa bridge (optional)
        self._lora_bridge: Optional[object] = None  # LoRaBridge
        self._enable_lora = enable_lora
        self._lora_serial_port = lora_serial_port
        self._lora_tcp_host = lora_tcp_host
        self._lora_backend = lora_backend

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

        # Start LoRa bridge if enabled
        if self._enable_lora:
            self._start_lora_bridge()

        # Start stale-agent cleanup thread
        self._cleanup_thread = threading.Thread(
            target=self._stale_cleanup_loop,
            daemon=True,
            name="stale-cleanup",
        )
        self._cleanup_thread.start()

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

        # Stop LoRa bridge
        if self._lora_bridge is not None:
            try:
                self._lora_bridge.stop()
            except Exception as e:
                logger.warning("Error stopping LoRa bridge: %s", e)
            self._lora_bridge = None

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

        if cmd.startswith("agents") or cmd == "list":
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

        # Trust but Verify: /verify <agent_id> [question]
        if cmd.startswith("/verify"):
            return self._handle_verify_command(command)

        # User-Reported Issues: /report <agent_id> [reported_status] | [actual_status]
        if cmd.startswith("/report"):
            return self._handle_report_command(command)

        # Site info: /siteid
        if cmd.startswith("/siteid") or cmd.startswith("site"):
            return f"Site ID: {get_site_id()}"

        if cmd.startswith("register"):
            return "Register requires device details — handled by session registry"

        if cmd.startswith("heartbeat"):
            return "Heartbeat received — use /tell <id> heartbeat for targeted"

        # Unknown gateway command — log and return info
        logger.info("Gateway command (not implemented): %s", cmd)
        return f"Command '{cmd}' accepted (no handler yet)"

    # ── LoRa Bridge ──────────────────────────────────────────────────────

    def _start_lora_bridge(self) -> None:
        """Start the LoRa bridge to connect a LoRa radio (Meshtastic or RangePi)."""
        try:
            from rgs.lora.bridge import LoRaBridge
            self._lora_bridge = LoRaBridge(
                registry=self._registry,
                serial_port=self._lora_serial_port,
                tcp_host=self._lora_tcp_host,
                on_register=self._on_lora_register,
                on_heartbeat=self._on_lora_heartbeat,
                backend=self._lora_backend,
            )
            self._lora_bridge.start()
            logger.info("LoRa bridge started (backend=%s, mock=%s)",
                       self._lora_backend, self._lora_bridge.is_mock_mode)
        except Exception as e:
            logger.error("Failed to start LoRa bridge: %s", e)
            self._lora_bridge = None

    def _on_lora_register(self, device_id: str, device_type: str,
                          firmware: str, node_id: int) -> None:
        """Callback when a LoRa device registers."""
        logger.info("LoRa device registered: %s (type=%s, node=%d)",
                    device_id, device_type, node_id)

    def _on_lora_heartbeat(self, device_id: str, node_id: int, status: int) -> None:
        """Callback when a LoRa device sends a heartbeat."""
        logger.info("LoRa heartbeat: %s (node=%d, status=%d)",
                    device_id, node_id, status)

    def _broadcast_alert_on_lora(self) -> Optional[int]:
        """Broadcast an ALERT on LoRa when an agent needs help.

        Called when the gateway detects an agent alert via HTTP.
        Returns the alert sequence number, or None if LoRa is not available.
        """
        if self._lora_bridge is None:
            return None
        try:
            seq = self._lora_bridge.broadcast_alert()
            logger.info("Alert broadcast on LoRa: seq=%d", seq)
            return seq
        except Exception as e:
            logger.error("LoRa alert broadcast failed: %s", e)
            return None

    def _broadcast_clear_on_lora(self, seq: int) -> None:
        """Broadcast a CLEAR on LoRa when an agent alert is resolved.

        Called when the gateway detects an agent alert has cleared.
        """
        if self._lora_bridge is None:
            return
        try:
            self._lora_bridge.broadcast_clear(seq)
            logger.info("Clear broadcast on LoRa: seq=%d", seq)
        except Exception as e:
            logger.error("LoRa clear broadcast failed: %s", e)

    @property
    def lora_bridge(self):
        """Access the LoRa bridge (or None if not enabled)."""
        return self._lora_bridge

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

    # ── Trust but Verify ──────────────────────────────────────────────────

    def _handle_verify_command(self, raw_command: str) -> str:
        """Handle /verify <agent_id> [question] via TCP text.

        Examples:
            /verify agent-001 last files
            /verify agent-001 repo activity
            /verify agent-001 project updates
        """
        parts = raw_command.strip().split(None, 2)  # /verify <agent_id> <question>
        if len(parts) < 2:
            return (
                "Usage: /verify <agent_id> [question]\n"
                "Questions: 'last files', 'project updates', 'repo activity'\n"
                "Default (no question): full verification summary"
            )

        agent_id = parts[1]
        question = parts[2] if len(parts) > 2 else "last files"

        result = self._verifier.answer_question(agent_id, question)
        logger.info("VERIFY %s: q='%s' answer='%s'", agent_id, question, result.answer[:80])

        # Return as readable text
        lines = [
            f"Verification Result for agent {agent_id}",
            f"Question: {question}",
            f"Answer: {result.answer}",
            f"Timestamp: {result.timestamp}",
        ]
        return "\n".join(lines)

    # ── User-Reported Issues ────────────────────────────────────────────────

    def _handle_report_command(self, raw_command: str) -> str:
        """Handle /report <agent_id> [reported|actual] via TCP text.

        Example:
            /report agent-001 agent says idle | actually modifying files
        """
        parts = raw_command.strip().split(None, 2)
        if len(parts) < 2:
            return (
                "Usage: /report <agent_id> [reported_status | actual_status]\n"
                "This will collect logs, generate a zip, and open email + folder."
            )

        agent_id = parts[1]
        status_parts = parts[2].split("|") if len(parts) > 2 else ["", ""]
        reported = status_parts[0].strip() if len(status_parts) > 0 else ""
        actual = status_parts[1].strip() if len(status_parts) > 1 else ""

        # Don't open GUI apps from TCP text (may be headless / remote)
        report = report_issue(
            agent_id=agent_id,
            reported_status=reported,
            actual_status=actual,
            log_dir=Path.cwd(),
            open_apps=False,
        )

        logger.info("REPORT %s: zip=%s", agent_id, report.zip_path)

        lines = [
            f"Issue Report Generated",
            f"  Site ID:          {report.site_id}",
            f"  Agent ID:         {report.agent_id}",
            f"  Timestamp:        {report.timestamp}",
            f"  Log Bundle:       {report.zip_path or '(no logs found)'}",
            f"  Email (mailto):   {(report.mailto_url or '')[:80]}...",
            f"  Reported Status:  {report.reported_status}",
            f"  Actual Status:    {report.actual_status}",
        ]
        return "\n".join(lines)

    # ── HTTP Detection ─────────────────────────────────────────────────────

    _HTTP_RE = re.compile(rb"^(GET|POST|PUT|DELETE|PATCH) ")

    def _is_http_request(self, data: bytes) -> bool:
        """Check if data looks like an HTTP request (GET/POST/... line)."""
        return bool(self._HTTP_RE.match(data))

    def _parse_http_request(self, raw: bytes) -> dict:
        """Parse an HTTP request into method, path, headers, body."""
        text = raw.decode("utf-8", errors="replace")
        parts = text.split("\r\n\r\n", 1)
        header_section = parts[0]
        body = parts[1] if len(parts) > 1 else ""

        lines = header_section.split("\r\n")
        request_line = lines[0] if lines else ""
        tokens = request_line.split()
        method = tokens[0] if len(tokens) >= 1 else "GET"
        path = tokens[1] if len(tokens) >= 2 else "/"

        headers = {}
        for line in lines[1:]:
            if ":" in line:
                key, val = line.split(":", 1)
                headers[key.strip().lower()] = val.strip()

        content_length = int(headers.get("content-length", 0))
        if body and len(body) < content_length:
            # We may have split mid-body; keep original raw for re-read
            pass

        return {
            "method": method,
            "path": path,
            "headers": headers,
            "body": body.strip(),
        }

    def _send_http_response(
        self,
        conn: socket.socket,
        status: int,
        status_text: str,
        body: str,
        content_type: str = "text/plain",
    ) -> None:
        """Send an HTTP response back to the client."""
        resp = (
            f"HTTP/1.1 {status} {status_text}\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
            f"{body}"
        )
        try:
            conn.sendall(resp.encode("utf-8"))
        except (OSError, BrokenPipeError):
            pass

    # ── HTTP Handlers ──────────────────────────────────────────────────────

    def _handle_http_request(self, conn: socket.socket, addr: tuple, req: dict) -> None:
        """Route an HTTP request to the appropriate handler.

        Supported endpoints:
            POST /register  -> register a new device (JSON: device_id, device_type, schema_version)
            POST /heartbeat -> heartbeat for an existing device (JSON: device_id)
            POST /update    -> task/progress update (JSON: device_id, task, progress)
            GET  /status    -> gateway status as JSON
            GET  /agents    -> list agents as JSON
            GET  /verify    -> trust-but-verify query (query params: agent_id, question)
            POST /verify    -> trust-but-verify with JSON body
            POST /report    -> generate issue report with log zip + email
            GET  /siteid    -> return the site ID for this installation
        """
        method = req["method"]
        path = req["path"].split("?")[0]  # strip query string
        body = req["body"]

        logger.info(
            "HTTP %s %s from %s:%d (body=%s)",
            method, path, addr[0], addr[1], body[:200],
        )

        if method == "POST" and path == "/register":
            self._http_register(conn, addr, body)
        elif method == "POST" and path == "/heartbeat":
            self._http_heartbeat(conn, addr, body)
        elif method == "POST" and path == "/update":
            self._http_update(conn, addr, body)
        elif method == "POST" and path == "/status":
            self._http_status(conn, addr, body)
        elif method == "GET" and path == "/status":
            self._http_status(conn, addr, "")
        elif method == "GET" and path == "/agents":
            self._http_agents(conn, addr, "")
        elif method == "GET" and path == "/verify":
            self._http_verify(conn, addr, req)
        elif method == "POST" and path == "/verify":
            self._http_verify(conn, addr, req)
        elif method == "POST" and path == "/report":
            self._http_report(conn, addr, body)
        elif method == "GET" and path == "/siteid":
            self._http_siteid(conn, addr)
        elif method == "GET" and path == "/stats":
            self._send_http_response(
                conn, 200, "OK",
                json.dumps(self._get_gateway_stats()),
                content_type="application/json",
            )
        elif method == "GET" and path == "/":
            self._send_http_response(
                conn, 200, "OK",
                'Raamses Gateway — send POST /register, POST /heartbeat, POST /update, GET /agents, GET /stats, GET /verify, POST /report',
            )
        else:
            self._send_http_response(
                conn, 404, "Not Found",
                '{"error": "unknown endpoint"}',
                content_type="application/json",
            )

    # ── Gateway system stats ────────────────────────────────────────────

    _gateway_start_time = time.time()

    def _get_gateway_stats(self) -> dict:
        """Collect real Pi/system health data for display devices.

        Returns cpu_percent, mem info, cpu_temp_c, uptime, load_avg, and
        disk usage. Uses only stdlib so it works on any Linux without extra
        dependencies. Values are sampled on each call (cheap enough for a
        30s heartbeat interval).
        """
        stats: dict = {}

        # CPU temperature (Pi has /sys/class/thermal/thermal_zone0/temp)
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                stats["cpu_temp_c"] = round(int(f.read().strip()) / 1000.0, 1)
        except Exception:
            pass

        # CPU usage — two-sample /proc/stat method (100ms apart)
        try:
            with open("/proc/stat") as f:
                parts1 = f.readline().split()[1:]
            idle1 = int(parts1[3])
            total1 = sum(int(x) for x in parts1)
            time.sleep(0.1)
            with open("/proc/stat") as f:
                parts2 = f.readline().split()[1:]
            idle2 = int(parts2[3])
            total2 = sum(int(x) for x in parts2)
            total_delta = total2 - total1
            idle_delta = idle2 - idle1
            if total_delta > 0:
                stats["cpu_percent"] = round(
                    (total_delta - idle_delta) / total_delta * 100, 1
                )
        except Exception:
            pass

        # Memory from /proc/meminfo
        try:
            mem_total = mem_avail = None
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        mem_total = int(line.split()[1])
                    elif line.startswith("MemAvailable:"):
                        mem_avail = int(line.split()[1])
            if mem_total and mem_avail:
                stats["mem_total_mb"] = round(mem_total / 1024)
                stats["mem_free_mb"] = round(mem_avail / 1024)
                stats["mem_used_percent"] = round(
                    (mem_total - mem_avail) / mem_total * 100, 1
                )
        except Exception:
            pass

        # Load average (1, 5, 15 min)
        try:
            load1, load5, load15 = os.getloadavg()
            stats["load_avg"] = {
                "1m": round(load1, 2),
                "5m": round(load5, 2),
                "15m": round(load15, 2),
            }
        except Exception:
            pass

        # Gateway uptime (since this process started)
        try:
            stats["uptime_seconds"] = int(time.time() - self._gateway_start_time)
        except Exception:
            pass

        # Disk usage on / (root partition)
        try:
            st = os.statvfs("/")
            disk_total = st.f_blocks * st.f_frsize
            disk_free = st.f_bavail * st.f_frsize
            if disk_total > 0:
                stats["disk_total_gb"] = round(disk_total / 1e9, 1)
                stats["disk_free_gb"] = round(disk_free / 1e9, 1)
                stats["disk_used_percent"] = round(
                    (disk_total - disk_free) / disk_total * 100, 1
                )
        except Exception:
            pass

        # Number of active registered agents
        try:
            stats["agents_registered"] = len(self._registry.list_active())
        except Exception:
            pass

        return stats

    def _http_register(self, conn: socket.socket, addr: tuple, body: str) -> None:
        """Handle POST /register with JSON payload."""
        try:
            data = json.loads(body) if body else {}
        except (json.JSONDecodeError, ValueError) as e:
            self._send_http_response(
                conn, 400, "Bad Request",
                json.dumps({"error": f"invalid JSON: {e}"}),
                content_type="application/json",
            )
            return

        dev_id = data.get("device_id", "")
        dev_type = data.get("device_type", "cyd")
        schema_ver = data.get("schema_version", "1.0")
        firmware = data.get("firmware_version") or data.get("firmware")
        source = data.get("source", "wifi")  # "wifi" or "lora_relay"
        node_id = data.get("node_id")  # Meshtastic node number (for lora_relay)

        if not dev_id:
            # Generate one from MAC or IP if missing
            dev_id = f"http-{addr[0].replace('.', '-')}-{datetime.now(timezone.utc).strftime('%H%M%S')}"

        # Determine transport based on source field
        transport = "lora_relay" if source == "lora_relay" else "wifi"

        try:
            session = self._registry.register(
                dev_id, dev_type, schema_ver, firmware,
                transport=transport,
                node_id=node_id,
            )
            # Attach conn as a file wrapper for sendall
            session.connection = conn

            with self._lock:
                self._connections[dev_id] = conn

            resp = {
                "status": "registered",
                "device_id": dev_id,
                "accepted": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "schema_version": schema_ver,
                "gateway": "rgs-gateway",
            }
            # If there's an active alert on this device, include it
            if session.alert_active:
                resp["alert"] = "Agent needs help"
                resp["alert_seq"] = session.alert_seq
            # Include gateway system stats for display devices
            resp["gateway_stats"] = self._get_gateway_stats()
            self._send_http_response(
                conn, 200, "OK",
                json.dumps(resp),
                content_type="application/json",
            )
            logger.info("HTTP Registration: %s (type=%s, fw=%s, addr=%s:%d)",
                        dev_id, dev_type, firmware, addr[0], addr[1])

        except Exception as e:
            logger.error("HTTP Registration failed for %s: %s", dev_id, e)
            self._send_http_response(
                conn, 500, "Internal Server Error",
                json.dumps({"error": str(e)}),
                content_type="application/json",
            )

    def _http_heartbeat(self, conn: socket.socket, addr: tuple, body: str) -> None:
        """Handle POST /heartbeat."""
        try:
            data = json.loads(body) if body else {}
        except (json.JSONDecodeError, ValueError):
            data = {}

        dev_id = data.get("device_id", "")
        if not dev_id:
            self._send_http_response(
                conn, 400, "Bad Request",
                json.dumps({"error": "device_id required"}),
                content_type="application/json",
            )
            return

        if self._registry.heartbeat(dev_id):
            # Check if this agent has an active alert — include it in the
            # heartbeat response so WiFi-connected Meshtastic devices see it
            session = self._registry.get(dev_id)
            alert_msg = ""
            alert_seq = None
            if session and session.alert_active:
                alert_msg = "Agent needs help"
                alert_seq = session.alert_seq

            resp = {
                "status": "ok",
                "device_id": dev_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            if alert_msg:
                resp["alert"] = alert_msg
                resp["alert_seq"] = alert_seq
            # Include gateway system stats for display devices
            resp["gateway_stats"] = self._get_gateway_stats()
            self._send_http_response(
                conn, 200, "OK",
                json.dumps(resp),
                content_type="application/json",
            )
            if alert_msg:
                logger.info("HB response to %s includes alert: %s (seq=%d)",
                            dev_id, alert_msg, alert_seq)
        else:
            self._send_http_response(
                conn, 404, "Not Found",
                json.dumps({"error": f"agent {dev_id} not registered"}),
                content_type="application/json",
            )

    def _http_update(self, conn: socket.socket, addr: tuple, body: str) -> None:
        """Handle POST /update with task/progress data."""
        try:
            data = json.loads(body) if body else {}
        except (json.JSONDecodeError, ValueError) as e:
            self._send_http_response(
                conn, 400, "Bad Request",
                json.dumps({"error": f"invalid JSON: {e}"}),
                content_type="application/json",
            )
            return

        dev_id = data.get("device_id", "")
        if not dev_id:
            self._send_http_response(
                conn, 400, "Bad Request",
                json.dumps({"error": "device_id required"}),
                content_type="application/json",
            )
            return

        # Task update
        task = data.get("task", "")
        if task:
            self._registry.mark_task(dev_id, task)
            logger.info("HTTP TASK %s: %s", dev_id, task)

        # Progress update
        progress = data.get("progress", data.get("pct", ""))
        if progress is not None and progress != "":
            progress_text = str(progress)
            if task:
                progress_text = f"{progress_text} {task}"
            self._registry.mark_task(dev_id, progress_text)
            logger.info("HTTP TASK %s: %s", dev_id, progress_text)

        # Alert
        alert = data.get("alert", "")
        if alert:
            logger.warning("ALERT from %s: %s", dev_id, alert)
            # Set alert state in registry
            seq = self._broadcast_alert_on_lora()
            if seq is None:
                # No LoRa bridge — generate a local sequence number
                seq = int(time.time()) & 0xFFFF
            self._registry.set_alert(dev_id, seq)
            logger.info("Alert set for %s: seq=%d (lora=%s)",
                       dev_id, seq, seq is not None and self._lora_bridge is not None)

        # Check for alert clear — if "alert_clear" field is present, or
        # if "alert" is empty and the agent previously had an alert
        alert_clear = data.get("alert_clear", "")
        if alert_clear:
            # Explicit clear request
            session = self._registry.get(dev_id)
            if session and session.alert_active:
                self._broadcast_clear_on_lora(session.alert_seq)
                self._registry.clear_alert(dev_id)
                logger.info("Alert cleared for %s: seq=%d", dev_id, session.alert_seq)
        elif not alert:
            # No alert in this update — check if we need to auto-clear
            session = self._registry.get(dev_id)
            if session and session.alert_active:
                self._broadcast_clear_on_lora(session.alert_seq)
                self._registry.clear_alert(dev_id)
                logger.info("Alert auto-cleared for %s (no alert in update): seq=%d",
                           dev_id, session.alert_seq)

        # Status fields
        status_fields = {}
        if "screen_width" in data:
            status_fields["screen_width"] = data["screen_width"]
        if "screen_height" in data:
            status_fields["screen_height"] = data["screen_height"]
        if "battery" in data:
            status_fields["battery"] = data["battery"]
        if "uptime" in data:
            status_fields["uptime"] = data["uptime"]

        resp = {
            "status": "accepted",
            "device_id": dev_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if status_fields:
            resp["fields"] = status_fields
        self._send_http_response(
            conn, 200, "OK",
            json.dumps(resp),
            content_type="application/json",
        )

    def _http_status(self, conn: socket.socket, addr: tuple, body: str) -> None:
        """Handle GET /status — return gateway status as JSON."""
        active = len(self._registry.list_active())
        total = self._registry.count()
        resp = {
            "status": "running",
            "agents_active": active,
            "agents_total": total,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._send_http_response(
            conn, 200, "OK",
            json.dumps(resp),
            content_type="application/json",
        )

    def _http_agents(self, conn: socket.socket, addr: tuple, body: str) -> None:
        """Handle GET /agents — return agent list as JSON."""
        agents = []
        for s in self._registry.list_active():
            agents.append({
                "device_id": s.device_id,
                "device_type": s.device_type,
                "schema_version": s.schema_version,
                "status": s.status,
                "current_task": s.current_task,
                "last_heartbeat": s.last_heartbeat.isoformat() if s.last_heartbeat else None,
                "transport": s.transport,
                "node_id": s.node_id,
                "alert_active": s.alert_active,
                "alert_seq": s.alert_seq if s.alert_active else None,
            })
        resp = {
            "count": len(agents),
            "agents": agents,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._send_http_response(
            conn, 200, "OK",
            json.dumps(resp, indent=2),
            content_type="application/json",
        )

    def _http_verify(self, conn: socket.socket, addr: tuple, req: dict) -> None:
        """Handle GET/POST /verify — trust-but-verify query.

        GET  /verify?agent_id=...&question=...
        POST /verify  {\"agent_id\": \"...\", \"question\": \"...\", \"claims\": {...}}
        """
        agent_id = ""
        question = "last files"
        claims = None

        if req["method"] == "GET":
            # Parse query string
            from urllib.parse import parse_qs
            query = req["path"].split("?", 1)[1] if "?" in req["path"] else ""
            params = parse_qs(query)
            agent_id = params.get("agent_id", [""])[0]
            question = params.get("question", ["last files"])[0]
        else:
            # POST with JSON body
            try:
                data = json.loads(req["body"]) if req["body"] else {}
            except (json.JSONDecodeError, ValueError):
                data = {}
            agent_id = data.get("agent_id", "")
            question = data.get("question", "last files")
            claims = data.get("claims")

        if not agent_id:
            self._send_http_response(
                conn, 400, "Bad Request",
                json.dumps({"error": "agent_id required"}),
                content_type="application/json",
            )
            return

        if claims:
            result = self._verifier.verify_agent_claims(agent_id, claims)
        else:
            result = self._verifier.answer_question(agent_id, question)

        logger.info("HTTP VERIFY %s: q='%s'", agent_id, question)
        self._send_http_response(
            conn, 200, "OK",
            json.dumps(result.to_dict(), indent=2),
            content_type="application/json",
        )

    def _http_report(self, conn: socket.socket, addr: tuple, body: str) -> None:
        """Handle POST /report — generate issue report with log zip + email.

        JSON body: {"agent_id": "...", "reported_status": "...", "actual_status": "..."}
        """
        try:
            data = json.loads(body) if body else {}
        except (json.JSONDecodeError, ValueError) as e:
            self._send_http_response(
                conn, 400, "Bad Request",
                json.dumps({"error": f"invalid JSON: {e}"}),
                content_type="application/json",
            )
            return

        agent_id = data.get("agent_id", "")
        if not agent_id:
            self._send_http_response(
                conn, 400, "Bad Request",
                json.dumps({"error": "agent_id required"}),
                content_type="application/json",
            )
            return

        reported = data.get("reported_status", "")
        actual = data.get("actual_status", "")

        # Don't open GUI apps from HTTP (may be headless / remote)
        report = report_issue(
            agent_id=agent_id,
            reported_status=reported,
            actual_status=actual,
            log_dir=Path.cwd(),
            open_apps=False,
        )

        logger.info("HTTP REPORT %s: zip=%s", agent_id, report.zip_path)
        self._send_http_response(
            conn, 200, "OK",
            json.dumps(report.to_dict(), indent=2),
            content_type="application/json",
        )

    def _http_siteid(self, conn: socket.socket, addr: tuple) -> None:
        """Handle GET /siteid — return the site ID for this installation."""
        resp = {
            "site_id": get_site_id(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._send_http_response(
            conn, 200, "OK",
            json.dumps(resp, indent=2),
            content_type="application/json",
        )

    # ── Client Handler ─────────────────────────────────────────────────────

    def _handle_client(self, conn: socket.socket, addr: tuple) -> None:
        """Handle a single connected client's message stream.

        Reads data until the client disconnects. Auto-detects HTTP vs TCP text
        protocol and routes accordingly.
        """
        device_id = f"client-{addr[0]}:{addr[1]}"
        buf = b""
        is_http = False

        try:
            while self._running:
                data = conn.recv(4096)
                if not data:
                    break  # client disconnected

                buf += data

                # Auto-detect HTTP on first read
                if not is_http:
                    if self._is_http_request(data):
                        is_http = True
                        logger.info("HTTP client detected from %s:%d", addr[0], addr[1])
                        # Process the HTTP request
                        req = self._parse_http_request(buf)
                        self._handle_http_request(conn, addr, req)
                        # HTTP is single-request-response; close the connection
                        # so the client reconnects cleanly (HTTPClient behavior)
                        buf = b""
                        break  # exit recv loop, connection will be cleaned up
                    else:
                        # Not HTTP — process as TCP text (may accumulate multi-line)
                        pass

                # If not HTTP, process as line-delimited TCP text
                if not is_http:
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
        # Check for gateway commands (no registration needed)
        cmd_lower = text.strip().lower()
        if cmd_lower in ("status", "ping", "agents", "list"):
            response = self._execute_gateway_command(cmd_lower)
            try:
                conn.sendall((response + "\n").encode("utf-8"))
            except (OSError, BrokenPipeError):
                pass
            return

        # Trust but Verify / Report Issue / Site ID commands (no registration needed)
        if text.strip().lower().startswith(("/verify", "/report", "/siteid")):
            response = self._execute_gateway_command(text.strip())
            try:
                conn.sendall((response + "\n").encode("utf-8"))
            except (OSError, BrokenPipeError):
                pass
            return

        # Check if this is a REGISTER message
        if text.startswith("REGISTER:"):
            parts = text[9:].split("|")
            if len(parts) >= 2:
                reg_id = parts[0]
                reg_type = parts[1]
                schema_ver = parts[2] if len(parts) > 2 else "1.0"

                session = self._registry.register(reg_id, reg_type, schema_ver)
                session.connection = conn

                # Acknowledge registration
                ack = f"REGISTER_ACK:true|{datetime.now(timezone.utc).isoformat()}|{schema_ver}|rgs-gateway"
                try:
                    conn.sendall((ack + "\n").encode("utf-8"))
                except (OSError, BrokenPipeError):
                    pass

                # Store connection
                with self._lock:
                    self._connections[reg_id] = conn

                logger.info("Registered agent: %s (type=%s, addr=%s:%d)",
                            reg_id, reg_type, conn.getpeername()[0], conn.getpeername()[1])
                return

        # Unknown message from unregistered client
        logger.info("Unregistered client %s sent: %s", device_id[:20], text[:100])
        if conn is not None:
            try:
                conn.sendall(b"INFO: unregistered client. Send 'REGISTER:<details>' first.\n")
            except (OSError, BrokenPipeError):
                pass

    # ── Stale-Agent Cleanup ────────────────────────────────────────────────

    def _stale_cleanup_loop(self) -> None:
        """Periodically check for stale agents and remove them."""
        while self._running:
            time.sleep(self._stale_check_interval)
            try:
                removed = self._registry.remove_stale()
                if removed:
                    logger.info("Cleaned up %d stale agent(s): %s",
                                len(removed), ", ".join(removed[:5]))
                    # Also close their socket connections
                    with self._lock:
                        for dev_id in removed:
                            conn = self._connections.pop(dev_id, None)
                            if conn:
                                try:
                                    conn.close()
                                except OSError:
                                    pass
            except Exception:
                logger.exception("Error during stale-agent cleanup")

    # ── Accessors ──────────────────────────────────────────────────────────

    @property
    def registry(self) -> SessionRegistry:
        """Access the session registry for monitoring/debugging."""
        return self._registry

    @property
    def port(self) -> int:
        return self._port


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Raamses Gateway Server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8765, help="TCP port (default: 8765)")
    parser.add_argument("--timeout", type=int, default=90, help="Heartbeat timeout in seconds (default: 90)")
    parser.add_argument("--lora", action="store_true", help="Enable LoRa bridge (Meshtastic radio)")
    parser.add_argument("--lora-serial", default=None, help="LoRa serial port (e.g. /dev/ttyUSB0)")
    parser.add_argument("--lora-tcp", default=None, help="LoRa TCP host (e.g. 192.168.1.100)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s %(message)s",
        datefmt="%H:%M:%S",
    )

    server = GatewayServer(
        host=args.host, port=args.port, heartbeat_timeout=args.timeout,
        enable_lora=args.lora, lora_serial_port=args.lora_serial,
        lora_tcp_host=args.lora_tcp,
    )
    print(f"[Gateway] Listening on {args.host}:{args.port}", flush=True)
    if args.lora:
        print(f"[Gateway] LoRa bridge enabled (serial={args.lora_serial}, tcp={args.lora_tcp})", flush=True)
    try:
        server.start()
    except KeyboardInterrupt:
        print("\n[Gateway] Shutting down...", flush=True)
