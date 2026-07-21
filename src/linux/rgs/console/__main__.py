"""RADAR entry point — run as `python -m rgs.console.radar` or here."""
import sys
import os

# Add parent directory so `from rgs.console.radar` resolves.
# This file lives at src/linux/rgs/console/__main__.py
_rgs_parent = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/linux/
if _rgs_parent not in sys.path:
    sys.path.insert(0, _rgs_parent)

from rgs.console.radar import main
main()
