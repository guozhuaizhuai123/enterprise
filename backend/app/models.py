import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    code: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True, index=True)
    parent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    manager_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_departments_manager_id_users",
        ),
        nullable=True,
        index=True,
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    users: Mapped[list["User"]] = relationship(
        back_populates="department", foreign_keys="User.department_id"
    )
    memberships: Mapped[list["UserDepartment"]] = relationship(
        back_populates="department", cascade="all, delete-orphan"
    )
    documents: Mapped[list["Document"]] = relationship(back_populates="department", cascade="all, delete-orphan")
    memories: Mapped[list["DepartmentMemory"]] = relationship(
        back_populates="department", cascade="all, delete-orphan"
    )
    holiday_periods: Mapped[list["HolidayPeriod"]] = relationship(
        back_populates="department", cascade="all, delete-orphan"
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    # Symmetric-encrypted (Fernet) password, decryptable by admin. See PRD §12 risk note.
    password_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="employee")  # admin | employee
    department_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("departments.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    department: Mapped[Department | None] = relationship(
        back_populates="users", foreign_keys=[department_id]
    )
    memberships: Mapped[list["UserDepartment"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    memories: Mapped[list["UserMemory"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    chat_setting: Mapped["UserChatSetting | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    work_schedule_days: Mapped[list["WorkScheduleDay"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    leave_requests: Mapped[list["LeaveRequest"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", foreign_keys="LeaveRequest.user_id"
    )
    attendance_records: Mapped[list["AttendanceRecord"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    employee_profile: Mapped["EmployeeProfile | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False,
        foreign_keys="EmployeeProfile.user_id",
    )
    assigned_roles: Mapped[list["UserRole"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserDepartment(Base):
    __tablename__ = "user_departments"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), primary_key=True)
    department_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("departments.id"), primary_key=True
    )
    position: Mapped[str] = mapped_column(String(100), default="")
    access_level: Mapped[str] = mapped_column(String(32), default="member")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    joined_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    left_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    user: Mapped[User] = relationship(back_populates="memberships")
    department: Mapped[Department] = relationship(back_populates="memberships")


class EmployeeProfile(Base):
    __tablename__ = "employee_profiles"
    __table_args__ = (
        CheckConstraint(
            "status IN ('probation', 'active', 'suspended', 'terminated')",
            name="ck_employee_profiles_status",
        ),
    )

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    full_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    phone: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    email: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    hire_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    termination_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", index=True)
    position: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    level: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    manager_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    salary: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    user: Mapped[User] = relationship(back_populates="employee_profile", foreign_keys=[user_id])


class EmploymentEvent(Base):
    __tablename__ = "employment_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    before_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    after_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    actor_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role", "department_id", name="uq_user_role_scope"),
        CheckConstraint(
            "role IN ('admin', 'employee', 'hr', 'manager', 'finance')",
            name="ck_user_roles_role",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    department_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("departments.id", ondelete="CASCADE"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user: Mapped[User] = relationship(back_populates="assigned_roles")


class WorkflowDefinition(Base):
    __tablename__ = "workflow_definitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class WorkflowNode(Base):
    __tablename__ = "workflow_nodes"
    __table_args__ = (
        UniqueConstraint("definition_id", "sequence", name="uq_workflow_node_sequence"),
        CheckConstraint(
            "assignee_type IN ('manager', 'role')",
            name="ck_workflow_nodes_assignee_type",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    definition_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflow_definitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    assignee_type: Mapped[str] = mapped_column(String(16), nullable=False)
    assignee_role: Mapped[str | None] = mapped_column(String(16), nullable=True)
    department_scoped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ApprovalInstance(Base):
    __tablename__ = "approval_instances"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_approval', 'approved', 'rejected', 'cancelled')",
            name="ck_approval_instances_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    definition_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflow_definitions.id"), nullable=False, index=True
    )
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    requester_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="pending_approval", index=True
    )
    current_node_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class ApprovalTask(Base):
    __tablename__ = "approval_tasks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'cancelled')",
            name="ck_approval_tasks_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    instance_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("approval_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    node_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflow_nodes.id"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    assignee_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    assignee_role: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    department_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    acted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ApprovalAction(Base):
    __tablename__ = "approval_actions"
    __table_args__ = (
        CheckConstraint(
            "action IN ('submit', 'approve', 'reject', 'cancel')",
            name="ck_approval_actions_action",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    instance_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("approval_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("approval_tasks.id", ondelete="SET NULL"), nullable=True
    )
    actor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    comment: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    from_status: Mapped[str] = mapped_column(String(24), nullable=False)
    to_status: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ExpenseClaim(Base):
    __tablename__ = "expense_claims"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'pending_approval', 'rejected', 'payment_pending', 'paid', 'cancelled')",
            name="ck_expense_claims_status",
        ),
        CheckConstraint("total_amount >= 0", name="ck_expense_claims_total_amount"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    claim_no: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)
    requester_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    department_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    purpose: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    project_code: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="CNY")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft", index=True)
    approval_instance_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("approval_instances.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    submission_key: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    items: Mapped[list["ExpenseItem"]] = relationship(
        back_populates="claim", cascade="all, delete-orphan", order_by="ExpenseItem.sort_order"
    )
    attachments: Mapped[list["ExpenseAttachment"]] = relationship(
        back_populates="claim", cascade="all, delete-orphan"
    )
    approval_instance: Mapped[ApprovalInstance | None] = relationship(
        foreign_keys=[approval_instance_id]
    )
    payment: Mapped["PaymentRecord | None"] = relationship(
        back_populates="claim", cascade="all, delete-orphan", uselist=False
    )


class PayrollSetting(Base):
    __tablename__ = "payroll_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    auto_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    pay_day: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    generation_lead_days: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="CNY")
    approval_role: Mapped[str] = mapped_column(String(16), nullable=False, default="finance")
    updated_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class PayrollRun(Base):
    __tablename__ = "payroll_runs"
    __table_args__ = (
        UniqueConstraint("period", name="uq_payroll_runs_period"),
        CheckConstraint(
            "status IN ('scheduled', 'generated', 'pending_approval', 'approved', 'rejected', 'paid')",
            name="ck_payroll_runs_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    period: Mapped[str] = mapped_column(String(7), nullable=False, index=True)
    pay_date: Mapped[date] = mapped_column(Date, nullable=False)
    generation_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="scheduled", index=True)
    expense_claim_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("expense_claims.id", ondelete="SET NULL"), nullable=True, unique=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    lines: Mapped[list["PayrollLine"]] = relationship(back_populates="run", cascade="all, delete-orphan", order_by="PayrollLine.employee_name")
    expense_claim: Mapped[ExpenseClaim | None] = relationship()


class PayrollLine(Base):
    __tablename__ = "payroll_lines"
    __table_args__ = (UniqueConstraint("run_id", "employee_id", name="uq_payroll_lines_employee"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("payroll_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_name: Mapped[str] = mapped_column(String(100), nullable=False)
    salary_input: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    net_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    run: Mapped[PayrollRun] = relationship(back_populates="lines")


class ExpenseItem(Base):
    __tablename__ = "expense_items"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_expense_items_amount"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    claim_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("expense_claims.id", ondelete="CASCADE"), nullable=False, index=True
    )
    expense_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    vendor: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    invoice_no: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    claim: Mapped[ExpenseClaim] = relationship(back_populates="items")


class FileAsset(Base):
    __tablename__ = "file_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    storage_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ExpenseAttachment(Base):
    __tablename__ = "expense_attachments"
    __table_args__ = (
        UniqueConstraint("claim_id", "file_id", name="uq_expense_attachment_file"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    claim_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("expense_claims.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("file_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    claim: Mapped[ExpenseClaim] = relationship(back_populates="attachments")
    file: Mapped[FileAsset] = relationship()


class PaymentRecord(Base):
    __tablename__ = "payment_records"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payment_records_amount"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    claim_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("expense_claims.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    paid_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="CNY")
    method: Mapped[str] = mapped_column(String(32), nullable=False)
    reference: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    claim: Mapped[ExpenseClaim] = relationship(back_populates="payment")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    actor_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    department_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    before_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    after_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class SensitiveEvent(Base):
    __tablename__ = "sensitive_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    department_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    question: Mapped[str] = mapped_column(Text, nullable=False)
    matched_keyword: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    reason: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SensitiveKeyword(Base):
    __tablename__ = "sensitive_keywords"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    keyword: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class WorkScheduleDay(Base):
    __tablename__ = "work_schedule_days"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 1 AND 7", name="ck_work_schedule_days_weekday"),
    )

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    weekday: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    start_time: Mapped[str] = mapped_column(String(5), default="09:00", nullable=False)
    end_time: Mapped[str] = mapped_column(String(5), default="18:00", nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    user: Mapped[User] = relationship(back_populates="work_schedule_days")


class LeaveRequest(Base):
    __tablename__ = "leave_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_leave_requests_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    leave_type: Mapped[str] = mapped_column(String(20), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)
    reviewed_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user: Mapped[User] = relationship(back_populates="leave_requests", foreign_keys=[user_id])


class HolidayPeriod(Base):
    __tablename__ = "holiday_periods"
    __table_args__ = (
        CheckConstraint(
            "scope_type IN ('company', 'department')",
            name="ck_holiday_periods_scope_type",
        ),
        CheckConstraint("start_date <= end_date", name="ck_holiday_periods_date_range"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    department_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("departments.id", ondelete="CASCADE"), nullable=True, index=True
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    department: Mapped[Department | None] = relationship(back_populates="holiday_periods")


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    __table_args__ = (
        UniqueConstraint("user_id", "attendance_date", name="uq_attendance_user_date"),
        CheckConstraint(
            "status IN ('present', 'late', 'absent', 'remote')",
            name="ck_attendance_records_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attendance_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    note: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    recorded_by: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    user: Mapped[User] = relationship(back_populates="attendance_records")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    department_id: Mapped[str] = mapped_column(String(36), ForeignKey("departments.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="")
    sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    uploaded_by: Mapped[str] = mapped_column(String(36), nullable=False)
    owner_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    contract_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("contracts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    owner_name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    department: Mapped[Department] = relationship(back_populates="documents")
    owner: Mapped[User | None] = relationship(foreign_keys=[owner_id])
    project: Mapped["Project | None"] = relationship(back_populates="documents")
    contract: Mapped["Contract | None"] = relationship(back_populates="documents")
    chunks: Mapped[list["DocumentChunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")
    thread_selections: Mapped[list["ThreadDocumentSelection"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentChunk(Base):
    """Precomputed at write time (PRD §5.2): BM25 tokens + embedding vector,
    persisted so query time never re-processes document content."""

    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id"), nullable=False)
    department_id: Mapped[str] = mapped_column(String(36), ForeignKey("departments.id"), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    tokens: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(JSON, nullable=False)

    document: Mapped[Document] = relationship(back_populates="chunks")


class Thread(Base):
    __tablename__ = "threads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    department_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    messages: Mapped[list["Message"]] = relationship(back_populates="thread", cascade="all, delete-orphan")
    context_setting: Mapped["ThreadContextSetting | None"] = relationship(
        back_populates="thread", cascade="all, delete-orphan", uselist=False
    )
    document_selections: Mapped[list["ThreadDocumentSelection"]] = relationship(
        back_populates="thread", cascade="all, delete-orphan"
    )


class AssistantAction(Base):
    __tablename__ = "assistant_actions"
    __table_args__ = (
        Index("ix_assistant_actions_user_thread_status", "user_id", "thread_id", "status"),
        UniqueConstraint("user_id", "idempotency_key", name="uq_assistant_actions_user_idempotency_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    thread_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    preview_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    parameter_hash: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    object_versions_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    confirmation_phrase: Mapped[str | None] = mapped_column(String(200), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    thread_id: Mapped[str] = mapped_column(String(36), ForeignKey("threads.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    thread: Mapped[Thread] = relationship(back_populates="messages")
    context_flag: Mapped["MessageContextFlag | None"] = relationship(
        back_populates="message", cascade="all, delete-orphan", uselist=False
    )


class UserMemory(Base):
    __tablename__ = "user_memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(80), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    user: Mapped[User] = relationship(back_populates="memories")


class DepartmentMemory(Base):
    __tablename__ = "department_memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    department_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("departments.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(80), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    department: Mapped[Department] = relationship(back_populates="memories")


class UserChatSetting(Base):
    __tablename__ = "user_chat_settings"
    __table_args__ = (
        CheckConstraint(
            "default_memory_level BETWEEN 1 AND 5",
            name="ck_user_chat_settings_default_memory_level",
        ),
    )

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), primary_key=True)
    default_memory_level: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    user: Mapped[User] = relationship(back_populates="chat_setting")


class ThreadContextSetting(Base):
    __tablename__ = "thread_context_settings"
    __table_args__ = (
        CheckConstraint("memory_level BETWEEN 1 AND 5", name="ck_thread_context_settings_memory_level"),
        CheckConstraint(
            "document_scope_mode IN ('all', 'selected')",
            name="ck_thread_context_settings_document_scope_mode",
        ),
    )

    thread_id: Mapped[str] = mapped_column(String(36), ForeignKey("threads.id"), primary_key=True)
    memory_level: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    document_scope_mode: Mapped[str] = mapped_column(String(16), default="all", nullable=False)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_through_message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    summary_token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    summary_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    thread: Mapped[Thread] = relationship(back_populates="context_setting")


class ThreadDocumentSelection(Base):
    __tablename__ = "thread_document_selections"

    thread_id: Mapped[str] = mapped_column(String(36), ForeignKey("threads.id"), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    thread: Mapped[Thread] = relationship(back_populates="document_selections")
    document: Mapped[Document] = relationship(back_populates="thread_selections")


class MessageContextFlag(Base):
    __tablename__ = "message_context_flags"

    message_id: Mapped[str] = mapped_column(String(36), ForeignKey("messages.id"), primary_key=True)
    context_eligible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reason: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    message: Mapped[Message] = relationship(back_populates="context_flag")


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint(
            "ticket_type IN ('same_department', 'cross_department', 'question', 'issue')",
            name="ck_tickets_type",
        ),
        CheckConstraint(
            "status IN ('pending_acceptance', 'pending_admin', 'in_progress', 'answered', 'completed', 'rejected', 'closed', 'cancelled')",
            name="ck_tickets_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    requester_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    target_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    department_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    # 跨部门协助时发起人指定的「需要协助的部门」，管理员据此知道该调度给哪个部门
    requested_department_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    ticket_type: Mapped[str] = mapped_column(String(24), nullable=False)
    subject: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending_acceptance", index=True)
    requires_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TicketMessage(Base):
    __tablename__ = "ticket_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    ticket_id: Mapped[str] = mapped_column(String(36), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Todo(Base):
    __tablename__ = "todos"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'in_progress', 'completed', 'cancelled')", name="ck_todos_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    assignee_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    ticket_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tickets.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class TicketEvent(Base):
    __tablename__ = "ticket_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    ticket_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=True, index=True)
    todo_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("todos.id", ondelete="CASCADE"), nullable=True, index=True)
    actor_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    detail: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    recipient_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    ticket_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=True)
    todo_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("todos.id", ondelete="CASCADE"), nullable=True)
    approval_instance_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("approval_instances.id", ondelete="CASCADE"), nullable=True, index=True
    )
    expense_claim_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("expense_claims.id", ondelete="CASCADE"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(String(300), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Project(Base):
    """项目：与合同是平行的一级经营对象，合同通过 project_id 弱引用归属项目。"""

    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(
            "type IN ('internal', 'client', 'rd', 'other')",
            name="ck_projects_type",
        ),
        CheckConstraint(
            "status IN ('preparing', 'active', 'closed', 'paused', 'cancelled')",
            name="ck_projects_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False, default="internal")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="preparing")
    department_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    manager_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    budget: Mapped[Decimal | None] = mapped_column(Numeric(16, 2), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    contracts: Mapped[list["Contract"]] = relationship(back_populates="project")
    documents: Mapped[list[Document]] = relationship(back_populates="project")


class Contract(Base):
    """合同：独立法律实体，可选归属某个项目（弱引用）。"""

    __tablename__ = "contracts"
    __table_args__ = (
        CheckConstraint(
            "type IN ('purchase', 'sales', 'service', 'lease', 'nda', 'other')",
            name="ck_contracts_type",
        ),
        CheckConstraint(
            "status IN ('draft', 'reviewing', 'active', 'fulfilled', 'expired', 'terminated')",
            name="ck_contracts_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False, default="purchase")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    party_a: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    party_b: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(16, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="CNY", nullable=False)
    sign_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    owner_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    project: Mapped[Project | None] = relationship(back_populates="contracts")
    documents: Mapped[list[Document]] = relationship(back_populates="contract")
