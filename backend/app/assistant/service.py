"""Persistence for controlled assistant action previews.

This module deliberately creates only an auditable preview.  Confirmation and
business execution are introduced by later slices.
"""
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from hashlib import sha256
import json
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from pydantic import BaseModel, ValidationError
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.assistant.planner import ActionPlan
from app.assistant.registry import ActionDefinition, get_action
from app.assistant.schemas import ActionConfirmRequest, ActionPreview, ActionResult
from app.audit.service import AuditService
from app.deps import Principal
from app.models import ApprovalInstance, AssistantAction, Contract, Document, ExpenseClaim, Project, Ticket


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
    "update_project": Project,
    "delete_project": Project,
    "update_contract": Contract,
    "delete_contract": Contract,
    "update_document": Document,
    "delete_document": Document,
    "delete_ticket": Ticket,
}
ActionAdapter = Callable[[Session, Principal, dict[str, Any]], Any]
_ACTION_ADAPTERS: dict[str, ActionAdapter] = {}


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


def _row_snapshot(row: Any) -> str:
    """Hash every persisted scalar target attribute for models without a revision field."""
    material = {column.name: _normalize_json(getattr(row, column.name)) for column in row.__table__.columns}
    encoded = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return "snapshot:" + sha256(encoded).hexdigest()


def _object_versions(db: Session, definition: ActionDefinition, payload: dict[str, Any]) -> dict[str, int | str]:
    """Resolve a target revision or deterministic snapshot for a mutable action."""
    model = _VERSIONED_ACTION_MODELS.get(definition.name)
    object_id = payload.get("id")
    if model is None or not isinstance(object_id, str):
        return {}
    row = db.get(model, object_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assistant action target was not found")
    version = getattr(row, "version", None) if row is not None else None
    return {object_id: version} if isinstance(version, int) else {object_id: _row_snapshot(row)}


def _parameter_hash(
    tool_name: str,
    payload: dict[str, Any],
    department_ids: tuple[str, ...],
    object_versions: dict[str, int | str],
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
        confirmation_step=0,
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
            "confirmation_step": 0,
            "requires_confirmation": requires_confirmation,
            "confirmation_steps_required": confirmation_steps_required,
            "expires_at": expires_at,
        },
    )
    return preview


def register_action_adapter(tool_name: str, adapter: ActionAdapter) -> None:
    """Register a server-owned adapter for one exact catalog action name."""
    if get_action(tool_name) is None:
        raise ValueError("assistant action is not registered")
    if not callable(adapter):
        raise TypeError("assistant action adapter must be callable")
    _ACTION_ADAPTERS[tool_name] = adapter


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _refresh_action(db: Session, action: AssistantAction) -> AssistantAction:
    db.expire(action)
    db.refresh(action)
    return action


