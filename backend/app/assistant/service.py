"""Persistence for controlled assistant action previews.

This module deliberately creates only an auditable preview.  Confirmation and
business execution are introduced by later slices.
"""
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from hashlib import sha256
import json
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.assistant.planner import ActionPlan
from app.assistant.registry import ActionDefinition, get_action
from app.assistant.schemas import ActionPreview
from app.audit.service import AuditService
from app.deps import Principal
from app.models import ApprovalInstance, AssistantAction, ExpenseClaim


_PREVIEW_TTL = timedelta(minutes=5)
_CONFIRMATION_POLICY: dict[str, tuple[str | None, bool, int]] = {
    "low": (None, False, 0),
    "sensitive": ("确认查看", True, 1),
    "high": ("确认执行", True, 1),
    "batch": ("确认批量执行", True, 2),
}
_VERSIONED_ACTION_MODELS = {
    "approve_approval": ApprovalInstance,
    "reject_approval": ApprovalInstance,
    "cancel_approval": ApprovalInstance,
    "update_expense_draft": ExpenseClaim,
    "delete_expense_draft": ExpenseClaim,
    "pay_expense": ExpenseClaim,
}


def _normalize_json(value: Any) -> Any:
    """Convert a validated payload to deterministic JSON-compatible values."""
    if isinstance(value, BaseModel):
        return _normalize_json(value.model_dump(mode="python"))
    if isinstance(value, Mapping):
        return {str(key): _normalize_json(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_normalize_json(item) for item in value]
    if isinstance(value, set):
        normalized = [_normalize_json(item) for item in value]
        return sorted(normalized, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat() if value.tzinfo else value.replace(tzinfo=UTC).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    if isinstance(value, Enum):
        return _normalize_json(value.value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"unsupported preview payload value: {type(value)!r}")


def _object_versions(db: Session, definition: ActionDefinition, payload: dict[str, Any]) -> dict[str, int]:
    """Resolve the optimistic-lock version for the one versioned target, if any."""
    model = _VERSIONED_ACTION_MODELS.get(definition.name)
    object_id = payload.get("id")
    if model is None or not isinstance(object_id, str):
        return {}
    row = db.get(model, object_id)
    version = getattr(row, "version", None) if row is not None else None
    return {object_id: version} if isinstance(version, int) else {}


def _parameter_hash(
    tool_name: str,
    payload: dict[str, Any],
    department_ids: tuple[str, ...],
    object_versions: dict[str, int],
) -> str:
    material = {
        "tool_name": tool_name,
        "payload": payload,
        "department_ids": sorted(department_ids),
        "object_versions": object_versions,
    }
    encoded = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return sha256(encoded).hexdigest()


def _registered_definition(plan: ActionPlan) -> ActionDefinition:
    definition = get_action(plan.action.name)
    if definition is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "assistant action is not registered")
    return definition


def create_preview(db: Session, principal: Principal, thread_id: str | None, plan: ActionPlan) -> ActionPreview:
    """Persist a non-executing action preview under the current principal's scope."""
    definition = _registered_definition(plan)
    if not principal.has_role(*definition.required_roles):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "principal is not authorized for this action")

    try:
        validated_input = definition.input_model.model_validate(plan.input.model_dump(mode="python"))
    except (AttributeError, ValidationError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "assistant action payload is invalid") from exc

    payload = _normalize_json(validated_input)
    object_versions = _object_versions(db, definition, payload)
    parameter_hash = _parameter_hash(definition.name, payload, principal.department_ids, object_versions)
    confirmation_phrase, requires_confirmation, confirmation_steps_required = _CONFIRMATION_POLICY[
        definition.risk_level
    ]
    expires_at = datetime.now(UTC) + _PREVIEW_TTL

    action = AssistantAction(
        thread_id=thread_id,
        user_id=principal.user_id,
        tool_name=definition.name,
        risk_level=definition.risk_level,
        status="preview",
        payload_json=payload,
        parameter_hash=parameter_hash,
        object_versions_json=object_versions,
        confirmation_phrase=confirmation_phrase,
        expires_at=expires_at,
        idempotency_key=str(uuid4()),
    )
    db.add(action)
    db.flush()

    preview = ActionPreview(
        action_id=action.id,
        tool_name=definition.name,
        risk_level=definition.risk_level,
        summary=definition.name,
        confirmation_phrase=confirmation_phrase,
        requires_confirmation=requires_confirmation,
        confirmation_step=0,
        confirmation_steps_required=confirmation_steps_required,
        expires_at=expires_at,
        parameter_hash=parameter_hash,
    )
    action.preview_json = preview.model_dump(mode="json")
    AuditService.record(
        db,
        principal,
        "assistant_action_previewed",
        "assistant_action",
        action.id,
        after={
            "tool_name": definition.name,
            "risk_level": definition.risk_level,
            "payload": payload,
            "parameter_hash": parameter_hash,
            "object_versions": object_versions,
            "confirmation_phrase": confirmation_phrase,
            "requires_confirmation": requires_confirmation,
            "confirmation_steps_required": confirmation_steps_required,
            "expires_at": expires_at,
        },
    )
    return preview
