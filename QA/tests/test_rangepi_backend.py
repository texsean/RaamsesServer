"""Tests for the RangePi LoRa backend — mock serial (no radio required)."""

import sys
import os
import time
import logging
import pytest
from unittest.mock import MagicMock, patch, call

# Ensure src/linux is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "linux"))

from rgs.lora.rangepi_backend import RangePiBackend
from rgs.lora.protocol import (
    Cmd, DeviceType, HeartbeatStatus,
    encode_register, encode_heartbeat, encode_alert, encode_clear,
    encode_ack, encode_buzz, parse_packet,
)

logging.basicConfig(level=logging.INFO)


class TestRangePiBackendMock:
    """Test the RangePiBackend with a mocked serial port."""

    @pytest.fixture
    def received_packets(self):
        """List to collect received packets from the callback."""
        return []

    @pytest.fixture
    def backend(self, received_packets):
        """Create a RangePiBackend with mocked serial — don't actually open a port."""
        b = RangePiBackend(
            serial_port="/dev/null",  # won't actually open
            on_receive=received_packets.append,
        )
        # Inject a mock serial object instead of opening a real one
        b._serial = MagicMock()
        b._serial.is_open = True
        b._serial.in_waiting = 0
        return b

    def test_initial_defaults(self):
        """Backend has correct default values."""
        b = RangePiBackend()
        assert b._serial_port == "/dev/ttyACM0"
        assert b._baudrate == 115200
        assert b._node_id == 1
        assert b.is_connected is False  # no serial open

    def test_custom_port(self):
        """Backend accepts a custom serial port."""
        b = RangePiBackend(serial_port="/dev/ttyUSB1")
        assert b._serial_port == "/dev/ttyUSB1"

    def test_send_data(self, backend):
        """send_data writes to the serial port."""
        data = encode_alert(1, 42)
        result = backend.send_data(data)
        assert result is True
        backend._serial.write.assert_called_once_with(data)
        backend._serial.flush.assert_called_once()

    def test_send_data_no_serial(self):
        """send_data returns False when serial is not open."""
        b = RangePiBackend()
        result = b.send_data(b"test")
        assert result is False

    def test_send_data_write_error(self, backend):
        """send_data returns False on write exception."""
        backend._serial.write.side_effect = Exception("write failed")
        result = backend.send_data(b"test")
        assert result is False

    def test_is_connected(self, backend):
        """is_connected reflects serial state."""
        assert backend.is_connected is True
        backend._serial.is_open = False
        assert backend.is_connected is False

    def test_node_id(self, backend):
        assert backend.node_id == 1


