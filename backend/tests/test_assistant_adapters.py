import json

import pytest
from fastapi import HTTPException
from sqlalchemy import event, create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.assistant.registry import get_action
import app.assistant.service as assistant_service
from app.db import Base
from app.deps import Principal
from app.models import (
    ApprovalInstance,
    ApprovalTask,
    Department,
    EmployeeProfile,
    ExpenseClaim,
    Project,
    Ticket,
    User,
    UserDepartment,
    UserRole,
    WorkflowDefinition,
    WorkflowNode,
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


def _principal(*, user_id: str, role: str = "admin", department_ids: tuple[str, ...] = ()) -> Principal:
    return Principal(
        user_id=user_id,
        username=user_id,
        role=role,
        department_id=department_ids[0] if department_ids else None,
        department_ids=department_ids,
    )


def _payload(name: str, **values):
    action = get_action(name)
    assert action is not None
    return action.input_model.model_validate(values).model_dump(mode="python")


def _adapter(name: str):
    return assistant_service._ACTION_ADAPTERS[name]


def test_installation_registers_the_approved_read_and_write_actions(monkeypatch):
    """Omitting an approved adapter would make a confirmed catalog action unsupported."""
    from app.assistant.adapters import install_production_adapters

    monkeypatch.setattr(assistant_service, "_ACTION_ADAPTERS", {})

    install_production_adapters()
    install_production_adapters()

    assert set(assistant_service._ACTION_ADAPTERS) == {
        "search_knowledge",
        "list_departments",
        "list_projects",
        "list_contracts",
        "list_expenses",
        "list_approvals",
        "list_tickets",
        "create_org_unit",
        "update_org_unit",
        "create_project",
        "update_project",
        "delete_project",
        "create_contract",
        "update_contract",
        "delete_contract",
        "create_document",
        "update_document",
        "delete_document",
        "create_expense_draft", "update_expense_draft", "delete_expense_draft", "create_leave_request", "create_ticket", "delete_ticket", "approve_approval", "reject_approval", "cancel_approval", "pay_expense", "generate_payroll",
    }


def test_root_without_memberships_searches_every_department_and_returns_safe_chunks(db, monkeypatch):
    """Replacing root scope with memberships would silently hide other departments' knowledge."""
    from app.assistant import adapters

    db.add_all([
        Department(id="dept-a", name="研发", code="RND"),
        Department(id="dept-b", name="财务", code="FIN"),
    ])
    db.flush()
    captured: dict[str, object] = {}

    def fake_search(_db, *, department_ids, query, top_k, document_ids=None):
        captured.update(department_ids=tuple(department_ids), query=query, top_k=top_k)
        return [
            adapters.RetrievedChunk(
                chunk_id="chunk-1",
                document_id="doc-1",
                text="研发制度摘要",
                bm25_score=0.2,
                cosine_score=0.7,
                combined_score=0.5,
            )
        ]

    monkeypatch.setattr(adapters.retriever, "search_departments", fake_search)
    adapters.install_production_adapters()

    result = _adapter("search_knowledge")(db, _principal(user_id="root"), _payload("search_knowledge", query=" 制度 "))

    assert captured == {"department_ids": ("dept-a", "dept-b"), "query": "制度", "top_k": 8}
    assert result == {
        "items": [{
            "document_id": "doc-1",
            "document_title": "",
            "chunk_id": "chunk-1",
            "excerpt": "研发制度摘要",
            "score": 0.5,
        }],
        "count": 1,
    }
    json.dumps(result)


def test_non_root_cannot_filter_read_actions_to_another_department(db):
    """Dropping the requested-scope check would let a manager enumerate another department's projects."""
    from app.assistant.adapters import install_production_adapters

    db.add_all([
        Department(id="dept-a", name="研发", code="RND"),
        Department(id="dept-b", name="财务", code="FIN"),
    ])
    db.flush()
    install_production_adapters()

    with pytest.raises(HTTPException) as exc_info:
        _adapter("list_projects")(
            db,
            _principal(user_id="manager", role="manager", department_ids=("dept-a",)),
            _payload("list_projects", department_id="dept-b"),
        )

    assert exc_info.value.status_code == 403


def test_expense_ticket_and_approval_adapters_keep_existing_visibility_boundaries(db):
    """Removing any established visibility predicate would leak a peer's financial, ticket, or approval record."""
    from app.assistant.adapters import install_production_adapters

    db.add_all([
        Department(id="dept-a", name="研发", code="RND"),
        Department(id="dept-b", name="财务", code="FIN"),
        User(id="viewer", username="viewer", password_encrypted="secret", role="manager", department_id="dept-a"),
        User(id="employee", username="employee", password_encrypted="secret", role="employee", department_id="dept-a"),
        User(id="outsider", username="outsider", password_encrypted="secret", role="employee", department_id="dept-b"),
        UserDepartment(user_id="viewer", department_id="dept-a", is_primary=True),
        EmployeeProfile(user_id="employee", full_name="Employee", manager_id="viewer"),
        EmployeeProfile(user_id="outsider", full_name="Outsider"),
        ExpenseClaim(id="expense-visible", claim_no="EXP-1", requester_id="employee", department_id="dept-a", title="可见费用"),
        ExpenseClaim(id="expense-hidden", claim_no="EXP-2", requester_id="outsider", department_id="dept-b", title="隐藏费用"),
        Ticket(id="ticket-visible", requester_id="employee", department_id="dept-a", ticket_type="issue", subject="可见工单", description="visible", status="in_progress"),
        Ticket(id="ticket-hidden", requester_id="outsider", department_id="dept-b", ticket_type="issue", subject="隐藏工单", description="hidden", status="in_progress"),
        WorkflowDefinition(id="flow-1", code="flow-1", name="审批流", version=1, active=True),
        ApprovalInstance(id="approval-visible", definition_id="flow-1", entity_type="expense_claim", entity_id="expense-visible", requester_id="viewer"),
        ApprovalInstance(id="approval-hidden", definition_id="flow-1", entity_type="expense_claim", entity_id="expense-hidden", requester_id="outsider"),
    ])
    db.flush()
    install_production_adapters()
    principal = _principal(user_id="viewer", role="manager", department_ids=("dept-a",))

    expenses = _adapter("list_expenses")(db, principal, _payload("list_expenses"))
    tickets = _adapter("list_tickets")(db, principal, _payload("list_tickets"))
    approvals = _adapter("list_approvals")(db, principal, _payload("list_approvals"))

    assert [item["id"] for item in expenses["items"]] == ["expense-visible"]
    assert [item["id"] for item in tickets["items"]] == ["ticket-visible"]
    assert [item["id"] for item in approvals["items"]] == ["approval-visible"]


def test_project_results_are_bounded_json_only_and_do_not_serialize_secret_fields(db):
    """Removing the output projection or limit could return an unbounded ORM object graph to the assistant."""
    from app.assistant.adapters import install_production_adapters

    db.add(Department(id="dept-a", name="研发", code="RND"))
    db.add_all(
        [
            Project(id=f"project-{index:02d}", code=f"P-{index:02d}", name=f"项目 {index:02d}", department_id="dept-a")
            for index in range(51)
        ]
    )
    db.flush()
    install_production_adapters()

    result = _adapter("list_projects")(db, _principal(user_id="root"), _payload("list_projects"))

    assert result["count"] == 50
    assert len(result["items"]) == 50
    assert {"password", "password_encrypted", "token", "content", "salary"}.isdisjoint(result["items"][0])
    json.dumps(result)


@pytest.mark.parametrize(
    ("action_name", "table_name"),
    [
        ("list_expenses", "expense_claims"),
        ("list_approvals", "approval_instances"),
        ("list_tickets", "tickets"),
    ],
)
def test_sensitive_and_workflow_lists_limit_the_database_page_before_visibility_projection(
    db, action_name, table_name
):
    """Removing a database limit would materialize every matching sensitive row before authorization."""
    from app.assistant.adapters import install_production_adapters

    db.add_all([
        Department(id="dept-a", name="研发", code="RND"),
        User(id="root", username="root", password_encrypted="secret", role="admin"),
        WorkflowDefinition(id="flow-1", code="flow-1", name="审批流", version=1, active=True),
    ])
    db.add_all(
        [
            ExpenseClaim(
                id=f"expense-{index:02d}",
                claim_no=f"EXP-{index:02d}",
                requester_id="root",
                department_id="dept-a",
                title=f"费用 {index:02d}",
            )
            for index in range(51)
        ]
        + [
            ApprovalInstance(
                id=f"approval-{index:02d}",
                definition_id="flow-1",
                entity_type="expense_claim",
                entity_id=f"expense-{index:02d}",
                requester_id="root",
            )
            for index in range(51)
        ]
        + [
            Ticket(
                id=f"ticket-{index:02d}",
                requester_id="root",
                department_id="dept-a",
                ticket_type="issue",
                subject=f"工单 {index:02d}",
                description="详情",
                status="in_progress",
            )
            for index in range(51)
        ]
    )
    db.flush()
    install_production_adapters()
    statements: list[str] = []

    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement.upper())

    event.listen(db.bind, "before_cursor_execute", capture)
    try:
        result = _adapter(action_name)(db, _principal(user_id="root"), _payload(action_name))
    finally:
        event.remove(db.bind, "before_cursor_execute", capture)

    base_queries = [statement for statement in statements if f"FROM {table_name.upper()}" in statement]
    assert len(result["items"]) == 50
    assert base_queries
    assert any("LIMIT" in statement for statement in base_queries)


