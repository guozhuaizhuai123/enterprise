from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class BusinessEvent(BaseModel):
    """Stable SSE envelope for non-RAG conversational business results."""

    model_config = ConfigDict(extra="forbid")

    node: Literal["query_result", "form_preview", "navigation", "action_preview", "clarification"]
    status: Literal["ready", "completed"]
    kind: Literal["business"] = "business"
    intent: str
    display: str
    payload: dict[str, Any] = Field(default_factory=dict)
    route_key: str | None = None
    form: Literal["leave", "ticket", "expense"] | None = None
    preview: dict[str, Any] | None = None
    tool_name: str | None = None
    result: dict[str, Any] | None = None
    action_id: str | None = None
    risk_level: ActionRisk | None = None
    summary: str | None = None
    changes: list[ActionChange] | None = None
    confirmation_phrase: str | None = None
    requires_confirmation: bool | None = None
    confirmation_step: int | None = None
    confirmation_steps_required: int | None = None
    expires_at: datetime | None = None
    parameter_hash: str | None = None

    @model_validator(mode="after")
    def validate_node_contract(self) -> "BusinessEvent":
        status_by_node = {
            "query_result": "completed",
            "form_preview": "ready",
            "navigation": "ready",
            "action_preview": "ready",
            "clarification": "ready",
        }
        if self.status != status_by_node[self.node]:
            raise ValueError("business event status does not match node")

        compatibility_fields = {
            "route_key",
            "form",
            "preview",
            "tool_name",
            "result",
            "action_id",
            "risk_level",
            "summary",
            "changes",
            "confirmation_phrase",
            "requires_confirmation",
            "confirmation_step",
            "confirmation_steps_required",
            "expires_at",
            "parameter_hash",
        }
        allowed_by_node = {
            "query_result": {"tool_name", "result"},
            "form_preview": {"form", "preview"},
            "navigation": {"route_key"},
            "action_preview": {
                "action_id",
                "tool_name",
                "risk_level",
                "summary",
                "changes",
                "confirmation_phrase",
                "requires_confirmation",
                "confirmation_step",
                "confirmation_steps_required",
                "expires_at",
                "parameter_hash",
            },
            "clarification": set(),
        }
        supplied = self.model_fields_set & compatibility_fields
        if not supplied <= allowed_by_node[self.node]:
            raise ValueError("business event compatibility fields do not match node")
        return self
