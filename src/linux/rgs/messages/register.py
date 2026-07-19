from dataclasses import dataclass
from typing import Optional


@dataclass
class Capabilities:
    screen: Optional[dict] = None
    input: Optional[dict] = None
    output: Optional[dict] = None
    power: Optional[dict] = None

    def to_dict(self) -> dict:
        result = {}
        if self.screen: result["screen"] = self.screen
        if self.input: result["input"] = self.input
        if self.output: result["output"] = self.output
        if self.power: result["power"] = self.power
        return result


@dataclass
class Register:
    device_id: str
    schema_version: str
    device_type: str
    firmware_version: Optional[str] = None
    capabilities: Optional[Capabilities] = None

    def to_dict(self) -> dict:
        data = {
            "device_id": self.device_id,
            "schema_version": self.schema_version,
            "device_type": self.device_type,
        }
        if self.firmware_version:
            data["firmware_version"] = self.firmware_version
        if self.capabilities:
            data["capabilities"] = self.capabilities.to_dict()
        return data


@dataclass
class RegisterAck:
    accepted: bool
    server_time: str
    schema_version: Optional[str] = None
    assigned_tier: Optional[str] = None
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        data = {"accepted": self.accepted, "server_time": self.server_time}
        if self.schema_version: data["schema_version"] = self.schema_version
        if self.assigned_tier: data["assigned_tier"] = self.assigned_tier
        if self.error_message: data["error_message"] = self.error_message
        return data
