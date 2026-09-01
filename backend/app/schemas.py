from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.assistant.schemas import (
    ActionChange,
    ActionConfirmRequest,
    ActionPreview,
    ActionResult,
    ActionRisk,
    ActionStatus,
)


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    user_id: str
    role: str
    department_id: str | None
    departments: list["DepartmentMembershipOut"] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    username: str


class MeOut(BaseModel):
    """当前登录者信息，用于校验已保存账号的会话是否仍然有效。"""
    user_id: str
    username: str
    role: str
    department_id: str | None
    departments: list["DepartmentMembershipOut"] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)


class DepartmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class DepartmentOut(BaseModel):
    id: str
    name: str
    created_at: datetime
    employee_count: int = 0
    document_count: int = 0

    class Config:
        from_attributes = True


class EmployeeCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)
    department_ids: list[str] = Field(min_length=1)
    positions: dict[str, str] = Field(default_factory=dict)


class EmployeeUpdate(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    department_ids: list[str] | None = None
    positions: dict[str, str] = Field(default_factory=dict)


class EmployeeOut(BaseModel):
    id: str
    username: str
    password: str | None = None
    department_id: str | None
    departments: list["DepartmentMembershipOut"] = Field(default_factory=list)
    created_at: datetime


class DepartmentMembershipOut(BaseModel):
    id: str
    name: str
    position: str = ""
    access_level: str = "member"


class OrgUnitCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=1, max_length=32)
    parent_id: str | None = None
    manager_id: str | None = None


class OrgUnitUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    code: str | None = Field(default=None, min_length=1, max_length=32)
    parent_id: str | None = None
    manager_id: str | None = None
    active: bool | None = None


class OrgUnitOut(BaseModel):
    id: str
    name: str
    code: str | None
    parent_id: str | None
    manager_id: str | None
    manager_name: str = ""
    active: bool
    created_at: datetime
    updated_at: datetime


class OrgMembershipOut(BaseModel):
    department_id: str
    department_name: str
    position: str = ""
    is_primary: bool = False
    joined_at: date | None = None
    left_at: date | None = None


class AdminEmployeeCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=100)
    department_ids: list[str] = Field(min_length=1)
    primary_department_id: str
    phone: str = Field(default="", max_length=32)
    email: str = Field(default="", max_length=200)
    hire_date: date | None = None
    status: Literal["probation", "active", "suspended", "terminated"] = "active"
    position: str = Field(default="", max_length=100)
    level: str = Field(default="", max_length=50)
    manager_id: str | None = None
    salary: str = Field(default="", max_length=64)
    roles: list[Literal["employee", "hr", "manager", "finance"]] = Field(
        default_factory=lambda: ["employee"]
    )


class AdminEmployeeUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=200)
    hire_date: date | None = None
    termination_date: date | None = None
    status: Literal["probation", "active", "suspended", "terminated"] | None = None
    position: str | None = Field(default=None, max_length=100)
    level: str | None = Field(default=None, max_length=50)
    manager_id: str | None = None
    salary: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=2000)
    department_ids: list[str] | None = None
    primary_department_id: str | None = None
    roles: list[Literal["employee", "hr", "manager", "finance"]] | None = None


class OrgEmployeeOut(BaseModel):
    id: str
    username: str
    full_name: str
    phone: str
    email: str
    hire_date: date | None
    termination_date: date | None
    status: str
    position: str
    level: str
    manager_id: str | None
    manager_name: str = ""
    salary: str
    notes: str
    department_id: str | None
    departments: list[OrgMembershipOut] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class EmploymentEventCreate(BaseModel):
    event_type: Literal["onboard", "probation_passed", "transfer", "position_change", "offboard"]
    effective_date: date
    status: Literal["probation", "active", "suspended", "terminated"] | None = None
    department_ids: list[str] | None = None
    primary_department_id: str | None = None
    manager_id: str | None = None
    position: str | None = Field(default=None, max_length=100)
    level: str | None = Field(default=None, max_length=50)
    note: str = Field(default="", max_length=500)


class EmploymentEventOut(BaseModel):
    id: str
    user_id: str
    event_type: str
    effective_date: date
    before_data: dict
    after_data: dict
    actor_id: str | None
    note: str
    created_at: datetime


class PasswordResetIn(BaseModel):
    password: str = Field(min_length=8, max_length=128)


class ApprovalDecisionIn(BaseModel):
    expected_version: int = Field(ge=1)
    comment: str = Field(default="", max_length=1000)


