from datetime import date

import pytest
from fastapi import HTTPException
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
from app.models import AttendanceRecord, Department, HolidayPeriod, LeaveRequest, User


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


def _confirm(db, admin: Principal, action_name: str, payload: dict):
    preview = create_preview(db, admin, "thread-1", _plan(action_name, payload))
    return assistant_service.confirm_action(
        db,
        admin,
        preview.action_id,
        ActionConfirmRequest(
            action_id=preview.action_id,
            confirmation_phrase=preview.confirmation_phrase or "",
            parameter_hash=preview.parameter_hash or "",
        ),
    )


def _setup(db):
    db.add_all(
        [
            Department(id="dept-a", name="研发", code="RND"),
            User(id="admin", username="administrator", password_encrypted="hashed", role="admin"),
            User(
                id="employee",
                username="employee",
                password_encrypted="hashed",
                role="employee",
                department_id="dept-a",
            ),
        ]
    )
    db.flush()


def _weekdays():
    return [
        {"weekday": weekday, "enabled": weekday <= 5, "start_time": "09:00", "end_time": "18:00"}
        for weekday in range(1, 8)
    ]


def test_confirmed_schedule_actions_use_transaction_neutral_service_cores(db, admin):
    """A schedule adapter must not call legacy services that commit its outer action transaction."""
    _setup(db)
    install_production_adapters()

    schedule = _confirm(db, admin, "update_work_schedule", {"id": "employee", "days": _weekdays()})
    holiday = _confirm(
        db,
        admin,
        "create_holiday",
        {
            "name": "国庆节",
            "scope_type": "company",
            "start_date": date(2026, 10, 1),
            "end_date": date(2026, 10, 7),
        },
    )
    attendance = _confirm(
        db,
        admin,
        "upsert_attendance",
        {
            "id": "employee",
            "attendance_date": date(2026, 9, 1),
            "status": "present",
            "note": "正常出勤",
        },
    )
    leave = _confirm(
        db,
        admin,
        "create_leave_request",
        {
            "leave_type": "年假",
            "start_date": date(2026, 9, 2),
            "end_date": date(2026, 9, 2),
            "reason": "休息",
        },
    )
    review = _confirm(db, admin, "review_leave_request", {"id": leave.result["id"], "status": "approved"})

    assert schedule.status == holiday.status == attendance.status == leave.status == review.status == "completed"
    assert db.query(HolidayPeriod).count() == 1
    assert db.query(AttendanceRecord).one().recorded_by == "admin"
    assert db.get(LeaveRequest, leave.result["id"]).status == "approved"


def test_confirmed_schedule_deletions_use_registered_high_risk_actions(db, admin):
    """Holiday and attendance deletion must go through confirmation and the shared transaction."""
    _setup(db)
    db.add_all(
        [
            HolidayPeriod(
                id="holiday",
                name="调休",
                scope_type="company",
                start_date=date(2026, 9, 7),
                end_date=date(2026, 9, 7),
                created_by="admin",
            ),
            AttendanceRecord(
                id="attendance",
                user_id="employee",
                attendance_date=date(2026, 9, 3),
                status="late",
                recorded_by="admin",
            ),
        ]
    )
    db.flush()
    install_production_adapters()

    removed_holiday = _confirm(db, admin, "delete_holiday", {"id": "holiday"})
    removed_attendance = _confirm(db, admin, "delete_attendance", {"id": "attendance"})

    assert removed_holiday.status == removed_attendance.status == "completed"
    assert db.get(HolidayPeriod, "holiday") is None
    assert db.get(AttendanceRecord, "attendance") is None


def test_schedule_management_actions_are_not_available_to_an_employee(db):
    """A forged employee plan must not persist a schedule-management preview."""
    _setup(db)
    employee = Principal("employee", "employee", "employee", "dept-a", ("dept-a",), ("employee",))

    with pytest.raises(HTTPException) as exc_info:
        create_preview(
            db,
            employee,
            "thread-1",
            _plan("create_holiday", {"name": "假期", "scope_type": "company", "start_date": date(2026, 9, 1), "end_date": date(2026, 9, 1)}),
        )
    assert exc_info.value.status_code == 403
