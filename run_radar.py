#!/usr/bin/env python3
"""Launch RADAR live dashboard."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src', 'linux'))
from rgs.console.radar import main
main()
