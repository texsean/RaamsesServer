"""
Raamses Envelope - Core message wrapper with SchemaVersion support.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import uuid


@dataclass
class Header:
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    device_id: str = ""
    schema_version: str = "1.0"
    version: str = "1.0"

    def to_dict(self) -> dict:
        return {
            "message_id": self.message_id,
            "timestamp": self.timestamp.isoformat(),
            "device_id": self.device_id,
            "schema_version": self.schema_version,
            "version": self.version,
        }


@dataclass
class RaamsesMessage:
    header: Header
    payload: object

    @classmethod
    def create(cls, device_id: str, schema_version: str, payload: object) -> "RaamsesMessage":
        header = Header(device_id=device_id, schema_version=schema_version)
        return cls(header=header, payload=payload)

    def is_compatible_with(self, device_schema_version: str) -> bool:
        try:
            msg_ver = tuple(map(int, self.header.schema_version.split(".")))
            dev_ver = tuple(map(int, device_schema_version.split(".")))
            return msg_ver <= dev_ver
        except Exception:
            return True
