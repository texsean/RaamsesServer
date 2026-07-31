"""Raamses Agent Bus — lightweight HTTP message bus for agent-to-agent comms.

Separate from the RGS gateway (port 8765). This runs on port 8787 and lets
agents register, send messages to each other, poll inboxes, and acknowledge
receipt. Uses only Python stdlib — no FastAPI, no deps.

Endpoints:
    POST /register         Agent check-in {name, role, ...}
    POST /send             Send a message {from, to, text, type}
    GET  /inbox/<name>      Poll unread messages for an agent
    POST /ack/<id>          Acknowledge (mark read) a message
    GET  /agents            List all registered/online agents
    GET  /history           Recent message log (debug)

All interactions are logged to logs/ with timestamps for historical records.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("agentbus")

# ── Data models ─────────────────────────────────────────────────────────

class Agent:
    """A registered agent on the bus."""
    def __init__(self, name: str, role: str = "agent", metadata: dict | None = None):
        self.name = name
        self.role = role
        self.metadata = metadata or {}
        self.registered_at = datetime.now(timezone.utc)
        self.last_seen = self.registered_at
        self.online = True

    def touch(self):
        self.last_seen = datetime.now(timezone.utc)
        self.online = True

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "role": self.role,
            "metadata": self.metadata,
            "registered_at": self.registered_at.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "online": self.online,
        }


class Message:
    """A message between agents."""
    def __init__(self, frm: str, to: str, text: str, msg_type: str = "text"):
        self.id = uuid.uuid4().hex[:12]
        self.frm = frm
        self.to = to
        self.text = text
        self.type = msg_type  # text, command, status, alert
        self.timestamp = datetime.now(timezone.utc)
        self.acked = False
        self.acked_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "from": self.frm,
            "to": self.to,
            "text": self.text,
            "type": self.type,
            "timestamp": self.timestamp.isoformat(),
            "acked": self.acked,
        }
        if self.acked_at:
            d["acked_at"] = self.acked_at.isoformat()
        return d


# ── Bus server ──────────────────────────────────────────────────────────

class AgentBus:
    """HTTP server for agent-to-agent messaging.

    Args:
        host: Bind address (default 0.0.0.0)
        port: Listen port (default 8787)
        log_dir: Directory for timestamped log files (default logs/ next to this file)
        agent_timeout: Seconds before an agent is marked offline (default 120)
        history_size: Max messages kept in history deque (default 500)
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8787,
        log_dir: Optional[str] = None,
        agent_timeout: int = 120,
        history_size: int = 500,
    ):
        self.host = host
        self.port = port
        self.agent_timeout = agent_timeout

        # Log directory — default to logs/ next to this file
        if log_dir is None:
            log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)

        # In-memory stores (protected by lock)
        self._lock = threading.Lock()
        self._agents: dict[str, Agent] = {}       # name -> Agent
        self._messages: dict[str, list[Message]] = {}  # agent name -> inbox
        self._all_messages: deque[Message] = deque(maxlen=history_size)
        self._msg_index: dict[str, Message] = {}   # id -> Message for ack lookup

        # Start the log file for this session
        self._log_file = self._open_log_file()
        self._log_lock = threading.Lock()

        self._sock: Optional[socket.socket] = None
        self._running = False
        self._prune_thread: Optional[threading.Thread] = None

    # ── Logging ─────────────────────────────────────────────────────────

    def _open_log_file(self) -> str:
        """Open a new timestamped log file for this session."""
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        filename = f"agentbus_{ts}.log"
        path = os.path.join(self.log_dir, filename)
        # Touch it
        with open(path, "w") as f:
            f.write(f"# Agent Bus log — started {datetime.now(timezone.utc).isoformat()}\n")
        logger.info("Log file: %s", path)
        return path

    def _log_event(self, event: str, data: dict | None = None) -> None:
        """Write a timestamped event to the log file."""
        ts = datetime.now(timezone.utc).isoformat()
        entry = {"timestamp": ts, "event": event}
        if data:
            entry["data"] = data
        line = json.dumps(entry, default=str)
        with self._log_lock:
            try:
                with open(self._log_file, "a") as f:
                    f.write(line + "\n")
            except Exception as e:
                logger.error("Failed to write log: %s", e)
        # Also log to the logger
        logger.info("%s | %s", event, data or "")

    # ── Agent management ─────────────────────────────────────────────────

    def register_agent(self, name: str, role: str = "agent", metadata: dict | None = None) -> Agent:
        """Register or re-register an agent."""
        with self._lock:
            if name in self._agents:
                agent = self._agents[name]
                agent.touch()
                if role:
                    agent.role = role
                if metadata:
                    agent.metadata.update(metadata)
            else:
                agent = Agent(name=name, role=role, metadata=metadata)
                self._agents[name] = agent
                self._messages.setdefault(name, [])
        self._log_event("register", {"name": name, "role": role, "metadata": metadata})
        return agent

    def get_agent(self, name: str) -> Optional[Agent]:
        with self._lock:
            return self._agents.get(name)

    def list_agents(self) -> list[dict]:
        with self._lock:
            self._prune_stale()
            return [a.to_dict() for a in self._agents.values()]

    def _prune_stale(self) -> None:
        """Mark agents offline if they haven't been seen recently. Call with lock."""
        now = datetime.now(timezone.utc)
        for agent in self._agents.values():
            if agent.online:
                age = (now - agent.last_seen).total_seconds()
                if age > self.agent_timeout:
                    agent.online = False

    # ── Messaging ───────────────────────────────────────────────────────

    def send_message(self, frm: str, to: str, text: str, msg_type: str = "text") -> Message:
        """Send a message from one agent to another."""
        msg = Message(frm=frm, to=to, text=text, msg_type=msg_type)
        with self._lock:
            # Store in recipient's inbox
            if to not in self._messages:
                self._messages[to] = []
            self._messages[to].append(msg)
            self._all_messages.append(msg)
            self._msg_index[msg.id] = msg
        self._log_event("send", msg.to_dict())
        return msg

    def get_inbox(self, name: str, unread_only: bool = True) -> list[dict]:
        """Get messages for an agent. Mark agent as seen."""
        with self._lock:
            if name in self._agents:
                self._agents[name].touch()
            inbox = self._messages.get(name, [])
            if unread_only:
                msgs = [m.to_dict() for m in inbox if not m.acked]
            else:
                msgs = [m.to_dict() for m in inbox]
        self._log_event("inbox_poll", {"agent": name, "count": len(msgs)})
        return msgs

    def ack_message(self, msg_id: str) -> bool:
        """Acknowledge a message by ID."""
        with self._lock:
            msg = self._msg_index.get(msg_id)
            if msg is None:
                return False
            msg.acked = True
            msg.acked_at = datetime.now(timezone.utc)
        self._log_event("ack", {"id": msg_id, "from": msg.frm, "to": msg.to})
        return True

    def get_history(self, limit: int = 50) -> list[dict]:
        with self._lock:
            msgs = list(self._all_messages)[-limit:]
        return [m.to_dict() for m in reversed(msgs)]

    # ── HTTP handling ────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the bus server (blocking)."""
        self._running = True
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.listen(32)
        logger.info("Agent Bus listening on %s:%d", self.host, self.port)
        self._log_event("bus_start", {"host": self.host, "port": self.port})
        print(f"Agent Bus listening on {self.host}:{self.port}", flush=True)

        # Start prune thread
        self._prune_thread = threading.Thread(target=self._prune_loop, daemon=True)
        self._prune_thread.start()

        try:
            while self._running:
                try:
                    conn, addr = self._sock.accept()
                    t = threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True)
                    t.start()
                except OSError:
                    break
        except KeyboardInterrupt:
            logger.info("Shutting down agent bus...")
        finally:
            self._running = False
            if self._sock:
                self._sock.close()
            self._log_event("bus_stop", {})

    def _prune_loop(self) -> None:
        """Background thread to mark stale agents offline."""
        while self._running:
            time.sleep(15)
            with self._lock:
                self._prune_stale()

    def _handle_client(self, conn: socket.socket, addr: tuple) -> None:
        """Handle a single HTTP connection."""
        try:
            conn.settimeout(10)
            buf = b""
            while b"\r\n\r\n" not in buf:
                chunk = conn.recv(4096)
                if not chunk:
                    return
                buf += chunk
                if len(buf) > 65536:
                    return

            header_part, _, body_part = buf.partition(b"\r\n\r\n")
            header_text = header_part.decode("utf-8", errors="replace")
            lines = header_text.split("\r\n")
            request_line = lines[0] if lines else ""
            parts = request_line.split(" ")
            method = parts[0].upper() if len(parts) > 0 else "GET"
            path = parts[1] if len(parts) > 1 else "/"

            # Parse Content-Length to get full body
            content_length = 0
            for line in lines[1:]:
                if line.lower().startswith("content-length:"):
                    try:
                        content_length = int(line.split(":", 1)[1].strip())
                    except ValueError:
                        pass
                    break

            body = body_part
            while len(body) < content_length:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                body += chunk
            body_str = body.decode("utf-8", errors="replace")[:content_length] if content_length else ""

            # Route the request
            self._route(conn, addr, method, path, body_str)
        except Exception as e:
            logger.error("Error handling client %s: %s", addr, e)
            self._log_event("error", {"addr": str(addr), "error": str(e)})
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _route(self, conn: socket.socket, addr: tuple, method: str, path: str, body: str) -> None:
        """Route an HTTP request to the appropriate handler."""
        # Clean path (strip query string)
        path_clean = path.split("?")[0]

        if method == "POST" and path_clean == "/register":
            self._handle_register(conn, addr, body)
        elif method == "POST" and path_clean == "/send":
            self._handle_send(conn, addr, body)
        elif method == "GET" and path_clean.startswith("/inbox/"):
            agent_name = path_clean[len("/inbox/"):]
            self._handle_inbox(conn, addr, agent_name)
        elif method == "POST" and path_clean.startswith("/ack/"):
            msg_id = path_clean[len("/ack/"):]
            self._handle_ack(conn, addr, msg_id)
        elif method == "GET" and path_clean == "/agents":
            self._handle_agents(conn, addr)
        elif method == "GET" and path_clean == "/history":
            self._handle_history(conn, addr)
        elif method == "GET" and path_clean == "/":
            self._send_response(conn, 200, "OK",
                "Raamses Agent Bus — POST /register, POST /send, "
                "GET /inbox/<name>, POST /ack/<id>, GET /agents, GET /history")
        else:
            self._send_response(conn, 404, "Not Found",
                json.dumps({"error": f"unknown endpoint: {method} {path_clean}"}),
                content_type="application/json")

    # ── Endpoint handlers ───────────────────────────────────────────────

    def _handle_register(self, conn: socket.socket, addr: tuple, body: str) -> None:
        try:
            data = json.loads(body) if body else {}
        except (json.JSONDecodeError, ValueError) as e:
            self._send_response(conn, 400, "Bad Request",
                json.dumps({"error": f"invalid JSON: {e}"}),
                content_type="application/json")
            return

        name = data.get("name", "").strip()
        if not name:
            self._send_response(conn, 400, "Bad Request",
                json.dumps({"error": "name is required"}),
                content_type="application/json")
            return

        role = data.get("role", "agent")
        metadata = data.get("metadata", {})

        agent = self.register_agent(name, role, metadata)
        resp = {
            "status": "registered",
            "name": agent.name,
            "role": agent.role,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._send_response(conn, 200, "OK",
            json.dumps(resp), content_type="application/json")

    def _handle_send(self, conn: socket.socket, addr: tuple, body: str) -> None:
        try:
            data = json.loads(body) if body else {}
        except (json.JSONDecodeError, ValueError) as e:
            self._send_response(conn, 400, "Bad Request",
                json.dumps({"error": f"invalid JSON: {e}"}),
                content_type="application/json")
            return

        frm = data.get("from", "").strip()
        to = data.get("to", "").strip()
        text = data.get("text", "").strip()
        msg_type = data.get("type", "text")

        if not frm or not to or not text:
            self._send_response(conn, 400, "Bad Request",
                json.dumps({"error": "from, to, and text are required"}),
                content_type="application/json")
            return

        msg = self.send_message(frm, to, text, msg_type)
        self._send_response(conn, 200, "OK",
            json.dumps({"status": "sent", "message_id": msg.id,
                        "timestamp": msg.timestamp.isoformat()}),
            content_type="application/json")

    def _handle_inbox(self, conn: socket.socket, addr: tuple, agent_name: str) -> None:
        if not agent_name:
            self._send_response(conn, 400, "Bad Request",
                json.dumps({"error": "agent name required"}),
                content_type="application/json")
            return

        msgs = self.get_inbox(agent_name, unread_only=True)
        self._send_response(conn, 200, "OK",
            json.dumps({"agent": agent_name, "count": len(msgs), "messages": msgs}),
            content_type="application/json")

    def _handle_ack(self, conn: socket.socket, addr: tuple, msg_id: str) -> None:
        if not msg_id:
            self._send_response(conn, 400, "Bad Request",
                json.dumps({"error": "message id required"}),
                content_type="application/json")
            return

        ok = self.ack_message(msg_id)
        if ok:
            self._send_response(conn, 200, "OK",
                json.dumps({"status": "acked", "id": msg_id}),
                content_type="application/json")
        else:
            self._send_response(conn, 404, "Not Found",
                json.dumps({"error": f"message {msg_id} not found"}),
                content_type="application/json")

    def _handle_agents(self, conn: socket.socket, addr: tuple) -> None:
        agents = self.list_agents()
        self._send_response(conn, 200, "OK",
            json.dumps({"count": len(agents), "agents": agents}),
            content_type="application/json")

    def _handle_history(self, conn: socket.socket, addr: tuple) -> None:
        history = self.get_history()
        self._send_response(conn, 200, "OK",
            json.dumps({"count": len(history), "messages": history}),
            content_type="application/json")

    # ── HTTP helpers ─────────────────────────────────────────────────────

    def _send_response(self, conn: socket.socket, code: int, status: str,
                        body: str, content_type: str = "text/plain") -> None:
        payload = body.encode("utf-8") if isinstance(body, str) else body
        header = (
            f"HTTP/1.1 {code} {status}\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {len(payload)}\r\n"
            f"Access-Control-Allow-Origin: *\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        )
        try:
            conn.sendall(header.encode("utf-8") + payload)
        except Exception as e:
            logger.error("Failed to send response: %s", e)


# ── CLI entry point ──────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Raamses Agent Bus — inter-agent messaging")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address (default 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8787, help="Listen port (default 8787)")
    parser.add_argument("--log-dir", default=None, help="Log directory (default: logs/ next to server.py)")
    parser.add_argument("--timeout", type=int, default=120, help="Agent offline timeout in seconds (default 120)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    bus = AgentBus(
        host=args.host,
        port=args.port,
        log_dir=args.log_dir,
        agent_timeout=args.timeout,
    )
    bus.start()


if __name__ == "__main__":
    main()