def test_project_and_approval_pages_prefetch_related_rows_in_constant_query_batches(db):
    """Replacing prefetched maps with per-row lookups would turn a 50-row page into N+1 database queries."""
    from app.assistant.adapters import install_production_adapters

    db.add_all([
        Department(id="dept-a", name="研发", code="RND"),
        User(id="viewer", username="viewer", password_encrypted="secret", role="manager", department_id="dept-a"),
        WorkflowDefinition(id="flow-1", code="flow-1", name="审批流", version=1, active=True),
        WorkflowNode(id="node-1", definition_id="flow-1", sequence=1, name="审批", assignee_type="role", assignee_role="manager"),
    ])
    db.add_all(
        [
            User(id=f"manager-{index:02d}", username=f"manager-{index:02d}", password_encrypted="secret", role="manager")
            for index in range(50)
        ]
        + [
            Project(
                id=f"project-{index:02d}",
                code=f"P-{index:02d}",
                name=f"项目 {index:02d}",
                department_id="dept-a",
                manager_id=f"manager-{index:02d}",
            )
            for index in range(50)
        ]
        + [
            ApprovalInstance(
                id=f"approval-{index:02d}",
                definition_id="flow-1",
                entity_type="project",
                entity_id=f"project-{index:02d}",
                requester_id="viewer",
            )
            for index in range(50)
        ]
        + [
            ApprovalTask(
                id=f"task-{index:02d}",
                instance_id=f"approval-{index:02d}",
                node_id="node-1",
                sequence=1,
                assignee_role="manager",
                department_id="dept-a",
            )
            for index in range(50)
        ]
    )
    db.flush()
    db.expire_all()
    install_production_adapters()
    statements: list[str] = []

    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement.upper())

    event.listen(db.bind, "before_cursor_execute", capture)
    try:
        projects = _adapter("list_projects")(db, _principal(user_id="viewer", role="manager", department_ids=("dept-a",)), _payload("list_projects"))
        approvals = _adapter("list_approvals")(db, _principal(user_id="viewer", role="manager", department_ids=("dept-a",)), _payload("list_approvals"))
    finally:
        event.remove(db.bind, "before_cursor_execute", capture)

    assert len(projects["items"]) == 50
    assert len(approvals["items"]) == 50
    assert sum("FROM USERS" in statement for statement in statements) <= 2
    assert sum("FROM APPROVAL_TASKS" in statement for statement in statements) <= 2


