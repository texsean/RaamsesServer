#!/usr/bin/env python3
"""Start the RGS Gateway Server in background mode."""
import sys
sys.path.insert(0, 'src/linux')
import signal
import threading
import time
import socket
import json

signal.signal(signal.SIGINT, signal.SIG_IGN)
from rgs.server.gateway import GatewayServer

print("[main] Starting RGS Gateway on port 8765...", flush=True)

gateway = GatewayServer(port=8765, heartbeat_timeout=90)

def run_gateway():
    gateway.start()

t = threading.Thread(target=run_gateway, daemon=True)
t.start()

# Wait for gateway to bind
time.sleep(1)

# Check port
s = socket.socket()
r = s.connect_ex(('127.0.0.1', 8765))
s.close()

if r == 0:
    print("[main] Gateway running. Port 8765 OPEN", flush=True)
    
    # Test: register a device
    time.sleep(0.5)
    s2 = socket.socket()
    s2.connect(('127.0.0.1', 8765))
    s2.sendall(b'REGISTER:test-cyd-01|cyd|1.0|2.1.0\n')
    time.sleep(0.5)
    try:
        d = s2.recv(4096).decode().strip()
        print(f"[main] REGISTER_ACK: {d}", flush=True)
    except socket.timeout:
        print("[main] REGISTER: timeout (router not initialized)", flush=True)
    s2.close()
else:
    print("[main] Gateway FAILED to start on port 8765", flush=True)
