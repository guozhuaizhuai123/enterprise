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
from app.models import Department, Notification, Ticket, TicketEvent, TicketMessage, Todo, User, UserDepartment


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


@pytest.fixture
def employee() -> Principal:
    return Principal("requester", "requester", "employee", "dept-a", ("dept-a",), ("employee",))


def _plan(action_name: str, payload: dict) -> ActionPlan:
    action = get_action(action_name)
    assert action is not None
    return ActionPlan(action=action, input=action.input_model.model_validate(payload))


def _confirm(db, principal: Principal, action_name: str, payload: dict):
    preview = create_preview(db, principal, "thread-1", _plan(action_name, payload))
    return assistant_service.confirm_action(
        db,
        principal,
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
            Department(id="dept-b", name="法务", code="LEGAL"),
            User(id="admin", username="administrator", password_encrypted="hashed", role="admin"),
            User(id="requester", username="requester", password_encrypted="hashed", role="employee", department_id="dept-a"),
            User(id="assignee", username="assignee", password_encrypted="hashed", role="employee", department_id="dept-b"),
            UserDepartment(user_id="requester", department_id="dept-a"),
            UserDepartment(user_id="assignee", department_id="dept-b"),
        ]
    )
    db.flush()


def test_confirmed_ticket_and_todo_actions_use_shared_transaction_neutral_service(db, admin, employee):
    """Assistant collaboration writes must preserve routing, events and notifications without calling commit."""
    _setup(db)
    install_production_adapters()

    created = _confirm(
        db,
        employee,
        "create_ticket",
        {
            "ticket_type": "cross_department",
            "subject": "合同审阅",
            "description": "请协助审阅合同",
            "department_id": "dept-a",
            "requested_department_id": "dept-b",
        },
    )
    ticket_id = created.result["id"]
    dispatched = _confirm(db, admin, "dispatch_ticket", {"id": ticket_id, "assignee_id": "assignee"})
    todo = _confirm(
        db,
        admin,
        "create_todo",
        {"assignee_id": "assignee", "ticket_id": ticket_id, "title": "审阅合同", "description": "本周完成"},
    )
    assignee = Principal("assignee", "assignee", "employee", "dept-b", ("dept-b",), ("employee",))
    updated = _confirm(db, assignee, "update_todo", {"id": todo.result["id"], "status": "completed"})

    ticket = db.get(Ticket, ticket_id)
    saved_todo = db.get(Todo, todo.result["id"])
    assert created.status == dispatched.status == todo.status == updated.status == "completed"
    assert ticket is not None and ticket.target_user_id == "assignee" and ticket.status == "completed"
    assert saved_todo is not None and saved_todo.completed_at is not None
    assert db.query(TicketMessage).filter(TicketMessage.ticket_id == ticket_id).count() == 1
    assert {"created", "dispatched", "todo_created", "todo_updated"}.issubset(
        {event.event_type for event in db.query(TicketEvent).all()}
    )


def test_ticket_deletion_is_confirmed_and_uses_the_shared_service(db, admin):
    """The high-risk delete action must not rely on a raw adapter session delete."""
    _setup(db)
    db.add(
        Ticket(
            id="ticket-delete",
            requester_id="requester",
            department_id="dept-a",
            ticket_type="issue",
            subject="可删除",
            description="已取消",
            status="pending_admin",
        )
    )
    db.flush()
    db.add_all(
        [
            TicketMessage(ticket_id="ticket-delete", sender_id="requester", content="待删除消息"),
            TicketEvent(ticket_id="ticket-delete", actor_id="admin", event_type="created"),
            Notification(
                recipient_id="requester",
                ticket_id="ticket-delete",
                kind="ticket_assigned",
                content="待删除通知",
            ),
            Todo(
                id="todo-retained",
                assignee_id="requester",
                created_by="admin",
                ticket_id="ticket-delete",
                title="保留待办",
            ),
        ]
    )
    db.flush()
    install_production_adapters()

    result = _confirm(db, admin, "delete_ticket", {"id": "ticket-delete"})

    assert result.status == "completed"
    assert db.get(Ticket, "ticket-delete") is None
    assert db.query(TicketMessage).filter_by(ticket_id="ticket-delete").count() == 0
    assert db.query(TicketEvent).filter_by(ticket_id="ticket-delete").count() == 0
    assert db.query(Notification).filter_by(ticket_id="ticket-delete").count() == 0
    assert db.get(Todo, "todo-retained").ticket_id is None


def test_employee_cannot_create_a_todo_for_another_user(db, employee):
    """The registry and service must both keep task creation administrative."""
    _setup(db)
    action = get_action("create_todo")
    assert action is not None

    with pytest.raises(HTTPException) as exc_info:
        create_preview(
            db,
            employee,
            "thread-1",
            _plan("create_todo", {"assignee_id": "assignee", "title": "越权待办"}),
        )
    assert exc_info.value.status_code == 403
