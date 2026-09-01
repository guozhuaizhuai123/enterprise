import json
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import event, create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.assistant.registry import get_action, list_actions
import app.assistant.service as assistant_service
from app.db import Base
from app.deps import Principal
from app.models import (
    ApprovalInstance,
    ApprovalTask,
    AttendanceRecord,
    Contract,
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

    assert set(assistant_service._ACTION_ADAPTERS) == {action.name for action in list_actions()}


def test_attendance_summary_returns_live_aggregate_without_employee_names(db):
    """Removing the live attendance adapter would send an operational query through document RAG."""
    from app.assistant.adapters import install_production_adapters

    today = date.today()
    db.add(Department(id="dept-a", name="研发", code="RND"))
    db.add_all([
        User(id="employee-a", username="alice", password_encrypted="secret", role="employee", department_id="dept-a"),
        User(id="employee-b", username="bob", password_encrypted="secret", role="employee", department_id="dept-a"),
        UserDepartment(user_id="employee-a", department_id="dept-a", is_primary=True),
        UserDepartment(user_id="employee-b", department_id="dept-a", is_primary=True),
        EmployeeProfile(user_id="employee-a", full_name="Alice", status="active"),
        EmployeeProfile(user_id="employee-b", full_name="Bob", status="probation"),
        AttendanceRecord(user_id="employee-a", attendance_date=today, status="present", recorded_by="root"),
    ])
    db.flush()
    install_production_adapters()

    result = _adapter("attendance_summary")(
        db,
        _principal(user_id="root"),
        _payload("attendance_summary"),
    )

    assert result == {
        "date": today.isoformat(),
        "active_employees": 2,
        "recorded": 1,
        "missing": 1,
        "status_counts": {"present": 1, "late": 0, "absent": 0, "remote": 0},
    }
    assert "items" not in result


def test_attendance_summary_aggregates_a_past_month_and_an_explicit_day(db):
    """Ignoring the requested period would answer every historical question with today's numbers."""
    from app.assistant.adapters import install_production_adapters

    db.add(Department(id="dept-a", name="研发", code="RND"))
    db.add_all([
        User(id="employee-a", username="alice", password_encrypted="secret", role="employee", department_id="dept-a"),
        User(id="employee-b", username="bob", password_encrypted="secret", role="employee", department_id="dept-a"),
        UserDepartment(user_id="employee-a", department_id="dept-a", is_primary=True),
        UserDepartment(user_id="employee-b", department_id="dept-a", is_primary=True),
        EmployeeProfile(user_id="employee-a", full_name="Alice", status="active"),
        EmployeeProfile(user_id="employee-b", full_name="Bob", status="active"),
        AttendanceRecord(user_id="employee-a", attendance_date=date(2026, 7, 1), status="present", recorded_by="root"),
        AttendanceRecord(user_id="employee-a", attendance_date=date(2026, 7, 2), status="late", recorded_by="root"),
        AttendanceRecord(user_id="employee-b", attendance_date=date(2026, 7, 2), status="present", recorded_by="root"),
        AttendanceRecord(user_id="employee-a", attendance_date=date(2026, 8, 3), status="absent", recorded_by="root"),
    ])
    db.flush()
    install_production_adapters()

    month = _adapter("attendance_summary")(
        db,
        _principal(user_id="root"),
        _payload("attendance_summary", month="2026-07"),
    )

    assert month == {
        "month": "2026-07",
        "period_start": "2026-07-01",
        "period_end": "2026-07-31",
        "active_employees": 2,
        "records": 3,
        "days_recorded": 2,
        "employees_recorded": 2,
        "status_counts": {"present": 2, "late": 1, "absent": 0, "remote": 0},
    }

    day = _adapter("attendance_summary")(
        db,
        _principal(user_id="root"),
        _payload("attendance_summary", attendance_date="2026-08-03"),
    )

    assert day == {
        "date": "2026-08-03",
        "active_employees": 2,
        "recorded": 1,
        "missing": 1,
        "status_counts": {"present": 0, "late": 0, "absent": 1, "remote": 0},
    }


def test_attendance_summary_rejects_both_period_fields_and_an_invalid_month():
    """Accepting a day and a month together would make the aggregate ambiguous."""
    from pydantic import ValidationError

    from app.assistant.registry import get_action

    action = get_action("attendance_summary")
    assert action is not None
    with pytest.raises(ValidationError):
        action.input_model.model_validate({"attendance_date": "2026-08-03", "month": "2026-08"})
    with pytest.raises(ValidationError):
        action.input_model.model_validate({"month": "2026-13-01"})
    with pytest.raises(ValidationError):
        action.input_model.model_validate({"month": "2026-08", "start_date": "2026-08-01", "end_date": "2026-08-07"})
    with pytest.raises(ValidationError):
        action.input_model.model_validate({"start_date": "2026-08-07"})
    with pytest.raises(ValidationError):
        action.input_model.model_validate({"start_date": "2026-08-07", "end_date": "2026-08-01"})

    expense = get_action("expense_summary")
    assert expense is not None
    with pytest.raises(ValidationError):
        expense.input_model.model_validate({"month": "2026-08", "start_date": "2026-08-01", "end_date": "2026-08-07"})
    with pytest.raises(ValidationError):
        expense.input_model.model_validate({"start_date": "2024-01-01", "end_date": "2026-01-01"})


def test_summaries_aggregate_an_explicit_date_range(db):
    """A week question answered with a month would report the wrong total as exact."""
    from app.assistant.adapters import install_production_adapters

    db.add(Department(id="dept-a", name="研发", code="RND"))
    db.add_all([
        User(id="employee-a", username="alice", password_encrypted="secret", role="employee", department_id="dept-a"),
        UserDepartment(user_id="employee-a", department_id="dept-a", is_primary=True),
        EmployeeProfile(user_id="employee-a", full_name="Alice", status="active"),
        AttendanceRecord(user_id="employee-a", attendance_date=date(2026, 8, 24), status="present", recorded_by="root"),
        AttendanceRecord(user_id="employee-a", attendance_date=date(2026, 8, 31), status="late", recorded_by="root"),
        ExpenseClaim(
            id="claim-in-range",
            claim_no="EXP-RANGE-IN",
            requester_id="employee-a",
            department_id="dept-a",
            title="周内打车",
            purpose="客户拜访",
            total_amount=Decimal("120.00"),
            status="paid",
            created_at=datetime(2026, 8, 25, 2, 0, tzinfo=UTC),
        ),
        ExpenseClaim(
            id="claim-out-of-range",
            claim_no="EXP-RANGE-OUT",
            requester_id="employee-a",
            department_id="dept-a",
            title="月内其他",
            purpose="其他",
            total_amount=Decimal("300.00"),
            status="paid",
            created_at=datetime(2026, 8, 31, 2, 0, tzinfo=UTC),
        ),
    ])
    db.flush()
    install_production_adapters()

    attendance = _adapter("attendance_summary")(
        db,
        _principal(user_id="root"),
        _payload("attendance_summary", start_date="2026-08-24", end_date="2026-08-30"),
    )
    assert attendance["period_start"] == "2026-08-24"
    assert attendance["period_end"] == "2026-08-30"
    assert attendance["records"] == 1
    assert "month" not in attendance

    expenses = _adapter("expense_summary")(
        db,
        _principal(user_id="employee-a", role="employee", department_ids=("dept-a",)),
        _payload("expense_summary", start_date="2026-08-24", end_date="2026-08-30"),
    )
    assert expenses["period_start"] == "2026-08-24"
    assert expenses["period_end"] == "2026-08-30"
    assert expenses["count"] == 1
    assert expenses["amount"] == "120.00"
    assert "month" not in expenses


def test_employee_attendance_summary_never_includes_a_colleague(db):
    from app.assistant.adapters import install_production_adapters

    today = date.today()
    db.add(Department(id="dept-a", name="研发", code="RND"))
    db.add_all([
        User(id="employee-a", username="alice", password_encrypted="secret", role="employee", department_id="dept-a"),
        User(id="employee-b", username="bob", password_encrypted="secret", role="employee", department_id="dept-a"),
        EmployeeProfile(user_id="employee-a", full_name="Alice", status="active"),
        EmployeeProfile(user_id="employee-b", full_name="Bob", status="active"),
        AttendanceRecord(user_id="employee-a", attendance_date=today, status="remote", recorded_by="employee-a"),
        AttendanceRecord(user_id="employee-b", attendance_date=today, status="late", recorded_by="employee-b"),
    ])
    db.flush()
    install_production_adapters()

    result = _adapter("attendance_summary")(
        db,
        _principal(user_id="employee-a", role="employee", department_ids=("dept-a",)),
        _payload("attendance_summary"),
    )

    assert result == {
        "date": today.isoformat(),
        "active_employees": 1,
        "recorded": 1,
        "missing": 0,
        "status_counts": {"present": 0, "late": 0, "absent": 0, "remote": 1},
    }


def test_employee_expense_summary_contains_only_own_month(db):
    from app.assistant.adapters import install_production_adapters

    db.add(Department(id="dept-a", name="研发", code="RND"))
    db.add_all([
        User(id="employee", username="employee", password_encrypted="secret", role="employee", department_id="dept-a"),
        User(id="colleague", username="colleague", password_encrypted="secret", role="employee", department_id="dept-a"),
        ExpenseClaim(
            id="own-expense",
            claim_no="EXP-OWN",
            requester_id="employee",
            department_id="dept-a",
            title="本人交通费",
            total_amount=Decimal("86.00"),
            status="draft",
            created_at=datetime(2026, 9, 1, 2, 0, tzinfo=UTC),
        ),
        ExpenseClaim(
            id="peer-expense",
            claim_no="EXP-PEER",
            requester_id="colleague",
            department_id="dept-a",
            title="同事费用",
            total_amount=Decimal("999.00"),
            status="paid",
            created_at=datetime(2026, 9, 1, 3, 0, tzinfo=UTC),
        ),
    ])
    db.flush()
    install_production_adapters()

    result = _adapter("expense_summary")(
        db,
        _principal(user_id="employee", role="employee", department_ids=("dept-a",)),
        _payload("expense_summary", month="2026-09"),
    )

    assert result == {
        "month": "2026-09",
        "period_start": "2026-09-01",
        "period_end": "2026-09-30",
        "count": 1,
        "amount": "86.00",
        "status_counts": {
            "draft": 1,
            "pending_approval": 0,
            "rejected": 0,
            "payment_pending": 0,
            "paid": 0,
            "cancelled": 0,
        },
        "route_key": "expenses",
    }


@pytest.mark.parametrize("month", ["2026-00", "2026-13", "0000-01", "9999-12"])
def test_expense_summary_rejects_invalid_calendar_months(db, month):
    from app.assistant.adapters import install_production_adapters

    install_production_adapters()

    with pytest.raises(HTTPException) as exc_info:
        _adapter("expense_summary")(
            db,
            _principal(user_id="employee", role="employee", department_ids=("dept-a",)),
            _payload("expense_summary", month=month),
        )

    assert exc_info.value.status_code == 422


def test_expense_summary_uses_shanghai_month_utc_boundaries(db):
    from app.assistant.adapters import install_production_adapters

    db.add(Department(id="dept-a", name="研发", code="RND"))
    db.add(User(id="employee", username="employee", password_encrypted="secret", role="employee", department_id="dept-a"))
    db.add_all([
        ExpenseClaim(
            id="before-month",
            claim_no="EXP-BEFORE",
            requester_id="employee",
            department_id="dept-a",
            title="月初前一瞬",
            total_amount=Decimal("1.00"),
            status="draft",
            created_at=datetime(2026, 8, 31, 15, 59, 59, 999999, tzinfo=UTC),
        ),
        ExpenseClaim(
            id="at-month-start",
            claim_no="EXP-START",
            requester_id="employee",
            department_id="dept-a",
            title="上海九月月初",
            total_amount=Decimal("10.00"),
            status="draft",
            created_at=datetime(2026, 8, 31, 16, 0, tzinfo=UTC),
        ),
        ExpenseClaim(
            id="before-next-month",
            claim_no="EXP-END",
            requester_id="employee",
            department_id="dept-a",
            title="上海九月末瞬间",
            total_amount=Decimal("20.00"),
            status="paid",
            created_at=datetime(2026, 9, 30, 15, 59, 59, 999999, tzinfo=UTC),
        ),
        ExpenseClaim(
            id="at-next-month",
            claim_no="EXP-AFTER",
            requester_id="employee",
            department_id="dept-a",
            title="上海十月月初",
            total_amount=Decimal("100.00"),
            status="paid",
            created_at=datetime(2026, 9, 30, 16, 0, tzinfo=UTC),
        ),
    ])
    db.flush()
    install_production_adapters()

    result = _adapter("expense_summary")(
        db,
        _principal(user_id="employee", role="employee", department_ids=("dept-a",)),
        _payload("expense_summary", month="2026-09"),
    )

    assert result["count"] == 2
    assert result["amount"] == "30.00"
    assert result["status_counts"] == {
        "draft": 1,
        "pending_approval": 0,
        "rejected": 0,
        "payment_pending": 0,
        "paid": 1,
        "cancelled": 0,
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


def test_non_root_default_department_project_and_contract_lists_stay_in_membership_scope(db):
    """Omitting default-scope filters would expose another department without an explicit department_id."""
    from app.assistant.adapters import install_production_adapters

    db.add_all([
        Department(id="dept-a", name="研发", code="RND"),
        Department(id="dept-b", name="财务", code="FIN"),
        Project(id="project-a", code="P-A", name="研发项目", department_id="dept-a"),
        Project(id="project-b", code="P-B", name="财务项目", department_id="dept-b"),
        Contract(id="contract-a", code="C-A", name="研发合同", project_id="project-a"),
        Contract(id="contract-b", code="C-B", name="财务合同", project_id="project-b"),
    ])
    db.flush()
    install_production_adapters()
    manager = _principal(user_id="manager", role="manager", department_ids=("dept-a",))

    departments = _adapter("list_departments")(db, manager, _payload("list_departments"))
    projects = _adapter("list_projects")(db, manager, _payload("list_projects"))
    contracts = _adapter("list_contracts")(db, manager, _payload("list_contracts"))

    assert [item["id"] for item in departments["items"]] == ["dept-a"]
    assert [item["id"] for item in projects["items"]] == ["project-a"]
    assert [item["id"] for item in contracts["items"]] == ["contract-a"]


def test_root_default_project_and_contract_lists_include_unassigned_and_standalone_objects(db):
    """Applying department IN filtering to root defaults would silently hide legitimate unassigned objects."""
    from app.assistant.adapters import install_production_adapters

    db.add_all([
        Department(id="dept-a", name="研发", code="RND"),
        Project(id="project-assigned", code="P-A", name="已归属项目", department_id="dept-a"),
        Project(id="project-unassigned", code="P-U", name="未归属项目", department_id=None),
        Contract(id="contract-assigned", code="C-A", name="已归属合同", project_id="project-assigned"),
        Contract(id="contract-unassigned-project", code="C-U", name="未归属项目合同", project_id="project-unassigned"),
        Contract(id="contract-standalone", code="C-S", name="独立合同", project_id=None),
    ])
    db.flush()
    install_production_adapters()
    root = _principal(user_id="root", role="admin")

    projects = _adapter("list_projects")(db, root, _payload("list_projects"))
    contracts = _adapter("list_contracts")(db, root, _payload("list_contracts"))

    assert {item["id"] for item in projects["items"]} == {
        "project-assigned",
        "project-unassigned",
    }
    assert {item["id"] for item in contracts["items"]} == {
        "contract-assigned",
        "contract-unassigned-project",
        "contract-standalone",
    }


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
