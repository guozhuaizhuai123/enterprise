"""The closed, server-owned catalog of administrative assistant actions.

This module deliberately contains only metadata and existing service entry
points.  Planning may inspect the catalog, but execution is introduced by the
confirmation service in a later task.
"""
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.assistant.schemas import ActionRisk
from app.expense.service import ExpenseService
from app.kb import service as kb_service
from app.organization.service import OrganizationService
from app.payroll.service import PayrollService
from app.schedule.service import create_leave_request_in_transaction
from app.models import (
    ApprovalInstance,
    AttendanceRecord,
    Contract,
    Department,
    DepartmentMemory,
    Document,
    ExpenseClaim,
    HolidayPeriod,
    LeaveRequest,
    PayrollSetting,
    Project,
    Ticket,
    Todo,
    SensitiveEvent,
    SensitiveKeyword,
    User,
)
from app.schemas import (
    AdminEmployeeCreate,
    AdminEmployeeUpdate,
    ApprovalDecisionIn,
    AttendanceUpdate,
    ContractCreate,
    ContractUpdate,
    DocumentCreate,
    DocumentUpdate,
    ExpenseClaimCreate,
    ExpenseClaimUpdate,
    ExpenseSubmitIn,
    EmploymentEventCreate,
    HolidayCreate,
    LeaveRequestCreate,
    LeaveRequestReview,
    OrgUnitCreate,
    OrgUnitUpdate,
    PaymentCreate,
    PayrollGenerateIn,
    PayrollSettingUpdate,
    PasswordResetIn,
    ProjectCreate,
    ProjectUpdate,
    TicketCreate,
    TicketDispatch,
    TodoCreate,
    TodoUpdate,
    MemoryCreate,
    MemoryUpdate,
    SensitiveKeywordCreate,
    SensitiveKeywordUpdate,
    WorkScheduleUpdate,
)
from app.workflow.service import WorkflowService


ActionHandler = Callable[..., Any]


class QueryInput(BaseModel):
    """Bounded filters common to read-only catalog actions."""

    department_id: str | None = None
    query: str | None = Field(default=None, max_length=500)


class _PeriodRangeMixin(BaseModel):
    """A closed date range: both ends or neither, ordered, and bounded to a year."""

    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def _validate_range(self):
        if (self.start_date is None) != (self.end_date is None):
            raise ValueError("date range requires both start_date and end_date")
        if self.start_date is not None and self.end_date is not None:
            if self.start_date > self.end_date:
                raise ValueError("date range start must not be after its end")
            if (self.end_date - self.start_date).days > 366:
                raise ValueError("date range must not exceed 366 days")
        return self


class ExpenseSummaryInput(_PeriodRangeMixin):
    department_id: str | None = None
    month: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")

    @model_validator(mode="after")
    def _reject_conflicting_period(self) -> "ExpenseSummaryInput":
        if self.month is not None and self.start_date is not None:
            raise ValueError("expense query accepts either month or a date range")
        return self


class AttendanceSummaryInput(_PeriodRangeMixin):
    """Exactly one period shape: one day, one month, or one range."""

    department_id: str | None = None
    attendance_date: date | None = None
    month: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")

    @model_validator(mode="after")
    def _reject_conflicting_period(self) -> "AttendanceSummaryInput":
        provided = sum(
            value is not None for value in (self.attendance_date, self.month, self.start_date)
        )
        if provided > 1:
            raise ValueError("attendance query accepts one of attendance_date, month or a date range")
        return self


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


class EmployeeTargetUpdate(AdminEmployeeUpdate):
    id: str = Field(min_length=1, max_length=64)


class EmploymentEventActionInput(EmploymentEventCreate):
    id: str = Field(min_length=1, max_length=64)


class PasswordResetActionInput(PasswordResetIn):
    id: str = Field(min_length=1, max_length=64)


class ExpenseSubmitActionInput(ExpenseSubmitIn):
    id: str = Field(min_length=1, max_length=64)


class PayrollSettingsActionInput(PayrollSettingUpdate):
    """Bind payroll settings to the sole server-owned settings record."""

    id: Literal["default"]


class WorkScheduleActionInput(WorkScheduleUpdate):
    """Bind a complete seven-day schedule to its selected employee."""

    id: str = Field(min_length=1, max_length=64)


class AttendanceActionInput(AttendanceUpdate):
    """Save an employee's attendance for one explicit calendar day."""

    id: str = Field(min_length=1, max_length=64)
    attendance_date: date


class LeaveReviewActionInput(LeaveRequestReview):
    id: str = Field(min_length=1, max_length=64)


class TicketDispatchActionInput(TicketDispatch):
    id: str = Field(min_length=1, max_length=64)


class TodoTargetUpdate(TodoUpdate):
    id: str = Field(min_length=1, max_length=64)


class SensitiveKeywordTargetUpdate(SensitiveKeywordUpdate):
    id: str = Field(min_length=1, max_length=64)


class DepartmentMemoryCreateAction(MemoryCreate):
    department_id: str = Field(min_length=1, max_length=64)


class DepartmentMemoryTargetUpdate(MemoryUpdate):
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
    secret_fields: frozenset[str] = frozenset()
    allow_missing_target: bool = False


