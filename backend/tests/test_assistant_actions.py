from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.assistant.planner import ActionPlan
from app.assistant import registry
from app.assistant.registry import ActionDefinition, get_action
from app.assistant.schemas import ActionChange, ActionPreview, ActionResult
from app.assistant.service import create_preview
from app.deps import Principal
from app.models import AssistantAction, AuditLog, ExpenseClaim, Project


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _principal(*, role="admin", department_ids=("dept-a",)):
    return Principal(
        user_id="admin",
        username="administrator",
        role=role,
        department_id=department_ids[0] if department_ids else None,
        department_ids=department_ids,
    )


def _plan(action_name, payload):
    action = get_action(action_name)
    assert action is not None
    return ActionPlan(action=action, input=action.input_model.model_validate(payload))


def test_create_preview_persists_metadata_with_five_minute_ttl_without_business_entity(db):
    """Removing preview persistence or calling the action handler would lose auditability or create a project."""
    before = datetime.now(timezone.utc)

    preview = create_preview(
        db,
        _principal(),
        "thread-1",
        _plan("create_project", {"code": "KB-1", "name": "知识库"}),
    )

    action = db.get(AssistantAction, preview.action_id)
    assert action is not None
    assert action.status == "preview"
    assert action.payload_json == {"code": "KB-1", "name": "知识库", "type": "internal", "status": "preparing", "department_id": None, "manager_id": None, "start_date": None, "end_date": None, "budget": None, "description": ""}
    assert action.preview_json["confirmation_phrase"] == "确认执行"
    assert action.parameter_hash == preview.parameter_hash
    assert action.expires_at is not None
    assert abs((preview.expires_at - before).total_seconds() - 300) < 2
    assert db.query(Project).count() == 0
    assert db.query(AuditLog).filter(AuditLog.action == "assistant_action_previewed").count() == 1


def test_create_preview_hash_is_stable_for_semantic_json_and_bound_to_department_scope(db):
    """Dropping canonical JSON or department scope from the hash would allow stale confirmation reuse."""
    first = create_preview(
        db,
        _principal(department_ids=("dept-b", "dept-a")),
        "thread-1",
        _plan("create_project", {"name": "知识库", "code": "KB-1"}),
    )
    second = create_preview(
        db,
        _principal(department_ids=("dept-a", "dept-b")),
        "thread-1",
        _plan("create_project", {"code": "KB-1", "name": "知识库"}),
    )
    other_scope = create_preview(
        db,
        _principal(department_ids=("dept-c",)),
        "thread-1",
        _plan("create_project", {"code": "KB-1", "name": "知识库"}),
    )

    assert first.parameter_hash == second.parameter_hash
    assert first.parameter_hash != other_scope.parameter_hash


def test_create_preview_binds_hash_to_current_supported_object_version(db):
    """Removing object-version binding would allow confirmation after the expense changed."""
    expense = ExpenseClaim(
        id="expense-1",
        claim_no="EXP-001",
        requester_id="admin",
        title="差旅行程",
    )
    db.add(expense)
    db.flush()
    payload = {
        "id": expense.id,
        "payment_date": date(2026, 8, 31),
        "method": "bank_transfer",
        "idempotency_key": "payment-key-1",
        "expected_version": 1,
    }

    first = create_preview(db, _principal(), "thread-1", _plan("pay_expense", payload))
    expense.version = 2
    db.flush()
    second = create_preview(db, _principal(), "thread-1", _plan("pay_expense", payload))

    first_action = db.get(AssistantAction, first.action_id)
    second_action = db.get(AssistantAction, second.action_id)
    assert first_action is not None
    assert second_action is not None
    assert first_action.object_versions_json == {"expense-1": 1}
    assert second_action.object_versions_json == {"expense-1": 2}
    assert first.parameter_hash != second.parameter_hash


def test_create_preview_rejects_role_mismatch_before_persistence(db):
    """Removing the service-side role check would let a forged plan persist a privileged preview."""
    with pytest.raises(HTTPException) as exc_info:
        create_preview(
            db,
            _principal(role="employee"),
            "thread-1",
            _plan("create_org_unit", {"name": "研发", "code": "RND"}),
        )

    assert getattr(exc_info.value, "status_code", None) == 403
    assert db.query(AssistantAction).count() == 0


