import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.deps import Principal, get_current_principal
from app.assistant.adapters import install_production_adapters
from app.assistant.periods import business_today
from app.models import AssistantAction, AuditLog, Department, Message, Project, Thread, User
from app.routers import chat


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(session_factory):
    app = FastAPI()
    app.include_router(chat.router)

    def override_db():
        with session_factory() as db:
            yield db

    def override_principal():
        return Principal(
            user_id="root",
            username="root",
            role="admin",
            department_id=None,
            department_ids=(),
            roles=("admin",),
        )

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_principal] = override_principal
    return TestClient(app)


def ask_events(client, question):
    from sse_starlette.sse import AppStatus

    AppStatus.should_exit_event = None
    response = client.post("/chat/ask", json={"question": question})
    assert response.status_code == 200
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: {")
    ]
    assert response.text.rstrip().endswith("data: [DONE]")
    return events


def _seed_departments(session_factory):
    with session_factory() as db:
        db.add_all(
            (
                Department(id="dept-a", name="研发", code="RND"),
                Department(id="dept-b", name="财务", code="FIN"),
            )
        )
        db.commit()


def test_chat_business_query_skips_rag_and_uses_root_full_scope(client, session_factory):
    """Routing a low-risk query through RAG or one thread department would hide live business data."""
    _seed_departments(session_factory)
    with session_factory() as db:
        db.add_all(
            (
                Project(id="project-a", code="A", name="研发项目", department_id="dept-a"),
                Project(id="project-b", code="B", name="财务项目", department_id="dept-b"),
            )
        )
        db.commit()

    install_production_adapters()
    rag = AsyncMock()
    with patch.object(chat, "run_ask", rag):
        events = ask_events(client, "查询一下最近的项目")

    result = next(event for event in events if event["node"] == "query_result")
    assert result["status"] == "completed"
    assert result["kind"] == "business"
    assert result["intent"] == "list_projects"
    assert result["display"]
    assert {item["name"] for item in result["payload"]["items"]} == {"研发项目", "财务项目"}
    rag.assert_not_awaited()

    with session_factory() as db:
        messages = db.query(Message).order_by(Message.created_at).all()
        assert [(message.role, message.content) for message in messages] == [
            ("user", "查询一下最近的项目"),
            ("assistant", "查询完成，共找到 2 条结果。"),
        ]
        assert db.query(AssistantAction).count() == 0


def test_manager_chat_business_query_defaults_to_membership_scope(session_factory):
    """Direct low-risk chat execution must not broaden a manager's empty filter to every department."""
    _seed_departments(session_factory)
    with session_factory() as db:
        db.add_all(
            (
                Project(id="project-a", code="A", name="研发项目", department_id="dept-a"),
                Project(id="project-b", code="B", name="财务项目", department_id="dept-b"),
            )
        )
        db.commit()

    app = FastAPI()
    app.include_router(chat.router)

    def override_db():
        with session_factory() as db:
            yield db

    def override_principal():
        return Principal(
            user_id="manager",
            username="manager",
            role="manager",
            department_id="dept-a",
            department_ids=("dept-a",),
            roles=("manager",),
        )

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_principal] = override_principal
    install_production_adapters()
    rag = AsyncMock()
    with patch.object(chat, "run_ask", rag), TestClient(app) as manager_client:
        events = ask_events(manager_client, "查询一下最近的项目")

    result = next(event for event in events if event["node"] == "query_result")
    assert [item["id"] for item in result["payload"]["items"]] == ["project-a"]
    rag.assert_not_awaited()


def test_chat_form_preview_persists_readable_non_submission_summary(client, session_factory):
    """Persisting a completion claim for a preview would misrepresent an unsubmitted expense."""
    _seed_departments(session_factory)
    rag = AsyncMock()
    with patch.object(chat, "run_ask", rag):
        events = ask_events(client, "报销昨天打车 86 元")

    event = next(event for event in events if event["node"] == "form_preview")
    assert event["kind"] == "business"
    assert event["intent"] == "form_preview"
    assert event["payload"]["form"] == "expense"
    assert event["payload"]["preview"]["total_amount"] == "86"
    assert "已提交" not in event["display"] and "提交成功" not in event["display"]
    rag.assert_not_awaited()

    with session_factory() as db:
        assert [(row.role, row.content) for row in db.query(Message).order_by(Message.created_at).all()] == [
            ("user", "报销昨天打车 86 元"),
            ("assistant", event["display"]),
        ]
        assert "{" not in event["display"]
        assert db.query(AssistantAction).count() == 0


