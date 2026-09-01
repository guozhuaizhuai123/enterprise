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
from app.models import Department, DepartmentMemory, SensitiveEvent, SensitiveKeyword, User


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
            SensitiveEvent(
                id="sensitive-event",
                username="employee",
                department_name="研发",
                question="敏感文本",
                matched_keyword="测试",
                reason="测试事件",
            ),
        ]
    )
    db.flush()


def test_confirmed_security_and_department_memory_actions_use_shared_services(db, admin):
    """Security settings and department memories must be confirmed, bounded and transaction-neutral."""
    _setup(db)
    install_production_adapters()

    created_keyword = _confirm(db, admin, "create_sensitive_keyword", {"keyword": " 内部测试 ", "enabled": True})
    updated_keyword = _confirm(
        db,
        admin,
        "update_sensitive_keyword",
        {"id": created_keyword.result["id"], "enabled": False},
    )
    created_memory = _confirm(
        db,
        admin,
        "create_department_memory",
        {"department_id": "dept-a", "title": " 发布规则 ", "content": " 先走审批 ", "enabled": True},
    )
    updated_memory = _confirm(
        db,
        admin,
        "update_department_memory",
        {"id": created_memory.result["id"], "enabled": False},
    )

    assert created_keyword.status == updated_keyword.status == created_memory.status == updated_memory.status == "completed"
    assert db.get(SensitiveKeyword, created_keyword.result["id"]).keyword == "内部测试"
    assert db.get(SensitiveKeyword, created_keyword.result["id"]).enabled is False
    assert db.get(DepartmentMemory, created_memory.result["id"]).title == "发布规则"
    assert db.get(DepartmentMemory, created_memory.result["id"]).enabled is False


def test_high_risk_security_and_memory_deletions_are_confirmed(db, admin):
    """The controlled delete adapters must call neutral services rather than raw ORM deletes."""
    _setup(db)
    db.add_all(
        [
            SensitiveKeyword(id="keyword-delete", keyword="旧关键字", updated_by="admin"),
            DepartmentMemory(
                id="memory-delete",
                department_id="dept-a",
                title="旧记忆",
                content="旧内容",
                created_by="admin",
                updated_by="admin",
            ),
        ]
    )
    db.flush()
    install_production_adapters()

    deleted_event = _confirm(db, admin, "delete_sensitive_event", {"id": "sensitive-event"})
    deleted_keyword = _confirm(db, admin, "delete_sensitive_keyword", {"id": "keyword-delete"})
    deleted_memory = _confirm(db, admin, "delete_department_memory", {"id": "memory-delete"})

    assert deleted_event.status == deleted_keyword.status == deleted_memory.status == "completed"
    assert db.get(SensitiveEvent, "sensitive-event") is None
    assert db.get(SensitiveKeyword, "keyword-delete") is None
    assert db.get(DepartmentMemory, "memory-delete") is None