def _metadata(
    name: str,
    input_model: type[BaseModel],
    required_roles: tuple[str, ...],
    risk_level: ActionRisk,
    *,
    execute: ActionHandler = _not_executable_yet,
    sensitive_read: bool = False,
    target_model: type[Any] | None = None,
    secret_fields: frozenset[str] = frozenset(),
    allow_missing_target: bool = False,
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
        secret_fields=secret_fields,
        allow_missing_target=allow_missing_target,
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
    _metadata("list_tickets", QueryInput, ("admin", "employee", "hr", "manager"), "low"),
    _metadata("attendance_summary", AttendanceSummaryInput, ("admin", "employee", "hr", "manager", "finance"), "low"),
    _metadata("expense_summary", ExpenseSummaryInput, ("admin", "employee", "hr", "manager", "finance"), "low"),
    _metadata("create_org_unit", OrgUnitCreate, ("admin", "hr"), "high", execute=OrganizationService.create_org_unit),
    _metadata("update_org_unit", OrgUnitTargetUpdate, ("admin", "hr"), "high", execute=OrganizationService.update_org_unit, target_model=Department),
    _metadata("create_employee", AdminEmployeeCreate, ("admin", "hr"), "high", execute=OrganizationService.create_employee, secret_fields=frozenset({"password"})),
    _metadata("update_employee", EmployeeTargetUpdate, ("admin", "hr"), "high", execute=OrganizationService.update_employee, target_model=User),
    _metadata("record_employment_event", EmploymentEventActionInput, ("admin", "hr"), "high", execute=OrganizationService.record_employment_event, target_model=User),
    _metadata("reset_employee_password", PasswordResetActionInput, ("admin", "hr"), "high", target_model=User, secret_fields=frozenset({"password"})),
    _metadata("create_project", ProjectCreate, ("admin", "hr", "manager"), "high"),
    _metadata("update_project", ProjectTargetUpdate, ("admin", "hr", "manager"), "high", target_model=Project),
    _metadata("create_contract", ContractCreate, ("admin", "hr", "manager"), "high"),
    _metadata("update_contract", ContractTargetUpdate, ("admin", "hr", "manager"), "high", target_model=Contract),
    _metadata("create_document", AssistantDocumentCreate, ("admin",), "high", execute=kb_service.create_document),
    _metadata("update_document", DocumentTargetUpdate, ("admin",), "high", execute=kb_service.update_document, target_model=Document),
    _metadata("create_expense_draft", ExpenseClaimCreate, ("admin", "employee", "hr", "manager", "finance"), "high", execute=ExpenseService.create_draft),
    _metadata("update_expense_draft", ExpenseDraftTargetUpdate, ("admin", "employee", "hr", "manager", "finance"), "high", execute=ExpenseService.update_draft, target_model=ExpenseClaim),
    _metadata("submit_expense", ExpenseSubmitActionInput, ("admin", "employee", "hr", "manager", "finance"), "high", execute=ExpenseService.submit, target_model=ExpenseClaim),
    _metadata("update_work_schedule", WorkScheduleActionInput, ("admin",), "high", target_model=User),
    _metadata("create_holiday", HolidayCreate, ("admin",), "high"),
    _metadata("delete_holiday", EntityInput, ("admin",), "high", target_model=HolidayPeriod),
    _metadata("upsert_attendance", AttendanceActionInput, ("admin",), "high", target_model=User),
    _metadata("delete_attendance", EntityInput, ("admin",), "high", target_model=AttendanceRecord),
    _metadata("create_leave_request", LeaveRequestCreate, ("admin", "employee", "hr", "manager", "finance"), "high", execute=create_leave_request_in_transaction),
    _metadata("review_leave_request", LeaveReviewActionInput, ("admin",), "high", target_model=LeaveRequest),
    _metadata("create_ticket", TicketCreate, ("admin", "employee", "hr", "manager", "finance"), "high"),
    _metadata("dispatch_ticket", TicketDispatchActionInput, ("admin",), "high", target_model=Ticket),
    _metadata("create_todo", TodoCreate, ("admin",), "high"),
    _metadata("update_todo", TodoTargetUpdate, ("admin", "employee", "hr", "manager", "finance"), "high", target_model=Todo),
    _metadata("create_sensitive_keyword", SensitiveKeywordCreate, ("admin",), "high"),
    _metadata("update_sensitive_keyword", SensitiveKeywordTargetUpdate, ("admin",), "high", target_model=SensitiveKeyword),
    _metadata("delete_sensitive_keyword", EntityInput, ("admin",), "high", target_model=SensitiveKeyword),
    _metadata("delete_sensitive_event", EntityInput, ("admin",), "high", target_model=SensitiveEvent),
    _metadata("create_department_memory", DepartmentMemoryCreateAction, ("admin",), "high"),
    _metadata("update_department_memory", DepartmentMemoryTargetUpdate, ("admin",), "high", target_model=DepartmentMemory),
    _metadata("delete_department_memory", EntityInput, ("admin",), "high", target_model=DepartmentMemory),
    _metadata("approve_approval", ApprovalActionInput, ("admin", "hr", "manager", "finance"), "high", execute=WorkflowService.act, target_model=ApprovalInstance),
    _metadata("reject_approval", ApprovalActionInput, ("admin", "hr", "manager", "finance"), "high", execute=WorkflowService.act, target_model=ApprovalInstance),
    _metadata("cancel_approval", ApprovalActionInput, ("admin", "hr", "manager", "finance"), "high", execute=WorkflowService.act, target_model=ApprovalInstance),
    _metadata("pay_expense", PaymentActionInput, ("admin", "finance"), "high", execute=ExpenseService.pay, target_model=ExpenseClaim),
    _metadata("generate_payroll", PayrollGenerateIn, ("admin",), "batch", execute=PayrollService.generate_run),
    _metadata("update_payroll_settings", PayrollSettingsActionInput, ("admin",), "high", execute=PayrollService.update_settings, target_model=PayrollSetting, allow_missing_target=True),
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
