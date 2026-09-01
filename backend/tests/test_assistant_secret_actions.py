from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.assistant.service as assistant_service
from app.assistant.adapters import install_production_adapters
from app.assistant.planner import ActionPlan
from app.assistant.registry import get_action
from app.assistant.schemas import ActionConfirmRequest
from app.assistant.service import create_preview
from app.db import Base
from app.deps import Principal
from app.models import (
    AssistantAction,
    AuditLog,
    Department,
    EmployeeProfile,
    ExpenseClaim,
    ExpenseItem,
    PayrollSetting,
    User,
    UserDepartment,
)
from app.security import verify_password


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def admin() -> Principal:
    return Principal("admin", "administrator", "admin", "dept-a", ("dept-a",), ("admin",))


def _plan(action_name: str, payload: dict) -> ActionPlan:
    action = get_action(action_name)
    assert action is not None
    return ActionPlan(action=action, input=action.input_model.model_validate(payload))


def _confirmation(preview) -> ActionConfirmRequest:
    return ActionConfirmRequest(
        action_id=preview.action_id,
        confirmation_phrase=preview.confirmation_phrase or "",
        parameter_hash=preview.parameter_hash or "",
    )


def _setup_organization(db):
    db.add_all(
        [
            Department(id="dept-a", name="研发", code="RND"),
            Department(id="dept-b", name="财务", code="FIN"),
            User(id="admin", username="administrator", password_encrypted="hashed", role="admin", department_id="dept-a"),
        ]
    )
    db.flush()


def test_employee_password_actions_encrypt_persisted_payload_and_never_expose_plaintext(db, admin):
    """Persisting a password in action, audit, preview, or result JSON would leak a credential."""
    _setup_organization(db)
    install_production_adapters()
    password = "Employee-Secret-9"

    preview = create_preview(
        db,
        admin,
        "thread-1",
        _plan(
            "create_employee",
            {
                "username": "assistant-created",
                "password": password,
                "full_name": "Assistant Created",
                "department_ids": ["dept-a"],
                "primary_department_id": "dept-a",
                "salary": "18000",
            },
        ),
    )
    action = db.get(AssistantAction, preview.action_id)
    assert action is not None
    persisted = action.payload_json
    serialized = str([persisted, action.preview_json, db.query(AuditLog).one().after_data])
    assert password not in serialized
    assert persisted["password"] != password
    assert "ciphertext" in persisted["password"]

    result = assistant_service.confirm_action(db, admin, preview.action_id, _confirmation(preview))

    created = db.query(User).filter_by(username="assistant-created").one()
    assert result.status == "completed"
    assert verify_password(password, created.password_encrypted)
    assert {"password", "salary", "password_encrypted"}.isdisjoint(result.result or {})
    assert password not in str(
        [
            action.payload_json,
            action.preview_json,
            action.result_json,
            *[row.after_data for row in db.query(AuditLog).all()],
        ]
    )


def test_password_action_fails_closed_after_secret_cannot_be_decrypted(db, admin, monkeypatch):
    """A key-rotation/decryption failure must prevent the password mutation from running."""
    _setup_organization(db)
    db.add(User(id="employee", username="employee", password_encrypted="old-hash", role="employee", department_id="dept-a"))
    db.flush()
    install_production_adapters()

    preview = create_preview(
        db,
        admin,
        "thread-1",
        _plan("reset_employee_password", {"id": "employee", "password": "New-Secret-9"}),
    )
    monkeypatch.setattr(assistant_service, "decrypt_password", lambda _token: (_ for _ in ()).throw(ValueError("rotated")))

    result = assistant_service.confirm_action(db, admin, preview.action_id, _confirmation(preview))

    assert result.status == "failed"
    assert result.error_code == "secret_unavailable"
    assert db.get(AssistantAction, preview.action_id).status == "failed"
    assert db.get(User, "employee").password_encrypted == "old-hash"


def test_direct_execution_also_invalidates_an_unreadable_secret_preview(db, admin, monkeypatch):
    """A rotated key between confirmation steps must not leave a confirmed password action reusable."""
    _setup_organization(db)
    db.add(User(id="employee", username="employee", password_encrypted="old-hash", role="employee", department_id="dept-a"))
    db.flush()
    install_production_adapters()
    preview = create_preview(
        db,
        admin,
        "thread-1",
        _plan("reset_employee_password", {"id": "employee", "password": "New-Secret-9"}),
    )
    action = db.get(AssistantAction, preview.action_id)
    action.status = "confirmed"
    action.confirmation_step = 1
    monkeypatch.setattr(assistant_service, "decrypt_password", lambda _token: (_ for _ in ()).throw(ValueError("rotated")))

    result = assistant_service.execute_action(
        db,
        admin,
        preview.action_id,
        confirmation_phrase=preview.confirmation_phrase,
    )

    assert result.status == "failed"
    assert result.error_code == "secret_unavailable"
    assert action.status == "failed"
    assert db.get(User, "employee").password_encrypted == "old-hash"


