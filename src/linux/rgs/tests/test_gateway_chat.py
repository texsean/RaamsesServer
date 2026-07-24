#!/usr/bin/env python3
"""
Gateway Test: Start gateway, connect Hermes agent, send a chat message.

This simulates a real gateway interaction:
  1. Start the Raamses Gateway on port 8765
  2. Connect a Hermes agent client
  3. Send a chat message from the gateway to the agent
  4. Agent receives it and responds

Usage:
    python test_gateway_chat.py
    python test_gateway_chat.py --message "Hello from the gateway!"
"""

import sys
import os
import time
import threading
import socket
import argparse

# Ensure rgs package is importable
_rgs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "linux")
if _rgs_dir not in sys.path:
    sys.path.insert(0, _rgs_dir)

from rgs.server.gateway import GatewayServer
from rgs.client.hermes_agent_client import HermesAgentClient, HERMES_RX_FIFO, HERMES_TX_FIFO, setup_fifos


def main():
    parser = argparse.ArgumentParser(description="Gateway Chat Test")
    parser.add_argument("--message", default="Hello Hermes! This is a test from the Raamses Gateway. Can you hear me?",
                        help="Chat message to send to the agent")
    parser.add_argument("--port", type=int, default=8765, help="Gateway port")
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    # Set up FIFOs
    setup_fifos()

    print("=" * 60)
    print("  RAAMSES GATEWAY CHAT TEST")
    print("=" * 60)
    print(flush=True)

    # Step 1: Start gateway
    print("[STEP 1] Starting Raamses Gateway...", flush=True)
    gw = GatewayServer(args.host, args.port)
    gw.initialize_router()
    
    gw_thread = threading.Thread(target=gw.start, daemon=True, name="gateway")
    gw_thread.start()
    time.sleep(1.5)

    # Verify gateway is listening
    test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        test_sock.connect((args.host, args.port))
        test_sock.close()
        print(f"  [OK] Gateway listening on {args.host}:{args.port}", flush=True)
    except ConnectionRefusedError:
        print(f"  [FAIL] Gateway not listening!", flush=True)
        return

    # Step 2: Connect Hermes agent client
    print(f"\n[STEP 2] Connecting Hermes Agent...", flush=True)
    agent = HermesAgentClient(
        device_id="hermes-agent-01",
        device_type="hermes",
        host=args.host,
        port=args.port,
        heartbeat_interval=5.0,
    )
    if not agent.start():
        print("  [FAIL] Agent failed to start!", flush=True)
        gw.stop()
        return
    time.sleep(2)
    print(f"  [OK] Agent registered (id=hermes-agent-01)", flush=True)

    # Step 3: Send a chat message from the gateway to the agent
    print(f"\n[STEP 3] Sending chat message from gateway to agent...", flush=True)
    print(f"  Message: \"{args.message}\"", flush=True)
    
    # Use the gateway's message router to send to the agent
    # Connect as a "console" client and register first, then use /tell
    console_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    console_sock.connect((args.host, args.port))
    console_sock.settimeout(5.0)
    
    # Register the console client first
    register_msg = "REGISTER:console-01|console|1.0\n"
    console_sock.sendall(register_msg.encode("utf-8"))
    time.sleep(0.5)
    try:
        reg_ack = console_sock.recv(4096).decode("utf-8").strip()
        print(f"  [CONSOLE] Registered: {reg_ack}", flush=True)
    except socket.timeout:
        print(f"  [CONSOLE] No registration ack", flush=True)
    
    # Send the tell command to the Hermes agent
    tell_msg = f"/tell hermes-agent-01 {args.message}\n"
    console_sock.sendall(tell_msg.encode("utf-8"))
    print(f"  [SENT] /tell hermes-agent-01 {args.message}", flush=True)
    
    # Read response from gateway
    time.sleep(1)
    try:
        response = console_sock.recv(4096).decode("utf-8").strip()
        print(f"  [GATEWAY RESPONSE] {response}", flush=True)
    except socket.timeout:
        print(f"  [GATEWAY] No response (timeout)", flush=True)
    console_sock.close()

    # Step 4: Wait for agent to receive and respond
    print(f"\n[STEP 4] Waiting for agent to receive message...", flush=True)
    time.sleep(3)

    # Check if agent received anything via the RX FIFO
    print(f"\n[STEP 5] Checking agent state...", flush=True)
    
    # Get gateway status
    status_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    status_sock.connect((args.host, args.port))
    status_sock.settimeout(5.0)
    status_sock.sendall(b"agents\n")
    try:
        agents_response = status_sock.recv(4096).decode("utf-8").strip()
        print(f"\n  [GATEWAY AGENTS STATUS]:", flush=True)
        for line in agents_response.split("\n"):
            print(f"  {line}", flush=True)
    except socket.timeout:
        print(f"  [GATEWAY] No agents response", flush=True)
    status_sock.close()

    # Step 6: Now send a response FROM the agent back through the gateway
    print(f"\n[STEP 6] Agent sending response back through gateway...", flush=True)
    agent_response = f"Received your message! Hermes agent here, monitoring the Raamses gateway. All systems nominal."
    agent.send_task(agent_response)
    print(f"  [AGENT SENT]: {agent_response}", flush=True)
    time.sleep(1)

    # Step 7: Read the agent's task update from the gateway
    print(f"\n[STEP 7] Final gateway status...", flush=True)
    status_sock2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    status_sock2.connect((args.host, args.port))
    status_sock2.settimeout(5.0)
    status_sock2.sendall(b"status\n")
    try:
        status_response = status_sock2.recv(4096).decode("utf-8").strip()
        print(f"  {status_response}", flush=True)
    except socket.timeout:
        print(f"  [GATEWAY] No status response", flush=True)
    status_sock2.close()

    # Summary
    print(f"\n{'='*60}")
    print(f"  TEST COMPLETE")
    print(f"{'='*60}")
    print(f"  Gateway: {args.host}:{args.port}")
    print(f"  Agent: hermes-agent-01 (registered={agent.registered})")
    print(f"  Message sent: \"{args.message}\"")
    print(f"  Agent response: \"{agent_response}\"")
    print(f"{'='*60}", flush=True)

    # Cleanup
    print(f"\n[CLEANUP] Shutting down...", flush=True)
    agent.disconnect()
    gw.stop()
    print("[CLEANUP] Done.", flush=True)


if __name__ == "__main__":
    main()