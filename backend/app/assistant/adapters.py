"""Bounded, server-owned read adapters for the assistant action catalog.

The action service owns confirmation and the outer transaction.  These
adapters only apply existing read visibility rules and project ORM rows into
small JSON-compatible response objects.
"""
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import exists, func, or_, select

from app.access import can_manage_employee, resolve_department_scope
from app.assistant.service import register_action_adapter
from app.collaboration.service import CollaborationService
from app.deps import Principal
from app.kb import retriever
from app.kb.service import _index_document
from app.kb import service as kb_service
from app.organization.service import OrganizationService
from app.expense.service import ExpenseService
from app.governance.service import GovernanceService
from app.schedule.service import (
    create_holiday_in_transaction,
    create_leave_request_in_transaction,
    delete_attendance_in_transaction,
    delete_holiday_in_transaction,
    replace_schedule_in_transaction,
    review_leave_request_in_transaction,
    upsert_attendance_in_transaction,
)
from app.workflow.service import WorkflowService
from app.payroll.service import PayrollService
from app.kb.retriever import RetrievedChunk
from app.models import (
    ApprovalInstance,
    ApprovalTask,
    AttendanceRecord,
    Contract,
    Department,
    DepartmentMemory,
    Document,
    EmployeeProfile,
    ExpenseClaim,
    HolidayPeriod,
    LeaveRequest,
    Project,
    Ticket,
    Todo,
    SensitiveEvent,
    SensitiveKeyword,
    User,
    UserDepartment,
    UserRole,
)
from app.project_contract import service as project_contract_service
from app.schemas import (
    ContractCreate,
    ContractUpdate,
    AdminEmployeeCreate,
    AdminEmployeeUpdate,
    AttendanceUpdate,
    DocumentCreate,
    DocumentUpdate,
    EmploymentEventCreate,
    HolidayCreate,
    LeaveRequestCreate,
    LeaveRequestReview,
    OrgUnitCreate,
    OrgUnitUpdate,
    PasswordResetIn,
    ProjectCreate,
    ProjectUpdate,
    MemoryCreate,
    MemoryUpdate,
    SensitiveKeywordCreate,
    SensitiveKeywordUpdate,
    TicketCreate,
    TicketDispatch,
    TodoCreate,
    TodoUpdate,
    WorkScheduleUpdate,
)


_MAX_ITEMS = 50
_MAX_KNOWLEDGE_CHUNKS = 8
_MAX_EXCERPT_LENGTH = 500
_EXPENSE_STATUSES = ("draft", "pending_approval", "rejected", "payment_pending", "paid", "cancelled")
_ATTENDANCE_STATUSES = ("present", "late", "absent", "remote")
_BUSINESS_TIMEZONE = ZoneInfo("Asia/Shanghai")


def _json_value(value: Any) -> str | int | float | bool | None:
    if isinstance(value, datetime):
        return (value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"assistant adapter cannot return {type(value)!r}")


def _excerpt(value: str) -> str:
    return value[:_MAX_EXCERPT_LENGTH]


def _result(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"items": items[:_MAX_ITEMS], "count": min(len(items), _MAX_ITEMS)}


def _require(principal: Principal, *roles: str) -> None:
    if not principal.has_role(*roles):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "principal is not authorized for this action")


def _authorized_departments(session: Any, principal: Principal, requested_department_id: str | None) -> tuple[str, ...]:
    requested = (requested_department_id,) if requested_department_id else None
    try:
        return resolve_department_scope(
            principal.department_ids,
            requested,
            is_root=principal.role == "admin",
            db=session,
        )
    except (PermissionError, ValueError) as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "requested department is not accessible") from exc


def _query(payload: dict[str, Any]) -> str:
    return str(payload.get("query") or "").strip()


def _user_details(session: Any, user_ids: set[str | None]) -> dict[str, tuple[str, str | None]]:
    ids = {user_id for user_id in user_ids if user_id}
    if not ids:
        return {}
    return {
        row.id: (row.username, row.department_id)
        for row in session.query(User).filter(User.id.in_(ids)).all()
    }


def _department_names(session: Any, department_ids: set[str | None]) -> dict[str, str]:
    ids = {department_id for department_id in department_ids if department_id}
    if not ids:
        return {}
    return {
        row.id: row.name
        for row in session.query(Department).filter(Department.id.in_(ids)).all()
    }


def _search_knowledge(session: Any, principal: Principal, payload: dict[str, Any]) -> dict[str, Any]:
    _require(principal, "admin", "hr", "manager")
    query = _query(payload)
    if not query:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "knowledge search query is required")
    department_ids = _authorized_departments(session, principal, payload.get("department_id"))
    chunks = retriever.search_departments(
        session,
        department_ids=department_ids,
        query=query,
        top_k=_MAX_KNOWLEDGE_CHUNKS,
    )
    document_titles = {
        document.id: document.title
        for document in session.query(Document).filter(Document.id.in_([chunk.document_id for chunk in chunks])).all()
    }
    items = [
        {
            "document_id": chunk.document_id,
            "document_title": document_titles.get(chunk.document_id, ""),
            "chunk_id": chunk.chunk_id,
            "excerpt": _excerpt(chunk.text),
            "score": float(chunk.combined_score),
        }
        for chunk in chunks[:_MAX_KNOWLEDGE_CHUNKS]
    ]
    return _result(items)


