"""Tests for the Raamses LoRa binary protocol module."""

import sys
import os
import struct
import pytest

# Ensure src/linux is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "linux"))

from rgs.lora.protocol import (
    Cmd, DeviceType, HeartbeatStatus,
    AlertPacket, AckPacket, ClearPacket, HeartbeatPacket,
    RegisterPacket, BuzzPacket, ParsedPacket,
    encode_alert, encode_clear, encode_heartbeat, encode_register,
    encode_ack, encode_buzz, encode_packet, parse_packet,
)


class TestCmdNames:
    def test_cmd_name_known(self):
        assert Cmd.name(0x01) == "ALERT"
        assert Cmd.name(0x02) == "ACK"
        assert Cmd.name(0x03) == "CLEAR"
        assert Cmd.name(0x04) == "HEARTBEAT"
        assert Cmd.name(0x05) == "REGISTER"
        assert Cmd.name(0x06) == "BUZZ"

    def test_cmd_name_unknown(self):
        assert Cmd.name(0xFF) == "UNKNOWN(0xff)"
        assert Cmd.name(0x00) == "UNKNOWN(0x00)"


class TestDeviceTypeNames:
    def test_known_types(self):
        assert DeviceType.name(0x01) == "heltec_v3"
        assert DeviceType.name(0x02) == "heltec_v4"
        assert DeviceType.name(0x03) == "thinknode_m2"

    def test_unknown_type(self):
        assert DeviceType.name(0xFF) == "unknown(0xff)"

    def test_code_from_name(self):
        assert DeviceType.code("heltec_v3") == 0x01
        assert DeviceType.code("heltec_v4") == 0x02
        assert DeviceType.code("thinknode_m2") == 0x03
        assert DeviceType.code("unknown") == 0x00


class TestHeartbeatStatus:
    def test_known_statuses(self):
        assert HeartbeatStatus.name(0x00) == "OK"
        assert HeartbeatStatus.name(0x01) == "WIFI_DISCONNECTED"
        assert HeartbeatStatus.name(0x02) == "GATEWAY_UNREACHABLE"
        assert HeartbeatStatus.name(0x03) == "LORA_ONLY_MODE"
        assert HeartbeatStatus.name(0xFF) == "ERROR"

    def test_unknown_status(self):
        assert HeartbeatStatus.name(0x42) == "UNKNOWN(0x42)"


class TestAlertPacket:
    def test_encode(self):
        pkt = encode_alert(alert_count=5, sequence=42)
        assert pkt[0] == Cmd.ALERT
        assert pkt[1] == 3  # payload length
        assert len(pkt) == 5

    def test_decode(self):
        pkt = encode_alert(alert_count=10, sequence=300)
        parsed = parse_packet(pkt)
        assert parsed is not None
        dec = parsed.decode()
        assert dec.alert_count == 10
        assert dec.sequence == 300

    def test_roundtrip_edge_values(self):
        for count in [0, 127, 255]:
            for seq in [0, 1, 255, 256, 65535]:
                pkt = encode_alert(count, seq)
                dec = parse_packet(pkt).decode()
                assert dec.alert_count == count & 0xFF
                assert dec.sequence == seq & 0xFFFF

    def test_decode_too_short(self):
        with pytest.raises(ValueError, match="too short"):
            AlertPacket.decode(b"\x05\x00")  # only 2 bytes, need 3


class TestClearPacket:
    def test_encode(self):
        pkt = encode_clear(alert_count=3, sequence=42)
        assert pkt[0] == Cmd.CLEAR
        assert pkt[1] == 3
        assert len(pkt) == 5

    def test_decode(self):
        pkt = encode_clear(alert_count=7, sequence=1000)
        parsed = parse_packet(pkt)
        dec = parsed.decode()
        assert dec.alert_count == 7
        assert dec.sequence == 1000

    def test_same_seq_as_alert(self):
        """CLEAR must carry the same sequence as the ALERT it resolves."""
        alert_pkt = encode_alert(alert_count=1, sequence=42)
        clear_pkt = encode_clear(alert_count=1, sequence=42)
        alert_seq = parse_packet(alert_pkt).decode().sequence
        clear_seq = parse_packet(clear_pkt).decode().sequence
        assert alert_seq == clear_seq


class TestHeartbeatPacket:
    def test_encode(self):
        pkt = encode_heartbeat(node_id=12345, status=HeartbeatStatus.OK)
        assert pkt[0] == Cmd.HEARTBEAT
        assert pkt[1] == 5  # 4 bytes node_id + 1 byte status
        assert len(pkt) == 7

    def test_decode(self):
        pkt = encode_heartbeat(node_id=999999, status=HeartbeatStatus.LORA_ONLY_MODE)
        parsed = parse_packet(pkt)
        dec = parsed.decode()
        assert dec.node_id == 999999
        assert dec.status == HeartbeatStatus.LORA_ONLY_MODE

    def test_all_status_values(self):
        for status in [0x00, 0x01, 0x02, 0x03, 0xFF]:
            pkt = encode_heartbeat(node_id=1, status=status)
            dec = parse_packet(pkt).decode()
            assert dec.status == status

    def test_decode_too_short(self):
        with pytest.raises(ValueError, match="too short"):
            HeartbeatPacket.decode(b"\x01\x02\x03")  # 3 bytes, need 5


