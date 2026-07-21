#!/usr/bin/env python3
"""Quick test to verify server starts and emulator connects."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
import asyncio
from rgs.server.mock_server import MockRaamsesServer
from rgs.client.device_emulator import DeviceEmulator

async def main():
    # Start server
    server = MockRaamsesServer('127.0.0.1', 19999)

    async def run_server():
        await server.run()

    srv_task = asyncio.create_task(run_server())
    await asyncio.sleep(1)  # Let server start first

    # Start emulator
    emu = DeviceEmulator(
        device_id="test-cyd-001",
        device_type="cyd",
        host="127.0.0.1",
        port=19999,
    )
    emu.running = True
    emu_task = asyncio.create_task(emu.run())

    # Let it run for 20 seconds
    await asyncio.sleep(20)

    emu.running = False
    await server.stop()
    srv_task.cancel()
    try:
        await srv_task
    except asyncio.CancelledError:
        pass
    emu_task.cancel()
    try:
        await emu_task
    except asyncio.CancelledError:
        pass

    print(f"\n[TEST] Results:", flush=True)
    print(f"  Commands received by emulator: {len(emu.received_commands)}", flush=True)
    print(f"  Alerts received by emulator: {len(emu.received_alerts)}", flush=True)
    if emu.received_commands:
        print(f"  Sample: {emu.received_commands[-1]}", flush=True)
    if emu.received_alerts:
        print(f"  Sample: {emu.received_alerts[-1]}", flush=True)

asyncio.run(main())