def _list_departments(session: Any, principal: Principal, payload: dict[str, Any]) -> dict[str, Any]:
    _require(principal, "admin", "hr", "manager")
    requested_department_id = payload.get("department_id")
    authorized_department_ids = _authorized_departments(session, principal, requested_department_id)
    query = session.query(Department).filter(Department.id.in_(authorized_department_ids))
    text = _query(payload)
    if text:
        like = f"%{text}%"
        query = query.filter(Department.name.ilike(like) | Department.code.ilike(like))
    rows = query.order_by(Department.name, Department.id).limit(_MAX_ITEMS).all()
    return _result([
        {
            "id": row.id,
            "name": row.name,
            "code": row.code,
            "parent_id": row.parent_id,
            "manager_id": row.manager_id,
            "active": row.active,
            "created_at": _json_value(row.created_at),
            "updated_at": _json_value(row.updated_at),
        }
        for row in rows
    ])


def _list_projects(session: Any, principal: Principal, payload: dict[str, Any]) -> dict[str, Any]:
    _require(principal, "admin", "hr", "manager")
    requested_department_id = payload.get("department_id")
    authorized_department_ids = _authorized_departments(session, principal, requested_department_id)
    query = session.query(Project)
    if principal.role != "admin" or requested_department_id is not None:
        query = query.filter(Project.department_id.in_(authorized_department_ids))
    text = _query(payload)
    if text:
        like = f"%{text}%"
        query = query.filter(Project.name.ilike(like) | Project.code.ilike(like))
    rows = query.order_by(Project.created_at.desc(), Project.id.desc()).limit(_MAX_ITEMS).all()
    departments = _department_names(session, {row.department_id for row in rows})
    users = _user_details(session, {row.manager_id for row in rows})
    return _result([
        {
            "id": row.id,
            "code": row.code,
            "name": row.name,
            "type": row.type,
            "status": row.status,
            "department_id": row.department_id,
            "department_name": departments.get(row.department_id, ""),
            "manager_id": row.manager_id,
            "manager_name": users.get(row.manager_id, ("", None))[0],
            "start_date": _json_value(row.start_date),
            "end_date": _json_value(row.end_date),
            "budget": _json_value(row.budget),
            "created_at": _json_value(row.created_at),
            "updated_at": _json_value(row.updated_at),
        }
        for row in rows
    ])


def _list_contracts(session: Any, principal: Principal, payload: dict[str, Any]) -> dict[str, Any]:
    _require(principal, "admin", "hr", "manager")
    requested_department_id = payload.get("department_id")
    authorized_department_ids = _authorized_departments(session, principal, requested_department_id)
    query = session.query(Contract)
    if principal.role != "admin" or requested_department_id is not None:
        query = query.join(Project, Contract.project_id == Project.id).filter(
            Project.department_id.in_(authorized_department_ids)
        )
    text = _query(payload)
    if text:
        like = f"%{text}%"
        query = query.filter(
            Contract.name.ilike(like) | Contract.code.ilike(like) | Contract.party_a.ilike(like) | Contract.party_b.ilike(like)
        )
    rows = query.order_by(Contract.created_at.desc(), Contract.id.desc()).limit(_MAX_ITEMS).all()
    projects = {
        row.id: row.name
        for row in session.query(Project).filter(Project.id.in_({item.project_id for item in rows if item.project_id})).all()
    }
    users = _user_details(session, {row.owner_id for row in rows})
    return _result([
        {
            "id": row.id,
            "code": row.code,
            "name": row.name,
            "type": row.type,
            "status": row.status,
            "project_id": row.project_id,
            "project_name": projects.get(row.project_id, ""),
            "party_a": row.party_a,
            "party_b": row.party_b,
            "amount": _json_value(row.amount),
            "currency": row.currency,
            "sign_date": _json_value(row.sign_date),
            "effective_date": _json_value(row.effective_date),
            "expiry_date": _json_value(row.expiry_date),
            "owner_id": row.owner_id,
            "owner_name": users.get(row.owner_id, ("", None))[0],
            "created_at": _json_value(row.created_at),
            "updated_at": _json_value(row.updated_at),
        }
        for row in rows
    ])


def _list_expenses(session: Any, principal: Principal, payload: dict[str, Any]) -> dict[str, Any]:
    _require(principal, "admin", "hr", "finance", "manager")
    query = session.query(ExpenseClaim)
    requested_department_id = payload.get("department_id")
    if requested_department_id:
        _authorized_departments(session, principal, requested_department_id)
        query = query.filter(ExpenseClaim.department_id == requested_department_id)
    text = _query(payload)
    if text:
        like = f"%{text}%"
        query = query.filter(
            ExpenseClaim.claim_no.ilike(like) | ExpenseClaim.title.ilike(like) | ExpenseClaim.purpose.ilike(like)
        )
    query = query.filter(ExpenseService.visibility_predicate(session, principal.user_id))
    rows = query.order_by(ExpenseClaim.created_at.desc(), ExpenseClaim.id.desc()).limit(_MAX_ITEMS).all()
    departments = _department_names(session, {row.department_id for row in rows})
    users = _user_details(session, {row.requester_id for row in rows})
    return _result([
        {
            "id": row.id,
            "claim_no": row.claim_no,
            "requester_id": row.requester_id,
            "requester_name": users.get(row.requester_id, ("", None))[0],
            "department_id": row.department_id,
            "department_name": departments.get(row.department_id, ""),
            "title": row.title,
            "project_code": row.project_code,
            "currency": row.currency,
            "total_amount": _json_value(row.total_amount),
            "status": row.status,
            "approval_instance_id": row.approval_instance_id,
            "submitted_at": _json_value(row.submitted_at),
            "created_at": _json_value(row.created_at),
            "updated_at": _json_value(row.updated_at),
        }
        for row in rows
    ])


