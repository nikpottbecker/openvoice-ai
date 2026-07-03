from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


Intent = Literal["appointment", "callback", "message", "spam", "unknown"]


class Appointment(BaseModel):
    name: str | None = None
    date: str | None = None
    time: str | None = None
    topic: str | None = None
    phone: str | None = None
    confirmed: bool = False

    @property
    def complete(self) -> bool:
        return bool(self.name and self.date and self.time and self.topic and self.phone and self.confirmed)

    def missing_fields(self) -> list[str]:
        missing = []
        if not self.name:
            missing.append("name")
        if not self.date:
            missing.append("date")
        if not self.time:
            missing.append("time")
        if not self.topic:
            missing.append("topic")
        if not self.phone:
            missing.append("phone")
        if not self.confirmed:
            missing.append("confirmed")
        return missing


class AgentState(BaseModel):
    call_id: str
    caller_id: str
    caller_name: str | None = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    intent: Intent = "unknown"
    appointment: Appointment = Field(default_factory=Appointment)
    transcript: list[dict[str, str]] = Field(default_factory=list)
    summary: str = ""
    llm_rounds: int = 0
    expected_slot: str | None = None
    slot_failures: dict[str, int] = Field(default_factory=dict)
    ended: bool = False


class LLMResult(BaseModel):
    reply: str
    intent: Intent = "unknown"
    appointment: Appointment = Field(default_factory=Appointment)
    summary: str = ""
    should_end_call: bool = False
    action: dict[str, Any] | None = None
