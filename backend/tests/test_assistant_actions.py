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
import app.assistant.service as assistant_service
from app.assistant import registry
from app.assistant.registry import ActionDefinition, get_action, list_actions
from app.assistant.schemas import ActionChange, ActionConfirmRequest, ActionPreview, ActionResult
from app.assistant.service import create_preview
from app.deps import Principal
from app.models import AssistantAction, AuditLog, Department, ExpenseClaim, Project


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


def _other_principal():
    return Principal(
        user_id="other-admin",
        username="other-administrator",
        role="admin",
        department_id="dept-a",
        department_ids=("dept-a",),
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


def test_confirm_action_rejects_wrong_parameter_hash_and_audits_it(db):
    """Removing hash binding would allow one preview's approval to execute another request."""
    preview = create_preview(
        db,
        _principal(),
        "thread-1",
        _plan("create_project", {"code": "KB-1", "name": "知识库"}),
    )

    result = assistant_service.confirm_action(
        db,
        _principal(),
        preview.action_id,
        ActionConfirmRequest(
            action_id=preview.action_id,
            confirmation_phrase="确认执行",
            parameter_hash="wrong-hash",
        ),
    )

    assert result.status == "failed"
    assert result.error_code == "parameter_hash_mismatch"
    assert db.get(AssistantAction, preview.action_id).status == "preview"
    assert db.query(AuditLog).filter(AuditLog.action == "assistant_action_confirmation_rejected").count() == 1


def _confirmation(preview, phrase=None, parameter_hash=None):
    return ActionConfirmRequest(
        action_id=preview.action_id,
        confirmation_phrase=phrase if phrase is not None else preview.confirmation_phrase or "",
        parameter_hash=parameter_hash if parameter_hash is not None else preview.parameter_hash or "",
    )


def test_confirm_action_rejects_wrong_owner_phrase_and_expired_preview_with_audit(db):
    """Skipping any request binding check would let an unauthorized or stale preview execute."""
    wrong_owner = create_preview(db, _principal(), "thread-1", _plan("create_project", {"code": "KB-1", "name": "知识库"}))
    wrong_phrase = create_preview(db, _principal(), "thread-1", _plan("create_project", {"code": "KB-2", "name": "协作"}))
    expired = create_preview(db, _principal(), "thread-1", _plan("create_project", {"code": "KB-3", "name": "过期"}))
    db.get(AssistantAction, expired.action_id).expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    owner_result = assistant_service.confirm_action(
        db, _other_principal(), wrong_owner.action_id, _confirmation(wrong_owner)
    )
    phrase_result = assistant_service.confirm_action(
        db, _principal(), wrong_phrase.action_id, _confirmation(wrong_phrase, phrase="错误确认")
    )
    expired_result = assistant_service.confirm_action(db, _principal(), expired.action_id, _confirmation(expired))

    assert [owner_result.error_code, phrase_result.error_code, expired_result.error_code] == [
        "owner_mismatch",
        "confirmation_phrase_mismatch",
        "action_expired",
    ]
    assert db.query(AuditLog).filter(AuditLog.action == "assistant_action_confirmation_rejected").count() == 2
    assert db.query(AuditLog).filter(AuditLog.action == "assistant_action_expired").count() == 1


def test_confirm_action_rechecks_current_permission_and_object_version(db, monkeypatch):
    """Using preview-time authorization or versions would execute actions that are no longer valid."""
    privileged = create_preview(db, _principal(), "thread-1", _plan("create_project", {"code": "KB-1", "name": "知识库"}))
    definition = get_action("create_project")
    assert definition is not None
    monkeypatch.setitem(
        registry._ACTION_BY_NAME,
        "create_project",
        ActionDefinition(
            name=definition.name,
            input_model=definition.input_model,
            required_roles=("finance",),
            risk_level=definition.risk_level,
            preview=definition.preview,
            execute=definition.execute,
        ),
    )

    permission_result = assistant_service.confirm_action(db, _principal(), privileged.action_id, _confirmation(privileged))

    expense = ExpenseClaim(id="expense-1", claim_no="EXP-001", requester_id="admin", title="差旅行程")
    db.add(expense)
    db.flush()
    versioned = create_preview(
        db,
        _principal(),
        "thread-1",
        _plan(
            "pay_expense",
            {
                "id": expense.id,
                "payment_date": date(2026, 8, 31),
                "method": "bank_transfer",
                "idempotency_key": "payment-key-1",
                "expected_version": 1,
            },
        ),
    )
    expense.version = 2
    db.flush()
    version_result = assistant_service.confirm_action(db, _principal(), versioned.action_id, _confirmation(versioned))

    assert permission_result.error_code == "permission_denied"
    assert version_result.error_code == "object_version_changed"
    assert db.query(AuditLog).filter(AuditLog.action == "assistant_action_confirmation_rejected").count() == 2


def test_confirm_action_executes_high_once_and_batch_on_second_confirmation(db, monkeypatch):
    """Changing confirmation count or bypassing the adapter would execute the wrong number of times."""
    calls = []

    def adapter(db, principal, payload):
        calls.append((principal.user_id, payload))
        return {"call_count": len(calls)}

    monkeypatch.setattr(assistant_service, "_ACTION_ADAPTERS", {}, raising=False)
    assistant_service.register_action_adapter("create_project", adapter)
    assistant_service.register_action_adapter("generate_payroll", adapter)
    high = create_preview(db, _principal(), "thread-1", _plan("create_project", {"code": "KB-1", "name": "知识库"}))
    batch = create_preview(db, _principal(), "thread-1", _plan("generate_payroll", {}))

    high_result = assistant_service.confirm_action(db, _principal(), high.action_id, _confirmation(high))
    first_batch_confirmation = assistant_service.confirm_action(db, _principal(), batch.action_id, _confirmation(batch))
    batch_result = assistant_service.confirm_action(db, _principal(), batch.action_id, _confirmation(batch))

    assert high_result.status == "completed"
    assert isinstance(first_batch_confirmation, ActionPreview)
    assert first_batch_confirmation.confirmation_step == 1
    assert batch_result.status == "completed"
    assert len(calls) == 2
    assert db.query(AuditLog).filter(AuditLog.action == "assistant_action_confirmed").count() == 3


def test_cancel_action_is_owner_only_and_idempotent(db):
    """Allowing another user to cancel or auditing every repeat would break action ownership and idempotency."""
    preview = create_preview(db, _principal(), "thread-1", _plan("create_project", {"code": "KB-1", "name": "知识库"}))

    wrong_user = assistant_service.cancel_action(db, _other_principal(), preview.action_id)
    first_cancel = assistant_service.cancel_action(db, _principal(), preview.action_id)
    second_cancel = assistant_service.cancel_action(db, _principal(), preview.action_id)

    assert wrong_user.error_code == "owner_mismatch"
    assert first_cancel.status == "cancelled"
    assert second_cancel.status == "cancelled"
    assert db.query(AuditLog).filter(AuditLog.action == "assistant_action_cancelled").count() == 1


def test_execute_action_fails_closed_without_adapter_and_uses_counting_adapter_once(db, monkeypatch):
    """Calling registry.execute or re-running a terminal action would bypass the explicit fail-closed boundary."""
    monkeypatch.setattr(assistant_service, "_ACTION_ADAPTERS", {}, raising=False)
    missing = create_preview(db, _principal(), "thread-1", _plan("create_project", {"code": "KB-1", "name": "知识库"}))
    missing_result = assistant_service.confirm_action(db, _principal(), missing.action_id, _confirmation(missing))

    calls = []

    def adapter(db, principal, payload):
        calls.append(payload)
        return {"created": payload["code"]}

    assistant_service.register_action_adapter("create_project", adapter)
    completed = create_preview(db, _principal(), "thread-1", _plan("create_project", {"code": "KB-2", "name": "协作"}))
    completed_result = assistant_service.confirm_action(db, _principal(), completed.action_id, _confirmation(completed))
    repeat_result = assistant_service.execute_action(db, _principal(), completed.action_id)

    assert missing_result.status == "failed"
    assert missing_result.error_code == "unsupported_action"
    assert completed_result.result == {"created": "KB-2"}
    assert repeat_result == completed_result
    assert len(calls) == 1
    assert db.query(AuditLog).filter(AuditLog.action == "assistant_action_failed").count() == 1


def test_low_risk_action_executes_without_confirmation(db, monkeypatch):
    """Requiring confirmation for low-risk reads would violate the configured lifecycle."""
    monkeypatch.setattr(assistant_service, "_ACTION_ADAPTERS", {}, raising=False)
    assistant_service.register_action_adapter("list_projects", lambda db, principal, payload: {"items": []})
    preview = create_preview(db, _principal(), "thread-1", _plan("list_projects", {}))

    result = assistant_service.execute_action(db, _principal(), preview.action_id)

    assert result.status == "completed"
    assert result.result == {"items": []}


def test_low_risk_query_executes_without_persisting_a_preview(db, monkeypatch):
    """Live reads should not create a confirmation row merely to return safe data."""
    monkeypatch.setattr(assistant_service, "_ACTION_ADAPTERS", {}, raising=False)
    assistant_service.register_action_adapter(
        "list_projects",
        lambda db, principal, payload: {"items": [{"id": "project-1"}], "count": 1},
    )

    result = assistant_service.execute_low_risk_query(
        db,
        _principal(),
        _plan("list_projects", {}),
    )

    assert result == {"items": [{"id": "project-1"}], "count": 1}
    assert db.query(AssistantAction).count() == 0


def test_execute_action_rechecks_high_risk_confirmation_phrase(db, monkeypatch):
    """Allowing a direct confirmed execution without the phrase would bypass the final confirmation check."""
    calls = []
    monkeypatch.setattr(assistant_service, "_ACTION_ADAPTERS", {}, raising=False)
    assistant_service.register_action_adapter(
        "create_project", lambda db, principal, payload: calls.append(payload) or {"created": payload["code"]}
    )
    preview = create_preview(db, _principal(), "thread-1", _plan("create_project", {"code": "KB-1", "name": "知识库"}))
    action = db.get(AssistantAction, preview.action_id)
    action.status = "confirmed"
    action.confirmation_step = 1

    rejected = assistant_service.execute_action(db, _principal(), preview.action_id)
    completed = assistant_service.execute_action(
        db, _principal(), preview.action_id, confirmation_phrase=preview.confirmation_phrase
    )

    assert rejected.error_code == "confirmation_phrase_mismatch"
    assert completed.status == "completed"
    assert len(calls) == 1


def test_is_confirmation_valid_rejects_non_preview_status(db):
    """Treating a terminal action as confirmable would reopen a completed or cancelled lifecycle."""
    preview = create_preview(db, _principal(), "thread-1", _plan("create_project", {"code": "KB-1", "name": "知识库"}))
    action = db.get(AssistantAction, preview.action_id)
    action.status = "cancelled"

    valid, error_code = assistant_service.is_confirmation_valid(action, _principal(), _confirmation(preview))

    assert valid is False
    assert error_code == "confirmation_not_available"


def test_stale_second_confirmation_from_an_independent_session_never_runs_adapter_twice(db, monkeypatch):
    """Removing the conditional preview claim lets a stale second session execute the same action twice."""
    calls = []
    monkeypatch.setattr(assistant_service, "_ACTION_ADAPTERS", {}, raising=False)
    assistant_service.register_action_adapter(
        "create_project", lambda adapter_db, principal, payload: calls.append(payload) or {"created": payload["code"]}
    )
    preview = create_preview(db, _principal(), "thread-1", _plan("create_project", {"code": "KB-1", "name": "知识库"}))
    db.commit()
    sessions = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    first = sessions()
    second = sessions()
    try:
        stale_preview = second.get(AssistantAction, preview.action_id)
        assert stale_preview is not None and stale_preview.status == "preview"
        first_result = assistant_service.confirm_action(first, _principal(), preview.action_id, _confirmation(preview))
        first.commit()
        second_result = assistant_service.confirm_action(second, _principal(), preview.action_id, _confirmation(preview))

        assert first_result.status == "completed"
        assert second_result.status == "completed"
        assert len(calls) == 1
    finally:
        first.close()
        second.close()


def test_stale_execute_loses_to_committed_cancel_without_calling_adapter(db, monkeypatch):
    """A cancellation that wins the conditional state transition must prevent a stale execution from starting."""
    calls = []
    monkeypatch.setattr(assistant_service, "_ACTION_ADAPTERS", {}, raising=False)
    assistant_service.register_action_adapter(
        "create_project", lambda adapter_db, principal, payload: calls.append(payload) or {"created": payload["code"]}
    )
    preview = create_preview(db, _principal(), "thread-1", _plan("create_project", {"code": "KB-1", "name": "知识库"}))
    action = db.get(AssistantAction, preview.action_id)
    action.status = "confirmed"
    action.confirmation_step = 1
    db.commit()
    sessions = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    stale_executor = sessions()
    canceller = sessions()
    try:
        stale_action = stale_executor.get(AssistantAction, preview.action_id)
        assert stale_action is not None and stale_action.status == "confirmed"
        cancelled = assistant_service.cancel_action(canceller, _principal(), preview.action_id)
        canceller.commit()
        execute_result = assistant_service.execute_action(
            stale_executor, _principal(), preview.action_id, confirmation_phrase=preview.confirmation_phrase
        )

        assert cancelled.status == "cancelled"
        assert execute_result.status == "cancelled"
        assert calls == []
    finally:
        stale_executor.close()
        canceller.close()


def test_stale_second_execute_from_an_independent_session_never_runs_adapter_twice(db, monkeypatch):
    """Removing the conditional executing claim lets a stale confirmed action run its adapter twice."""
    calls = []
    monkeypatch.setattr(assistant_service, "_ACTION_ADAPTERS", {}, raising=False)
    assistant_service.register_action_adapter(
        "create_project", lambda adapter_db, principal, payload: calls.append(payload) or {"created": payload["code"]}
    )
    preview = create_preview(db, _principal(), "thread-1", _plan("create_project", {"code": "KB-1", "name": "知识库"}))
    action = db.get(AssistantAction, preview.action_id)
    action.status = "confirmed"
    action.confirmation_step = 1
    db.commit()
    sessions = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    first = sessions()
    second = sessions()
    try:
        stale_action = second.get(AssistantAction, preview.action_id)
        assert stale_action is not None and stale_action.status == "confirmed"
        first_result = assistant_service.execute_action(
            first, _principal(), preview.action_id, confirmation_phrase=preview.confirmation_phrase
        )
        first.commit()
        second_result = assistant_service.execute_action(
            second, _principal(), preview.action_id, confirmation_phrase=preview.confirmation_phrase
        )

        assert first_result.status == "completed"
        assert second_result.status == "completed"
        assert len(calls) == 1
    finally:
        first.close()
        second.close()


def test_project_update_target_snapshot_rejects_current_target_change(db, monkeypatch):
    """Dropping target IDs or snapshots lets an update confirmation apply to a changed project."""
    project = Project(id="project-1", code="KB-1", name="原项目")
    db.add(project)
    db.flush()
    preview = create_preview(
        db,
        _principal(),
        "thread-1",
        _plan("update_project", {"id": project.id, "name": "新项目"}),
    )
    action = db.get(AssistantAction, preview.action_id)
    project.name = "并发更新"
    db.flush()
    calls = []
    monkeypatch.setattr(assistant_service, "_ACTION_ADAPTERS", {}, raising=False)
    assistant_service.register_action_adapter(
        "update_project", lambda adapter_db, principal, payload: calls.append(payload) or {"updated": payload["id"]}
    )

    result = assistant_service.confirm_action(db, _principal(), preview.action_id, _confirmation(preview))

    assert action.object_versions_json[project.id].startswith("snapshot:")
    assert result.error_code == "object_version_changed"
    assert calls == []


def test_adapter_write_then_exception_rolls_back_savepoint_and_records_failure(db, monkeypatch):
    """Without a savepoint, a failing adapter can leave its business write in the caller transaction."""
    def mutating_failure(adapter_db, principal, payload):
        adapter_db.add(Project(code="ROLLBACK-1", name="不应保留"))
        adapter_db.flush()
        raise RuntimeError("adapter failed")

    monkeypatch.setattr(assistant_service, "_ACTION_ADAPTERS", {}, raising=False)
    assistant_service.register_action_adapter("create_project", mutating_failure)
    preview = create_preview(db, _principal(), "thread-1", _plan("create_project", {"code": "KB-1", "name": "知识库"}))

    result = assistant_service.confirm_action(db, _principal(), preview.action_id, _confirmation(preview))
    db.expire_all()

    assert result.status == "failed"
    assert result.error_code == "execution_failed"
    assert db.query(Project).filter(Project.code == "ROLLBACK-1").count() == 0
    assert db.query(AuditLog).filter(AuditLog.action == "assistant_action_failed").count() == 1


def test_org_and_expense_updates_bind_target_ids_and_reject_changed_or_deleted_targets(db, monkeypatch):
    """Omitting either target ID allows a mutable assistant update to run against a different current object."""
    department = Department(id="dept-1", name="研发", code="RND")
    expense = ExpenseClaim(id="expense-1", claim_no="EXP-001", requester_id="admin", title="差旅行程")
    db.add_all([department, expense])
    db.flush()
    org_preview = create_preview(
        db, _principal(), "thread-1", _plan("update_org_unit", {"id": department.id, "name": "工程"})
    )
    expense_preview = create_preview(
        db, _principal(), "thread-1", _plan("update_expense_draft", {"id": expense.id, "title": "新行程"})
    )
    org_action = db.get(AssistantAction, org_preview.action_id)
    expense_action = db.get(AssistantAction, expense_preview.action_id)
    department.name = "并发改名"
    db.delete(expense)
    db.flush()
    calls = []
    monkeypatch.setattr(assistant_service, "_ACTION_ADAPTERS", {}, raising=False)
    assistant_service.register_action_adapter(
        "update_org_unit", lambda adapter_db, principal, payload: calls.append(payload) or {"updated": payload["id"]}
    )
    assistant_service.register_action_adapter(
        "update_expense_draft", lambda adapter_db, principal, payload: calls.append(payload) or {"updated": payload["id"]}
    )

    org_result = assistant_service.confirm_action(db, _principal(), org_preview.action_id, _confirmation(org_preview))
    expense_result = assistant_service.confirm_action(
        db, _principal(), expense_preview.action_id, _confirmation(expense_preview)
    )

    assert org_action.payload_json["id"] == department.id
    assert expense_action.payload_json["id"] == expense.id
    assert org_action.object_versions_json[department.id].startswith("snapshot:")
    assert expense_action.object_versions_json[expense.id] == 1
    assert [org_result.error_code, expense_result.error_code] == ["object_version_changed", "object_version_changed"]
    assert calls == []


def test_post_claim_target_recheck_blocks_interleaved_change_before_adapter(tmp_path, monkeypatch):
    """A target changed after precheck but before the execution claim must fail before its adapter runs."""
    engine = create_engine(f"sqlite:///{tmp_path / 'assistant-actions.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    setup = sessions()
    executor = sessions()
    modifier = sessions()
    try:
        department = Department(id="dept-1", name="研发", code="RND")
        setup.add(department)
        setup.flush()
        preview = create_preview(
            setup, _principal(), "thread-1", _plan("update_org_unit", {"id": department.id, "name": "工程"})
        )
        action = setup.get(AssistantAction, preview.action_id)
        action.status = "confirmed"
        action.confirmation_step = 1
        setup.commit()
        calls = []
        monkeypatch.setattr(assistant_service, "_ACTION_ADAPTERS", {}, raising=False)
        assistant_service.register_action_adapter(
            "update_org_unit", lambda adapter_db, principal, payload: calls.append(payload) or {"updated": payload["id"]}
        )
        original_transition = assistant_service._conditional_transition

        def change_target_between_precheck_and_claim(db, action, **kwargs):
            if kwargs["new_status"] == "executing":
                target = modifier.get(Department, department.id)
                assert target is not None
                target.name = "插入式更新"
                modifier.commit()
            return original_transition(db, action, **kwargs)

        monkeypatch.setattr(assistant_service, "_conditional_transition", change_target_between_precheck_and_claim)
        result = assistant_service.execute_action(
            executor, _principal(), preview.action_id, confirmation_phrase=preview.confirmation_phrase
        )

        assert result.status == "failed"
        assert result.error_code == "object_version_changed"
        assert calls == []
        assert executor.query(AuditLog).filter(AuditLog.action == "assistant_action_failed").count() == 1
    finally:
        executor.close()
        modifier.close()
        setup.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_every_existing_target_mutation_is_id_bound_and_version_or_snapshot_checked():
    """Adding a mutable catalog action without this mapping would silently recreate the stale-target bypass."""
    target_writes = {
        "approve_approval",
        "reject_approval",
        "cancel_approval",
        "pay_expense",
    }
    target_writes.update(
        definition.name
        for definition in list_actions()
        if definition.name.startswith(("update_", "delete_"))
    )

    for definition in list_actions():
        if definition.name not in target_writes:
            continue
        assert definition.target_model is not None
        assert definition.input_model.model_fields["id"].is_required()
