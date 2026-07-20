#!/usr/bin/env python3
"""Quick test to verify server starts and emulator connects."""
import sys
sys.path.insert(0, 'src/python')
import asyncio
from raamses.server.mock_server import MockRaamsesServer
from raamses.client.device_emulator import DeviceEmulator

async def main():
    # Start server
    server = MockRaamsesServer('127.0.0.1', 19999)
    
    async def run_server():
        server._server = await asyncio.start_server(
            server.handle_client, '127.0.0.1', 19999)
        addr = server._server.sockets[0].getsockname()
        print(f"[TEST] Server on {addr[0]}:{addr[1]}", flush=True)
        while True:
            await asyncio.sleep(1)
    
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
    srv_task.cancel()
    try:
        await srv_task
    except asyncio.CancelledError:
        pass
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
