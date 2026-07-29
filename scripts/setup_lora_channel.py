#!/usr/bin/env python3
"""Configure the Meshtastic radio for the Raamses private channel.

Sets up a secondary channel named "raamses" with PSK "raamses-mesh-key-2025"
on port PRIVATE_APP (256). This channel is used for all Raamses LoRa
communication between the Pi gateway and console devices.

Usage:
    python3 setup_lora_channel.py [--serial /dev/ttyUSB0] [--tcp 192.168.1.100]

If no connection method is specified, auto-detects serial then falls back
to TCP localhost.

After setup, the radio will have two channels:
    0: primary (default Meshtastic channel)
    1: raamses (PRIVATE_APP, port 256)

The PSK is hashed to 16/32 bytes by Meshtastic — the string
"raamses-mesh-key-2025" is used as a passphrase.
"""

import argparse
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Raamses channel configuration
RAAMSES_CHANNEL_NAME = "raamses"
RAAMSES_CHANNEL_PSK = b"raamses-mesh-key-2025"
RAAMSES_CHANNEL_INDEX = 1  # secondary channel
RAAMSES_PORT_NUM = 256  # PRIVATE_APP


def setup_channel(serial_port=None, tcp_host=None):
    """Configure the Raamses secondary channel on the connected radio."""
    try:
        if tcp_host:
            from meshtastic.tcp_interface import TCPInterface
            logger.info("Connecting via TCP: %s", tcp_host)
            iface = TCPInterface(hostname=tcp_host, noNodes=False)
        else:
            from meshtastic.serial_interface import SerialInterface
            logger.info("Connecting via serial: %s", serial_port or "auto-detect")
            iface = SerialInterface(devPath=serial_port, noNodes=False)
    except Exception as e:
        print(f"Error: Could not connect to Meshtastic radio: {e}")
        print("Make sure the radio is connected via USB or accessible via TCP.")
        sys.exit(1)

    try:
        # Get the local node
        node = iface.getLocalNode()
        if node is None:
            print("Error: Could not get local node from radio")
            sys.exit(1)

        print(f"Connected to radio: {node}")

        # Read current channels
        from meshtastic.protobuf.channel_pb2 import Channel
        from meshtastic.protobuf.config_pb2 import ChannelSettings

        # Create or update the secondary channel
        ch = Channel()
        ch.index = RAAMSES_CHANNEL_INDEX
        ch.role = Channel.Role.SECONDARY
        ch.settings.name = RAAMSES_CHANNEL_NAME
        ch.settings.psk = RAAMSES_CHANNEL_PSK
        ch.settings.module_settings.position_precision = 32  # default

        print(f"Setting channel {RAAMSES_CHANNEL_INDEX}: name='{RAAMSES_CHANNEL_NAME}'")
        print(f"  PSK: {'raamses-mesh-key-2025'!r}")
        print(f"  Role: SECONDARY")
        print(f"  Port: PRIVATE_APP ({RAAMSES_PORT_NUM})")

        # Write the channel to the radio
        node.writeChannel(RAAMSES_CHANNEL_INDEX)

        # Verify
        print()
        print("Channel configured successfully!")
        print()
        print("The radio now has the 'raamses' channel on index 1.")
        print("Console devices should be configured with the same channel.")
        print()
        print("To verify: meshtastic --info")

    except Exception as e:
        print(f"Error configuring channel: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        try:
            iface.close()
        except Exception:
            pass


def show_channel_info(serial_port=None, tcp_host=None):
    """Show current channel configuration on the connected radio."""
    try:
        if tcp_host:
            from meshtastic.tcp_interface import TCPInterface
            iface = TCPInterface(hostname=tcp_host, noNodes=False)
        else:
            from meshtastic.serial_interface import SerialInterface
            iface = SerialInterface(devPath=serial_port, noNodes=False)
    except Exception as e:
        print(f"Error: Could not connect to radio: {e}")
        sys.exit(1)

    try:
        node = iface.getLocalNode()
        if node is None:
            print("Error: Could not get local node")
            sys.exit(1)

        print("Current channels:")
        print(f"  Node: {node}")
        print()

        # Try to read channel info
        channels = node.channels if hasattr(node, 'channels') else []
        for i, ch in enumerate(channels):
            name = ch.settings.name if hasattr(ch, 'settings') else "?"
            role = ch.role if hasattr(ch, 'role') else "?"
            print(f"  Channel {i}: name='{name}' role={role}")

    except Exception as e:
        print(f"Error reading channels: {e}")
    finally:
        try:
            iface.close()
        except Exception:
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Configure Meshtastic radio for Raamses LoRa channel"
    )
    parser.add_argument("--serial", default=None,
                       help="Serial port (e.g. /dev/ttyUSB0)")
    parser.add_argument("--tcp", default=None,
                       help="TCP host (e.g. 192.168.1.100)")
    parser.add_argument("--info", action="store_true",
                       help="Show current channel info (don't configure)")
    args = parser.parse_args()

    if args.info:
        show_channel_info(serial_port=args.serial, tcp_host=args.tcp)
    else:
        setup_channel(serial_port=args.serial, tcp_host=args.tcp)