class ApprovalTaskOut(BaseModel):
    id: str
    instance_id: str
    entity_type: str
    entity_id: str
    requester_id: str
    requester_name: str = ""
    node_name: str
    sequence: int
    status: str
    assignee_id: str | None
    assignee_role: str | None
    department_id: str | None
    instance_status: str
    version: int
    created_at: datetime
    acted_at: datetime | None


class ApprovalActionOut(BaseModel):
    id: str
    task_id: str | None
    actor_id: str
    actor_name: str = ""
    action: str
    comment: str
    from_status: str
    to_status: str
    created_at: datetime


class ApprovalHandlerOut(BaseModel):
    id: str
    username: str
    display_name: str


class ApprovalRouteStepOut(BaseModel):
    sequence: int
    name: str
    status: str
    handlers: list[ApprovalHandlerOut] = Field(default_factory=list)


class ApprovalInstanceOut(BaseModel):
    id: str
    workflow_code: str
    workflow_name: str
    entity_type: str
    entity_id: str
    requester_id: str
    requester_name: str = ""
    status: str
    current_node_sequence: int
    version: int
    submitted_at: datetime
    completed_at: datetime | None
    updated_at: datetime
    tasks: list[ApprovalTaskOut] = Field(default_factory=list)
    actions: list[ApprovalActionOut] = Field(default_factory=list)
    approval_route: list[ApprovalRouteStepOut] = Field(default_factory=list)
    can_approve: bool = False
    can_reject: bool = False
    can_cancel: bool = False


class ApprovalHistoryItemOut(BaseModel):
    """审批人视角的一条已处理记录（我的审批历史）。"""

    id: str
    instance_id: str
    entity_type: str
    entity_id: str
    node_name: str = "审批"
    sequence: int = 0
    requester_id: str
    requester_name: str = ""
    action: str
    comment: str = ""
    actor_name: str = ""
    from_status: str = ""
    to_status: str = ""
    instance_status: str = ""
    created_at: datetime


class ExpenseItemIn(BaseModel):
    expense_date: date
    category: str = Field(min_length=1, max_length=50)
    description: str = Field(default="", max_length=500)
    vendor: str = Field(default="", max_length=120)
    invoice_no: str = Field(default="", max_length=100)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    tax_amount: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=12, decimal_places=2)


class ExpenseItemOut(ExpenseItemIn):
    id: str
    sort_order: int


class ExpenseClaimCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    purpose: str = Field(default="", max_length=1000)
    project_code: str = Field(default="", max_length=80)
    currency: Literal["CNY"] = "CNY"
    total_amount: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    items: list[ExpenseItemIn] = Field(min_length=1, max_length=100)


class ExpensePreviewIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class ExpensePreviewOut(BaseModel):
    is_expense_request: bool
    title: str | None = None
    purpose: str | None = None
    total_amount: str | None = None
    category: str | None = None
    department_name: str | None = None
    description: str | None = None


class ExpenseClaimUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    purpose: str | None = Field(default=None, max_length=1000)
    project_code: str | None = Field(default=None, max_length=80)
    total_amount: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    items: list[ExpenseItemIn] | None = Field(default=None, min_length=1, max_length=100)


class ExpenseSubmitIn(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=100)


class ExpenseAttachmentOut(BaseModel):
    id: str
    file_id: str
    original_name: str
    content_type: str
    size_bytes: int
    sha256: str
    created_at: datetime


class PaymentCreate(BaseModel):
    payment_date: date
    method: str = Field(min_length=1, max_length=32)
    reference: str = Field(default="", max_length=100)
    idempotency_key: str = Field(min_length=8, max_length=100)
    expected_version: int = Field(ge=1)


class PaymentOut(BaseModel):
    id: str
    paid_by: str
    amount: Decimal
    currency: str
    method: str
    reference: str
    payment_date: date
    created_at: datetime


class ExpenseClaimOut(BaseModel):
    id: str
    claim_no: str
    requester_id: str
    requester_name: str = ""
    department_id: str | None
    department_name: str = ""
    title: str
    purpose: str
    project_code: str
    currency: str
    total_amount: Decimal
    status: str
    approval_instance_id: str | None
    version: int
    submitted_at: datetime | None
    created_at: datetime
    updated_at: datetime
    items: list[ExpenseItemOut] = Field(default_factory=list)
    attachments: list[ExpenseAttachmentOut] = Field(default_factory=list)
    payment: PaymentOut | None = None


