"""The closed, server-owned catalog of administrative assistant actions.

This module deliberately contains only metadata and existing service entry
points.  Planning may inspect the catalog, but execution is introduced by the
confirmation service in a later task.
"""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from app.assistant.schemas import ActionRisk
from app.expense.service import ExpenseService
from app.kb import service as kb_service
from app.organization.service import OrganizationService
from app.payroll.service import PayrollService
from app.schedule.service import create_leave_request
from app.models import ApprovalInstance, Contract, Department, Document, ExpenseClaim, Project, Ticket
from app.schemas import (
    ApprovalDecisionIn,
    ContractCreate,
    ContractUpdate,
    DocumentCreate,
    DocumentUpdate,
    ExpenseClaimCreate,
    ExpenseClaimUpdate,
    LeaveRequestCreate,
    OrgUnitCreate,
    OrgUnitUpdate,
    PaymentCreate,
    PayrollGenerateIn,
    ProjectCreate,
    ProjectUpdate,
    TicketCreate,
)
from app.workflow.service import WorkflowService


ActionHandler = Callable[..., Any]


class QueryInput(BaseModel):
    """Bounded filters common to read-only catalog actions."""

    department_id: str | None = None
    query: str | None = Field(default=None, max_length=500)


class EntityInput(BaseModel):
    id: str = Field(min_length=1, max_length=64)


class ProjectTargetUpdate(ProjectUpdate):
    """Assistant updates always bind the project selected during preview."""

    id: str = Field(min_length=1, max_length=64)


class ContractTargetUpdate(ContractUpdate):
    """Assistant updates always bind the contract selected during preview."""

    id: str = Field(min_length=1, max_length=64)


class DocumentTargetUpdate(DocumentUpdate):
    """Assistant updates always bind the document selected during preview."""

    id: str = Field(min_length=1, max_length=64)

class AssistantDocumentCreate(DocumentCreate):
    department_id: str = Field(min_length=1, max_length=64)


class OrgUnitTargetUpdate(OrgUnitUpdate):
    """Assistant updates always bind the organization unit selected during preview."""

    id: str = Field(min_length=1, max_length=64)


class ExpenseDraftTargetUpdate(ExpenseClaimUpdate):
    """Assistant updates always bind the expense draft selected during preview."""

    id: str = Field(min_length=1, max_length=64)


class ApprovalActionInput(ApprovalDecisionIn):
    id: str = Field(min_length=1, max_length=64)


class PaymentActionInput(PaymentCreate):
    id: str = Field(min_length=1, max_length=64)


def _not_executable_yet(*_args: Any, **_kwargs: Any) -> Any:
    """Guard router-only business paths until Task 3 supplies service handlers."""
    raise NotImplementedError("assistant action execution is not available yet")


@dataclass(frozen=True)
class ActionDefinition:
    name: str
    input_model: type[BaseModel]
    required_roles: tuple[str, ...]
    risk_level: ActionRisk
    preview: ActionHandler
    execute: ActionHandler
    sensitive_read: bool = False
    target_model: type[Any] | None = None


def _metadata(
    name: str,
    input_model: type[BaseModel],
    required_roles: tuple[str, ...],
    risk_level: ActionRisk,
    *,
    execute: ActionHandler = _not_executable_yet,
    sensitive_read: bool = False,
    target_model: type[Any] | None = None,
) -> ActionDefinition:
    return ActionDefinition(
        name=name,
        input_model=input_model,
        required_roles=required_roles,
        risk_level=risk_level,
        preview=_not_executable_yet,
        execute=execute,
        sensitive_read=sensitive_read,
        target_model=target_model,
    )