class TestRegisterPacket:
    def test_encode(self):
        pkt = encode_register(node_id=999, device_type=DeviceType.HELTEC_V3,
                              firmware_version=0x0102)
        assert pkt[0] == Cmd.REGISTER
        assert pkt[1] == 7  # 4+1+2
        assert len(pkt) == 9

    def test_decode(self):
        pkt = encode_register(node_id=123456, device_type=DeviceType.HELTEC_V4,
                              firmware_version=0x0203)
        parsed = parse_packet(pkt)
        dec = parsed.decode()
        assert dec.node_id == 123456
        assert dec.device_type == DeviceType.HELTEC_V4
        assert dec.firmware_version == 0x0203
        assert dec.firmware_major == 2
        assert dec.firmware_minor == 3
        assert dec.firmware_string == "2.3"

    def test_decode_too_short(self):
        with pytest.raises(ValueError, match="too short"):
            RegisterPacket.decode(b"\x01" * 5)  # 5 bytes, need 7


class TestAckPacket:
    def test_encode(self):
        pkt = encode_ack(pager_id=5)
        assert pkt[0] == Cmd.ACK
        assert pkt[1] == 1
        assert len(pkt) == 3

    def test_decode(self):
        pkt = encode_ack(pager_id=254)
        dec = parse_packet(pkt).decode()
        assert dec.pager_id == 254

    def test_decode_too_short(self):
        with pytest.raises(ValueError, match="too short"):
            AckPacket.decode(b"")


class TestBuzzPacket:
    def test_encode(self):
        pkt = encode_buzz(duration_half_seconds=4)
        assert pkt[0] == Cmd.BUZZ
        assert pkt[1] == 1
        assert len(pkt) == 3

    def test_decode(self):
        pkt = encode_buzz(duration_half_seconds=10)
        dec = parse_packet(pkt).decode()
        assert dec.duration_half_seconds == 10


class TestParsePacket:
    def test_valid_packet(self):
        pkt = encode_alert(alert_count=1, sequence=1)
        parsed = parse_packet(pkt)
        assert parsed is not None
        assert parsed.cmd == Cmd.ALERT
        assert parsed.cmd_name == "ALERT"

    def test_empty_data(self):
        assert parse_packet(b"") is None

    def test_one_byte(self):
        assert parse_packet(b"\x01") is None

    def test_length_mismatch(self):
        # cmd=0x01, len=5, but only 1 byte of payload
        assert parse_packet(b"\x01\x05\x00") is None

    def test_zero_length_payload(self):
        pkt = encode_packet(Cmd.ACK, b"")
        parsed = parse_packet(pkt)
        assert parsed is not None
        assert parsed.cmd == Cmd.ACK
        assert len(parsed.payload) == 0

    def test_unknown_command(self):
        # cmd=0xFF, len=0
        pkt = b"\xFF\x00"
        parsed = parse_packet(pkt)
        assert parsed is not None
        assert parsed.cmd == 0xFF
        assert parsed.decode() is None  # no decoder for unknown cmd

    def test_decode_all_types(self):
        """All command types should decode successfully."""
        test_cases = [
            (encode_alert(1, 1), AlertPacket),
            (encode_clear(1, 1), ClearPacket),
            (encode_heartbeat(1, 0), HeartbeatPacket),
            (encode_register(1, DeviceType.HELTEC_V3, 0x0100), RegisterPacket),
            (encode_ack(1), AckPacket),
            (encode_buzz(1), BuzzPacket),
        ]
        for pkt, expected_class in test_cases:
            parsed = parse_packet(pkt)
            assert parsed is not None
            decoded = parsed.decode()
            assert isinstance(decoded, expected_class), \
                f"Expected {expected_class.__name__}, got {type(decoded).__name__}"


class TestSequenceAntiReplay:
    """Test the sequence number anti-replay logic described in the protocol."""

    def test_seq_monotonic(self):
        """Alert sequence should increment monotonically."""
        seqs = []
        for _ in range(5):
            pkt = encode_alert(alert_count=0, sequence=len(seqs) + 1)
            seqs.append(parse_packet(pkt).decode().sequence)
        assert seqs == [1, 2, 3, 4, 5]

    def test_clear_matches_alert_seq(self):
        """CLEAR must reference the same sequence as the ALERT."""
        alert_seq = 42
        alert_pkt = encode_alert(alert_count=1, sequence=alert_seq)
        clear_pkt = encode_clear(alert_count=1, sequence=alert_seq)
        assert parse_packet(alert_pkt).decode().sequence == \
               parse_packet(clear_pkt).decode().sequence

    def test_uint16_wraparound(self):
        """Sequence numbers should wrap at uint16 boundary."""
        pkt = encode_alert(alert_count=0, sequence=0xFFFF)
        dec = parse_packet(pkt).decode()
        assert dec.sequence == 65535