def _approval_department_expression() -> Any:
    first_task_department = (
        select(ApprovalTask.department_id)
        .where(ApprovalTask.instance_id == ApprovalInstance.id)
        .order_by(ApprovalTask.sequence, ApprovalTask.id)
        .limit(1)
        .scalar_subquery()
    )
    requester_department = (
        select(User.department_id)
        .where(User.id == ApprovalInstance.requester_id)
        .scalar_subquery()
    )
    return func.coalesce(first_task_department, requester_department)


def _approval_requester_name_expression() -> Any:
    return (
        select(User.username)
        .where(User.id == ApprovalInstance.requester_id)
        .scalar_subquery()
    )


def _approval_visibility_expression(principal: Principal) -> Any | None:
    if principal.has_role("admin", "hr"):
        return None
    effective_roles = tuple(sorted(set(principal.roles) | {principal.role}))
    department_ids = tuple(principal.department_ids) or ("",)
    role_assignment = (
        ApprovalTask.assignee_role.in_(effective_roles)
        & or_(
            ApprovalTask.department_id.is_(None),
            ApprovalTask.department_id.in_(department_ids),
            exists().where(
                UserRole.user_id == principal.user_id,
                UserRole.role == ApprovalTask.assignee_role,
                or_(
                    UserRole.department_id.is_(None),
                    UserRole.department_id == ApprovalTask.department_id,
                ),
            ),
        )
    )
    pending_inbox = exists().where(
        ApprovalTask.instance_id == ApprovalInstance.id,
        ApprovalTask.status == "pending",
        ApprovalInstance.status == "pending_approval",
        or_(ApprovalTask.assignee_id == principal.user_id, role_assignment),
    )
    assigned_task = exists().where(
        ApprovalTask.instance_id == ApprovalInstance.id,
        ApprovalTask.assignee_id == principal.user_id,
    )
    return or_(
        ApprovalInstance.requester_id == principal.user_id,
        pending_inbox,
        assigned_task,
    )


def _list_approvals(session: Any, principal: Principal, payload: dict[str, Any]) -> dict[str, Any]:
    _require(principal, "admin", "hr", "finance", "manager")
    requested_department_id = payload.get("department_id")
    if requested_department_id:
        _authorized_departments(session, principal, requested_department_id)
    text = _query(payload)
    query = session.query(ApprovalInstance)
    if text:
        like = f"%{text}%"
        query = query.filter(
            ApprovalInstance.id.ilike(like)
            | ApprovalInstance.entity_type.ilike(like)
            | ApprovalInstance.entity_id.ilike(like)
        )
    department_expression = _approval_department_expression()
    requester_name_expression = _approval_requester_name_expression()
    if requested_department_id:
        query = query.filter(department_expression == requested_department_id)
    visibility = _approval_visibility_expression(principal)
    if visibility is not None:
        query = query.filter(visibility)
    rows = (
        query.add_columns(
            department_expression.label("department_id"),
            requester_name_expression.label("requester_name"),
        )
        .order_by(ApprovalInstance.submitted_at.desc(), ApprovalInstance.id.desc())
        .limit(_MAX_ITEMS)
        .all()
    )
    items: list[dict[str, Any]] = []
    for row, department_id, requester_name in rows:
        items.append({
            "id": row.id,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "requester_id": row.requester_id,
            "requester_name": requester_name or "",
            "department_id": department_id,
            "status": row.status,
            "current_node_sequence": row.current_node_sequence,
            "version": row.version,
            "submitted_at": _json_value(row.submitted_at),
            "completed_at": _json_value(row.completed_at),
            "updated_at": _json_value(row.updated_at),
        })
    return _result(items)


def _list_tickets(session: Any, principal: Principal, payload: dict[str, Any]) -> dict[str, Any]:
    _require(principal, "admin", "employee", "hr", "manager")
    query = session.query(Ticket)
    requested_department_id = payload.get("department_id")
    if requested_department_id:
        _authorized_departments(session, principal, requested_department_id)
        query = query.filter(Ticket.department_id == requested_department_id)
    text = _query(payload)
    if text:
        like = f"%{text}%"
        query = query.filter(Ticket.subject.ilike(like) | Ticket.description.ilike(like))
    if principal.role != "admin":
        query = query.filter(
            or_(
                Ticket.requester_id == principal.user_id,
                Ticket.target_user_id == principal.user_id,
                Ticket.target_user_id.is_(None) & Ticket.department_id.in_(principal.department_ids or ("",)),
            )
        )
    rows = query.order_by(Ticket.created_at.desc(), Ticket.id.desc()).limit(_MAX_ITEMS).all()
    departments = _department_names(session, {row.department_id for row in rows})
    users = _user_details(session, {row.requester_id for row in rows} | {row.target_user_id for row in rows})
    items = [
        {
            "id": row.id,
            "requester_id": row.requester_id,
            "requester_name": users.get(row.requester_id, ("", None))[0],
            "target_user_id": row.target_user_id,
            "target_user_name": users.get(row.target_user_id, ("", None))[0],
            "department_id": row.department_id,
            "department_name": departments.get(row.department_id, ""),
            "requested_department_id": row.requested_department_id,
            "ticket_type": row.ticket_type,
            "subject": row.subject,
            "description": _excerpt(row.description),
            "status": row.status,
            "requires_admin": row.requires_admin,
            "created_at": _json_value(row.created_at),
            "updated_at": _json_value(row.updated_at),
            "closed_at": _json_value(row.closed_at),
        }
        for row in rows
    ]
    return _result(items)


