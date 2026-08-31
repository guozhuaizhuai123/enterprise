from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


ActionRisk = Literal["low", "sensitive", "high", "batch"]
ActionStatus = Literal[
    "preview",
    "confirmed",
    "executing",
    "completed",
    "cancelled",
    "expired",
    "failed",
]


class ActionChange(BaseModel):
    field: str
    before: object | None = None
    after: object | None = None


class ActionPreview(BaseModel):
    action_id: str
    tool_name: str
    risk_level: ActionRisk
    summary: str
    changes: list[ActionChange] = Field(default_factory=list)
    confirmation_phrase: str | None = None
    requires_confirmation: bool = True
    confirmation_step: int = 0
    confirmation_steps_required: int = 1
    expires_at: datetime | None = None
    parameter_hash: str | None = None


class ActionConfirmRequest(BaseModel):
    action_id: str
    confirmation_phrase: str
    parameter_hash: str


class ActionResult(BaseModel):
    action_id: str
    status: ActionStatus
    result: dict | None = None
    error_code: str | None = None
