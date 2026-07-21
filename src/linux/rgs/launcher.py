#!/usr/bin/env python3
"""
Raamses Server Launcher

Starts the mock Raamses server and optional device emulators for testing.

Usage:
    python launcher.py                          # Server only
    python launcher.py --emulators cyd epaper   # Server + 2 emulators
    python launcher.py --emulators cyd:cyd-001 watch:watch-01  # Custom IDs
"""

import asyncio
import argparse
import sys
import os

# Ensure the rgs package is importable.
# launcher.py lives at src/linux/rgs/launcher.py; sys.path needs src/linux/
_rgs_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # src/linux/
if _rgs_parent not in sys.path:
    sys.path.insert(0, _rgs_parent)

from rgs.server.mock_server import MockRaamsesServer
from rgs.client.device_emulator import DeviceEmulator


async def run_server(port: int):
    server = MockRaamsesServer('127.0.0.1', port)
    server._server = await asyncio.start_server(
        server.handle_client, '127.0.0.1', port)
    addr = server._server.sockets[0].getsockname()
    print(f"\n{'='*60}", flush=True)
    print(f"  MOCK RAAMSES SERVER RUNNING", flush=True)
    print(f"  {addr[0]}:{addr[1]}", flush=True)
    print(f"{'='*60}\n", flush=True)
    return server


async def run_emulator(emulator: DeviceEmulator):
    emulator.running = True
    try:
        await emulator.run()
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[EMULATOR {emulator.device_id}] Error: {e}", flush=True)


LOG_FILE = "/tmp/raamses_server_live.log"


async def main():
    # Open log file for all output
    log = open(LOG_FILE, "a")

    parser = argparse.ArgumentParser(description="Raamses Server Launcher")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9999)
    parser.add_argument("--emulators", nargs="+", default=[],
                        metavar="TYPE[=ID]",
                        help="Device types to emulate (e.g., cyd epaper watch)")
    args = parser.parse_args()

    def log_print(*args, **kwargs):
        text = " ".join(str(a) for a in args)
        log.write(text + "\n")
        log.flush()

    # Start server
    server_task = asyncio.create_task(run_server(args.port))
    log_print("[LAUNCHER] Starting server on port", args.port)
    await asyncio.sleep(0.5)  # Let server bind

    tasks = [server_task]
    devices = []

    if args.emulators:
        print(f"\nStarting {len(args.emulators)} device emulator(s)...\n", flush=True)

    for spec in args.emulators:
        if "=" in spec:
            device_type, device_id = spec.split("=", 1)
        else:
            device_type = spec
            import uuid
            device_id = f"emu-{device_type}-{uuid.uuid4().hex[:6]}"

        emulator = DeviceEmulator(
            device_id=device_id,
            device_type=device_type,
            host=args.host,
            port=args.port,
        )
        devices.append(emulator)
        tasks.append(asyncio.create_task(run_emulator(emulator)))

    try:
        # Keep running until interrupted
        while True:
            await asyncio.sleep(1)
            running = sum(1 for t in tasks[1:] if not t.done())
            print(f"\r[Launcher] Server up | {running} emulator(s) running  ", end="", flush=True)
    except KeyboardInterrupt:
        print("\n\n[Launcher] Shutting down...", flush=True)
        for t in tasks[1:]:
            t.cancel()
        for t in tasks[1:]:
            try:
                await t
            except asyncio.CancelledError:
                pass
        if server_task.done():
            st = server_task.result()
            st._server.close()
            await st._server.wait_closed()
        print("[Launcher] Done.", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
