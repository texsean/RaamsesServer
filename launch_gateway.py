#!/usr/bin/env python3
"""Launch the Raamses gateway with concurrent HTTP + LoRa support.

This is the recommended way to start the gateway when you want both
WiFi (HTTP) and LoRa (Meshtastic) transport active simultaneously.

Usage:
    # HTTP only (no LoRa)
    python3 launch_gateway.py

    # HTTP + LoRa (auto-detect serial radio)
    python3 launch_gateway.py --lora

    # HTTP + LoRa (specific serial port)
    python3 launch_gateway.py --lora --lora-serial /dev/ttyUSB0

    # HTTP + LoRa (TCP-connected radio, e.g. ESP32 Meshtastic)
    python3 launch_gateway.py --lora --lora-tcp 192.168.1.100

The gateway will:
    1. Start the HTTP/TCP server on port 8765 (WiFi devices)
    2. Connect to the Meshtastic radio and listen on port 256 (LoRa devices)
    3. When an agent alert is detected via HTTP, broadcast ALERT on LoRa
    4. When the alert clears, broadcast CLEAR on LoRa
    5. LoRa devices that register via the radio appear in the same registry
"""

import argparse
import logging
import signal
import sys
import os

def main():
    parser = argparse.ArgumentParser(
        description="Raamses Gateway with concurrent HTTP + LoRa support"
    )
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    parser.add_argument("--port", type=int, default=8765, help="HTTP/TCP port")
    parser.add_argument("--timeout", type=int, default=90, help="Heartbeat timeout (seconds)")
    parser.add_argument("--lora", action="store_true", help="Enable LoRa bridge")
    parser.add_argument("--lora-serial", default=None, help="LoRa serial port")
    parser.add_argument("--lora-tcp", default=None, help="LoRa TCP host")
    parser.add_argument("--log", default="gateway.log", help="Log file path")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    # Set up logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.FileHandler(args.log, mode="a"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Ensure src/linux is on PYTHONPATH
    script_dir = os.path.dirname(os.path.abspath(__file__))
    src_linux = os.path.join(script_dir, "src", "linux")
    if os.path.isdir(src_linux):
        sys.path.insert(0, src_linux)

    from rgs.server.gateway import GatewayServer

    server = GatewayServer(
        host=args.host,
        port=args.port,
        heartbeat_timeout=args.timeout,
        enable_lora=args.lora,
        lora_serial_port=args.lora_serial,
        lora_tcp_host=args.lora_tcp,
    )

    print("=" * 60)
    print("  Raamses Gateway Server")
    print(f"  HTTP/TCP: {args.host}:{args.port}")
    if args.lora:
        if args.lora_tcp:
            print(f"  LoRa:     TCP {args.lora_tcp} (port 256)")
        elif args.lora_serial:
            print(f"  LoRa:     Serial {args.lora_serial} (port 256)")
        else:
            print(f"  LoRa:     Auto-detect (port 256)")
    else:
        print("  LoRa:     disabled")
    print(f"  Log:      {args.log}")
    print("=" * 60)
    print()

    def signal_handler(sig, frame):
        print("\n[Gateway] Shutting down...", flush=True)
        server.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        server.start()
    except KeyboardInterrupt:
        print("\n[Gateway] Shutting down...", flush=True)


if __name__ == "__main__":
    main()