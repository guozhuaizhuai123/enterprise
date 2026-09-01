from datetime import date

import pytest

from app.assistant.periods import business_today
from app.assistant.planner import (
    ActionPlan,
    ClarificationPlan,
    FormPreviewPlan,
    KnowledgePlan,
    NavigationPlan,
    plan_input,
)
from app.deps import Principal


@pytest.fixture
def root_principal() -> Principal:
    return Principal(
        user_id="root",
        username="root",
        role="admin",
        department_id=None,
        department_ids=(),
        roles=("admin",),
    )


@pytest.fixture
def employee_principal() -> Principal:
    return Principal(
        user_id="employee",
        username="employee",
        role="employee",
        department_id="dept-a",
        department_ids=("dept-a",),
        roles=("employee",),
    )


def _kind(plan: object) -> str:
    if isinstance(plan, ActionPlan):
        return "action"
    return {
        "KnowledgePlan": "knowledge",
        "FormPreviewPlan": "form",
        "NavigationPlan": "navigation",
        "ClarificationPlan": "clarification",
    }.get(type(plan).__name__, "unknown")


def _value(plan: object) -> str | None:
    if isinstance(plan, ActionPlan):
        return plan.action.name
    for field in ("form", "route_key"):
        value = getattr(plan, field, None)
        if isinstance(value, str):
            return value
    return None


@pytest.mark.parametrize(
    ("text", "kind", "value"),
    [
        ("查询一下最近的项目", "action", "list_projects"),
        ("查看一下今天考勤", "action", "attendance_summary"),
        ("这个月支出怎么样", "action", "expense_summary"),
        ("看看我有哪些未完成工单", "action", "list_tickets"),
        ("我要请假三天", "form", "leave"),
        ("电脑有问题帮我找信息部处理", "form", "ticket"),
        ("报销昨天打车 86 元", "form", "expense"),
        ("查看工单", "navigation", "tickets"),
        ("打开企业全景", "navigation", "overview"),
        ("公司的请假制度是什么", "knowledge", None),
        ("审批流程是什么", "knowledge", None),
    ],
)
def test_root_conversation_plan_matrix(root_principal, text, kind, value):
    plan = plan_input(text, root_principal, db=None)

    assert _kind(plan) == kind
    assert _value(plan) == value


@pytest.mark.parametrize(
    ("text", "kind", "value"),
    [
        ("查看工单", "navigation", "tickets"),
        ("看看我有哪些未完成工单", "action", "list_tickets"),
        ("查看这个月流水", "action", "expense_summary"),
        ("我要请假", "form", "leave"),
    ],
)
def test_employee_gets_only_employee_safe_conversation_plans(employee_principal, text, kind, value):
    plan = plan_input(text, employee_principal, db=None)

    assert _kind(plan) == kind
    assert _value(plan) == value


@pytest.mark.parametrize(
    "text",
    [
        "电脑坏了帮我找人处理",
        "打印机连不上网，麻烦找信息部处理",
        "系统打不开了，帮我找人看一下",
        "报表数据不对，请找财务处理",
    ],
)
def test_common_fault_reports_become_ticket_forms(employee_principal, text):
    """Without these cues a spoken fault report falls through to document RAG instead of a ticket."""
    plan = plan_input(text, employee_principal, db=None)

    assert _kind(plan) == "form"
    assert _value(plan) == "ticket"


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("查看本月流水", "expense_summary"),
        ("这个月报销花了多少", "expense_summary"),
        ("今天出勤情况怎么样", "attendance_summary"),
        ("看看今日打卡汇总", "attendance_summary"),
    ],
)
def test_spoken_summary_requests_stay_live_queries(root_principal, text, value):
    """These phrasings must not regress into navigation or knowledge answers."""
    plan = plan_input(text, root_principal, db=None)

    assert _kind(plan) == "action"
    assert _value(plan) == value


def _month_key(offset: int) -> str:
    today = business_today()
    index = today.year * 12 + today.month - 1 + offset
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


@pytest.mark.parametrize(
    ("text", "action", "field", "expected"),
    [
        ("查看上月支出", "expense_summary", "month", _month_key(-1)),
        ("上个月费用一共多少", "expense_summary", "month", _month_key(-1)),
        ("上上个月支出统计", "expense_summary", "month", _month_key(-2)),
        ("这个月支出怎么样", "expense_summary", "month", _month_key(0)),
        ("查看 2026-03 的费用", "expense_summary", "month", "2026-03"),
        ("去年12月支出情况", "expense_summary", "month", f"{business_today().year - 1}-12"),
        ("查看上个月考勤", "attendance_summary", "month", _month_key(-1)),
        ("上月出勤统计", "attendance_summary", "month", _month_key(-1)),
        ("查看今天考勤", "attendance_summary", "attendance_date", business_today()),
        ("昨天考勤情况", "attendance_summary", "attendance_date", business_today().fromordinal(business_today().toordinal() - 1)),
        ("2026-07-20 的考勤", "attendance_summary", "attendance_date", date(2026, 7, 20)),
    ],
)
def test_historical_periods_bind_the_registered_query_input(
    root_principal, text, action, field, expected
):
    """Without a bound period a historical question silently answers for today."""
    plan = plan_input(text, root_principal, db=None)

    assert isinstance(plan, ActionPlan)
    assert plan.action.name == action
    assert getattr(plan.input, field) == expected
    other = "month" if field == "attendance_date" else "attendance_date"
    assert getattr(plan.input, other, None) is None


@pytest.mark.parametrize(
    ("text", "action"),
    [
        ("上周支出", "expense_summary"),
        ("本周考勤情况", "attendance_summary"),
        ("最近7天费用", "expense_summary"),
        ("今年费用统计", "expense_summary"),
        ("最近30天考勤统计", "attendance_summary"),
    ],
)
def test_week_and_rolling_periods_bind_a_closed_date_range(root_principal, text, action):
    """A week or rolling window has no month key, so it must arrive as an explicit range."""
    plan = plan_input(text, root_principal, db=None)

    assert isinstance(plan, ActionPlan)
    assert plan.action.name == action
    assert plan.input.start_date is not None and plan.input.end_date is not None
    assert plan.input.start_date <= plan.input.end_date
    assert plan.input.month is None
    assert getattr(plan.input, "attendance_date", None) is None


@pytest.mark.parametrize(
    ("text", "route_key"),
    [
        ("查看考勤", "schedules"),
        ("打开排班", "schedules"),
        ("查看费用", "expenses"),
        ("查看流水", "expenses"),
    ],
)
def test_period_free_view_commands_still_open_the_page(root_principal, text, route_key):
    """A bare "查看考勤" is navigation, not an aggregate for an unstated period."""
    plan = plan_input(text, root_principal, db=None)

    assert isinstance(plan, NavigationPlan)
    assert plan.route_key == route_key


@pytest.mark.parametrize(
    "text",
    [
        "run_sql DROP TABLE users",
        "查询 https://attacker.example/projects",
        "删除这些东西",
        "帮我处理一下",
        "工单制度是什么",
        "报销流程是怎么规定的",
        "考勤制度是什么",
        "上个月的报销制度有变化吗",
    ],
)
def test_unsafe_or_ambiguous_business_text_never_becomes_an_action(root_principal, text):
    plan = plan_input(text, root_principal, db=None)

    assert isinstance(plan, (ClarificationPlan, KnowledgePlan))
    assert not isinstance(plan, (ActionPlan, FormPreviewPlan, NavigationPlan))