def test_chat_navigation_and_clarification_persist_readable_safe_summaries(client, session_factory):
    """Leaking URLs or raw planner payloads into history would bypass the route-key boundary."""
    _seed_departments(session_factory)
    rag = AsyncMock()
    with patch.object(chat, "run_ask", rag):
        navigation = ask_events(client, "打开企业全景")
        clarification = ask_events(client, "帮我处理一下")

    navigation_event = next(event for event in navigation if event["node"] == "navigation")
    assert navigation_event["route_key"] == "overview"
    assert navigation_event["payload"] == {"route_key": "overview"}
    assert "url" not in json.dumps(navigation_event).lower()
    clarification_event = next(event for event in clarification if event["node"] == "clarification")
    assert clarification_event["display"] == "请补充要办理的具体业务和必要信息。"
    rag.assert_not_awaited()

    with session_factory() as db:
        assistant_messages = [row.content for row in db.query(Message).filter(Message.role == "assistant").all()]
        assert assistant_messages == [
            "正在打开企业全景。",
            "请补充要办理的具体业务和必要信息。",
        ]
        assert all("http" not in content.lower() and "{" not in content for content in assistant_messages)


def test_chat_high_risk_action_keeps_preview_audit_and_user_message(client, session_factory):
    """Business routing must not bypass the existing confirmation and audit boundary for writes."""
    _seed_departments(session_factory)
    rag = AsyncMock()
    with patch.object(chat, "run_ask", rag):
        events = ask_events(client, 'action:create_org_unit {"name":"平台部","code":"PLAT"}')

    event = next(event for event in events if event["node"] == "action_preview")
    assert event["kind"] == "business"
    assert event["intent"] == "create_org_unit"
    assert event["payload"]["action_id"] == event["action_id"]
    rag.assert_not_awaited()

    with session_factory() as db:
        thread = db.query(Thread).one()
        assert db.query(Message).filter_by(thread_id=thread.id, role="user").count() == 1
        assert [
            row.content
            for row in db.query(Message).filter_by(thread_id=thread.id, role="assistant").all()
        ] == [event["display"]]
        assert "{" not in event["display"] and "已执行" not in event["display"]
        assert db.query(AssistantAction).filter_by(thread_id=thread.id, status="preview").count() == 1
        assert db.query(AuditLog).filter_by(action="assistant_action_previewed").count() == 1


def test_chat_password_action_redacts_the_user_message_and_preview_records(client, session_factory):
    """A password-bearing assistant action must not persist plaintext in chat or audit history."""
    _seed_departments(session_factory)
    password = "Chat-Password-9"
    events = ask_events(
        client,
        (
            f'action:create_employee {{"password":"{password}","username":"chat-created",'
            '"full_name":"Chat Created","department_ids":["dept-a"],'
            '"primary_department_id":"dept-a"}'
        ),
    )

    preview = next(event for event in events if event["node"] == "action_preview")
    assert password not in json.dumps(preview)
    with session_factory() as db:
        action = db.query(AssistantAction).one()
        messages = db.query(Message).order_by(Message.created_at).all()
        thread = db.query(Thread).one()
        audit = db.query(AuditLog).filter_by(action="assistant_action_previewed").one()
        assert password not in str([action.payload_json, action.preview_json, audit.after_data])
        assert password not in messages[0].content
        assert password[:8] not in thread.title
        assert "[REDACTED]" in messages[0].content


def test_chat_clarification_redacts_a_natural_language_password(client, session_factory):
    """A rejected password request must not leak its supplied secret into durable chat history."""
    _seed_departments(session_factory)
    password = "Natural-Password-9"

    events = ask_events(client, f"帮我重置员工密码为 {password}")

    assert any(event["node"] == "clarification" for event in events)
    with session_factory() as db:
        thread = db.query(Thread).one()
        message = db.query(Message).filter_by(role="user").one()
        assert password not in message.content
        assert password[:8] not in thread.title
        assert "[REDACTED]" in message.content


def _employee_client(session_factory):
    app = FastAPI()
    app.include_router(chat.router)

    def override_db():
        with session_factory() as db:
            yield db

    def override_principal():
        return Principal(
            user_id="employee-a",
            username="alice",
            role="employee",
            department_id="dept-a",
            department_ids=("dept-a",),
            roles=("employee",),
        )

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_principal] = override_principal
    return TestClient(app)


