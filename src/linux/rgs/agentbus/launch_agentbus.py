#!/usr/bin/env python3
"""Single-command launcher for the Raamses Agent Bus.

Usage:
    PYTHONPATH=src/linux python3 -m rgs.agentbus.launch_agentbus
    PYTHONPATH=src/linux python3 -m rgs.agentbus.launch_agentbus --port 8787
    PYTHONPATH=src/linux python3 -m rgs.agentbus.launch_agentbus --port 8787 --log-dir /var/log/raamses/agentbus

The agent bus runs on port 8787 by default, separate from the RGS gateway (8765).
All interactions are logged to logs/ with timestamped filenames for historical records.
"""

from __future__ import annotations

import logging
import sys

from rgs.agentbus.server import AgentBus


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Raamses Agent Bus — inter-agent messaging on port 8787"
    )
    parser.add_argument("--host", default="0.0.0.0",
                        help="Bind address (default 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8787,
                        help="Listen port (default 8787)")
    parser.add_argument("--log-dir", default=None,
                        help="Log directory (default: logs/ next to server.py)")
    parser.add_argument("--timeout", type=int, default=120,
                        help="Agent offline timeout in seconds (default 120)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )

    print(f"Starting Raamses Agent Bus on {args.host}:{args.port}", flush=True)
    if args.log_dir:
        print(f"Logs: {args.log_dir}", flush=True)
    else:
        print("Logs: logs/ (next to server.py)", flush=True)

    bus = AgentBus(
        host=args.host,
        port=args.port,
        log_dir=args.log_dir,
        agent_timeout=args.timeout,
    )
    bus.start()


if __name__ == "__main__":
    main()