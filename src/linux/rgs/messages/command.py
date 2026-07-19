from dataclasses import dataclass
from typing import Optional


@dataclass
class Command:
    command_id: str
    action: str
    payload: Optional[str] = None

    def to_dict(self) -> dict:
        data = {"command_id": self.command_id, "action": self.action}
        if self.payload:
            data["payload"] = self.payload
        return data


@dataclass
class CommandResult:
    command_id: str
    success: bool
    message: Optional[str] = None

    def to_dict(self) -> dict:
        data = {"command_id": self.command_id, "success": self.success}
        if self.message:
            data["message"] = self.message
        return data
