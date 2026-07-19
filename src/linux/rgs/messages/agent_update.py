from dataclasses import dataclass
from typing import Optional


@dataclass
class TokenUsage:
    total: Optional[int] = None
    last_hour: Optional[int] = None
    today: Optional[int] = None


@dataclass
class AgentUpdate:
    agent_id: str
    status: str
    token_usage: Optional[TokenUsage] = None
    sub_agent_count: Optional[int] = None
    needs_human_input: Optional[bool] = None

    def to_dict(self) -> dict:
        data = {"agent_id": self.agent_id, "status": self.status}
        if self.token_usage:
            data["token_usage"] = {k: v for k, v in self.token_usage.__dict__.items() if v is not None}
        if self.sub_agent_count is not None:
            data["sub_agent_count"] = self.sub_agent_count
        if self.needs_human_input is not None:
            data["needs_human_input"] = self.needs_human_input
        return data
