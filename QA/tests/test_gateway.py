"""Tests for the gateway message router and session registry."""

import pytest
from raamses.server.session_registry import SessionRegistry, AgentSession
from raamses.server.message_router import MessageRouter


# ── Session Registry Tests ─────────────────────────────────────────────────

class TestSessionRegistry:
    def test_register_new_agent(self):
        reg = SessionRegistry()
        session = reg.register("dev-001", "terminal", "1.0", "v2.1")
        assert session.device_id == "dev-001"
        assert session.device_type == "terminal"
        assert session.schema_version == "1.0"
        assert session.firmware_version == "v2.1"
        assert session.status == "active"
        assert reg.count() == 1

    def test_re_register_updates_session(self):
        reg = SessionRegistry()
        s1 = reg.register("dev-001", "terminal", "1.0")
        s2 = reg.register("dev-001", "android", "1.1")
        assert s2.device_type == "android"
        assert s2.schema_version == "1.1"
        assert s1 is s2  # same object

    def test_unregister(self):
        reg = SessionRegistry()
        reg.register("dev-001", "terminal", "1.0")
        removed = reg.unregister("dev-001")
        assert removed is not None
        assert removed.device_id == "dev-001"
        assert reg.count() == 0

    def test_unregister_unknown(self):
        reg = SessionRegistry()
        removed = reg.unregister("dev-999")
        assert removed is None

    def test_heartbeat(self):
        reg = SessionRegistry()
        reg.register("dev-001", "terminal", "1.0")
        assert reg.heartbeat("dev-001") is True
        assert reg.heartbeat("dev-999") is False

    def test_mark_task(self):
        reg = SessionRegistry()
        reg.register("dev-001", "terminal", "1.0")
        assert reg.mark_task("dev-001", "deploy service") is True
        session = reg.get("dev-001")
        assert session.current_task == "deploy service"

    def test_list_active(self):
        reg = SessionRegistry()
        reg.register("dev-001", "terminal", "1.0")
        reg.register("dev-002", "android", "1.0")
        reg.unregister("dev-002")
        active = reg.list_active()
        assert len(active) == 1
        assert active[0].device_id == "dev-001"


# ── Message Router Tests ───────────────────────────────────────────────────

def _make_router(registry):
    """Helper to create a router with mock handlers."""
    calls = []

    def execute_gateway(cmd):
        calls.append(("gateway", cmd))
        return f"executed: {cmd}"

    def deliver_to_agent(dev_id, session, cmd):
        calls.append(("agent", dev_id, cmd))
        return {"success": True}

    router = MessageRouter(registry, execute_gateway, deliver_to_agent)
    router._calls = calls  # expose for testing
    return router


class TestMessageRouter:
    def test_classify_gateway_command(self):
        reg = SessionRegistry()
        router = _make_router(reg)
        msg_type, target, payload = router.classify("status")
        assert msg_type == "gateway"
        assert target is None

    def test_classify_register(self):
        reg = SessionRegistry()
        router = _make_router(reg)
        msg_type, target, payload = router.classify("register")
        assert msg_type == "gateway"

    def test_classify_agent_cmd(self):
        reg = SessionRegistry()
        router = _make_router(reg)
        msg_type, target, payload = router.classify("/cmd dev-001 deploy service")
        assert msg_type == "agent_command"
        assert target == "dev-001"
        assert payload == "deploy service"

    def test_classify_agent_tell(self):
        reg = SessionRegistry()
        router = _make_router(reg)
        msg_type, target, payload = router.classify("/tell dev-001 hello")
        assert msg_type == "agent_command"
        assert target == "dev-001"
        assert payload == "hello"

    def test_classify_agent_pause(self):
        reg = SessionRegistry()
        router = _make_router(reg)
        msg_type, target, payload = router.classify("/pause dev-001")
        assert msg_type == "agent_command"
        assert target == "dev-001"
        assert payload == ""

    def test_classify_empty(self):
        reg = SessionRegistry()
        router = _make_router(reg)
        msg_type, target, payload = router.classify("")
        assert msg_type == "gateway"
        assert target is None
        assert payload == ""

    def test_route_gateway_command(self):
        reg = SessionRegistry()
        router = _make_router(reg)
        result = router.route("status")
        assert result["status"] == "executed"
        assert result["type"] == "gateway"

    def test_route_agent_command_existing_agent(self):
        reg = SessionRegistry()
        reg.register("dev-001", "terminal", "1.0")
        router = _make_router(reg)
        result = router.route("/cmd dev-001 deploy service")
        assert result["status"] == "delivered"
        assert result["type"] == "agent_command"
        assert result["target"] == "dev-001"

    def test_route_agent_command_unknown_agent(self):
        reg = SessionRegistry()
        router = _make_router(reg)
        result = router.route("/cmd dev-999 deploy service")
        assert result["status"] == "dropped"
        assert result["target"] == "dev-999"

    def test_route_agent_command_offline_agent(self):
        reg = SessionRegistry()
        reg.register("dev-001", "terminal", "1.0")
        session = reg.get("dev-001")
        session.status = "offline"
        router = _make_router(reg)
        result = router.route("/cmd dev-001 deploy")
        assert result["status"] == "dropped"

    def test_route_agent_command_paused_agent(self):
        reg = SessionRegistry()
        reg.register("dev-001", "terminal", "1.0")
        session = reg.get("dev-001")
        session.status = "paused"
        router = _make_router(reg)
        result = router.route("/pause dev-001")
        assert result["status"] == "dropped"

    def test_route_delivered_updates_calls(self):
        reg = SessionRegistry()
        reg.register("dev-001", "terminal", "1.0")
        router = _make_router(reg)
        router.route("/cmd dev-001 test")
        assert ("agent", "dev-001", "/cmd dev-001 test") in router._calls

    def test_route_gateway_updates_calls(self):
        reg = SessionRegistry()
        router = _make_router(reg)
        router.route("status")
        assert ("gateway", "status") in router._calls