def _month_day_bounds(month: str) -> tuple[date, date]:
    try:
        year, month_number = (int(part) for part in month.split("-", 1))
        start = date(year, month_number, 1)
        end_year, end_month = (year + 1, 1) if month_number == 12 else (year, month_number + 1)
        return start, date(end_year, end_month, 1) - timedelta(days=1)
    except (OverflowError, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "attendance month is invalid") from exc


def _attendance_scope(session: Any, principal: Principal, payload: dict[str, Any]) -> tuple[str, ...]:
    """Reuse the existing role scope: admin/hr/manager aggregate, others see themselves."""
    profile_query = session.query(EmployeeProfile.user_id).filter(
        EmployeeProfile.status.in_(("probation", "active"))
    )
    if principal.has_role("admin", "hr", "manager"):
        department_ids = _authorized_departments(session, principal, payload.get("department_id"))
        profile_query = profile_query.filter(
            EmployeeProfile.user_id.in_(
                select(UserDepartment.user_id).where(UserDepartment.department_id.in_(department_ids))
            )
        )
    else:
        requested_department_id = payload.get("department_id")
        if requested_department_id and requested_department_id not in principal.department_ids:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "requested department is not accessible")
        profile_query = profile_query.filter(EmployeeProfile.user_id == principal.user_id)
    return tuple(row[0] for row in profile_query.distinct().all())


def _attendance_status_counts(
    session: Any, user_ids: tuple[str, ...], start: date, end: date
) -> dict[str, int]:
    status_counts = {item: 0 for item in _ATTENDANCE_STATUSES}
    if not user_ids:
        return status_counts
    rows = (
        session.query(AttendanceRecord.status, func.count(AttendanceRecord.id))
        .filter(
            AttendanceRecord.user_id.in_(user_ids),
            AttendanceRecord.attendance_date >= start,
            AttendanceRecord.attendance_date <= end,
        )
        .group_by(AttendanceRecord.status)
        .all()
    )
    for attendance_status, count in rows:
        if attendance_status in status_counts:
            status_counts[attendance_status] = count
    return status_counts


def _payload_date(payload: dict[str, Any], key: str, message: str) -> date | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, message) from exc
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, message)


def _attendance_coverage(
    session: Any, user_ids: tuple[str, ...], start: date, end: date
) -> tuple[int, int]:
    if not user_ids:
        return 0, 0
    days, employees = (
        session.query(
            func.count(func.distinct(AttendanceRecord.attendance_date)),
            func.count(func.distinct(AttendanceRecord.user_id)),
        )
        .filter(
            AttendanceRecord.user_id.in_(user_ids),
            AttendanceRecord.attendance_date >= start,
            AttendanceRecord.attendance_date <= end,
        )
        .one()
    )
    return days or 0, employees or 0


def _attendance_span_result(
    session: Any,
    user_ids: tuple[str, ...],
    start: date,
    end: date,
    *,
    month: str | None,
) -> dict[str, Any]:
    status_counts = _attendance_status_counts(session, user_ids, start, end)
    days_recorded, employees_recorded = _attendance_coverage(session, user_ids, start, end)
    result: dict[str, Any] = {
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "active_employees": len(user_ids),
        "records": sum(status_counts.values()),
        "days_recorded": days_recorded,
        "employees_recorded": employees_recorded,
        "status_counts": status_counts,
    }
    if month is not None:
        result["month"] = month
    return result


def _attendance_summary(session: Any, principal: Principal, payload: dict[str, Any]) -> dict[str, Any]:
    _require(principal, "admin", "employee", "hr", "manager", "finance")
    active_user_ids = _attendance_scope(session, principal, payload)

    month = payload.get("month")
    if month:
        start, end = _month_day_bounds(str(month))
        return _attendance_span_result(session, active_user_ids, start, end, month=str(month))

    range_start = _payload_date(payload, "start_date", "attendance range is invalid")
    range_end = _payload_date(payload, "end_date", "attendance range is invalid")
    if range_start is not None and range_end is not None:
        if range_start > range_end:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "attendance range is invalid")
        return _attendance_span_result(session, active_user_ids, range_start, range_end, month=None)

    target_date = (
        _payload_date(payload, "attendance_date", "attendance date is invalid")
        or datetime.now(_BUSINESS_TIMEZONE).date()
    )
    status_counts = _attendance_status_counts(session, active_user_ids, target_date, target_date)
    recorded = sum(status_counts.values())
    return {
        "date": target_date.isoformat(),
        "active_employees": len(active_user_ids),
        "recorded": recorded,
        "missing": max(len(active_user_ids) - recorded, 0),
        "status_counts": status_counts,
    }


