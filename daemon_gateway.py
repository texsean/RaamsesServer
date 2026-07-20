#!/usr/bin/env python3
"""RGS Gateway Server daemon - runs in foreground (for background process)."""
import sys, signal, os, logging
sys.path.insert(0, 'src/linux')
signal.signal(signal.SIGINT, signal.SIG_IGN)

logging.basicConfig(
    filename='gateway.log',
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger('rgs_gateway')

from rgs.server.gateway import GatewayServer

logger.info("Starting RGS Gateway daemon on port 8765")
gateway = GatewayServer(port=8765, heartbeat_timeout=90)
gateway.start()
