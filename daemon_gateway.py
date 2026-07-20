#!/usr/bin/env python3
"""RGS Gateway Server daemon - runs in foreground (for background process)."""
import sys, signal, os, logging, sys

sys.path.insert(0, 'src/linux')
signal.signal(signal.SIGINT, signal.SIG_IGN)

# Configure logging BEFORE importing gateway
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.FileHandler('gateway.log'),
        logging.StreamHandler(),
    ],
)

from rgs.server.gateway import GatewayServer

logging.getLogger('rgs').setLevel(logging.INFO)
logging.info("Starting RGS Gateway daemon on port 8765")
gateway = GatewayServer(port=8765, heartbeat_timeout=90)
gateway.start()