def _expense_month_bounds(month: str | None) -> tuple[str, datetime, datetime]:
    current = datetime.now(_BUSINESS_TIMEZONE)
    resolved_month = month or current.strftime("%Y-%m")
    try:
        year, month_number = (int(part) for part in resolved_month.split("-", 1))
        start_local = datetime(year, month_number, 1, tzinfo=_BUSINESS_TIMEZONE)
        if month_number == 12:
            end_local = datetime(year + 1, 1, 1, tzinfo=_BUSINESS_TIMEZONE)
        else:
            end_local = datetime(year, month_number + 1, 1, tzinfo=_BUSINESS_TIMEZONE)
    except (OverflowError, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "expense month is invalid") from exc
    return resolved_month, start_local.astimezone(UTC), end_local.astimezone(UTC)


def _local_day_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    """Half-open UTC bounds for an inclusive local-day range."""
    start_local = datetime(start.year, start.month, start.day, tzinfo=_BUSINESS_TIMEZONE)
    end_local = datetime(end.year, end.month, end.day, tzinfo=_BUSINESS_TIMEZONE) + timedelta(days=1)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def _expense_summary(session: Any, principal: Principal, payload: dict[str, Any]) -> dict[str, Any]:
    _require(principal, "admin", "employee", "hr", "manager", "finance")
    range_start = _payload_date(payload, "start_date", "expense range is invalid")
    range_end = _payload_date(payload, "end_date", "expense range is invalid")
    if range_start is not None and range_end is not None:
        if range_start > range_end:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "expense range is invalid")
        month = None
        start_at, end_at = _local_day_bounds(range_start, range_end)
        period = {"period_start": range_start.isoformat(), "period_end": range_end.isoformat()}
    else:
        month, start_at, end_at = _expense_month_bounds(payload.get("month"))
        month_start, month_end = _month_day_bounds(month)
        period = {"period_start": month_start.isoformat(), "period_end": month_end.isoformat()}
    query = session.query(ExpenseClaim).filter(
        ExpenseClaim.created_at >= start_at,
        ExpenseClaim.created_at < end_at,
        ExpenseService.visibility_predicate(session, principal.user_id),
    )
    requested_department_id = payload.get("department_id")
    if requested_department_id:
        _authorized_departments(session, principal, requested_department_id)
        query = query.filter(ExpenseClaim.department_id == requested_department_id)
    rows = query.with_entities(
        ExpenseClaim.status,
        func.count(ExpenseClaim.id),
        func.coalesce(func.sum(ExpenseClaim.total_amount), 0),
    ).group_by(ExpenseClaim.status).all()
    status_counts = {item: 0 for item in _EXPENSE_STATUSES}
    count = 0
    amount = Decimal("0.00")
    for expense_status, bucket_count, bucket_amount in rows:
        if expense_status in status_counts:
            status_counts[expense_status] = bucket_count
        count += bucket_count
        amount += Decimal(str(bucket_amount))
    result = {
        **period,
        "count": count,
        "amount": str(amount.quantize(Decimal("0.01"))),
        "status_counts": status_counts,
        "route_key": "expenses",
    }
    if month is not None:
        result["month"] = month
    return result


def install_production_adapters() -> None:
    """Install exactly the approved read adapters; repeated calls are harmless."""
    register_action_adapter("search_knowledge", _search_knowledge)
    register_action_adapter("list_departments", _list_departments)
    register_action_adapter("list_projects", _list_projects)
    register_action_adapter("list_contracts", _list_contracts)
    register_action_adapter("list_expenses", _list_expenses)
    register_action_adapter("list_approvals", _list_approvals)
    register_action_adapter("list_tickets", _list_tickets)
    register_action_adapter("attendance_summary", _attendance_summary)
    register_action_adapter("expense_summary", _expense_summary)
    register_action_adapter("create_org_unit", _create_org)
    register_action_adapter("update_org_unit", _update_org)
    register_action_adapter("create_employee", _create_employee)
    register_action_adapter("update_employee", _update_employee)
    register_action_adapter("record_employment_event", _record_employment_event)
    register_action_adapter("reset_employee_password", _reset_employee_password)
    register_action_adapter("create_project", _create_project)
    register_action_adapter("update_project", _update_project)
    register_action_adapter("delete_project", _delete_project)
    register_action_adapter("create_contract", _create_contract)
    register_action_adapter("update_contract", _update_contract)
    register_action_adapter("delete_contract", _delete_contract)
    register_action_adapter("create_document", _create_document)
    register_action_adapter("update_document", _update_document)
    register_action_adapter("delete_document", _delete_document)
    register_action_adapter("update_work_schedule", _update_work_schedule)
    register_action_adapter("create_holiday", _create_holiday)
    register_action_adapter("delete_holiday", _delete_holiday)
    register_action_adapter("upsert_attendance", _upsert_attendance)
    register_action_adapter("delete_attendance", _delete_attendance)
    register_action_adapter("review_leave_request", _review_leave_request)
    register_action_adapter("dispatch_ticket", _dispatch_ticket)
    register_action_adapter("create_todo", _create_todo)
    register_action_adapter("update_todo", _update_todo)
    register_action_adapter("create_sensitive_keyword", _create_sensitive_keyword)
    register_action_adapter("update_sensitive_keyword", _update_sensitive_keyword)
    register_action_adapter("delete_sensitive_keyword", _delete_sensitive_keyword)
    register_action_adapter("delete_sensitive_event", _delete_sensitive_event)
    register_action_adapter("create_department_memory", _create_department_memory)
    register_action_adapter("update_department_memory", _update_department_memory)
    register_action_adapter("delete_department_memory", _delete_department_memory)
    for _name,_fn in {"create_expense_draft":_create_expense,"update_expense_draft":_update_expense,"delete_expense_draft":_delete_expense,"submit_expense":_submit_expense,"create_leave_request":_leave,"create_ticket":_ticket,"delete_ticket":_delete_ticket,"approve_approval":lambda s,p,x:_approval(s,p,x,"approve"),"reject_approval":lambda s,p,x:_approval(s,p,x,"reject"),"cancel_approval":lambda s,p,x:_approval(s,p,x,"cancel"),"pay_expense":_pay,"generate_payroll":_payroll,"update_payroll_settings":_update_payroll_settings}.items():
        register_action_adapter(_name,_fn)

