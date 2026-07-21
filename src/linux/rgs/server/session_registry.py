"""Agent session registry — tracks connected agents and their current tasks.

Each agent registers with a unique device_id (UUID). The gateway uses this
registry to route agent-targeted commands to the correct connection.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentSession:
    """Tracks the live state of a single registered agent."""
    device_id: str
    device_type: str
    schema_version: str
    firmware_version: Optional[str] = None
    capabilities: Optional[dict] = None
    connection: Optional[object] = None  # TCP/WS socket handle
    status: str = "active"              # active | paused | offline
    current_task: str = ""              # what the agent is currently working on
    task_assigned_at: Optional[datetime] = None
    last_heartbeat: Optional[datetime] = None
    registered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def mark_heartbeat(self) -> None:
        self.last_heartbeat = datetime.now(timezone.utc)

    def mark_task(self, task: str) -> None:
        self.current_task = task
        self.task_assigned_at = datetime.now(timezone.utc)

    def is_stale(self, timeout_seconds: int = 90) -> bool:
        """Return True if the agent hasn't sent a heartbeat within the timeout."""
        if self.last_heartbeat is None:
            return False  # never heartbeat'd — not stale yet
        elapsed = (datetime.now(timezone.utc) - self.last_heartbeat).total_seconds()
        return elapsed > timeout_seconds


class SessionRegistry:
    """Thread-safe registry of connected agents.

    All public methods are safe to call from multiple threads.
    """

    def __init__(self, heartbeat_timeout: int = 90):
        self._heartbeat_timeout = heartbeat_timeout
        self._sessions: dict[str, AgentSession] = {}
        self._conn_index: dict[int, str] = {}  # id(conn) -> device_id reverse index
        self._lock = threading.RLock()

    def register(self, device_id: str, device_type: str,
                 schema_version: str, firmware_version: Optional[str] = None,
                 capabilities: Optional[dict] = None,
                 connection: object = None) -> AgentSession:
        """Register or re-register an agent. Returns the session object.
        
        Optionally accepts a connection object for O(1) lookup by connection.
        """
        with self._lock:
            if device_id in self._sessions:
                session = self._sessions[device_id]
                session.device_type = device_type
                session.schema_version = schema_version
                session.firmware_version = firmware_version
                session.capabilities = capabilities
                session.status = "active"
                session.mark_heartbeat()
                logger.info("Re-register: %s (type=%s, schema=%s)",
                            device_id, device_type, schema_version)
            else:
                session = AgentSession(
                    device_id=device_id,
                    device_type=device_type,
                    schema_version=schema_version,
                    firmware_version=firmware_version,
                    capabilities=capabilities,
                )
                session.mark_heartbeat()
                self._sessions[device_id] = session
                logger.info("Registered: %s (type=%s, schema=%s)",
                            device_id, device_type, schema_version)

            # Update connection index if a connection was provided
            if connection is not None:
                conn_id = id(connection)
                # Remove old entry if re-registering
                if device_id in self._conn_index.values():
                    old_conn_id = [k for k, v in self._conn_index.items() if v == device_id]
                    for k in old_conn_id:
                        del self._conn_index[k]
                self._conn_index[conn_id] = device_id

            return session

    def unregister(self, device_id: str) -> Optional[AgentSession]:
        """Remove an agent from the registry. Returns the removed session."""
        with self._lock:
            session = self._sessions.pop(device_id, None)
            if session is not None:
                # Also remove from connection index
                stale_keys = [k for k, v in self._conn_index.items() if v == device_id]
                for k in stale_keys:
                    del self._conn_index[k]
            return session

    def get(self, device_id: str) -> Optional[AgentSession]:
        """Look up a session by device_id."""
        with self._lock:
            return self._sessions.get(device_id)

    def heartbeat(self, device_id: str) -> bool:
        """Record a heartbeat for an agent. Returns True if the agent is registered."""
        with self._lock:
            session = self._sessions.get(device_id)
            if session is not None:
                session.mark_heartbeat()
                return True
            return False

    def mark_task(self, device_id: str, task: str) -> bool:
        """Record what task an agent is currently working on."""
        with self._lock:
            session = self._sessions.get(device_id)
            if session is not None:
                session.mark_task(task)
                return True
            return False

    def list_active(self) -> list[AgentSession]:
        """Return all agents with status 'active' or 'paused'."""
        with self._lock:
            return [
                s for s in self._sessions.values()
                if s.status in ("active", "paused")
            ]

    def remove_stale(self) -> list[str]:
        """Remove agents whose heartbeats have timed out. Returns removed IDs."""
        stale = []
        with self._lock:
            for dev_id, session in list(self._sessions.items()):
                if session.status == "active" and session.is_stale(self._heartbeat_timeout):
                    stale.append(dev_id)
                    session.status = "offline"
                    logger.warning("Stale agent removed: %s (last heartbeat %s)",
                                   dev_id, session.last_heartbeat)
                    # Clean up connection index
                    stale_keys = [k for k, v in self._conn_index.items() if v == dev_id]
                    for k in stale_keys:
                        del self._conn_index[k]
        return stale

    def count(self) -> int:
        with self._lock:
            return len(self._sessions)

    def get_session_by_connection(self, conn) -> Optional[AgentSession]:
        """Look up a session by its TCP connection object (O(1) via reverse index)."""
        with self._lock:
            conn_id = id(conn)
            device_id = self._conn_index.get(conn_id)
            if device_id is not None:
                return self._sessions.get(device_id)
            # Fallback: O(n) scan for connections not in the index
            for session in self._sessions.values():
                if session.connection is conn:
                    return session
            return None
