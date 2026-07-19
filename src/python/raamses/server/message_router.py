"""Message router — classifies incoming messages and dispatches them correctly.

Two message types:
  1. Gateway communication → execute locally on the server
  2. Agent-targeted commands → route to the specified agent

For type 2: if the agent has moved on to a different task, the command is
dropped and logged. This is the configured behavior.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional, Callable

from raamses.server.session_registry import SessionRegistry

logger = logging.getLogger(__name__)

# Pattern to detect agent-targeted commands.
# Formats: /cmd <agent_id> <action>, /tell <agent_id> <message>, /ask <agent_id> <question>
# Also bare device_id lines like "agent: do something" or just "A B" (short form)
AGENT_TARGET_PATTERNS = [
    (re.compile(r"^/cmd\s+(\S+)\s+(.*)", re.IGNORECASE), 2),  # /cmd <agent_id> <action>
    (re.compile(r"^/tell\s+(\S+)\s+(.*)", re.IGNORECASE), 2),  # /tell <agent_id> <message>
    (re.compile(r"^/ask\s+(\S+)\s+(.*)", re.IGNORECASE), 2),   # /ask <agent_id> <question>
    (re.compile(r"^/pause\s+(\S+)", re.IGNORECASE), 1),         # /pause <agent_id>
    (re.compile(r"^/resume\s+(\S+)", re.IGNORECASE), 1),        # /resume <agent_id>
    (re.compile(r"^/stop\s+(\S+)", re.IGNORECASE), 1),          # /stop <agent_id>
    (re.compile(r"^/restart\s+(\S+)", re.IGNORECASE), 1),       # /restart <agent_id>
    (re.compile(r"^/approve\s+(\S+)", re.IGNORECASE), 1),       # /approve <agent_id>
    (re.compile(r"^/reject\s+(\S+)", re.IGNORECASE), 1),        # /reject <agent_id>
    (re.compile(r"^/ack\s+(\S+)", re.IGNORECASE), 1),           # /ack <alert_id>
]

# Gateway-local commands that execute on the server itself
GATEWAY_COMMANDS = {
    "register", "registerack", "heartbeat", "status", "quit", "exit",
    "agents", "list", "help", "about", "connect", "disconnect",
    "mock", "clear", "cls", "reset", "ping",
}

# Agent-update messages (not commands, but device-initiated)
AGENT_UPDATE_PATTERNS = re.compile(
    r"^(update|task|progress|done|error|alert)\s+(.*)",
    re.IGNORECASE,
)


class MessageRouter:
    """Classifies and routes incoming messages to the correct handler.

    Parameters:
        registry: SessionRegistry to look up agent sessions
        execute_gateway: Callable that executes gateway-local commands
        deliver_to_agent: Callable that delivers a command to an agent's connection
    """

    def __init__(
        self,
        registry: SessionRegistry,
        execute_gateway: Callable[[str], str],
        deliver_to_agent: Callable[[str, object, str], dict],
    ) -> None:
        self._registry = registry
        self._execute_gateway = execute_gateway
        self._deliver_to_agent = deliver_to_agent

    def classify(self, raw_input: str) -> tuple[str, Optional[str], Optional[str]]:
        """Classify an incoming message.

        Returns:
            (type, target_id, payload)
            - type: "gateway" | "agent_command" | "agent_update"
            - target_id: device_id if agent-targeted, else None
            - payload: the command/action text
        """
        text = raw_input.strip()
        if not text:
            return ("gateway", None, "")

        # Check for agent-targeted slash commands
        for pattern, group_count in AGENT_TARGET_PATTERNS:
            m = pattern.match(text)
            if m:
                target_id = m.group(1)
                payload = m.group(group_count).strip() if group_count > 1 and m.lastindex and m.lastindex >= group_count else ""
                return ("agent_command", target_id, payload)

        # Check for gateway-local commands
        first_word = text.split()[0].lower() if text.split() else text
        if first_word in GATEWAY_COMMANDS:
            return ("gateway", None, text)

        # Check for agent-update style messages (device-initiated status reports)
        m = AGENT_UPDATE_PATTERNS.match(text)
        if m:
            return ("agent_update", None, text)

        # Default: if it starts with "/" it's a gateway command (unknown or not yet implemented)
        if text.startswith("/"):
            return ("gateway", None, text)

        # Unknown — treat as gateway passthrough
        return ("gateway", None, text)

    def route(self, raw_input: str) -> dict:
        """Full route: classify, dispatch, and return the result.

        Returns:
            dict with keys:
              - type: classification result
              - status: "delivered" | "dropped" | "executed"
              - message: human-readable result description
              - target: target device_id if agent-targeted, else None
        """
        msg_type, target_id, payload = self.classify(raw_input)

        if msg_type == "gateway":
            result = self._execute_gateway(raw_input)
            return {
                "type": "gateway",
                "status": "executed",
                "message": result or "Command executed",
                "target": None,
            }

        if msg_type == "agent_command" and target_id:
            return self._route_to_agent(target_id, raw_input)

        if msg_type == "agent_update":
            # Agent is reporting status — try to find its session
            # The update message might be from a known agent's connection
            # or might need device_id extraction
            return {
                "type": "agent_update",
                "status": "executed",
                "message": f"Agent update received: {payload[:80]}",
                "target": None,
            }

        return {
            "type": "gateway",
            "status": "executed",
            "message": f"Gateway passthrough: {raw_input[:80]}",
            "target": None,
        }

    def _route_to_agent(self, target_id: str, raw_command: str) -> dict:
        """Route a command to a specific agent.

        If the agent exists and is active, deliver the command.
        If the agent has moved on or is offline, drop and log.
        """
        session = self._registry.get(target_id)

        if session is None:
            # Agent not registered at all
            msg = f"Agent {target_id} not registered — dropped"
            logger.warning("DROPPED: %s — agent not registered", raw_command)
            return {
                "type": "agent_command",
                "status": "dropped",
                "message": msg,
                "target": target_id,
            }

        if session.status == "offline":
            msg = f"Agent {target_id} is offline — dropped"
            logger.warning("DROPPED: %s — agent %s offline", raw_command, target_id)
            return {
                "type": "agent_command",
                "status": "dropped",
                "message": msg,
                "target": target_id,
            }

        if session.status == "paused":
            msg = f"Agent {target_id} is paused — command dropped"
            logger.warning("DROPPED: %s — agent %s paused", raw_command, target_id)
            return {
                "type": "agent_command",
                "status": "dropped",
                "message": msg,
                "target": target_id,
            }

        # Agent is active — deliver the command
        result = self._deliver_to_agent(target_id, session, raw_command)
        delivered = bool(result and result.get("success"))

        if delivered:
            latest_task = session.current_task or "(none)"
            logger.info("DELIVERED: %s to agent %s (task: %s)",
                        raw_command, target_id, latest_task)
            return {
                "type": "agent_command",
                "status": "delivered",
                "message": f"Command sent to {target_id} (current task: {latest_task})",
                "target": target_id,
                "result": result,
            }

        # Agent is active but we couldn't deliver — likely the connection is gone
        # Agent has moved on / lost connection
        latest_task = session.current_task or "(none)"
        msg = f"Agent {target_id} has moved on (latest: {latest_task})"
        logger.warning("DROPPED: %s — agent %s has moved on to: %s",
                       raw_command, target_id, latest_task)
        return {
            "type": "agent_command",
            "status": "dropped",
            "message": msg,
            "target": target_id,
        }