class PayrollSettingOut(BaseModel):
    auto_enabled: bool
    pay_day: int
    generation_lead_days: int
    currency: str
    approval_role: str
    updated_at: datetime


class PayrollSettingUpdate(BaseModel):
    auto_enabled: bool = True
    pay_day: int = Field(ge=1, le=28)
    generation_lead_days: int = Field(ge=0, le=31)


class PayrollLineOut(BaseModel):
    id: str
    employee_id: str
    employee_name: str
    salary_input: str
    gross_amount: Decimal
    net_amount: Decimal


class PayrollRunOut(BaseModel):
    id: str
    period: str
    pay_date: date
    generation_date: date
    status: str
    expense_claim_id: str | None
    total_amount: Decimal
    generated_at: datetime | None
    created_at: datetime
    lines: list[PayrollLineOut] = Field(default_factory=list)


class PayrollGenerateIn(BaseModel):
    period: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")


class DashboardMetricBucket(BaseModel):
    count: int
    amount: Decimal


class DashboardOrganizationMetrics(BaseModel):
    active_employees: int
    departments: int


class DashboardApprovalMetrics(BaseModel):
    pending: int


class DashboardOperationalMetrics(BaseModel):
    pending_leave_requests: int
    attendance_missing_today: int
    unfinished_todos: int


class DashboardMonthlyExpense(BaseModel):
    month: str
    count: int
    amount: Decimal


class DashboardOverviewOut(BaseModel):
    period_start: date
    period_end: date
    timezone: str
    organization: DashboardOrganizationMetrics | None
    expenses: dict[str, DashboardMetricBucket]
    approvals: DashboardApprovalMetrics
    operations: DashboardOperationalMetrics
    monthly_expenses: list[DashboardMonthlyExpense]


class DocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    category: str = ""
    sensitive: bool = False
    content: str = Field(min_length=1)
    owner_id: str | None = None
    project_id: str | None = None
    contract_id: str | None = None


class DocumentUpdate(BaseModel):
    title: str | None = None
    category: str | None = None
    sensitive: bool | None = None
    content: str | None = None
    owner_id: str | None = None
    project_id: str | None = None
    contract_id: str | None = None


class EmployeeDocumentCreate(BaseModel):
    department_id: str
    title: str = Field(min_length=1, max_length=200)
    category: str = ""
    sensitive: bool = False
    content: str = Field(min_length=1)
    project_id: str | None = None
    contract_id: str | None = None


class EmployeeDocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = None
    sensitive: bool | None = None
    content: str | None = Field(default=None, min_length=1)
    project_id: str | None = None
    contract_id: str | None = None


class DocumentOut(BaseModel):
    id: str
    department_id: str
    title: str
    category: str
    sensitive: bool
    owner_id: str | None = None
    owner_name: str = ""
    owner_active: bool = False
    project_id: str | None = None
    project_name: str = ""
    contract_id: str | None = None
    contract_name: str = ""
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DocumentDetailOut(DocumentOut):
    content: str


class OwnerOptionOut(BaseModel):
    id: str
    username: str
    role: str
    department_name: str = ""
    # 一个人可能属于多个部门，派发时按部门分组需要展示在每一个所属部门下
    departments: list[str] = []
    department_ids: list[str] = []


class SensitiveEventOut(BaseModel):
    id: str
    user_id: str | None
    username: str
    department_name: str
    question: str
    matched_keyword: str
    reason: str
    created_at: datetime

    class Config:
        from_attributes = True


class SensitiveKeywordCreate(BaseModel):
    keyword: str = Field(min_length=1, max_length=100)
    enabled: bool = True


class SensitiveKeywordUpdate(BaseModel):
    keyword: str | None = Field(default=None, min_length=1, max_length=100)
    enabled: bool | None = None


class SensitiveKeywordOut(BaseModel):
    id: str
    keyword: str
    enabled: bool
    updated_by: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    thread_id: str | None = None
    department_ids: list[str] | None = None
    memory_level: int | None = Field(default=None, ge=1, le=5)
    document_scope_mode: Literal["all", "selected"] | None = None
    document_ids: list[str] | None = None


class ThreadOut(BaseModel):
    id: str
    title: str
    created_at: datetime

    class Config:
        from_attributes = True