def test_create_preview_audit_redacts_secret_shaped_payload_keys(db, monkeypatch):
    """Passing raw secrets to audit metadata would expose them in the audit log."""
    class SecretPayload(BaseModel):
        api_token: str
        label: str

    action = ActionDefinition(
        name="create_project",
        input_model=SecretPayload,
        required_roles=("admin",),
        risk_level="high",
        preview=lambda: None,
        execute=lambda: None,
    )
    monkeypatch.setitem(registry._ACTION_BY_NAME, action.name, action)

    preview = create_preview(
        db,
        _principal(),
        "thread-1",
        ActionPlan(action=action, input=SecretPayload(api_token="top-secret", label="知识库")),
    )

    audit = db.query(AuditLog).filter(AuditLog.entity_id == preview.action_id).one()
    assert audit.after_data["payload"] == {"api_token": "[REDACTED]", "label": "知识库"}


@pytest.mark.parametrize(
    ("action_name", "payload", "phrase", "requires_confirmation", "steps"),
    [
        ("list_projects", {}, None, False, 0),
        ("search_knowledge", {}, "确认查看", True, 1),
        ("create_org_unit", {"name": "研发", "code": "RND"}, "确认执行", True, 1),
        ("generate_payroll", {}, "确认批量执行", True, 2),
    ],
)
def test_create_preview_applies_confirmation_policy(action_name, payload, phrase, requires_confirmation, steps, db):
    """Changing a risk policy branch must change the preview's confirmation metadata."""
    preview = create_preview(db, _principal(), "thread-1", _plan(action_name, payload))

    assert preview.confirmation_phrase == phrase
    assert preview.requires_confirmation is requires_confirmation
    assert preview.confirmation_step == 0
    assert preview.confirmation_steps_required == steps


def test_action_preview_stores_hash_and_expires(db):
    """Removing a preview's hash or expiry must break confirmation preconditions."""
    action = AssistantAction(
        id="act-1",
        thread_id="thread-1",
        user_id="admin",
        tool_name="create_project",
        risk_level="high",
        status="preview",
        payload_json={"name": "研发平台"},
        preview_json={"summary": "新建研发平台"},
        parameter_hash="sha256:expected",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        idempotency_key="idem-act-1",
    )
    db.add(action)
    db.commit()

    assert action.status == "preview"
    assert action.parameter_hash == "sha256:expected"
    assert action.expires_at is not None


def test_idempotency_key_is_unique_per_user(db):
    """Dropping user-scoped idempotency would allow duplicate business execution."""
    first = AssistantAction(
        id="act-1",
        user_id="admin",
        tool_name="create_project",
        risk_level="high",
        status="preview",
        idempotency_key="same-key",
    )
    second = AssistantAction(
        id="act-2",
        user_id="admin",
        tool_name="create_project",
        risk_level="high",
        status="preview",
        idempotency_key="same-key",
    )
    db.add_all([first, second])

    with pytest.raises(IntegrityError):
        db.commit()


def test_action_protocol_rejects_unknown_risk_levels():
    """Relaxing the public risk enum would let callers bypass confirmation policy."""
    preview = ActionPreview(
        action_id="act-1",
        tool_name="create_project",
        risk_level="high",
        summary="新建研发平台",
        changes=[ActionChange(field="name", before=None, after="研发平台")],
    )
    assert preview.risk_level == "high"

    with pytest.raises(ValueError):
        ActionPreview(
            action_id="act-2",
            tool_name="create_project",
            risk_level="unrestricted",
            summary="新建研发平台",
        )


def test_action_result_exposes_terminal_status_and_error():
    """Removing result status or error code would hide an action's execution outcome."""
    result = ActionResult(
        action_id="act-1",
        status="failed",
        error_code="version_conflict",
    )
    assert result.status == "failed"
    assert result.error_code == "version_conflict"