class TestRangePiPacketParsing:
    """Test the internal packet parsing logic of RangePiBackend."""

    @pytest.fixture
    def received_packets(self):
        return []

    @pytest.fixture
    def backend(self, received_packets):
        b = RangePiBackend(on_receive=received_packets.append)
        # Don't start the reader thread — we'll call _try_parse manually
        return b

    def test_parse_single_packet(self, backend, received_packets):
        """A complete packet in the buffer is parsed and delivered."""
        pkt = encode_alert(3, 7)
        backend._rx_buffer.extend(pkt)
        backend._try_parse()

        assert len(received_packets) == 1
        assert received_packets[0] == pkt
        assert len(backend._rx_buffer) == 0

    def test_parse_multiple_packets(self, backend, received_packets):
        """Multiple packets in the buffer are all parsed."""
        pkt1 = encode_alert(1, 1)
        pkt2 = encode_heartbeat(42, HeartbeatStatus.OK)
        pkt3 = encode_ack(5)
        backend._rx_buffer.extend(pkt1 + pkt2 + pkt3)
        backend._try_parse()

        assert len(received_packets) == 3
        assert received_packets[0] == pkt1
        assert received_packets[1] == pkt2
        assert received_packets[2] == pkt3

    def test_parse_incomplete_packet(self, backend, received_packets):
        """An incomplete packet stays in the buffer."""
        pkt = encode_register(100, DeviceType.HELTEC_V3, 0x0100)
        # Only put the first 3 bytes (incomplete)
        backend._rx_buffer.extend(pkt[:3])
        backend._try_parse()

        assert len(received_packets) == 0
        assert len(backend._rx_buffer) == 3

    def test_parse_incomplete_then_complete(self, backend, received_packets):
        """An incomplete packet is completed by a later chunk."""
        pkt = encode_register(100, DeviceType.HELTEC_V3, 0x0100)
        backend._rx_buffer.extend(pkt[:3])
        backend._try_parse()
        assert len(received_packets) == 0

        # Add remaining bytes
        backend._rx_buffer.extend(pkt[3:])
        backend._try_parse()

        assert len(received_packets) == 1
        assert received_packets[0] == pkt

    def test_parse_malformed_packet(self, backend, received_packets):
        """A malformed packet (bad length) is dropped, parsing stops."""
        # cmd=0x01, len=99 but only 2 bytes of payload
        backend._rx_buffer.extend(bytes([0x01, 99, 0xAA, 0xBB]))
        backend._try_parse()

        # Should not deliver anything (incomplete — waiting for 99 bytes)
        assert len(received_packets) == 0
        # Buffer should still have the data (waiting for more)
        assert len(backend._rx_buffer) == 4

    def test_parse_empty_buffer(self, backend, received_packets):
        """An empty buffer is handled gracefully."""
        backend._try_parse()
        assert len(received_packets) == 0

    def test_parse_all_packet_types(self, backend, received_packets):
        """All Raamses packet types can be parsed."""
        packets = [
            encode_alert(1, 1),
            encode_ack(2),
            encode_clear(1, 1),
            encode_heartbeat(99, HeartbeatStatus.OK),
            encode_register(99, DeviceType.HELTEC_V3, 0x0100),
            encode_buzz(4),
        ]
        for pkt in packets:
            backend._rx_buffer.extend(pkt)
        backend._try_parse()

        assert len(received_packets) == len(packets)
        for i, original in enumerate(packets):
            assert received_packets[i] == original


class TestRangePiBridgeIntegration:
    """Test the LoRaBridge with the RangePi backend (mock mode)."""

    @pytest.fixture
    def registry(self):
        from rgs.server.session_registry import SessionRegistry
        return SessionRegistry()

    @pytest.fixture
    def bridge(self, registry):
        """Create a LoRa bridge with RangePi backend in mock mode."""
        from rgs.lora.bridge import LoRaBridge
        b = LoRaBridge(registry=registry, backend="rangepi")
        b._mock_mode = True
        return b

    def test_rangepi_backend_selected(self, bridge):
        """Bridge reports the RangePi backend."""
        assert bridge._backend_name == "rangepi"

    def test_mock_broadcast_alert(self, bridge):
        """Alert broadcast works in mock mode with RangePi backend."""
        seq = bridge.broadcast_alert()
        assert seq > 0

    def test_mock_broadcast_clear(self, bridge):
        """Clear broadcast works in mock mode with RangePi backend."""
        seq = bridge.broadcast_alert()
        bridge.broadcast_clear(seq)  # should not raise

    def test_mock_send_buzz(self, bridge):
        """Buzz command works in mock mode with RangePi backend."""
        bridge.send_buzz(2)  # should not raise

    def test_handle_register_rangepi(self, bridge, registry):
        """REGISTER packet from RangePi is handled correctly."""
        pkt = encode_register(
            node_id=1,  # RangePi node_id
            device_type=DeviceType.HELTEC_V3,
            firmware_version=0x0102,
        )
        parsed = parse_packet(pkt)
        bridge._handle_packet(parsed, from_node=1)

        session = registry.get("lora-1")
        assert session is not None
        assert session.transport == "lora"
        assert session.device_type == "heltec_v3"