@pytest.mark.parametrize("actor_role", ["finance", "manager"])
def test_expense_visibility_is_evaluated_once_for_a_finance_or_manager_page(db, actor_role):
    """Rechecking each claim through can_view would issue one role/profile lookup per visible expense."""
    from app.assistant.adapters import install_production_adapters

    db.add_all([
        Department(id="dept-a", name="研发", code="RND"),
        User(id="actor", username="actor", password_encrypted="secret", role=actor_role, department_id="dept-a"),
    ])
    if actor_role == "finance":
        db.add(UserRole(user_id="actor", role="finance"))
    db.add_all([
        User(id=f"claimant-{index:02d}", username=f"claimant-{index:02d}", password_encrypted="secret", role="employee")
        for index in range(50)
    ])
    if actor_role == "manager":
        db.add_all([
            EmployeeProfile(user_id=f"claimant-{index:02d}", full_name=f"申请人 {index:02d}", manager_id="actor")
            for index in range(50)
        ])
    db.add_all([
        ExpenseClaim(
            id=f"expense-{index:02d}",
            claim_no=f"EXP-{index:02d}",
            requester_id=f"claimant-{index:02d}",
            department_id="dept-a",
            title=f"费用 {index:02d}",
        )
        for index in range(50)
    ])
    db.flush()
    db.expire_all()
    install_production_adapters()
    statements: list[str] = []

    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement.upper())

    event.listen(db.bind, "before_cursor_execute", capture)
    try:
        result = _adapter("list_expenses")(
            db,
            _principal(user_id="actor", role=actor_role, department_ids=("dept-a",)),
            _payload("list_expenses"),
        )
    finally:
        event.remove(db.bind, "before_cursor_execute", capture)

    assert len(result["items"]) == 50
    assert sum("FROM USER_ROLES" in statement for statement in statements) <= 1
    assert sum("FROM EMPLOYEE_PROFILES" in statement for statement in statements) <= 1