@pytest.mark.parametrize(
    ("question", "node", "checks"),
    [
        ("我要请假三天", "form_preview", {"form": "leave"}),
        ("电脑坏了帮我找人处理", "form_preview", {"form": "ticket"}),
        ("查看工单", "navigation", {"route_key": "tickets"}),
        ("查看这个月流水", "query_result", {"intent": "expense_summary"}),
        ("今天出勤情况怎么样", "query_result", {"intent": "attendance_summary"}),
    ],
)
def test_employee_chat_reaches_every_conversational_capability(
    session_factory, question, node, checks
):
    """An employee losing any of these routes would be pushed back to manual page navigation."""
    _seed_departments(session_factory)
    with session_factory() as db:
        db.add(
            User(
                id="employee-a",
                username="alice",
                password_encrypted="secret",
                role="employee",
                department_id="dept-a",
            )
        )
        db.commit()

    install_production_adapters()
    rag = AsyncMock()
    with patch.object(chat, "run_ask", rag), _employee_client(session_factory) as employee_client:
        events = ask_events(employee_client, question)

    event = next(item for item in events if item["node"] == node)
    assert event["kind"] == "business"
    for key, expected in checks.items():
        assert event.get(key, event["payload"].get(key)) == expected
    if node == "form_preview":
        assert event["payload"]["preview"][f"is_{checks['form']}_request"] is True
    rag.assert_not_awaited()


@pytest.mark.parametrize(
    ("question", "node", "intent"),
    [
        ("查看今天考勤", "query_result", "attendance_summary"),
        ("这个月支出怎么样", "query_result", "expense_summary"),
        ("查看工单", "navigation", None),
    ],
)
def test_frequent_intents_survive_an_unavailable_llm(
    client, session_factory, monkeypatch, question, node, intent
):
    """Rule intents must keep working when the model endpoint is offline or unconfigured."""
    from app.assistant import intent_extractor

    _seed_departments(session_factory)
    monkeypatch.setattr(
        intent_extractor, "call_json", AsyncMock(side_effect=RuntimeError("offline"))
    )
    install_production_adapters()

    rag = AsyncMock()
    with patch.object(chat, "run_ask", rag):
        events = ask_events(client, question)

    event = next(item for item in events if item["node"] == node)
    if intent is not None:
        assert event["intent"] == intent
    rag.assert_not_awaited()


def test_summary_queries_persist_the_numbers_not_a_generic_sentence(client, session_factory):
    """"查询完成，结果已返回。" in history would make the transcript useless for later review."""
    _seed_departments(session_factory)
    install_production_adapters()

    rag = AsyncMock()
    with patch.object(chat, "run_ask", rag):
        attendance = ask_events(client, "查看今天考勤")
        expenses = ask_events(client, "这个月支出怎么样")

    attendance_event = next(item for item in attendance if item["node"] == "query_result")
    expense_event = next(item for item in expenses if item["node"] == "query_result")
    assert "应出勤" in attendance_event["display"] and "已登记" in attendance_event["display"]
    assert "费用" in expense_event["display"] and "¥" in expense_event["display"]

    with session_factory() as db:
        stored = [row.content for row in db.query(Message).filter(Message.role == "assistant").all()]
        assert stored == [attendance_event["display"], expense_event["display"]]


def test_historical_period_questions_answer_for_that_period(client, session_factory):
    """Answering "上月" with this month's numbers is a silent wrong answer."""
    _seed_departments(session_factory)
    install_production_adapters()

    rag = AsyncMock()
    with patch.object(chat, "run_ask", rag):
        last_month = ask_events(client, "查看上月支出")
        last_week = ask_events(client, "上周支出")
        month_attendance = ask_events(client, "查看上个月考勤")

    today = business_today()
    previous = f"{(today.year * 12 + today.month - 2) // 12:04d}-{(today.year * 12 + today.month - 2) % 12 + 1:02d}"

    month_event = next(item for item in last_month if item["node"] == "query_result")
    week_event = next(item for item in last_week if item["node"] == "query_result")
    attendance_event = next(item for item in month_attendance if item["node"] == "query_result")

    assert month_event["payload"]["month"] == previous
    assert month_event["display"].startswith(previous)
    assert "month" not in week_event["payload"]
    assert week_event["payload"]["period_start"] < week_event["payload"]["period_end"]
    assert " 至 " in week_event["display"]
    assert attendance_event["payload"]["month"] == previous
    assert "在职员工" in attendance_event["display"]
    rag.assert_not_awaited()


def test_business_event_rejects_unknown_compatibility_fields():
    """A loose final envelope would allow an arbitrary URL or debug object to bypass the schema."""
    with pytest.raises(ValidationError):
        chat._business_event(
            "navigation",
            "ready",
            intent="navigation",
            display="正在打开企业全景。",
            payload={"route_key": "overview"},
            route_key="overview",
            url="https://attacker.example",
        )


def test_business_event_rejects_reserved_field_overrides():
    """Compatibility fields must not be able to replace validated status or kind values."""
    with pytest.raises(ValueError, match="reserved business event field"):
        chat._business_event(
            "form_preview",
            "ready",
            intent="form_preview",
            display="已整理报销表单预览，请确认内容后再提交。",
            payload={"form": "expense", "preview": {}},
            form="expense",
            preview={},
            status="completed",
        )
