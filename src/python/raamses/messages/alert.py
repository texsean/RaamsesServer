from dataclasses import dataclass
from typing import Optional


@dataclass
class Alert:
    severity: str
    title: str
    message: str
    requires_ack: Optional[bool] = None
    vibrate: Optional[bool] = None

    def to_dict(self) -> dict:
        data = {"severity": self.severity, "title": self.title, "message": self.message}
        if self.requires_ack is not None:
            data["requires_ack"] = self.requires_ack
        if self.vibrate is not None:
            data["vibrate"] = self.vibrate
        return data
