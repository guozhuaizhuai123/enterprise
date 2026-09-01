import asyncio
from unittest.mock import AsyncMock

import pytest

from app.assistant import intent_extractor
from app.assistant.planner import ActionPlan, ClarificationPlan, KnowledgePlan, NavigationPlan
from app.deps import Principal


@pytest.fixture
def root_principal() -> Principal:
    return Principal("root", "root", "admin", None, (), ("admin",))


@pytest.fixture
def employee_principal() -> Principal:
    return Principal(
        "employee",
        "employee",
        "employee",
        "dept-a",
        ("dept-a",),
        ("employee",),
    )


def test_unregistered_sql_candidate_fails_closed(monkeypatch, root_principal):
    """Trusting an LLM tool name would make arbitrary SQL executable."""
    call_json = AsyncMock(
        return_value={
            "kind": "action",
            "name": "run_sql",
            "arguments": {"sql": "DROP TABLE users"},
        }
    )
    monkeypatch.setattr(intent_extractor, "call_json", call_json)

    plan = asyncio.run(intent_extractor.plan_conversation("清空用户", root_principal, db=None))

    assert isinstance(plan, ClarificationPlan)
    call_json.assert_awaited_once()


def test_explicit_rule_survives_llm_failure_without_calling_llm(monkeypatch, root_principal):
    """Sending a complete rule intent to an unavailable model would break offline operations."""
    call_json = AsyncMock(side_effect=RuntimeError("offline"))
    monkeypatch.setattr(intent_extractor, "call_json", call_json)

    plan = asyncio.run(
        intent_extractor.plan_conversation("查看今天考勤", root_principal, db=None)
    )

    assert isinstance(plan, ActionPlan)
    assert plan.action.name == "attendance_summary"
    call_json.assert_not_awaited()


@pytest.mark.parametrize(
    "candidate",
    [
        {"kind": "action", "name": "create_org_unit", "arguments": {"name": "研发", "code": "RND"}},
        {"kind": "action", "name": "create_expense_draft", "arguments": {}},
    ],
)
def test_unauthorized_or_invalid_action_candidate_fails_closed(
    monkeypatch, employee_principal, candidate
):
    """Skipping server role or Pydantic validation would authorize malformed writes."""
    monkeypatch.setattr(intent_extractor, "call_json", AsyncMock(return_value=candidate))

    plan = asyncio.run(
        intent_extractor.plan_conversation("请创建一项业务记录", employee_principal, db=None)
    )

    assert isinstance(plan, ClarificationPlan)


@pytest.mark.parametrize("route_key", ["unknown", "payroll"])
def test_unknown_or_unauthorized_route_candidate_fails_closed(
    monkeypatch, employee_principal, route_key
):
    """Accepting a model-provided route outside the role whitelist would bypass UI authorization."""
    monkeypatch.setattr(
        intent_extractor,
        "call_json",
        AsyncMock(return_value={"kind": "navigation", "route_key": route_key}),
    )

    plan = asyncio.run(
        intent_extractor.plan_conversation("请带我去办理业务", employee_principal, db=None)
    )

    assert isinstance(plan, ClarificationPlan)


def test_allowed_route_ignores_candidate_url(monkeypatch, employee_principal):
    """An arbitrary model URL must never cross the server-owned route-key boundary."""
    monkeypatch.setattr(
        intent_extractor,
        "call_json",
        AsyncMock(
            return_value={
                "kind": "navigation",
                "route_key": "tickets",
                "url": "https://attacker.example/steal",
            }
        ),
    )

    plan = asyncio.run(
        intent_extractor.plan_conversation("请带我去办理业务", employee_principal, db=None)
    )

    assert plan == NavigationPlan(route_key="tickets")
    assert not hasattr(plan, "url")


def test_action_candidate_uses_registry_risk_and_ignores_downgrade(monkeypatch, root_principal):
    """Using candidate risk metadata would let a high-risk write skip confirmation."""
    monkeypatch.setattr(
        intent_extractor,
        "call_json",
        AsyncMock(
            return_value={
                "kind": "action",
                "name": "create_org_unit",
                "arguments": {"name": "研发", "code": "RND"},
                "risk_level": "low",
                "handler": "run_sql",
                "http_method": "DELETE",
            }
        ),
    )

    plan = asyncio.run(
        intent_extractor.plan_conversation("请创建一个研发组织部门", root_principal, db=None)
    )

    assert isinstance(plan, ActionPlan)
    assert plan.action.name == "create_org_unit"
    assert plan.action.risk_level == "high"
    assert plan.input.model_dump() == {
        "name": "研发",
        "code": "RND",
        "parent_id": None,
        "manager_id": None,
    }


def test_prompt_contains_only_employee_authorized_catalog_metadata(
    monkeypatch, employee_principal
):
    """Leaking admin actions or runtime data into the prompt would widen the model trust boundary."""
    call_json = AsyncMock(return_value={})
    monkeypatch.setattr(intent_extractor, "call_json", call_json)
    database_marker = object()

    plan = asyncio.run(
        intent_extractor.plan_conversation(
            "请创建一项业务记录", employee_principal, db=database_marker
        )
    )

    assert isinstance(plan, ClarificationPlan)
    system_prompt, user_prompt = call_json.await_args.args
    prompt = system_prompt + "\n" + user_prompt
    assert "attendance_summary" in prompt
    assert "department_id" in prompt
    assert "tickets" in prompt
    assert "create_org_unit" not in prompt
    assert repr(database_marker) not in prompt
    for forbidden in ("risk_level", "handler", "http_method", "salary", "secret", "token"):
        assert forbidden not in prompt.lower()


def test_ordinary_knowledge_question_does_not_call_llm(monkeypatch, employee_principal):
    """Routing policy questions through the action extractor would risk accidental execution."""
    call_json = AsyncMock()
    monkeypatch.setattr(intent_extractor, "call_json", call_json)

    plan = asyncio.run(
        intent_extractor.plan_conversation("公司的请假制度是什么", employee_principal, db=None)
    )

    assert isinstance(plan, KnowledgePlan)
    call_json.assert_not_awaited()


def test_generic_ambiguous_request_stays_clarification_without_llm(monkeypatch, root_principal):
    """A model must not invent a business object from a generic help request."""
    call_json = AsyncMock()
    monkeypatch.setattr(intent_extractor, "call_json", call_json)

    plan = asyncio.run(
        intent_extractor.plan_conversation("帮我处理一下", root_principal, db=None)
    )

    assert isinstance(plan, ClarificationPlan)
    call_json.assert_not_awaited()


def test_unsafe_free_text_never_reaches_llm(monkeypatch, root_principal):
    """Letting unsafe SQL or URLs reach the model would permit tool-boundary laundering."""
    call_json = AsyncMock()
    monkeypatch.setattr(intent_extractor, "call_json", call_json)

    for text in ("run_sql DROP TABLE users", "查询 https://attacker.example/projects"):
        plan = asyncio.run(intent_extractor.plan_conversation(text, root_principal, db=None))
        assert isinstance(plan, ClarificationPlan)

    call_json.assert_not_awaited()
