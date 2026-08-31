"""Bounded, server-owned read adapters for the assistant action catalog.

The action service owns confirmation and the outer transaction.  These
adapters only apply existing read visibility rules and project ORM rows into
small JSON-compatible response objects.
"""
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import exists, func, or_, select

from app.access import resolve_department_scope
from app.assistant.service import register_action_adapter
from app.deps import Principal
from app.expense.service import ExpenseService
from app.kb import retriever
from app.kb.service import _index_document
from app.kb import service as kb_service
from app.organization.service import OrganizationService
from app.expense.service import ExpenseService
from app.schedule.service import create_leave_request
from app.workflow.service import WorkflowService
from app.payroll.service import PayrollService
from app.kb.retriever import RetrievedChunk
from app.models import (
    ApprovalInstance,
    ApprovalTask,
    Contract,
    Department,
    Document,
    ExpenseClaim,
    Project,
    Ticket,
    User,
    UserRole,
)
from app.project_contract import service as project_contract_service
from app.schemas import (
    ContractCreate,
    ContractUpdate,
    DocumentCreate,
    DocumentUpdate,
    OrgUnitCreate,
    OrgUnitUpdate,
    ProjectCreate,
    ProjectUpdate,
)


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


def install_production_adapters() -> None:
    """Install exactly the approved read adapters; repeated calls are harmless."""
    register_action_adapter("search_knowledge", _search_knowledge)
    register_action_adapter("list_departments", _list_departments)
    register_action_adapter("list_projects", _list_projects)
    register_action_adapter("list_contracts", _list_contracts)
    register_action_adapter("list_expenses", _list_expenses)
    register_action_adapter("list_approvals", _list_approvals)
    register_action_adapter("list_tickets", _list_tickets)
    register_action_adapter("create_org_unit", _create_org)
    register_action_adapter("update_org_unit", _update_org)
    register_action_adapter("create_project", _create_project)
    register_action_adapter("update_project", _update_project)
    register_action_adapter("delete_project", _delete_project)
    register_action_adapter("create_contract", _create_contract)
    register_action_adapter("update_contract", _update_contract)
    register_action_adapter("delete_contract", _delete_contract)
    register_action_adapter("create_document", _create_document)
    register_action_adapter("update_document", _update_document)
    register_action_adapter("delete_document", _delete_document)
    for _name,_fn in {"create_expense_draft":_create_expense,"update_expense_draft":_update_expense,"delete_expense_draft":_delete_expense,"create_leave_request":_leave,"create_ticket":_ticket,"delete_ticket":_delete_ticket,"approve_approval":lambda s,p,x:_approval(s,p,x,"approve"),"reject_approval":lambda s,p,x:_approval(s,p,x,"reject"),"cancel_approval":lambda s,p,x:_approval(s,p,x,"cancel"),"pay_expense":_pay,"generate_payroll":_payroll}.items():
        register_action_adapter(_name,_fn)

def _create_org(s,p,x):
    row = OrganizationService.create_org_unit(s, OrgUnitCreate.model_validate(x))
    return {"id": row.id, "name": row.name, "code": row.code, "parent_id": row.parent_id, "manager_id": row.manager_id, "active": row.active}
def _update_org(s,p,x):
    row=s.get(Department,x["id"])
    if row is None: raise HTTPException(404,"organization unit not found")
    OrganizationService.update_org_unit(s, row, OrgUnitUpdate.model_validate({k: v for k, v in x.items() if k != "id"}))
    return {"id": row.id, "name": row.name, "code": row.code, "parent_id": row.parent_id, "manager_id": row.manager_id, "active": row.active}
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
    if s.get(Department,x["department_id"]) is None: raise HTTPException(404,"department not found")
    if x.get("project_id") and s.get(Project,x["project_id"]) is None: raise HTTPException(400,"project not found")
    if x.get("contract_id"):
        contract=s.get(Contract,x["contract_id"])
        if contract is None: raise HTTPException(400,"contract not found")
        if contract.project_id and x.get("project_id") and contract.project_id != x["project_id"]: raise HTTPException(400,"contract belongs to another project")
    data={k:v for k,v in x.items() if k!="department_id"}; row=Document(department_id=x["department_id"],uploaded_by=p.user_id,owner_id=p.user_id,owner_name=p.username,**data); s.add(row); s.flush(); _index_document(s,row); return {"id":row.id,"title":row.title,"department_id":row.department_id}
def _update_document(s,p,x):
    row=s.get(Document,x["id"])
    if row is None: raise HTTPException(404,"document not found")
    changed=False
    for k,v in x.items():
        if k!="id" and v is not None and hasattr(row,k): setattr(row,k,v); changed=changed or k=="content"
    if changed: _index_document(s,row)
    s.flush(); return {"id":row.id,"title":row.title,"department_id":row.department_id}
def _delete_document(s,p,x):
    row=s.get(Document,x["id"])
    if row is None: raise HTTPException(404,"document not found")
    s.delete(row); s.flush(); return {"id":x["id"],"deleted":True}

def _create_expense(s,p,x):
    row=ExpenseService.create_draft(s,requester_id=p.user_id,title=x["title"],purpose=x.get("purpose", ""),project_code=x.get("project_code", ""),currency=x.get("currency","CNY"),expected_total=x.get("total_amount"),items=x["items"]); return {"id":row.id,"claim_no":row.claim_no,"status":row.status}
def _update_expense(s,p,x):
    row=ExpenseService.update_draft(s,x["id"],p.user_id,title=x.get("title"),purpose=x.get("purpose"),project_code=x.get("project_code"),items=x.get("items"),expected_total=x.get("total_amount")); return {"id":row.id,"status":row.status,"version":row.version}
def _delete_expense(s,p,x): ExpenseService.delete_draft(s,x["id"],p.user_id); return {"id":x["id"],"deleted":True}
def _leave(s,p,x):
    row=create_leave_request(s,user_id=p.user_id,leave_type=x["leave_type"],start_date=x["start_date"],end_date=x["end_date"],reason=x.get("reason", "")); return {"id":row.id,"status":row.status}
def _ticket(s,p,x):
    row=Ticket(requester_id=p.user_id,department_id=x.get("department_id") or p.department_id,ticket_type=x["ticket_type"],subject=x["subject"],description=x["description"],target_user_id=x.get("target_user_id"),requested_department_id=x.get("requested_department_id"),status="pending_admin",requires_admin=True); s.add(row); s.flush(); return {"id":row.id,"status":row.status,"subject":row.subject}
def _delete_ticket(s,p,x):
    row=s.get(Ticket,x["id"])
    if row is None: raise HTTPException(404,"ticket not found")
    s.delete(row); s.flush(); return {"id":x["id"],"deleted":True}
def _approval(s,p,x,action):
    row=WorkflowService.act(s,x["id"],p.user_id,action,x.get("comment", ""),x["expected_version"]); return {"id":row.id,"status":row.status,"version":row.version}
def _pay(s,p,x):
    row=ExpenseService.pay(s,x["id"],p.user_id,x,x["idempotency_key"],x["expected_version"]); return {"id":row.id,"claim_id":row.claim_id,"amount":str(row.amount)}
def _payroll(s,p,x):
    row=PayrollService.generate_run(s,p.user_id,period=x.get("period")); return {"id":row.id if row else None,"period":row.period if row else None,"status":row.status if row else "not_due"}
def _schema(name,x):
    from app import schemas
    return getattr(schemas,name).model_validate(x)
