"""RADAR — Raamses Agent Display And Reporter"""
import sys, os
# Add parent directories to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'linux'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from rgs.console.radar import main
main()
