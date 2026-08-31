"""Bounded, server-owned read adapters for the assistant action catalog.

The action service owns confirmation and the outer transaction.  These
adapters only apply existing read visibility rules and project ORM rows into
small JSON-compatible response objects.
"""
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from app.access import resolve_department_scope
from app.assistant.service import register_action_adapter
from app.deps import Principal
from app.expense.service import ExpenseService
from app.kb import retriever
from app.kb.retriever import RetrievedChunk
from app.models import ApprovalInstance, ApprovalTask, Contract, Department, Document, ExpenseClaim, Project, Ticket, User
from app.routers.approvals import _can_view as approval_can_view
from app.routers.tickets import _can_view as ticket_can_view


_MAX_ITEMS = 50
_MAX_KNOWLEDGE_CHUNKS = 8
_MAX_EXCERPT_LENGTH = 500


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


def _user_name(session: Any, user_id: str | None) -> str:
    user = session.get(User, user_id) if user_id else None
    return user.username if user else ""


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
    query = session.query(Department)
    requested_department_id = payload.get("department_id")
    if requested_department_id:
        _authorized_departments(session, principal, requested_department_id)
        query = query.filter(Department.id == requested_department_id)
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
    query = session.query(Project)
    requested_department_id = payload.get("department_id")
    if requested_department_id:
        _authorized_departments(session, principal, requested_department_id)
        query = query.filter(Project.department_id == requested_department_id)
    text = _query(payload)
    if text:
        like = f"%{text}%"
        query = query.filter(Project.name.ilike(like) | Project.code.ilike(like))
    rows = query.order_by(Project.created_at.desc(), Project.id.desc()).limit(_MAX_ITEMS).all()
    departments = {row.id: row.name for row in session.query(Department).filter(Department.id.in_([item.department_id for item in rows if item.department_id])).all()}
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
            "manager_name": _user_name(session, row.manager_id),
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
    query = session.query(Contract)
    requested_department_id = payload.get("department_id")
    if requested_department_id:
        _authorized_departments(session, principal, requested_department_id)
        query = query.join(Project, Contract.project_id == Project.id).filter(Project.department_id == requested_department_id)
    text = _query(payload)
    if text:
        like = f"%{text}%"
        query = query.filter(
            Contract.name.ilike(like) | Contract.code.ilike(like) | Contract.party_a.ilike(like) | Contract.party_b.ilike(like)
        )
    rows = query.order_by(Contract.created_at.desc(), Contract.id.desc()).limit(_MAX_ITEMS).all()
    projects = {row.id: row.name for row in session.query(Project).filter(Project.id.in_([item.project_id for item in rows if item.project_id])).all()}
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
            "owner_name": _user_name(session, row.owner_id),
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
    rows = query.order_by(ExpenseClaim.created_at.desc(), ExpenseClaim.id.desc()).all()
    departments = {row.id: row.name for row in session.query(Department).filter(Department.id.in_([item.department_id for item in rows if item.department_id])).all()}
    return _result([
        {
            "id": row.id,
            "claim_no": row.claim_no,
            "requester_id": row.requester_id,
            "requester_name": _user_name(session, row.requester_id),
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
        if ExpenseService.can_view(session, row, principal.user_id)
    ])


def _approval_department_id(session: Any, instance: ApprovalInstance) -> str | None:
    task = (
        session.query(ApprovalTask)
        .filter(ApprovalTask.instance_id == instance.id)
        .order_by(ApprovalTask.sequence, ApprovalTask.id)
        .first()
    )
    if task and task.department_id:
        return task.department_id
    requester = session.get(User, instance.requester_id)
    return requester.department_id if requester else None


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
    rows = query.order_by(ApprovalInstance.submitted_at.desc(), ApprovalInstance.id.desc()).all()
    items: list[dict[str, Any]] = []
    for row in rows:
        department_id = _approval_department_id(session, row)
        if requested_department_id and department_id != requested_department_id:
            continue
        if not approval_can_view(session, row, principal):
            continue
        tasks = (
            session.query(ApprovalTask)
            .filter(ApprovalTask.instance_id == row.id)
            .order_by(ApprovalTask.sequence, ApprovalTask.id)
            .limit(10)
            .all()
        )
        items.append({
            "id": row.id,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "requester_id": row.requester_id,
            "requester_name": _user_name(session, row.requester_id),
            "department_id": department_id,
            "status": row.status,
            "current_node_sequence": row.current_node_sequence,
            "version": row.version,
            "submitted_at": _json_value(row.submitted_at),
            "completed_at": _json_value(row.completed_at),
            "updated_at": _json_value(row.updated_at),
            "tasks": [
                {
                    "id": task.id,
                    "sequence": task.sequence,
                    "status": task.status,
                    "assignee_id": task.assignee_id,
                    "assignee_role": task.assignee_role,
                    "department_id": task.department_id,
                    "acted_at": _json_value(task.acted_at),
                }
                for task in tasks
            ],
        })
        if len(items) == _MAX_ITEMS:
            break
    return _result(items)


def _list_tickets(session: Any, principal: Principal, payload: dict[str, Any]) -> dict[str, Any]:
    _require(principal, "admin", "hr", "manager")
    query = session.query(Ticket)
    requested_department_id = payload.get("department_id")
    if requested_department_id:
        _authorized_departments(session, principal, requested_department_id)
        query = query.filter(Ticket.department_id == requested_department_id)
    text = _query(payload)
    if text:
        like = f"%{text}%"
        query = query.filter(Ticket.subject.ilike(like) | Ticket.description.ilike(like))
    rows = query.order_by(Ticket.created_at.desc(), Ticket.id.desc()).all()
    departments = {row.id: row.name for row in session.query(Department).filter(Department.id.in_([item.department_id for item in rows if item.department_id])).all()}
    items: list[dict[str, Any]] = []
    for row in rows:
        if not ticket_can_view(session, principal, row):
            continue
        items.append({
            "id": row.id,
            "requester_id": row.requester_id,
            "requester_name": _user_name(session, row.requester_id),
            "target_user_id": row.target_user_id,
            "target_user_name": _user_name(session, row.target_user_id),
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
        })
        if len(items) == _MAX_ITEMS:
            break
    return _result(items)


def install_production_adapters() -> None:
    """Install exactly the approved read adapters; repeated calls are harmless."""
    register_action_adapter("search_knowledge", _search_knowledge)
    register_action_adapter("list_departments", _list_departments)
    register_action_adapter("list_projects", _list_projects)
    register_action_adapter("list_contracts", _list_contracts)
    register_action_adapter("list_expenses", _list_expenses)
    register_action_adapter("list_approvals", _list_approvals)
    register_action_adapter("list_tickets", _list_tickets)
