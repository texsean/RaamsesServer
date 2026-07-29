"""Raamses LoRa binary protocol — encode/decode for Meshtastic private channel.

Wire format per packet:
    [0]   cmd    uint8   Command code (see Cmd class)
    [1]   len    uint8   Payload length (0-255)
    [2:N] bytes         Payload (len bytes)

Total packet size: len + 2 bytes. Max payload 255 bytes, well within
Meshtastic's ~237-byte limit.

Commands (from docs/RAAMSES_LORA_PROTOCOL.md v1.1):
    0x01 ALERT     — Agent needs help (bridge → nodes)
    0x02 ACK        — Acknowledge receipt (node → bridge)
    0x03 CLEAR      — Alert resolved (bridge → nodes)
    0x04 HEARTBEAT  — Periodic keepalive (node → bridge, every 30s)
    0x05 REGISTER   — Device registration (node → bridge, on boot)
    0x06 BUZZ       — Test buzzer/LED (bridge → node)

Sequence numbers (uint16, little-endian, monotonic per alert event):
    ALERT carries seq=N, CLEAR references the same seq=N.
    Receivers reject ALERT with seq <= lastAlertSeq.
    Receivers ignore CLEAR with seq < lastAlertSeq.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Optional, Union


# ── Command codes ──────────────────────────────────────────────────────

class Cmd:
    """LoRa protocol command codes."""
    ALERT     = 0x01
    ACK       = 0x02
    CLEAR     = 0x03
    HEARTBEAT = 0x04
    REGISTER  = 0x05
    BUZZ      = 0x06

    # Names for logging
    _NAMES = {
        0x01: "ALERT",
        0x02: "ACK",
        0x03: "CLEAR",
        0x04: "HEARTBEAT",
        0x05: "REGISTER",
        0x06: "BUZZ",
    }

    @classmethod
    def name(cls, code: int) -> str:
        return cls._NAMES.get(code, f"UNKNOWN(0x{code:02x})")


# ── Device type codes ──────────────────────────────────────────────────

class DeviceType:
    """Device type codes for REGISTER command."""
    HELTEC_V3   = 0x01
    HELTEC_V4   = 0x02
    THINKNODE_M2 = 0x03

    _NAMES = {
        0x01: "heltec_v3",
        0x02: "heltec_v4",
        0x03: "thinknode_m2",
    }

    @classmethod
    def name(cls, code: int) -> str:
        return cls._NAMES.get(code, f"unknown(0x{code:02x})")

    @classmethod
    def code(cls, name: str) -> int:
        for code, n in cls._NAMES.items():
            if n == name:
                return code
        return 0x00  # unknown


# ── Heartbeat status values ───────────────────────────────────────────

class HeartbeatStatus:
    """Status byte values in HEARTBEAT payload."""
    OK                 = 0x00
    WIFI_DISCONNECTED  = 0x01
    GATEWAY_UNREACHABLE = 0x02
    LORA_ONLY_MODE     = 0x03
    ERROR              = 0xFF

    _NAMES = {
        0x00: "OK",
        0x01: "WIFI_DISCONNECTED",
        0x02: "GATEWAY_UNREACHABLE",
        0x03: "LORA_ONLY_MODE",
        0xFF: "ERROR",
    }

    @classmethod
    def name(cls, code: int) -> str:
        return cls._NAMES.get(code, f"UNKNOWN(0x{code:02x})")


# ── Packet structures ──────────────────────────────────────────────────

@dataclass
class AlertPacket:
    """ALERT (0x01) — bridge broadcasts when agent needs help."""
    alert_count: int   # rolling 0-255
    sequence: int      # uint16, monotonic per alert event

    def encode(self) -> bytes:
        return _encode(Cmd.ALERT, struct.pack("<BH", self.alert_count & 0xFF, self.sequence & 0xFFFF))

    @classmethod
    def decode(cls, payload: bytes) -> "AlertPacket":
        if len(payload) < 3:
            raise ValueError(f"ALERT payload too short: {len(payload)} (need 3)")
        count, seq = struct.unpack("<BH", payload[:3])
        return cls(alert_count=count, sequence=seq)


@dataclass
class AckPacket:
    """ACK (0x02) — console acknowledges ALERT receipt."""
    pager_id: int      # 0=bridge, 1-254=node

    def encode(self) -> bytes:
        return _encode(Cmd.ACK, struct.pack("<B", self.pager_id & 0xFF))

    @classmethod
    def decode(cls, payload: bytes) -> "AckPacket":
        if len(payload) < 1:
            raise ValueError(f"ACK payload too short: {len(payload)} (need 1)")
        return cls(pager_id=payload[0])


@dataclass
class ClearPacket:
    """CLEAR (0x03) — bridge broadcasts when alert is resolved."""
    alert_count: int
    sequence: int      # matches the ALERT being cleared

    def encode(self) -> bytes:
        return _encode(Cmd.CLEAR, struct.pack("<BH", self.alert_count & 0xFF, self.sequence & 0xFFFF))

    @classmethod
    def decode(cls, payload: bytes) -> "ClearPacket":
        if len(payload) < 3:
            raise ValueError(f"CLEAR payload too short: {len(payload)} (need 3)")
        count, seq = struct.unpack("<BH", payload[:3])
        return cls(alert_count=count, sequence=seq)


@dataclass
class HeartbeatPacket:
    """HEARTBEAT (0x04) — consoles send every 30 seconds."""
    node_id: int       # uint32, Meshtastic node number
    status: int        # HeartbeatStatus value

    def encode(self) -> bytes:
        return _encode(Cmd.HEARTBEAT, struct.pack("<IB", self.node_id & 0xFFFFFFFF, self.status & 0xFF))

    @classmethod
    def decode(cls, payload: bytes) -> "HeartbeatPacket":
        if len(payload) < 5:
            raise ValueError(f"HEARTBEAT payload too short: {len(payload)} (need 5)")
        node_id, status = struct.unpack("<IB", payload[:5])
        return cls(node_id=node_id, status=status)


@dataclass
class RegisterPacket:
    """REGISTER (0x05) — console sends on boot or WiFi fallback."""
    node_id: int          # uint32, Meshtastic node number
    device_type: int      # DeviceType code
    firmware_version: int # uint16, major=high byte, minor=low byte

    def encode(self) -> bytes:
        return _encode(Cmd.REGISTER,
                       struct.pack("<IBH",
                                   self.node_id & 0xFFFFFFFF,
                                   self.device_type & 0xFF,
                                   self.firmware_version & 0xFFFF))

    @classmethod
    def decode(cls, payload: bytes) -> "RegisterPacket":
        if len(payload) < 7:
            raise ValueError(f"REGISTER payload too short: {len(payload)} (need 7)")
        node_id, dev_type, fw = struct.unpack("<IBH", payload[:7])
        return cls(node_id=node_id, device_type=dev_type, firmware_version=fw)

    @property
    def firmware_major(self) -> int:
        return (self.firmware_version >> 8) & 0xFF

    @property
    def firmware_minor(self) -> int:
        return self.firmware_version & 0xFF

    @property
    def firmware_string(self) -> str:
        return f"{self.firmware_major}.{self.firmware_minor}"


@dataclass
class BuzzPacket:
    """BUZZ (0x06) — test command, console flashes LED."""
    duration_half_seconds: int  # duration * 500ms

    def encode(self) -> bytes:
        return _encode(Cmd.BUZZ, struct.pack("<B", self.duration_half_seconds & 0xFF))

    @classmethod
    def decode(cls, payload: bytes) -> "BuzzPacket":
        if len(payload) < 1:
            raise ValueError(f"BUZZ payload too short: {len(payload)} (need 1)")
        return cls(duration_half_seconds=payload[0])


# ── Raw packet encode/decode ───────────────────────────────────────────

def _encode(cmd: int, payload: bytes) -> bytes:
    """Encode a command + payload into the wire format."""
    if len(payload) > 255:
        raise ValueError(f"Payload too long: {len(payload)} bytes (max 255)")
    return bytes([cmd & 0xFF, len(payload)]) + payload


def encode_packet(cmd: int, payload: bytes = b"") -> bytes:
    """Encode a raw command + payload into wire format."""
    return _encode(cmd, payload)


@dataclass
class ParsedPacket:
    """Result of parsing a raw LoRa packet."""
    cmd: int
    payload: bytes

    @property
    def cmd_name(self) -> str:
        return Cmd.name(self.cmd)

    def decode(self) -> Optional[object]:
        """Decode payload into the appropriate packet dataclass.

        Returns None for unknown commands.
        """
        decoders = {
            Cmd.ALERT: AlertPacket.decode,
            Cmd.ACK: AckPacket.decode,
            Cmd.CLEAR: ClearPacket.decode,
            Cmd.HEARTBEAT: HeartbeatPacket.decode,
            Cmd.REGISTER: RegisterPacket.decode,
            Cmd.BUZZ: BuzzPacket.decode,
        }
        decoder = decoders.get(self.cmd)
        if decoder is None:
            return None
        return decoder(self.payload)


def parse_packet(data: bytes) -> Optional[ParsedPacket]:
    """Parse raw bytes into a ParsedPacket.

    Returns None if the data is too short or the length field doesn't match.

    Wire format:
        [0] cmd  uint8
        [1] len  uint8  (length of remaining payload)
        [2:]     payload bytes
    """
    if len(data) < 2:
        return None
    cmd = data[0]
    plen = data[1]
    if len(data) < 2 + plen:
        return None  # incomplete packet
    payload = data[2:2 + plen]
    return ParsedPacket(cmd=cmd, payload=payload)


# ── Convenience: encode typed packets ───────────────────────────────────

def encode_alert(alert_count: int, sequence: int) -> bytes:
    """Encode an ALERT packet."""
    return AlertPacket(alert_count=alert_count, sequence=sequence).encode()


def encode_clear(alert_count: int, sequence: int) -> bytes:
    """Encode a CLEAR packet."""
    return ClearPacket(alert_count=alert_count, sequence=sequence).encode()


def encode_heartbeat(node_id: int, status: int = HeartbeatStatus.OK) -> bytes:
    """Encode a HEARTBEAT packet."""
    return HeartbeatPacket(node_id=node_id, status=status).encode()


def encode_register(node_id: int, device_type: int, firmware_version: int) -> bytes:
    """Encode a REGISTER packet."""
    return RegisterPacket(node_id=node_id, device_type=device_type,
                          firmware_version=firmware_version).encode()


def encode_ack(pager_id: int) -> bytes:
    """Encode an ACK packet."""
    return AckPacket(pager_id=pager_id).encode()


def encode_buzz(duration_half_seconds: int) -> bytes:
    """Encode a BUZZ packet."""
    return BuzzPacket(duration_half_seconds=duration_half_seconds).encode()