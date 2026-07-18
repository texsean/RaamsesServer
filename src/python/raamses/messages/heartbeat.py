from dataclasses import dataclass
from typing import Optional

@dataclass
class Heartbeat:
    uptime_seconds: int
    battery_percent: Optional[int] = None
    signal_strength: Optional[int] = None
    free_memory_kb: Optional[int] = None

    def to_dict(self) -> dict:
        data = {"uptime_seconds": self.uptime_seconds}
        if self.battery_percent is not None: data["battery_percent"] = self.battery_percent
        if self.signal_strength is not None: data["signal_strength"] = self.signal_strength
        if self.free_memory_kb is not None: data["free_memory_kb"] = self.free_memory_kb
        return data