def test_approval_list_omits_unbounded_task_history_but_keeps_department(db):
    """Ranking every task in an instance history would make one approval result read unbounded history."""
    from app.assistant.adapters import install_production_adapters

    db.add_all([
        Department(id="dept-a", name="研发", code="RND"),
        User(id="requester", username="requester", password_encrypted="secret", role="manager", department_id="dept-a"),
        WorkflowDefinition(id="flow-1", code="flow-1", name="审批流", version=1, active=True),
        WorkflowNode(id="node-1", definition_id="flow-1", sequence=1, name="审批", assignee_type="role", assignee_role="manager"),
        ApprovalInstance(id="approval-1", definition_id="flow-1", entity_type="project", entity_id="project-1", requester_id="requester"),
    ])
    db.add_all([
        ApprovalTask(
            id=f"task-{index:04d}",
            instance_id="approval-1",
            node_id="node-1",
            sequence=index,
            assignee_role="manager",
            department_id="dept-a",
        )
        for index in range(200)
    ])
    db.flush()
    install_production_adapters()
    statements: list[str] = []

    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement.upper())

    event.listen(db.bind, "before_cursor_execute", capture)
    try:
        result = _adapter("list_approvals")(
            db,
            _principal(user_id="requester", role="manager", department_ids=("dept-a",)),
            _payload("list_approvals"),
        )
    finally:
        event.remove(db.bind, "before_cursor_execute", capture)

    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["id"] == "approval-1"
    assert item["department_id"] == "dept-a"
    assert item["requester_name"] == "requester"
    assert "tasks" not in item
    assert not any("ROW_NUMBER" in statement for statement in statements)


def test_approval_department_uses_the_first_task_before_requester_fallback(db):
    """Replacing first-task scope with requester scope would mislabel and misfilter cross-department approvals."""
    from app.assistant.adapters import install_production_adapters

    db.add_all([
        Department(id="dept-a", name="研发", code="RND"),
        Department(id="dept-b", name="财务", code="FIN"),
        User(id="requester", username="requester", password_encrypted="secret", role="employee", department_id="dept-a"),
        WorkflowDefinition(id="flow-1", code="flow-1", name="审批流", version=1, active=True),
        WorkflowNode(id="node-1", definition_id="flow-1", sequence=1, name="审批", assignee_type="role", assignee_role="finance"),
        ApprovalInstance(id="approval-1", definition_id="flow-1", entity_type="expense_claim", entity_id="expense-1", requester_id="requester"),
        ApprovalTask(id="task-first", instance_id="approval-1", node_id="node-1", sequence=1, assignee_role="finance", department_id="dept-b"),
        ApprovalTask(id="task-later", instance_id="approval-1", node_id="node-1", sequence=2, assignee_role="finance", department_id="dept-a"),
    ])
    db.flush()
    install_production_adapters()
    root = _principal(user_id="root")

    all_departments = _adapter("list_approvals")(db, root, _payload("list_approvals"))
    finance = _adapter("list_approvals")(db, root, _payload("list_approvals", department_id="dept-b"))
    engineering = _adapter("list_approvals")(db, root, _payload("list_approvals", department_id="dept-a"))

    assert all_departments["items"][0]["department_id"] == "dept-b"
    assert [item["id"] for item in finance["items"]] == ["approval-1"]
    assert engineering["items"] == []