class ThreadContextUpdate(BaseModel):
    memory_level: int | None = Field(default=None, ge=1, le=5)
    document_scope_mode: Literal["all", "selected"] | None = None
    document_ids: list[str] | None = None

    @model_validator(mode="after")
    def selected_scope_requires_documents(self):
        if self.document_scope_mode == "selected" and not self.document_ids:
            raise ValueError("selected scope requires at least one document")
        return self


class ThreadContextOut(BaseModel):
    memory_level: int
    document_scope_mode: Literal["all", "selected"]
    document_ids: list[str]


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    citations: list[dict] | None
    created_at: datetime

    class Config:
        from_attributes = True


class MemoryCreate(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=500)
    enabled: bool = True


class MemoryUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=80)
    content: str | None = Field(default=None, min_length=1, max_length=500)
    enabled: bool | None = None


class MemoryOut(BaseModel):
    id: str
    title: str
    content: str
    enabled: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DepartmentMemoryOut(MemoryOut):
    department_id: str
    created_by: str
    updated_by: str


class UserChatSettingOut(BaseModel):
    default_memory_level: int


class UserChatSettingUpdate(BaseModel):
    default_memory_level: int = Field(ge=1, le=5)


class ScheduleDayInput(BaseModel):
    weekday: int = Field(ge=1, le=7)
    enabled: bool
    start_time: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    end_time: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class ScheduleDayOut(ScheduleDayInput):
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class WorkScheduleUpdate(BaseModel):
    days: list[ScheduleDayInput] = Field(min_length=7, max_length=7)


class LeaveRequestCreate(BaseModel):
    leave_type: str = Field(min_length=1, max_length=20)
    start_date: date
    end_date: date
    reason: str = Field(default="", max_length=300)


class LeaveRequestReview(BaseModel):
    status: Literal["approved", "rejected"]


class LeaveRequestOut(BaseModel):
    id: str
    user_id: str
    username: str = ""
    leave_type: str
    start_date: date
    end_date: date
    reason: str
    status: Literal["pending", "approved", "rejected"]
    reviewed_by: str | None
    reviewed_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


class LeavePreviewIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    today: date | None = None


class LeavePreviewOut(BaseModel):
    is_leave_request: bool
    leave_type: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    reason: str = ""


class HolidayCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scope_type: Literal["company", "department"]
    department_id: str | None = None
    start_date: date
    end_date: date
    description: str = Field(default="", max_length=300)


class HolidayOut(BaseModel):
    id: str
    name: str
    scope_type: Literal["company", "department"]
    department_id: str | None
    department_name: str = ""
    start_date: date
    end_date: date
    description: str
    created_by: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AttendanceUpdate(BaseModel):
    status: Literal["present", "late", "absent", "remote"]
    note: str = Field(default="", max_length=300)


class AttendanceRecordOut(BaseModel):
    id: str
    user_id: str
    username: str = ""
    attendance_date: date
    status: Literal["present", "late", "absent", "remote"]
    note: str
    recorded_by: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MyWorkScheduleOut(BaseModel):
    days: list[ScheduleDayOut]
    leave_requests: list[LeaveRequestOut]
    holidays: list[HolidayOut] = Field(default_factory=list)


class AttendanceHistoryOut(BaseModel):
    year: int
    period_start: date
    period_end: date
    scheduled_work_days: int
    organization_holiday_days: int
    weekly_rest_days: int
    approved_leave_days: int
    expected_attendance_days: int
    recorded_attendance_days: int
    unrecorded_attendance_days: int
    present_days: int
    late_days: int
    absent_days: int
    remote_days: int
    attendance_rate: float | None
    leave_requests: list[LeaveRequestOut]
    holidays: list[HolidayOut]
    attendance_records: list[AttendanceRecordOut]


class EmployeeWorkScheduleOut(BaseModel):
    user_id: str
    username: str
    days: list[ScheduleDayOut]


class TicketCreate(BaseModel):
    ticket_type: Literal["same_department", "cross_department", "question", "issue"]
    subject: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=4000)
    target_user_id: str | None = None
    department_id: str | None = None
    # 仅跨部门协助使用：需要协助的部门
    requested_department_id: str | None = None


class TicketPreviewIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class TicketPreviewOut(BaseModel):
    is_ticket_request: bool
    ticket_type: Literal["same_department", "cross_department", "question", "issue"] | None = None
    subject: str | None = None
    description: str | None = None
    target_username: str | None = None
    department_name: str | None = None


class TicketMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class TicketAction(BaseModel):
    reason: str = Field(default="", max_length=500)


class TicketDispatch(BaseModel):
    """管理员把工单进一步派发给协助部门的具体个人。"""
    assignee_id: str


class TicketOut(BaseModel):
    id: str
    requester_id: str
    requester_name: str = ""
    target_user_id: str | None
    target_user_name: str = ""
    department_id: str | None
    department_name: str = ""
    requested_department_id: str | None = None
    requested_department_name: str = ""
    ticket_type: str
    subject: str
    description: str
    status: str
    requires_admin: bool
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None


class TicketMessageOut(BaseModel):
    id: str
    ticket_id: str
    sender_id: str
    sender_name: str = ""
    content: str
    created_at: datetime


class TodoCreate(BaseModel):
    assignee_id: str
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=4000)
    due_at: datetime | None = None
    ticket_id: str | None = None


class TodoUpdate(BaseModel):
    status: Literal["pending", "in_progress", "completed", "cancelled"]


class TodoOut(BaseModel):
    id: str
    assignee_id: str
    assignee_name: str = ""
    created_by: str
    creator_name: str = ""
    ticket_id: str | None
    title: str
    description: str
    status: str
    due_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TicketEventOut(BaseModel):
    id: str
    ticket_id: str | None
    todo_id: str | None
    actor_id: str
    actor_name: str = ""
    event_type: str
    detail: str
    created_at: datetime


class NotificationOut(BaseModel):
    id: str
    ticket_id: str | None
    todo_id: str | None
    approval_instance_id: str | None = None
    expense_claim_id: str | None = None
    kind: str
    content: str
    read_at: datetime | None
    created_at: datetime


# ---------------------------------------------------------------------------
# 项目管理与合同管理
# ---------------------------------------------------------------------------

class ProjectCreate(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=120)
    type: Literal["internal", "client", "rd", "other"] = "internal"
    status: Literal["preparing", "active", "closed", "paused", "cancelled"] = "preparing"
    department_id: str | None = None
    manager_id: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    budget: Decimal | None = Field(default=None, ge=0)
    description: str = ""


class ProjectUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=32)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    type: Literal["internal", "client", "rd", "other"] | None = None
    status: Literal["preparing", "active", "closed", "paused", "cancelled"] | None = None
    department_id: str | None = None
    manager_id: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    budget: Decimal | None = Field(default=None, ge=0)
    description: str | None = None


class ProjectOut(BaseModel):
    id: str
    code: str
    name: str
    type: str
    status: str
    department_id: str | None
    department_name: str = ""
    manager_id: str | None
    manager_name: str = ""
    start_date: date | None
    end_date: date | None
    budget: Decimal | None
    description: str
    contract_count: int = 0
    created_by: str | None
    created_at: datetime
    updated_at: datetime


class ContractCreate(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=160)
    type: Literal["purchase", "sales", "service", "lease", "nda", "other"] = "purchase"
    status: Literal["draft", "reviewing", "active", "fulfilled", "expired", "terminated"] = "draft"
    project_id: str | None = None
    party_a: str = ""
    party_b: str = ""
    amount: Decimal | None = Field(default=None, ge=0)
    currency: str = "CNY"
    sign_date: date | None = None
    effective_date: date | None = None
    expiry_date: date | None = None
    owner_id: str | None = None
    description: str = ""


class ContractUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=32)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    type: Literal["purchase", "sales", "service", "lease", "nda", "other"] | None = None
    status: Literal["draft", "reviewing", "active", "fulfilled", "expired", "terminated"] | None = None
    project_id: str | None = None
    party_a: str | None = None
    party_b: str | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = None
    sign_date: date | None = None
    effective_date: date | None = None
    expiry_date: date | None = None
    owner_id: str | None = None
    description: str | None = None


class ContractOut(BaseModel):
    id: str
    code: str
    name: str
    type: str
    status: str
    project_id: str | None
    project_name: str = ""
    party_a: str
    party_b: str
    amount: Decimal | None
    currency: str
    sign_date: date | None
    effective_date: date | None
    expiry_date: date | None
    owner_id: str | None
    owner_name: str = ""
    description: str
    created_by: str | None
    created_at: datetime
    updated_at: datetime


class ProjectWorkspaceOut(BaseModel):
    project: ProjectOut
    contracts: list[ContractOut]
    documents: list[DocumentOut]