def _create_org(s,p,x):
    row = OrganizationService.create_org_unit(s, OrgUnitCreate.model_validate(x))
    return {"id": row.id, "name": row.name, "code": row.code, "parent_id": row.parent_id, "manager_id": row.manager_id, "active": row.active}
def _update_org(s,p,x):
    row=s.get(Department,x["id"])
    if row is None: raise HTTPException(404,"organization unit not found")
    OrganizationService.update_org_unit(s, row, OrgUnitUpdate.model_validate({k: v for k, v in x.items() if k != "id"}))
    return {"id": row.id, "name": row.name, "code": row.code, "parent_id": row.parent_id, "manager_id": row.manager_id, "active": row.active}
def _employee_result(s, user):
    profile = s.get(EmployeeProfile, user.id)
    return {
        "id": user.id,
        "username": user.username,
        "status": profile.status if profile else "active",
        "department_id": user.department_id,
        "position": profile.position if profile else "",
    }
def _create_employee(s,p,x):
    user = OrganizationService.create_employee(s, AdminEmployeeCreate.model_validate(x))
    return _employee_result(s, user)
def _update_employee(s,p,x):
    user = s.get(User, x["id"])
    if user is None: raise HTTPException(404,"employee not found")
    if not can_manage_employee(s, p, user.id, write=True):
        raise HTTPException(403,"employee is outside management scope")
    OrganizationService.update_employee(s, user, AdminEmployeeUpdate.model_validate({k: v for k, v in x.items() if k != "id"}), p.user_id)
    return _employee_result(s, user)
def _record_employment_event(s,p,x):
    user = s.get(User, x["id"])
    if user is None: raise HTTPException(404,"employee not found")
    event = OrganizationService.record_employment_event(s, user, EmploymentEventCreate.model_validate({k: v for k, v in x.items() if k != "id"}), p.user_id)
    return {"id": event.id, "user_id": event.user_id, "event_type": event.event_type, "effective_date": event.effective_date, "status": s.get(EmployeeProfile, user.id).status}
def _reset_employee_password(s,p,x):
    user = s.get(User, x["id"])
    if user is None: raise HTTPException(404,"employee not found")
    if not can_manage_employee(s, p, user.id, write=True):
        raise HTTPException(403,"employee is outside management scope")
    OrganizationService.reset_employee_password(s, user, PasswordResetIn.model_validate({"password": x["password"]}))
    return {"id": user.id, "password_reset": True}
def _create_project(s,p,x):
    row = project_contract_service.create_project(s, ProjectCreate.model_validate(x), created_by=p.user_id)
    return {"id": row.id, "code": row.code, "name": row.name, "status": row.status, "department_id": row.department_id, "manager_id": row.manager_id}
def _update_project(s,p,x):
    row=s.get(Project,x["id"])
    if row is None: raise HTTPException(404,"project not found")
    row = project_contract_service.update_project(s, row, ProjectUpdate.model_validate({k: v for k, v in x.items() if k != "id"}))
    return {"id": row.id, "code": row.code, "name": row.name, "status": row.status, "department_id": row.department_id, "manager_id": row.manager_id}
def _delete_project(s,p,x):
    row=s.get(Project,x["id"])
    if row is None: raise HTTPException(404,"project not found")
    project_contract_service.delete_project(s, row)
    return {"id":x["id"],"deleted":True}
def _create_contract(s,p,x):
    row = project_contract_service.create_contract(s, ContractCreate.model_validate(x), created_by=p.user_id)
    return {"id": row.id, "code": row.code, "name": row.name, "status": row.status, "project_id": row.project_id, "owner_id": row.owner_id}
def _update_contract(s,p,x):
    row=s.get(Contract,x["id"])
    if row is None: raise HTTPException(404,"contract not found")
    row = project_contract_service.update_contract(s, row, ContractUpdate.model_validate({k: v for k, v in x.items() if k != "id"}))
    return {"id": row.id, "code": row.code, "name": row.name, "status": row.status, "project_id": row.project_id, "owner_id": row.owner_id}
def _delete_contract(s,p,x):
    row=s.get(Contract,x["id"])
    if row is None: raise HTTPException(404,"contract not found")
    project_contract_service.delete_contract(s, row)
    return {"id":x["id"],"deleted":True}
def _create_document(s,p,x):
    department_id = str(x["department_id"])
    kb_service.require_department(s, department_id)
    payload = DocumentCreate.model_validate({key: value for key, value in x.items() if key != "department_id"})
    owner = s.get(User, payload.owner_id or p.user_id)
    if owner is None:
        raise HTTPException(400, "owner not found")
    project_id, contract_id = kb_service.resolve_document_links(s, payload.project_id, payload.contract_id)
    row = kb_service.create_document(
        s,
        department_id=department_id,
        title=payload.title,
        category=payload.category,
        sensitive=payload.sensitive,
        content=payload.content,
        uploaded_by=p.user_id,
        owner_id=owner.id,
        owner_name=owner.username,
        project_id=project_id,
        contract_id=contract_id,
    )
    return {"id": row.id, "title": row.title, "department_id": row.department_id, "category": row.category, "sensitive": row.sensitive, "owner_id": row.owner_id, "project_id": row.project_id, "contract_id": row.contract_id}