# Keep this tuple explicit: accepting an action must require adding its policy
# metadata here.  There is intentionally no dynamic route, URL, or SQL lookup.
_ACTIONS: tuple[ActionDefinition, ...] = (
    _metadata("search_knowledge", QueryInput, ("admin", "hr", "manager"), "sensitive", sensitive_read=True),
    _metadata("list_departments", QueryInput, ("admin", "hr", "manager"), "low"),
    _metadata("list_projects", QueryInput, ("admin", "hr", "manager"), "low"),
    _metadata("list_contracts", QueryInput, ("admin", "hr", "manager"), "low"),
    _metadata("list_expenses", QueryInput, ("admin", "hr", "finance", "manager"), "sensitive", sensitive_read=True),
    _metadata("list_approvals", QueryInput, ("admin", "hr", "finance", "manager"), "sensitive", sensitive_read=True),
    _metadata("list_tickets", QueryInput, ("admin", "hr", "manager"), "low"),
    _metadata("create_org_unit", OrgUnitCreate, ("admin", "hr"), "high", execute=OrganizationService.create_org_unit),
    _metadata("update_org_unit", OrgUnitTargetUpdate, ("admin", "hr"), "high", execute=OrganizationService.update_org_unit, target_model=Department),
    _metadata("create_project", ProjectCreate, ("admin", "hr", "manager"), "high"),
    _metadata("update_project", ProjectTargetUpdate, ("admin", "hr", "manager"), "high", target_model=Project),
    _metadata("create_contract", ContractCreate, ("admin", "hr", "manager"), "high"),
    _metadata("update_contract", ContractTargetUpdate, ("admin", "hr", "manager"), "high", target_model=Contract),
    _metadata("create_document", AssistantDocumentCreate, ("admin",), "high", execute=kb_service.create_document),
    _metadata("update_document", DocumentTargetUpdate, ("admin",), "high", execute=kb_service.update_document, target_model=Document),
    _metadata("create_expense_draft", ExpenseClaimCreate, ("admin", "employee", "hr", "manager", "finance"), "high", execute=ExpenseService.create_draft),
    _metadata("update_expense_draft", ExpenseDraftTargetUpdate, ("admin", "employee", "hr", "manager", "finance"), "high", execute=ExpenseService.update_draft, target_model=ExpenseClaim),
    _metadata("create_leave_request", LeaveRequestCreate, ("admin", "employee", "hr", "manager", "finance"), "high", execute=create_leave_request),
    _metadata("create_ticket", TicketCreate, ("admin", "employee", "hr", "manager", "finance"), "high"),
    _metadata("approve_approval", ApprovalActionInput, ("admin", "hr", "manager", "finance"), "high", execute=WorkflowService.act, target_model=ApprovalInstance),
    _metadata("reject_approval", ApprovalActionInput, ("admin", "hr", "manager", "finance"), "high", execute=WorkflowService.act, target_model=ApprovalInstance),
    _metadata("cancel_approval", ApprovalActionInput, ("admin", "hr", "manager", "finance"), "high", execute=WorkflowService.act, target_model=ApprovalInstance),
    _metadata("pay_expense", PaymentActionInput, ("admin", "finance"), "high", execute=ExpenseService.pay, target_model=ExpenseClaim),
    _metadata("generate_payroll", PayrollGenerateIn, ("admin",), "batch", execute=PayrollService.generate_run),
    _metadata("delete_project", EntityInput, ("admin", "hr", "manager"), "high", target_model=Project),
    _metadata("delete_contract", EntityInput, ("admin", "hr", "manager"), "high", target_model=Contract),
    _metadata("delete_document", EntityInput, ("admin",), "high", execute=kb_service.delete_document, target_model=Document),
    _metadata("delete_expense_draft", EntityInput, ("admin", "employee", "hr", "manager", "finance"), "high", execute=ExpenseService.delete_draft, target_model=ExpenseClaim),
    _metadata("delete_ticket", EntityInput, ("admin",), "high", target_model=Ticket),
)

_ACTION_BY_NAME = {action.name: action for action in _ACTIONS}


def get_action(name: str) -> ActionDefinition | None:
    """Return only an exact registered action name; never interpret a URL or alias."""
    return _ACTION_BY_NAME.get(name)


def list_actions() -> tuple[ActionDefinition, ...]:
    """Return the deterministic, closed action catalog."""
    return _ACTIONS