def test_organization_expense_submission_and_payroll_settings_use_registered_neutral_adapters(db, admin):
    """Bypassing service adapters would drop ownership checks, workflow submission, or payroll validation."""
    _setup_organization(db)
    db.add_all(
        [
            User(id="employee", username="employee", password_encrypted="hashed", role="employee", department_id="dept-a"),
            EmployeeProfile(user_id="employee", full_name="Employee", status="active"),
            ExpenseClaim(
                id="expense-1",
                claim_no="EXP-1",
                requester_id="employee",
                department_id="dept-a",
                title="Taxi",
                status="draft",
            ),
            ExpenseItem(
                id="item-1",
                claim_id="expense-1",
                expense_date=date(2026, 9, 1),
                category="交通",
                amount="86.00",
            ),
        ]
    )
    db.flush()
    install_production_adapters()

    assert get_action("update_employee") is not None
    assert get_action("record_employment_event") is not None
    assert get_action("submit_expense") is not None
    assert get_action("update_payroll_settings") is not None

    employee_update = assistant_service._ACTION_ADAPTERS["update_employee"](
        db,
        admin,
        {"id": "employee", "position": "工程师", "salary": "20000"},
    )
    event = assistant_service._ACTION_ADAPTERS["record_employment_event"](
        db,
        admin,
        {
            "id": "employee",
            "event_type": "position_change",
            "effective_date": date(2026, 9, 1),
            "position": "高级工程师",
        },
    )
    settings = assistant_service._ACTION_ADAPTERS["update_payroll_settings"](
        db,
        admin,
        {"auto_enabled": False, "pay_day": 15, "generation_lead_days": 3},
    )

    assert employee_update == {
        "id": "employee",
        "username": "employee",
        "status": "active",
        "department_id": "dept-a",
        "position": "工程师",
    }
    assert event["event_type"] == "position_change"
    assert "before_data" not in event and "after_data" not in event
    assert settings["pay_day"] == 15
    assert {"salary", "phone", "email", "notes"}.isdisjoint(employee_update)


def test_submit_expense_uses_the_existing_requester_workflow_and_confirmation(db):
    """Submitting through a generic write path would skip expense ownership and its approval workflow."""
    _setup_organization(db)
    employee = Principal("employee", "employee", "employee", "dept-a", ("dept-a",), ("employee",))
    db.add_all(
        [
            User(id="employee", username="employee", password_encrypted="hashed", role="employee", department_id="dept-a"),
            User(id="manager", username="manager", password_encrypted="hashed", role="manager", department_id="dept-a"),
            EmployeeProfile(user_id="employee", full_name="Employee", manager_id="manager", status="active"),
            UserDepartment(user_id="employee", department_id="dept-a", is_primary=True),
            ExpenseClaim(
                id="expense-submit",
                claim_no="EXP-SUBMIT",
                requester_id="employee",
                department_id="dept-a",
                title="Taxi",
                status="draft",
            ),
            ExpenseItem(
                id="item-submit",
                claim_id="expense-submit",
                expense_date=date(2026, 9, 1),
                category="交通",
                amount="86.00",
            ),
        ]
    )
    db.flush()
    install_production_adapters()

    preview = create_preview(
        db,
        employee,
        "thread-1",
        _plan("submit_expense", {"id": "expense-submit", "idempotency_key": "assistant-submit-1"}),
    )
    result = assistant_service.confirm_action(db, employee, preview.action_id, _confirmation(preview))

    claim = db.get(ExpenseClaim, "expense-submit")
    assert result.status == "completed"
    assert result.result == {
        "id": "expense-submit",
        "claim_no": "EXP-SUBMIT",
        "status": "pending_approval",
        "approval_instance_id": claim.approval_instance_id,
        "version": claim.version,
    }
    assert claim.approval_instance_id is not None


def test_payroll_settings_preview_can_bind_the_absent_default_record_until_confirmed(db, admin):
    """Creating settings during a preview would make a supposedly reversible action mutate production data."""
    _setup_organization(db)
    install_production_adapters()

    preview = create_preview(
        db,
        admin,
        "thread-1",
        _plan(
            "update_payroll_settings",
            {"id": "default", "auto_enabled": False, "pay_day": 15, "generation_lead_days": 3},
        ),
    )

    assert db.query(PayrollSetting).count() == 0
    result = assistant_service.confirm_action(db, admin, preview.action_id, _confirmation(preview))

    assert result.status == "completed"
    assert result.result == {
        "id": "default",
        "auto_enabled": False,
        "pay_day": 15,
        "generation_lead_days": 3,
        "currency": "CNY",
        "approval_role": "finance",
    }
