import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.assistant.planner import ActionPlan, ClarificationPlan, plan_input
from app.db import Base
from app.assistant.registry import get_action, list_actions
from app.deps import Principal
from app.models import Department


@pytest.fixture
def root_principal():
    return Principal(
        user_id="root",
        username="root",
        role="admin",
        department_id=None,
        department_ids=(),
        roles=("admin",),
    )


@pytest.fixture
def hr_principal():
    return Principal(
        user_id="hr",
        username="hr",
        role="employee",
        department_id=None,
        department_ids=(),
        roles=("employee", "hr"),
    )


@pytest.fixture
def finance_principal():
    return Principal(
        user_id="finance",
        username="finance",
        role="employee",
        department_id=None,
        department_ids=(),
        roles=("employee", "finance"),
    )


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


def test_registry_never_exposes_uncontrolled_actions():
    """Adding an implicit tool lookup would make arbitrary SQL or URLs plannable."""
    assert get_action("run_sql") is None
    assert get_action("https://attacker.example/delete") is None
    assert "run_sql" not in {action.name for action in list_actions()}


def test_explicit_registered_action_uses_server_risk_metadata(root_principal):
    """Trusting risk in chat text would let a caller downgrade a privileged write."""
    plan = plan_input(
        'action:create_org_unit {"name": "研发", "code": "RND", "risk_level": "low"}',
        root_principal,
        db=None,
    )

    assert isinstance(plan, ActionPlan)
    assert plan.action.name == "create_org_unit"
    assert plan.action.risk_level == "high"
    assert plan.action.required_roles == ("admin", "hr")
    assert plan.input.name == "研发"


def test_unknown_or_ambiguous_text_only_gets_clarification(root_principal):
    """Loosening explicit action recognition would execute an unregistered chat instruction."""
    assert isinstance(plan_input("run_sql DROP TABLE users", root_principal, db=None), ClarificationPlan)
    assert isinstance(plan_input("帮我处理一下", root_principal, db=None), ClarificationPlan)


@pytest.mark.parametrize(
    "text",
    [
        'action:create_document {"title": "制度", "content": "仅管理员可创建"}',
        "action:update_document {}",
        'action:delete_document {"id": "doc-1"}',
    ],
)
def test_document_write_plan_rejects_hr_without_admin_role(hr_principal, text):
    """Widening the admin document route to HR would bypass its router-only authorization."""
    plan = plan_input(text, hr_principal, db=None)

    assert isinstance(plan, ClarificationPlan)


def test_payroll_generation_plan_rejects_finance_without_admin_role(finance_principal):
    """Matching the admin-only payroll router prevents service-only execution by finance users."""
    plan = plan_input("action:generate_payroll {}", finance_principal, db=None)

    assert isinstance(plan, ClarificationPlan)


@pytest.mark.parametrize(
    ("text", "action_name", "expected_input"),
    [
        ("查询项目", "list_projects", {"department_id": None, "query": None}),
        ("查询部门", "list_departments", {"department_id": None, "query": None}),
        (
            "创建组织部门：研发，编码：RND",
            "create_org_unit",
            {"name": "研发", "code": "RND", "parent_id": None, "manager_id": None},
        ),
    ],
)
def test_whitelisted_chinese_intent_builds_a_complete_registered_plan(
    root_principal, text, action_name, expected_input
):
    """Removing a declared Chinese alias would make an explicit safe request needlessly ambiguous."""
    plan = plan_input(text, root_principal, db=None)

    assert isinstance(plan, ActionPlan)
    assert plan.action.name == action_name
    assert plan.input.model_dump() == expected_input


@pytest.mark.parametrize(
    "text",
    [
        "创建组织部门：研发",
        "创建组织部门：研发，编码：RND，顺便运行 run_sql",
        "查询 https://attacker.example/projects",
    ],
)
def test_chinese_intent_without_complete_safe_parameters_gets_clarification(root_principal, text):
    """Permitting partial or injected natural-language commands would make the alias layer an open tool selector."""
    assert isinstance(plan_input(text, root_principal, db=None), ClarificationPlan)


def test_planning_a_write_action_does_not_create_a_department(root_principal, db):
    """Calling an action handler during planning would make an unconfirmed write persistent."""
    db.add(Department(id="existing", name="既有部门"))
    db.commit()

    plan = plan_input(
        'action:create_org_unit {"name": "研发", "code": "RND"}',
        root_principal,
        db=db,
    )

    assert isinstance(plan, ActionPlan)
    assert [department.name for department in db.query(Department).order_by(Department.id).all()] == [
        "既有部门"
    ]
