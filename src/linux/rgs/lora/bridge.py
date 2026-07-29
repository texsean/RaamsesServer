"""Raamses LoRa Bridge — connects LoRa radio to the gateway server.

Supports two radio backends:
  - "meshtastic" (default): Meshtastic mesh radio via serial or TCP.
    Uses the meshtastic Python library, protobuf mesh routing, port 256.
  - "rangepi": RangePi USB LoRa dongle (RP2040 + LoRa module).
    Uses raw serial-to-LoRa transparent mode. No mesh routing.

This module provides the LoRaBridge class that:
1. Connects to a LoRa radio (Meshtastic or RangePi)
2. Listens for Raamses binary packets
3. Handles REGISTER and HEARTBEAT from LoRa nodes
4. Broadcasts ALERT and CLEAR to all LoRa nodes when the gateway detects
   agent state changes
5. Runs in a background thread alongside the HTTP/TCP gateway

The bridge is designed to work WITHOUT a physical radio — if no radio is
detected, it runs in "mock mode" where it logs what it would send/receive,
allowing the gateway to start and serve HTTP clients normally.

Architecture:

    ┌──────────────────────────────────────────┐
    │              GatewayServer                │
    │  ┌─────────────┐    ┌──────────────────┐  │
    │  │ TCP+HTTP     │    │   LoRaBridge     │  │
    │  │ (port 8765)  │    │  (Meshtastic)    │  │
    │  │              │    │                  │  │
    │  │ WiFi devices │    │ LoRa devices     │  │
    │  │ HTTP POST    │    │ port 256         │  │
    │  └──────┬───────┘    └────────┬─────────┘  │
    │         │                     │            │
    │         └────── SessionRegistry ───────────┘
    │                  (shared)
    └──────────────────────────────────────────┘

When the gateway detects an agent alert via HTTP poll, the bridge broadcasts
ALERT on LoRa so offline LoRa-only nodes see it too. When the alert clears,
the bridge broadcasts CLEAR with the same sequence number.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional, Callable

from rgs.lora.protocol import (
    Cmd, DeviceType, HeartbeatStatus,
    AlertPacket, ClearPacket, HeartbeatPacket, RegisterPacket, AckPacket, BuzzPacket,
    parse_packet, encode_alert, encode_clear, encode_ack, encode_buzz,
)
from rgs.server.session_registry import SessionRegistry

logger = logging.getLogger(__name__)

# Meshtastic port for Raamses private app
RAAMSES_PORT_NUM = 256  # PRIVATE_APP

# Meshtastic channel index for the "raamses" secondary channel
RAAMSES_CHANNEL_INDEX = 1  # secondary channel (0 = primary)


class LoRaBridge:
    """Bridge between Meshtastic LoRa radio and the Raamses gateway.

    Parameters:
        registry: Shared SessionRegistry (same one used by the gateway)
        serial_port: Serial device path (e.g. /dev/ttyUSB0). None = auto-detect.
        tcp_host: TCP hostname for Meshtastic TCP interface (e.g. "192.168.1.100")
                  If set, uses TCP instead of serial.
        channel_index: Meshtastic channel index (default 1 = secondary channel)
        alert_seq_start: Initial alert sequence number (default 0)
        on_register: Callback(device_id, device_type, firmware, node_id) called on LoRa REGISTER
        on_heartbeat: Callback(device_id, node_id, status) called on LoRa HEARTBEAT
        on_ack: Callback(pager_id, from_node) called on LoRa ACK
    """

    def __init__(
        self,
        registry: SessionRegistry,
        serial_port: Optional[str] = None,
        tcp_host: Optional[str] = None,
        channel_index: int = RAAMSES_CHANNEL_INDEX,
        alert_seq_start: int = 0,
        on_register: Optional[Callable] = None,
        on_heartbeat: Optional[Callable] = None,
        on_ack: Optional[Callable] = None,
        backend: str = "meshtastic",
    ) -> None:
        """Create a LoRaBridge.

        Args:
            backend: "meshtastic" (default) or "rangepi".
                - "meshtastic": uses serial_port / tcp_host for Meshtastic radio
                - "rangepi": uses serial_port (default /dev/ttyACM0) for RangePi dongle
        """
        self._registry = registry
        self._serial_port = serial_port
        self._tcp_host = tcp_host
        self._channel_index = channel_index
        self._backend_name = backend.lower()
        self._on_register = on_register
        self._on_heartbeat = on_heartbeat
        self._on_ack = on_ack

        self._interface = None  # Meshtastic interface OR RangePiBackend
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._alert_seq = alert_seq_start
        self._alert_count = 0
        self._lock = threading.Lock()
        self._mock_mode = False  # True when no radio detected

        # Track which node IDs we've seen (for relay logging)
        self._known_nodes: set[int] = set()

    # ── Lifecycle ──────────────────────────────────────────────────────

    def start(self) -> bool:
        """Connect to the Meshtastic radio and start the listener thread.

        Returns True if connected (or running in mock mode), False on error.
        """
        try:
            self._connect_radio()
        except Exception as e:
            logger.warning("LoRa radio connection failed: %s — running in mock mode", e)
            self._mock_mode = True
            print(f"[LoRaBridge] No radio detected — running in mock mode ({e})")

        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="lora-bridge",
        )
        self._thread.start()

        if self._mock_mode:
            print("[LoRaBridge] Mock mode active — LoRa packets will be logged but not sent/received")
        else:
            backend_label = f"{self._backend_name} backend" if self._backend_name != "meshtastic" else f"port {RAAMSES_PORT_NUM}"
            print(f"[LoRaBridge] Connected to radio ({self._backend_name}), listening on {backend_label}")

        return True

    def stop(self) -> None:
        """Stop the bridge and disconnect from the radio."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

        if self._interface is not None:
            try:
                if self._backend_name == "rangepi":
                    self._interface.stop()
                else:
                    self._interface.close()
            except Exception:
                pass
            self._interface = None

        logger.info("LoRa Bridge stopped")

    # ── Radio Connection ────────────────────────────────────────────────

    def _connect_radio(self) -> None:
        """Connect to the LoRa radio via the selected backend."""
        if self._backend_name == "rangepi":
            self._connect_rangepi()
        else:
            self._connect_meshtastic()

    def _connect_rangepi(self) -> None:
        """Connect to a RangePi USB LoRa dongle."""
        from rgs.lora.rangepi_backend import RangePiBackend
        port = self._serial_port or "/dev/ttyACM0"
        logger.info("Connecting to RangePi via serial: %s", port)
        self._interface = RangePiBackend(
            serial_port=port,
            baudrate=115200,
            on_receive=self._on_receive_rangepi,
            node_id=1,
        )
        self._interface.start()

    def _connect_meshtastic(self) -> None:
        """Connect to a Meshtastic radio via serial or TCP."""
        if self._tcp_host:
            # TCP interface (for remote Meshtastic node)
            from meshtastic.tcp_interface import TCPInterface
            logger.info("Connecting to Meshtastic via TCP: %s", self._tcp_host)
            self._interface = TCPInterface(hostname=self._tcp_host, noNodes=False)
        else:
            # Serial interface (auto-detect or specific port)
            from meshtastic.serial_interface import SerialInterface
            logger.info("Connecting to Meshtastic via serial: %s",
                        self._serial_port or "auto-detect")
            self._interface = SerialInterface(devPath=self._serial_port, noNodes=False)

        # Subscribe to receive data on the PRIVATE_APP port
        from meshtastic import pub
        pub.subscribe(self._on_receive, f"meshtastic.receive.data.PRIVATE_APP")
        logger.info("Subscribed to meshtastic.receive.data.PRIVATE_APP")

    # ── Receive Handler ─────────────────────────────────────────────────

    def _on_receive(self, packet: dict, interface=None) -> None:
        """Callback for received Meshtastic packets on port 256.

        The packet dict has this structure (from meshtastic.mesh_interface):
        {
            "from": <node_num>,
            "to": <node_num>,
            "decoded": {
                "portnum": "PRIVATE_APP",
                "payload": <bytes>,  # raw binary payload
                ...
            },
            "raw": <MeshPacket protobuf>,
        }
        """
        try:
            from_node = packet.get("from", 0)
            decoded = packet.get("decoded", {})
            payload = decoded.get("payload", b"")

            if not payload:
                logger.debug("Empty payload from node %d", from_node)
                return

            parsed = parse_packet(payload)
            if parsed is None:
                logger.warning("Malformed LoRa packet from node %d: %s",
                              from_node, payload.hex())
                return

            logger.info("LoRa RX: %s from node %d (%d bytes)",
                        parsed.cmd_name, from_node, len(payload))

            # Dispatch to handler
            self._handle_packet(parsed, from_node)

        except Exception as e:
            logger.exception("Error processing LoRa packet: %s", e)

    def _on_receive_rangepi(self, raw_bytes: bytes) -> None:
        """Callback for received packets from the RangePi backend.

        The RangePi backend delivers complete Raamses binary packets
        (already framed: cmd + len + payload). We parse and dispatch.
        """
        try:
            parsed = parse_packet(raw_bytes)
            if parsed is None:
                logger.warning("Malformed RangePi packet: %s", raw_bytes.hex())
                return

            # RangePi has no node ID in the mesh sense — use the radio's node_id
            from_node = self._interface.node_id if self._interface else 1

            logger.info("RangePi RX: %s (%d bytes)",
                        parsed.cmd_name, len(raw_bytes))

            self._handle_packet(parsed, from_node)

        except Exception as e:
            logger.exception("Error processing RangePi packet: %s", e)

    def _handle_packet(self, parsed, from_node: int) -> None:
        """Handle a parsed LoRa packet from a remote node."""
        decoded = parsed.decode()

        if parsed.cmd == Cmd.REGISTER and decoded is not None:
            self._handle_register(decoded, from_node)

        elif parsed.cmd == Cmd.HEARTBEAT and decoded is not None:
            self._handle_heartbeat(decoded, from_node)

        elif parsed.cmd == Cmd.ACK and decoded is not None:
            self._handle_ack(decoded, from_node)

        else:
            logger.debug("Unhandled LoRa command 0x%02x from node %d",
                        parsed.cmd, from_node)

    def _handle_register(self, reg: RegisterPacket, from_node: int) -> None:
        """Handle REGISTER from a LoRa node."""
        device_id = f"lora-{from_node}"
        device_type_name = DeviceType.name(reg.device_type)

        logger.info("LoRa REGISTER: node=%d type=%s fw=%s",
                   from_node, device_type_name, reg.firmware_string)

        self._known_nodes.add(from_node)

        # Register in the shared session registry
        self._registry.register(
            device_id=device_id,
            device_type=device_type_name,
            schema_version="1.0",
            firmware_version=reg.firmware_string,
            transport="lora",
            node_id=from_node,
        )

        if self._on_register:
            self._on_register(device_id, device_type_name, reg.firmware_string, from_node)

    def _handle_heartbeat(self, hb: HeartbeatPacket, from_node: int) -> None:
        """Handle HEARTBEAT from a LoRa node."""
        device_id = f"lora-{from_node}"
        status_name = HeartbeatStatus.name(hb.status)

        logger.info("LoRa HEARTBEAT: node=%d status=%s", from_node, status_name)

        self._known_nodes.add(from_node)

        # Update heartbeat in registry (auto-registers if not present)
        if not self._registry.heartbeat(device_id):
            # Not registered — auto-register from heartbeat
            logger.info("Auto-registering LoRa node %d from heartbeat", from_node)
            self._registry.register(
                device_id=device_id,
                device_type="unknown",
                schema_version="1.0",
                transport="lora",
                node_id=from_node,
            )
        else:
            # Update node_id if not set
            session = self._registry.get(device_id)
            if session and session.node_id is None:
                session.node_id = from_node

        if self._on_heartbeat:
            self._on_heartbeat(device_id, from_node, hb.status)

    def _handle_ack(self, ack: AckPacket, from_node: int) -> None:
        """Handle ACK from a LoRa node."""
        logger.info("LoRa ACK: node=%d pager_id=%d", from_node, ack.pager_id)
        if self._on_ack:
            self._on_ack(ack.pager_id, from_node)

    # ── Broadcast (Bridge → LoRa nodes) ──────────────────────────────────

    def broadcast_alert(self, alert_count: Optional[int] = None) -> int:
        """Broadcast an ALERT to all LoRa nodes.

        Increments the alert sequence counter and sends ALERT(count, seq).
        Returns the sequence number used.
        """
        with self._lock:
            self._alert_seq = (self._alert_seq + 1) & 0xFFFF
            seq = self._alert_seq
            if alert_count is not None:
                self._alert_count = alert_count & 0xFF
            else:
                self._alert_count = (self._alert_count + 1) & 0xFF
            count = self._alert_count

        payload = encode_alert(count, seq)
        logger.info("LoRa TX: ALERT count=%d seq=%d", count, seq)
        self._send_data(payload)

        return seq

    def broadcast_clear(self, seq: int, alert_count: Optional[int] = None) -> None:
        """Broadcast a CLEAR for the given sequence to all LoRa nodes.

        The sequence must match the ALERT being cleared.
        """
        with self._lock:
            if alert_count is not None:
                self._alert_count = alert_count & 0xFF
            count = self._alert_count

        payload = encode_clear(count, seq)
        logger.info("LoRa TX: CLEAR count=%d seq=%d", count, seq)
        self._send_data(payload)

    def send_buzz(self, duration_half_seconds: int = 2) -> None:
        """Send a BUZZ test command to all nodes."""
        payload = encode_buzz(duration_half_seconds)
        logger.info("LoRa TX: BUZZ duration=%d half-seconds", duration_half_seconds)
        self._send_data(payload)

    def _send_data(self, data: bytes) -> bool:
        """Send binary data on port 256 (PRIVATE_APP) to all nodes.

        Returns True if sent, False if in mock mode or error.
        """
        if self._mock_mode:
            logger.info("[MOCK] Would send on LoRa: %s", data.hex())
            return False

        if self._interface is None:
            logger.warning("LoRa interface not connected — cannot send")
            return False

        try:
            if self._backend_name == "rangepi":
                # RangePi backend — raw serial to LoRa
                return self._interface.send_data(data)
            else:
                # Meshtastic backend — sendData with port/channel
                self._interface.sendData(
                    data=data,
                    destinationId="^all",
                    portNum=RAAMSES_PORT_NUM,
                    channelIndex=self._channel_index,
                    wantAck=False,
                )
                return True
        except Exception as e:
            logger.error("LoRa send failed: %s", e)
            return False

    # ── Main Loop ────────────────────────────────────────────────────────

    def _run_loop(self) -> None:
        """Background thread loop — keeps the connection alive and processes events.

        In mock mode, just sleeps and logs periodically.
        With a real radio, the meshtastic pubsub handles received packets
        via callbacks, so this loop mainly keeps the thread alive and
        periodically checks radio health.
        """
        health_check_interval = 60  # seconds
        last_health_check = 0

        while self._running:
            time.sleep(1)

            # Periodic health check
            now = time.time()
            if now - last_health_check > health_check_interval:
                last_health_check = now
                if not self._mock_mode and self._interface is not None:
                    try:
                        if self._backend_name == "rangepi":
                            # RangePi backend — check is_connected
                            if not self._interface.is_connected:
                                logger.warning("RangePi serial disconnected — attempting reconnect")
                                try:
                                    self._connect_radio()
                                except Exception as e:
                                    logger.error("Reconnect failed: %s", e)
                                    self._mock_mode = True
                        else:
                            # Meshtastic backend — check isConnected()
                            if hasattr(self._interface, 'isConnected'):
                                if not self._interface.isConnected():
                                    logger.warning("LoRa radio disconnected — attempting reconnect")
                                    try:
                                        self._connect_radio()
                                    except Exception as e:
                                        logger.error("Reconnect failed: %s", e)
                                        self._mock_mode = True
                    except Exception as e:
                        logger.warning("Health check error: %s", e)

    # ── Accessors ────────────────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        """True if the radio is connected (not mock mode)."""
        return not self._mock_mode and self._interface is not None

    @property
    def is_mock_mode(self) -> bool:
        """True if running without a physical radio."""
        return self._mock_mode

    @property
    def known_nodes(self) -> set[int]:
        """Set of Meshtastic node IDs that have communicated with this bridge."""
        return self._known_nodes.copy()

    @property
    def alert_seq(self) -> int:
        """Current alert sequence number."""
        return self._alert_seq

    @property
    def alert_count(self) -> int:
        """Current alert count (rolling 0-255)."""
        return self._alert_count