def _update_document(s,p,x):
    row=s.get(Document,x["id"])
    if row is None: raise HTTPException(404,"document not found")
    payload = DocumentUpdate.model_validate({key: value for key, value in x.items() if key != "id"})
    project_id = payload.project_id if "project_id" in payload.model_fields_set else row.project_id
    contract_id = payload.contract_id if "contract_id" in payload.model_fields_set else row.contract_id
    project_id, contract_id = kb_service.resolve_document_links(s, project_id, contract_id)
    owner_name = None
    if payload.owner_id is not None:
        owner = s.get(User, payload.owner_id)
        if owner is None:
            raise HTTPException(400, "owner not found")
        owner_name = owner.username
    row = kb_service.update_document(
        s,
        row,
        title=payload.title,
        category=payload.category,
        sensitive=payload.sensitive,
        content=payload.content,
        owner_id=payload.owner_id,
        owner_name=owner_name,
        project_id=project_id,
        contract_id=contract_id,
    )
    return {"id": row.id, "title": row.title, "department_id": row.department_id, "category": row.category, "sensitive": row.sensitive, "owner_id": row.owner_id, "project_id": row.project_id, "contract_id": row.contract_id}
def _delete_document(s,p,x):
    row=s.get(Document,x["id"])
    if row is None: raise HTTPException(404,"document not found")
    kb_service.delete_document(s, row)
    return {"id":x["id"],"deleted":True}

def _create_expense(s,p,x):
    row=ExpenseService.create_draft(s,requester_id=p.user_id,title=x["title"],purpose=x.get("purpose", ""),project_code=x.get("project_code", ""),currency=x.get("currency","CNY"),expected_total=x.get("total_amount"),items=x["items"]); return {"id":row.id,"claim_no":row.claim_no,"status":row.status}
def _update_expense(s,p,x):
    row=ExpenseService.update_draft(s,x["id"],p.user_id,title=x.get("title"),purpose=x.get("purpose"),project_code=x.get("project_code"),items=x.get("items"),expected_total=x.get("total_amount")); return {"id":row.id,"status":row.status,"version":row.version}
def _delete_expense(s,p,x): ExpenseService.delete_draft(s,x["id"],p.user_id); return {"id":x["id"],"deleted":True}
def _submit_expense(s,p,x):
    row = ExpenseService.submit(s, x["id"], p.user_id, x["idempotency_key"])
    return {"id": row.id, "claim_no": row.claim_no, "status": row.status, "approval_instance_id": row.approval_instance_id, "version": row.version}


def _schedule_employee(s, employee_id):
    user = s.get(User, employee_id)
    if user is None or user.role != "employee":
        raise HTTPException(404, "employee not found")
    return user


def _update_work_schedule(s, p, x):
    employee = _schedule_employee(s, x["id"])
    payload = WorkScheduleUpdate.model_validate({"days": x["days"]})
    rows = replace_schedule_in_transaction(s, employee.id, payload.days, p.user_id)
    return {
        "id": employee.id,
        "username": employee.username,
        "days": [
            {
                "weekday": row.weekday,
                "enabled": row.enabled,
                "start_time": row.start_time,
                "end_time": row.end_time,
            }
            for row in rows
        ],
    }


def _create_holiday(s, p, x):
    payload = HolidayCreate.model_validate(x)
    row = create_holiday_in_transaction(s, created_by=p.user_id, **payload.model_dump())
    return {
        "id": row.id,
        "name": row.name,
        "scope_type": row.scope_type,
        "department_id": row.department_id,
        "start_date": row.start_date,
        "end_date": row.end_date,
    }


def _delete_holiday(s, p, x):
    del p
    row = s.get(HolidayPeriod, x["id"])
    if row is None:
        raise HTTPException(404, "holiday not found")
    delete_holiday_in_transaction(s, row)
    return {"id": x["id"], "deleted": True}


def _upsert_attendance(s, p, x):
    employee = _schedule_employee(s, x["id"])
    payload = AttendanceUpdate.model_validate({"status": x["status"], "note": x.get("note", "")})
    attendance_date = x["attendance_date"]
    if isinstance(attendance_date, str):
        attendance_date = date.fromisoformat(attendance_date)
    row = upsert_attendance_in_transaction(
        s,
        user_id=employee.id,
        attendance_date=attendance_date,
        status=payload.status,
        note=payload.note,
        recorded_by=p.user_id,
    )
    return {
        "id": row.id,
        "user_id": row.user_id,
        "attendance_date": row.attendance_date,
        "status": row.status,
        "note": row.note,
    }


def _delete_attendance(s, p, x):
    del p
    row = s.get(AttendanceRecord, x["id"])
    if row is None:
        raise HTTPException(404, "attendance record not found")
    delete_attendance_in_transaction(s, row)
    return {"id": x["id"], "deleted": True}