def _conditional_transition(
    db: Session,
    action: AssistantAction,
    *,
    expected_status: str,
    expected_step: int,
    new_status: str,
    new_step: int | None = None,
    executed_at: datetime | None = None,
) -> bool:
    """Atomically move an action forward only if its persisted lifecycle state still matches."""
    values: dict[str, Any] = {"status": new_status, "updated_at": _now_utc()}
    if new_step is not None:
        values["confirmation_step"] = new_step
    if executed_at is not None:
        values["executed_at"] = executed_at
    result = db.execute(
        update(AssistantAction)
        .where(
            AssistantAction.id == action.id,
            AssistantAction.status == expected_status,
            AssistantAction.confirmation_step == expected_step,
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    _refresh_action(db, action)
    return result.rowcount == 1


def _is_expired(action: AssistantAction) -> bool:
    if action.expires_at is None:
        return False
    expires_at = action.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= _now_utc()


def is_confirmation_valid(
    action: AssistantAction, principal: Principal, request: ActionConfirmRequest
) -> tuple[bool, str | None]:
    """Check request-bound confirmation facts that do not require a database read."""
    if action.user_id != principal.user_id:
        return False, "owner_mismatch"
    batch_second_confirmation = (
        action.risk_level == "batch" and action.status == "confirmed" and action.confirmation_step == 1
    )
    if action.status != "preview" and not batch_second_confirmation:
        return False, "confirmation_not_available"
    if request.action_id != action.id:
        return False, "action_id_mismatch"
    if request.parameter_hash != action.parameter_hash:
        return False, "parameter_hash_mismatch"
    if action.confirmation_phrase != request.confirmation_phrase:
        return False, "confirmation_phrase_mismatch"
    if _is_expired(action):
        return False, "action_expired"
    return True, None


def _result(
    action: AssistantAction, *, status_value: str | None = None, error_code: str | None = None
) -> ActionResult:
    return ActionResult(
        action_id=action.id,
        status=status_value or action.status,
        result=action.result_json,
        error_code=error_code if error_code is not None else action.error_code,
    )


def _preview_from_action(action: AssistantAction, definition: ActionDefinition) -> ActionPreview:
    """Rebuild the public preview from persisted data after a batch confirmation."""
    preview_data = dict(action.preview_json or {})
    return ActionPreview(
        action_id=action.id,
        tool_name=action.tool_name,
        risk_level=definition.risk_level,
        summary=str(preview_data.get("summary", action.tool_name)),
        changes=preview_data.get("changes", []),
        confirmation_phrase=action.confirmation_phrase,
        requires_confirmation=_CONFIRMATION_POLICY[definition.risk_level][1],
        confirmation_step=action.confirmation_step,
        confirmation_steps_required=_CONFIRMATION_POLICY[definition.risk_level][2],
        expires_at=action.expires_at,
        parameter_hash=action.parameter_hash,
    )


def _record_rejection(db: Session, principal: Principal, action: AssistantAction, error_code: str) -> None:
    AuditService.record(
        db,
        principal,
        "assistant_action_confirmation_rejected",
        "assistant_action",
        action.id,
        after={"error_code": error_code},
    )


def _expire_action(db: Session, principal: Principal, action: AssistantAction) -> ActionResult:
    if action.status in {"preview", "confirmed"} and _conditional_transition(
        db,
        action,
        expected_status=action.status,
        expected_step=action.confirmation_step,
        new_status="expired",
    ):
        action.error_code = "action_expired"
        AuditService.record(
            db,
            principal,
            "assistant_action_expired",
            "assistant_action",
            action.id,
            after={"error_code": action.error_code},
        )
    return _result(action, error_code="action_expired")


def _current_action_state(
    db: Session, principal: Principal, action: AssistantAction
) -> tuple[ActionDefinition | None, dict[str, Any] | None, str | None]:
    """Revalidate mutable action constraints before confirmation or execution."""
    definition = get_action(action.tool_name)
    if definition is None or definition.risk_level != action.risk_level:
        return None, None, "action_definition_changed"
    if not principal.has_role(*definition.required_roles):
        return definition, None, "permission_denied"
    try:
        validated_input = definition.input_model.model_validate(action.payload_json)
        payload = _normalize_json(validated_input)
    except (ValidationError, TypeError, ValueError):
        return definition, None, "invalid_action_payload"

    try:
        current_versions = _object_versions(db, definition, payload)
    except HTTPException:
        return definition, None, "object_version_changed"
    if current_versions != (action.object_versions_json or {}):
        return definition, None, "object_version_changed"
    expected_hash = _parameter_hash(definition.name, payload, principal.department_ids, current_versions)
    if expected_hash != action.parameter_hash:
        return definition, None, "parameter_hash_mismatch"
    return definition, payload, None


def confirm_action(
    db: Session, principal: Principal, action_id: str, request: ActionConfirmRequest
) -> ActionResult | ActionPreview:
    """Reject confirmation requests whose saved request binding no longer matches."""
    action = db.get(AssistantAction, action_id)
    if action is None:
        return ActionResult(action_id=action_id, status="failed", error_code="action_not_found")
    if action.user_id != principal.user_id:
        _record_rejection(db, principal, action, "owner_mismatch")
        return _result(action, status_value="failed", error_code="owner_mismatch")
    if action.status == "completed":
        return _result(action)
    if action.status in {"cancelled", "executing", "expired", "failed"}:
        return _result(action)

    valid, error_code = is_confirmation_valid(action, principal, request)
    if not valid:
        if error_code == "action_expired":
            return _expire_action(db, principal, action)
        _record_rejection(db, principal, action, error_code or "invalid_confirmation")
        return _result(action, status_value="failed", error_code=error_code)

    definition, _payload, state_error = _current_action_state(db, principal, action)
    if state_error is not None:
        _record_rejection(db, principal, action, state_error)
        return _result(action, status_value="failed", error_code=state_error)
    assert definition is not None
    _phrase, requires_confirmation, steps_required = _CONFIRMATION_POLICY[definition.risk_level]
    if not requires_confirmation:
        _record_rejection(db, principal, action, "confirmation_not_required")
        return _result(action, status_value="failed", error_code="confirmation_not_required")

    if definition.risk_level == "batch":
        if action.status == "preview" and action.confirmation_step == 0:
            next_step = 1
        elif action.status == "confirmed" and action.confirmation_step == 1:
            next_step = 2
        else:
            _record_rejection(db, principal, action, "confirmation_not_available")
            return _result(action, status_value="failed", error_code="confirmation_not_available")
    elif action.status == "preview" and action.confirmation_step == 0:
        next_step = 1
    else:
        _record_rejection(db, principal, action, "confirmation_not_available")
        return _result(action, status_value="failed", error_code="confirmation_not_available")

    if not _conditional_transition(
        db,
        action,
        expected_status=action.status,
        expected_step=action.confirmation_step,
        new_status="confirmed",
        new_step=next_step,
    ):
        return _result(action)
    AuditService.record(
        db,
        principal,
        "assistant_action_confirmed",
        "assistant_action",
        action.id,
        after={"confirmation_step": next_step, "confirmation_steps_required": steps_required},
    )
    if next_step < steps_required:
        return _preview_from_action(action, definition)

    action.confirmed_at = _now_utc()
    return execute_action(db, principal, action.id, confirmation_phrase=request.confirmation_phrase)


def cancel_action(db: Session, principal: Principal, action_id: str) -> ActionResult:
    """Cancel a caller-owned nonterminal action without committing the transaction."""
    action = db.get(AssistantAction, action_id)
    if action is None:
        return ActionResult(action_id=action_id, status="failed", error_code="action_not_found")
    if action.user_id != principal.user_id:
        _record_rejection(db, principal, action, "owner_mismatch")
        return _result(action, status_value="failed", error_code="owner_mismatch")
    if action.status not in {"preview", "confirmed"}:
        return _result(action)
    if not _conditional_transition(
        db,
        action,
        expected_status=action.status,
        expected_step=action.confirmation_step,
        new_status="cancelled",
    ):
        return _result(action)
    action.error_code = None
    AuditService.record(
        db,
        principal,
        "assistant_action_cancelled",
        "assistant_action",
        action.id,
    )
    return _result(action)


def _normalized_adapter_result(value: Any) -> dict[str, Any]:
    normalized = _normalize_json(value)
    return normalized if isinstance(normalized, dict) else {"value": normalized}


class _AdapterSession:
    """Expose normal session operations while preventing adapters from owning the transaction."""

    _FORBIDDEN = frozenset({"begin", "begin_nested", "close", "commit", "rollback"})

    def __init__(self, db: Session):
        self._db = db

    def __getattr__(self, name: str) -> Any:
        if name in self._FORBIDDEN:
            raise RuntimeError("assistant action adapters must not control transactions")
        return getattr(self._db, name)


def execute_action(
    db: Session, principal: Principal, action_id: str, *, confirmation_phrase: str | None = None
) -> ActionResult:
    """Execute only an explicitly registered adapter after fresh fail-closed checks."""
    action = db.get(AssistantAction, action_id)
    if action is None:
        return ActionResult(action_id=action_id, status="failed", error_code="action_not_found")
    if action.user_id != principal.user_id:
        _record_rejection(db, principal, action, "owner_mismatch")
        return _result(action, status_value="failed", error_code="owner_mismatch")
    if action.status == "completed":
        return _result(action)
    if action.status in {"cancelled", "expired", "failed"}:
        return _result(action)
    if _is_expired(action):
        return _expire_action(db, principal, action)

    definition, payload, state_error = _current_action_state(db, principal, action)
    if state_error is not None:
        _record_rejection(db, principal, action, state_error)
        return _result(action, status_value="failed", error_code=state_error)
    assert definition is not None and payload is not None

    if definition.risk_level == "low":
        expected_status, expected_step = "preview", 0
    elif action.status != "confirmed" or action.confirmation_step != _CONFIRMATION_POLICY[definition.risk_level][2]:
        _record_rejection(db, principal, action, "confirmation_required")
        return _result(action, status_value="failed", error_code="confirmation_required")
    else:
        expected_status, expected_step = "confirmed", action.confirmation_step
    if definition.risk_level != "low" and action.confirmation_phrase != confirmation_phrase:
        _record_rejection(db, principal, action, "confirmation_phrase_mismatch")
        return _result(action, status_value="failed", error_code="confirmation_phrase_mismatch")

    if not _conditional_transition(
        db,
        action,
        expected_status=expected_status,
        expected_step=expected_step,
        new_status="executing",
        executed_at=_now_utc(),
    ):
        return _result(action)

    adapter = _ACTION_ADAPTERS.get(action.tool_name)
    if adapter is None:
        action.status = "failed"
        action.error_code = "unsupported_action"
        AuditService.record(
            db,
            principal,
            "assistant_action_failed",
            "assistant_action",
            action.id,
            after={"error_code": action.error_code},
        )
        return _result(action)

    AuditService.record(db, principal, "assistant_action_execution_started", "assistant_action", action.id)
    try:
        with db.begin_nested():
            action.result_json = _normalized_adapter_result(adapter(_AdapterSession(db), principal, payload))
    except Exception:
        action.status = "failed"
        action.error_code = "execution_failed"
        AuditService.record(
            db,
            principal,
            "assistant_action_failed",
            "assistant_action",
            action.id,
            after={"error_code": action.error_code},
        )
        return _result(action)

    action.status = "completed"
    action.error_code = None
    AuditService.record(
        db,
        principal,
        "assistant_action_completed",
        "assistant_action",
        action.id,
        after={"result": action.result_json},
    )
    return _result(action)
