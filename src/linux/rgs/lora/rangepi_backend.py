"""RangePi LoRa backend — USB serial transport for the RangePi dongle.

The RangePi is an RP2040-based LoRa dongle (by SB Components) that appears
as /dev/ttyACM0. Unlike Meshtastic, it has no mesh routing or protobuf —
it's a transparent serial-to-LoRa bridge. You write binary bytes to USB
serial, the RP2040 firmware forwards them to the LoRa module's UART,
and the LoRa module transmits them over the air.

This class provides the same interface as the Meshtastic backend:
  - start() / stop() lifecycle
  - _send_data(bytes) for TX
  - _on_receive callback for RX (via a reader thread)

Wire format over USB serial:
  Raw Raamses binary packets: [cmd:u8] [len:u8] [payload:len bytes]
  The host buffers incoming serial bytes and uses parse_packet() to
  extract complete packets.

The RangePi's LoRa module runs in transparent mode at 9600 baud.
In transparent mode, the module transmits when it sees a pause in
incoming UART data (~100ms idle). Packets up to ~58 bytes are typical
for LoRa transparent mode; larger payloads may be split.

For the Raamses protocol, max packet is 257 bytes (cmd + len + 255 payload),
but actual packets are much smaller:
  - ALERT:     5 bytes  (cmd + len + 3 payload)
  - CLEAR:     5 bytes
  - HEARTBEAT: 7 bytes  (cmd + len + 5 payload)
  - REGISTER:  9 bytes  (cmd + len + 7 payload)
  - ACK:       3 bytes
  - BUZZ:      3 bytes
All well within LoRa transparent mode limits.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional, Callable

from rgs.lora.protocol import parse_packet

logger = logging.getLogger(__name__)

# Default serial parameters for the RangePi
DEFAULT_PORT = "/dev/ttyACM0"
DEFAULT_BAUDRATE = 115200
READ_TIMEOUT = 0.5  # seconds — short for responsive polling

# How long to wait for more bytes before attempting to parse a packet
PACKET_TIMEOUT = 0.1  # 100ms — matches LoRa transparent mode idle gap


class RangePiBackend:
    """USB serial backend for the RangePi LoRa dongle.

    This replaces the Meshtastic interface for use with the RangePi.
    It provides a serial reader thread that buffers incoming bytes and
    emits complete Raamses packets via the on_receive callback.

    Parameters:
        serial_port: USB CDC serial path (default /dev/ttyACM0)
        baudrate: USB serial baud rate (default 115200)
        on_receive: Callback(raw_bytes: bytes) called for each complete packet.
                    The caller is responsible for parse_packet() + dispatch.
        node_id: Pretend node ID for this radio (for compatibility with
                 Meshtastic-style device IDs). Default 1.
    """

    def __init__(
        self,
        serial_port: Optional[str] = None,
        baudrate: int = DEFAULT_BAUDRATE,
        on_receive: Optional[Callable[[bytes], None]] = None,
        node_id: int = 1,
    ) -> None:
        self._serial_port = serial_port or DEFAULT_PORT
        self._baudrate = baudrate
        self._on_receive = on_receive
        self._node_id = node_id

        self._serial = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._rx_buffer = bytearray()

    # ── Lifecycle ──────────────────────────────────────────────────────

    def start(self) -> bool:
        """Open the serial port and start the reader thread.

        Returns True if connected, False on error.
        """
        try:
            import serial
        except ImportError:
            raise ImportError("pyserial is required for RangePi backend: pip install pyserial")

        try:
            self._serial = serial.Serial(
                port=self._serial_port,
                baudrate=self._baudrate,
                timeout=READ_TIMEOUT,
                write_timeout=2.0,
            )
            logger.info("RangePi serial opened: %s @ %d baud", self._serial_port, self._baudrate)
        except Exception as e:
            logger.error("Failed to open RangePi serial %s: %s", self._serial_port, e)
            raise

        # Send a Ctrl-C to break out of any running MicroPython main loop
        # so the RangePi is ready for raw binary passthrough
        try:
            self._serial.write(b'\x03\x03')
            time.sleep(0.3)
            self._serial.read(self._serial.in_waiting or 1024)  # flush
            logger.info("Sent Ctrl-C to RangePi (stop any running main.py)")
        except Exception:
            pass  # Best effort — firmware might already be in bridge mode

        self._running = True
        self._thread = threading.Thread(
            target=self._reader_loop,
            daemon=True,
            name="rangepi-reader",
        )
        self._thread.start()

        return True

    def stop(self) -> None:
        """Stop the reader thread and close the serial port."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None

        logger.info("RangePi backend stopped")

    # ── TX ─────────────────────────────────────────────────────────────

    def send_data(self, data: bytes) -> bool:
        """Send binary data to the RangePi for LoRa transmission.

        Returns True if written to serial, False on error.
        """
        if self._serial is None:
            logger.warning("RangePi serial not open — cannot send")
            return False

        try:
            self._serial.write(data)
            self._serial.flush()
            logger.debug("RangePi TX: %d bytes %s", len(data), data.hex())
            return True
        except Exception as e:
            logger.error("RangePi send failed: %s", e)
            return False

    # ── RX Reader Thread ────────────────────────────────────────────────

    def _reader_loop(self) -> None:
        """Background thread that reads serial bytes and extracts packets.

        Buffers incoming bytes, attempts to parse a complete packet after
        each read or after PACKET_TIMEOUT. Calls on_receive for each
        complete packet.
        """
        while self._running:
            try:
                if self._serial is None:
                    time.sleep(0.1)
                    continue

                # Read available bytes
                n = self._serial.in_waiting
                if n > 0:
                    chunk = self._serial.read(n)
                else:
                    # Short timeout read — blocks briefly waiting for data
                    chunk = self._serial.read(64)

                if chunk:
                    self._rx_buffer.extend(chunk)
                    self._try_parse()

            except Exception as e:
                logger.error("RangePi reader error: %s", e)
                time.sleep(0.5)  # back off on error

    def _try_parse(self) -> None:
        """Attempt to extract complete packets from the RX buffer.

        Wire format: [cmd:u8] [len:u8] [payload:len bytes]
        Total packet = len + 2 bytes.
        """
        while len(self._rx_buffer) >= 2:
            cmd = self._rx_buffer[0]
            plen = self._rx_buffer[1]
            total = plen + 2

            if len(self._rx_buffer) < total:
                # Incomplete packet — wait for more bytes
                break

            # Extract complete packet
            packet_bytes = bytes(self._rx_buffer[:total])
            del self._rx_buffer[:total]

            # Validate via parse_packet
            parsed = parse_packet(packet_bytes)
            if parsed is not None:
                logger.info("RangePi RX: %s (%d bytes)",
                            parsed.cmd_name, len(packet_bytes))
                if self._on_receive:
                    self._on_receive(packet_bytes)
            else:
                logger.warning("RangePi: malformed packet, dropping: %s",
                              packet_bytes.hex())

    # ── Accessors ──────────────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        """True if the serial port is open."""
        return self._serial is not None and self._serial.is_open

    @property
    def node_id(self) -> int:
        """The node ID associated with this radio."""
        return self._node_id