def _review_leave_request(s, p, x):
    payload = LeaveRequestReview.model_validate({"status": x["status"]})
    row = review_leave_request_in_transaction(
        s,
        request_id=x["id"],
        status=payload.status,
        reviewed_by=p.user_id,
    )
    return {"id": row.id, "user_id": row.user_id, "status": row.status, "reviewed_by": row.reviewed_by}


def _leave(s,p,x):
    payload = LeaveRequestCreate.model_validate(x)
    row = create_leave_request_in_transaction(
        s,
        user_id=p.user_id,
        leave_type=payload.leave_type,
        start_date=payload.start_date,
        end_date=payload.end_date,
        reason=payload.reason,
    )
    return {"id": row.id, "status": row.status}
def _ticket(s,p,x):
    row = CollaborationService.create_ticket(s, TicketCreate.model_validate(x), p)
    return {"id": row.id, "status": row.status, "subject": row.subject, "target_user_id": row.target_user_id}


def _dispatch_ticket(s, p, x):
    row = s.get(Ticket, x["id"])
    if row is None:
        raise HTTPException(404, "ticket not found")
    payload = TicketDispatch.model_validate({"assignee_id": x["assignee_id"]})
    row = CollaborationService.dispatch_ticket(s, row, payload, p)
    return {"id": row.id, "status": row.status, "target_user_id": row.target_user_id}


def _create_todo(s, p, x):
    row = CollaborationService.create_todo(s, TodoCreate.model_validate(x), p)
    return {"id": row.id, "assignee_id": row.assignee_id, "ticket_id": row.ticket_id, "status": row.status}


def _update_todo(s, p, x):
    row = s.get(Todo, x["id"])
    if row is None:
        raise HTTPException(404, "todo not found")
    row = CollaborationService.update_todo(s, row, TodoUpdate.model_validate({"status": x["status"]}), p)
    return {"id": row.id, "status": row.status, "ticket_id": row.ticket_id, "completed_at": row.completed_at}


def _create_sensitive_keyword(s, p, x):
    row = GovernanceService.create_sensitive_keyword(s, SensitiveKeywordCreate.model_validate(x), p)
    return {"id": row.id, "keyword": row.keyword, "enabled": row.enabled}


def _update_sensitive_keyword(s, p, x):
    row = s.get(SensitiveKeyword, x["id"])
    if row is None:
        raise HTTPException(404, "keyword not found")
    payload = SensitiveKeywordUpdate.model_validate({key: value for key, value in x.items() if key != "id"})
    row = GovernanceService.update_sensitive_keyword(s, row, payload, p)
    return {"id": row.id, "keyword": row.keyword, "enabled": row.enabled}


def _delete_sensitive_keyword(s, p, x):
    row = s.get(SensitiveKeyword, x["id"])
    if row is None:
        raise HTTPException(404, "keyword not found")
    GovernanceService.delete_sensitive_keyword(s, row, p)
    return {"id": x["id"], "deleted": True}


def _delete_sensitive_event(s, p, x):
    row = s.get(SensitiveEvent, x["id"])
    if row is None:
        raise HTTPException(404, "sensitive event not found")
    GovernanceService.delete_sensitive_event(s, row, p)
    return {"id": x["id"], "deleted": True}


def _create_department_memory(s, p, x):
    payload = MemoryCreate.model_validate({key: value for key, value in x.items() if key != "department_id"})
    row = GovernanceService.create_department_memory(s, x["department_id"], payload, p)
    return {"id": row.id, "department_id": row.department_id, "title": row.title, "enabled": row.enabled}


def _update_department_memory(s, p, x):
    row = s.get(DepartmentMemory, x["id"])
    if row is None:
        raise HTTPException(404, "department memory not found")
    payload = MemoryUpdate.model_validate({key: value for key, value in x.items() if key != "id"})
    row = GovernanceService.update_department_memory(s, row, payload, p)
    return {"id": row.id, "department_id": row.department_id, "title": row.title, "enabled": row.enabled}


def _delete_department_memory(s, p, x):
    row = s.get(DepartmentMemory, x["id"])
    if row is None:
        raise HTTPException(404, "department memory not found")
    GovernanceService.delete_department_memory(s, row, p)
    return {"id": x["id"], "deleted": True}


def _delete_ticket(s,p,x):
    row=s.get(Ticket,x["id"])
    if row is None: raise HTTPException(404,"ticket not found")
    CollaborationService.delete_ticket(s, row, p)
    return {"id": x["id"], "deleted": True}
def _approval(s,p,x,action):
    row=WorkflowService.act(s,x["id"],p.user_id,action,x.get("comment", ""),x["expected_version"]); return {"id":row.id,"status":row.status,"version":row.version}
def _pay(s,p,x):
    row=ExpenseService.pay(s,x["id"],p.user_id,x,x["idempotency_key"],x["expected_version"]); return {"id":row.id,"claim_id":row.claim_id,"amount":str(row.amount)}
def _payroll(s,p,x):
    row=PayrollService.generate_run(s,p.user_id,period=x.get("period")); return {"id":row.id if row else None,"period":row.period if row else None,"status":row.status if row else "not_due"}
def _update_payroll_settings(s,p,x):
    row = PayrollService.update_settings(s, x, p.user_id)
    return {"id": row.id, "auto_enabled": row.auto_enabled, "pay_day": row.pay_day, "generation_lead_days": row.generation_lead_days, "currency": row.currency, "approval_role": row.approval_role}
def _schema(name,x):
    from app import schemas
    return getattr(schemas,name).model_validate(x)
