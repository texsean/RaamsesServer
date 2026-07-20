#!/usr/bin/env python3
"""Launch 3 simulated device agents connecting to the RGS gateway."""
import sys
sys.path.insert(0, 'src/linux')
sys.path.insert(0, 'src/linux/rgs/client')

import argparse
import logging
import socket
import threading
import time
from datetime import datetime, timezone
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)

class SimDevice:
    """Simulated device that connects to RGS gateway."""
    
    def __init__(self, device_id, device_type, heartbeat_interval=8):
        self.device_id = device_id
        self.device_type = device_type
        self.heartbeat_interval = heartbeat_interval
        self.sock = None
        self.running = False
        self.registered = False
        self.current_task = None
        
    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(5.0)
        self.sock.connect(('127.0.0.1', 8765))
        self.sock.settimeout(None)
        logging.info("[CONNECTED] %s -> 127.0.0.1:8765", self.device_id)
        
    def send_register(self):
        msg = f"REGISTER:{self.device_id}|{self.device_type}|1.0|1.0.0"
        self.sock.sendall(f"{msg}\n".encode())
        logging.info("[REGISTER_SENT] %s", msg)
        
    def send_heartbeat(self):
        self.sock.sendall(b"heartbeat\n")
        logging.debug("[HEARTBEAT] %s", self.device_id)
        
    def send_task(self, task):
        self.sock.sendall(f"task: {task}\n".encode())
        logging.info("[TASK] %s -> %s", self.device_id, task)
        
    def send_progress(self, pct, task):
        self.sock.sendall(f"progress: {pct}% {task}\n".encode())
        
    def send_done(self, result):
        self.sock.sendall(f"done: {result}\n".encode())
        
    def recv_loop(self):
        buf = b""
        while self.running:
            try:
                data = self.sock.recv(4096)
                if not data:
                    logging.info("[DISCONNECTED] %s - server closed", self.device_id)
                    self.running = False
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    text = line.decode("utf-8", errors="replace").strip()
                    if text:
                        logging.info("[RECV] %s <- %s", self.device_id, text[:120])
                        if text.startswith("REGISTER_ACK:"):
                            self.registered = True
            except (OSError, ConnectionError, UnicodeDecodeError):
                self.running = False
                break
                
    def heartbeat_loop(self):
        while self.running:
            time.sleep(self.heartbeat_interval)
            if self.running:
                self.send_heartbeat()
                
    def simulate_task(self):
        """Simulate a realistic task cycle."""
        tasks = [
            "initialize monitoring",
            "collect sensor data", 
            "process telemetry",
            "upload dashboard update",
            "check system status",
        ]
        for task in tasks:
            if not self.running:
                break
            self.send_task(task)
            for pct in [25, 50, 75, 100]:
                if not self.running:
                    break
                time.sleep(2)
                self.send_progress(pct, task)
            self.send_done(f"completed: {task}")
        logging.info("[DONE] %s finished demo task cycle", self.device_id)
        
    def start(self):
        self.running = True
        self.connect()
        self.send_register()
        
        # Start receive thread
        recv_thread = threading.Thread(target=self.recv_loop, daemon=True)
        recv_thread.start()
        
        # Wait for registration
        for i in range(50):  # 5 second timeout
            if self.registered:
                break
            time.sleep(0.1)
            
        if self.registered:
            logging.info("[REGISTERED] %s accepted by gateway", self.device_id)
            # Start heartbeat
            hb_thread = threading.Thread(target=self.heartbeat_loop, daemon=True)
            hb_thread.start()
            # Simulate work
            self.simulate_task()
            # Continue heartbeats
            while self.running:
                time.sleep(30)
        else:
            logging.error("[FAILED] %s registration timeout", self.device_id)
            self.running = False
            
    def stop(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except:
                pass

# ---- Main ----
devices = [
    SimDevice("agent-cyd-01", "cyd", heartbeat_interval=10),
    SimDevice("agent-full-02", "full", heartbeat_interval=12),
    SimDevice("agent-epaper-03", "epaper", heartbeat_interval=15),
]

threads = []
for d in devices:
    t = threading.Thread(target=d.start, daemon=True)
    threads.append((t, d))
    t.start()
    time.sleep(0.5)  # stagger connections

logging.info("[MAIN] All %d devices launched", len(devices))

# Keep main alive
try:
    while True:
        time.sleep(10)
        alive = sum(1 for _, d in threads if d.running)
        logging.info("[MAIN] %d/%d devices still connected", alive, len(devices))
except KeyboardInterrupt:
    logging.info("[MAIN] Interrupted, stopping...")
    for _, d in threads:
        d.stop()
    
logging.info("[MAIN] All devices stopped")
