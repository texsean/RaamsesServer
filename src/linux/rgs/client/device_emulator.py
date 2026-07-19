"""
Configurable Device Emulator

Allows us to emulate different hardware devices with varying/limited capabilities
for testing the server and protocol.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import uuid


@dataclass
class DeviceProfile:
    """Defines the capabilities and limitations of an emulated device."""
    name: str
    device_type: str
    schema_version: str = "1.0"
    screen: Optional[Dict[str, Any]] = None      # width, height, color_depth, refresh_type
    input: Optional[Dict[str, Any]] = None       # has_touch, has_buttons, button_count
    output: Optional[Dict[str, Any]] = None      # has_vibration, has_led, has_speaker
    power: Optional[Dict[str, Any]] = None       # has_battery
    max_message_size: Optional[int] = None       # simulate limited devices


# Predefined profiles for common hardware
DEVICE_PROFILES = {
    "cyd_320x240_color": DeviceProfile(
        name="CYD 2.8\" Color",
        device_type="cyd",
        schema_version="1.0",
        screen={"width": 320, "height": 240, "color_depth": 16, "refresh_type": "lcd"},
        input={"has_touch": True, "has_buttons": False},
        output={"has_vibration": False},
        power={"has_battery": False},
    ),
    "epaper_200x200_1bit": DeviceProfile(
        name="E-Paper 200x200 1-bit",
        device_type="epaper",
        schema_version="1.0",
        screen={"width": 200, "height": 200, "color_depth": 1, "refresh_type": "epaper"},
        input={"has_buttons": True, "button_count": 2},
        output={"has_vibration": False},
        power={"has_battery": True},
    ),
    "watch_small": DeviceProfile(
        name="Smart Watch (Small)",
        device_type="watch",
        schema_version="1.0",
        screen={"width": 120, "height": 120, "color_depth": 16},
        input={"has_buttons": True, "button_count": 1},
        output={"has_vibration": True},
        power={"has_battery": True},
    ),
    "limited_old_device": DeviceProfile(
        name="Old Limited Device",
        device_type="legacy",
        schema_version="1.0",
        screen={"width": 128, "height": 64, "color_depth": 1},
        input={"has_buttons": True, "button_count": 3},
        output={},
        power={"has_battery": True},
        max_message_size=256,
    ),
}
