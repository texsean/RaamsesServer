"""Tests for the LoRa bridge — mock mode (no radio required)."""

import sys
import os
import time
import logging
import pytest

# Ensure src/linux is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "linux"))

from rgs.lora.bridge import LoRaBridge
from rgs.lora.protocol import (
    Cmd, DeviceType, HeartbeatStatus,
    encode_register, encode_heartbeat, encode_alert, encode_clear,
    encode_ack, parse_packet,
)
from rgs.server.session_registry import SessionRegistry

logging.basicConfig(level=logging.INFO)


@pytest.fixture
def registry():
    return SessionRegistry()


@pytest.fixture
def bridge(registry):
    """Create a LoRa bridge in mock mode (no radio connected)."""
    b = LoRaBridge(registry=registry)
    # Don't call start() — just set mock mode manually
    b._mock_mode = True
    return b


class TestBridgeMockMode:
    def test_mock_mode_property(self, bridge):
        assert bridge.is_mock_mode is True
        assert bridge.is_connected is False

    def test_broadcast_alert_returns_seq(self, bridge):
        seq1 = bridge.broadcast_alert()
        seq2 = bridge.broadcast_alert()
        assert seq2 == seq1 + 1

    def test_broadcast_clear(self, bridge):
        seq = bridge.broadcast_alert()
        bridge.broadcast_clear(seq)  # should not raise

    def test_send_buzz(self, bridge):
        bridge.send_buzz(3)  # should not raise

    def test_alert_count_increments(self, bridge):
        bridge.broadcast_alert()
        bridge.broadcast_alert()
        assert bridge.alert_count == 2


class TestBridgePacketHandling:
    def test_handle_register(self, bridge, registry):
        """Simulate a REGISTER packet from a LoRa node."""
        pkt = encode_register(
            node_id=12345,
            device_type=DeviceType.HELTEC_V3,
            firmware_version=0x0102,
        )
        parsed = parse_packet(pkt)
        bridge._handle_packet(parsed, from_node=12345)

        session = registry.get("lora-12345")
        assert session is not None
        assert session.transport == "lora"
        assert session.node_id == 12345
        assert session.device_type == "heltec_v3"
        assert session.firmware_version == "1.2"

    def test_handle_heartbeat_existing(self, bridge, registry):
        """Heartbeat updates an existing LoRa session."""
        # First register
        reg_pkt = encode_register(12345, DeviceType.HELTEC_V3, 0x0100)
        bridge._handle_packet(parse_packet(reg_pkt), from_node=12345)

        # Then heartbeat
        hb_pkt = encode_heartbeat(12345, HeartbeatStatus.OK)
        bridge._handle_packet(parse_packet(hb_pkt), from_node=12345)

        session = registry.get("lora-12345")
        assert session is not None
        assert session.last_heartbeat is not None

    def test_handle_heartbeat_auto_register(self, bridge, registry):
        """Heartbeat auto-registers an unknown LoRa node."""
        hb_pkt = encode_heartbeat(99999, HeartbeatStatus.LORA_ONLY_MODE)
        bridge._handle_packet(parse_packet(hb_pkt), from_node=99999)

        session = registry.get("lora-99999")
        assert session is not None
        assert session.transport == "lora"
        assert session.node_id == 99999

    def test_handle_ack(self, bridge, registry):
        """ACK from a node is handled without error."""
        ack_pkt = encode_ack(pager_id=3)
        bridge._handle_packet(parse_packet(ack_pkt), from_node=42)

    def test_known_nodes_tracking(self, bridge, registry):
        """Bridge tracks which node IDs have communicated."""
        reg_pkt = encode_register(111, DeviceType.HELTEC_V3, 0x0100)
        bridge._handle_packet(parse_packet(reg_pkt), from_node=111)

        hb_pkt = encode_heartbeat(222, HeartbeatStatus.OK)
        bridge._handle_packet(parse_packet(hb_pkt), from_node=222)

        assert 111 in bridge.known_nodes
        assert 222 in bridge.known_nodes


class TestRegistryTransportFields:
    def test_wifi_transport_default(self, registry):
        registry.register("wifi-001", "cyd", "1.0")
        session = registry.get("wifi-001")
        assert session.transport == "wifi"
        assert session.node_id is None

    def test_lora_transport(self, registry):
        registry.register("lora-123", "heltec_v3", "1.0",
                          transport="lora", node_id=123)
        session = registry.get("lora-123")
        assert session.transport == "lora"
        assert session.node_id == 123

    def test_lora_relay_transport(self, registry):
        registry.register("relay-456", "heltec_v3", "1.0",
                          transport="lora_relay", node_id=456)
        session = registry.get("relay-456")
        assert session.transport == "lora_relay"

    def test_list_by_transport(self, registry):
        registry.register("wifi-1", "cyd", "1.0")
        registry.register("lora-1", "heltec_v3", "1.0", transport="lora", node_id=1)
        registry.register("lora-2", "heltec_v4", "1.0", transport="lora", node_id=2)

        wifi = registry.list_by_transport("wifi")
        lora = registry.list_by_transport("lora")
        assert len(wifi) == 1
        assert len(lora) == 2

    def test_get_by_node_id(self, registry):
        registry.register("lora-42", "heltec_v3", "1.0", transport="lora", node_id=42)
        session = registry.get_by_node_id(42)
        assert session is not None
        assert session.device_id == "lora-42"

    def test_get_by_node_id_not_found(self, registry):
        assert registry.get_by_node_id(999) is None


class TestRegistryAlertTracking:
    def test_set_alert(self, registry):
        registry.register("agent-1", "cyd", "1.0")
        assert registry.set_alert("agent-1", seq=5) is True
        session = registry.get("agent-1")
        assert session.alert_active is True
        assert session.alert_seq == 5

    def test_clear_alert(self, registry):
        registry.register("agent-1", "cyd", "1.0")
        registry.set_alert("agent-1", seq=5)
        assert registry.clear_alert("agent-1") is True
        session = registry.get("agent-1")
        assert session.alert_active is False

    def test_get_alert_state(self, registry):
        registry.register("agent-1", "cyd", "1.0")
        assert registry.get_alert_state("agent-1") is False
        registry.set_alert("agent-1", seq=1)
        assert registry.get_alert_state("agent-1") is True
        registry.clear_alert("agent-1")
        assert registry.get_alert_state("agent-1") is False

    def test_set_alert_unknown_agent(self, registry):
        assert registry.set_alert("unknown", seq=1) is False

    def test_clear_alert_unknown_agent(self, registry):
        assert registry.clear_alert("unknown") is False

    def test_get_alert_state_unknown_agent(self, registry):
        assert registry.get_alert_state("unknown") is None

    def test_list_alerted(self, registry):
        registry.register("agent-1", "cyd", "1.0")
        registry.register("agent-2", "cyd", "1.0")
        registry.register("agent-3", "cyd", "1.0")
        registry.set_alert("agent-1", seq=1)
        registry.set_alert("agent-3", seq=2)

        alerted = registry.list_alerted()
        assert len(alerted) == 2
        alerted_ids = {s.device_id for s in alerted}
        assert "agent-1" in alerted_ids
        assert "agent-3" in alerted_ids
        assert "agent-2" not in alerted_ids