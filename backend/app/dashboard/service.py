from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.deps import Principal
from app.models import (
    ApprovalInstance,
    AttendanceRecord,
    Department,
    EmployeeProfile,
    ExpenseClaim,
    LeaveRequest,
    Todo,
    User,
    UserDepartment,
    UserRole,
)


EXPENSE_STATUSES = ("draft", "pending_approval", "rejected", "payment_pending", "paid", "cancelled")


class DashboardService:
    @staticmethod
    def _effective_scope(db: Session, principal: Principal) -> tuple[set[str], set[str] | None]:
        roles = set(principal.roles) | {principal.role}
        allowed = roles.intersection({"admin", "hr", "finance"})
        if not allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "dashboard role required")
        if "admin" in allowed:
            return allowed, None
        role_rows = db.query(UserRole).filter(
            UserRole.user_id == principal.user_id,
            UserRole.role.in_(allowed),
        ).all()
        if any(row.department_id is None for row in role_rows):
            return allowed, None
        scoped = {row.department_id for row in role_rows if row.department_id}
        return allowed, scoped or set(principal.department_ids)

    @staticmethod
    def overview(
        db: Session,
        principal: Principal,
        start: date,
        end: date,
        department_id: str | None = None,
    ) -> dict:
        if start > end:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "period start must be before end")
        roles, scope = DashboardService._effective_scope(db, principal)
        if department_id:
            if scope is not None and department_id not in scope:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "department is outside dashboard scope")
            scope = {department_id}
        start_at = datetime.combine(start, time.min, tzinfo=UTC)
        end_at = datetime.combine(end + timedelta(days=1), time.min, tzinfo=UTC)

        organization = None
        if roles.intersection({"admin", "hr"}):
            employee_query = db.query(func.count(func.distinct(EmployeeProfile.user_id))).filter(
                EmployeeProfile.status.in_(("probation", "active"))
            )
            department_query = db.query(func.count(Department.id)).filter(Department.active.is_(True))
            if scope is not None:
                employee_query = employee_query.join(
                    UserDepartment, UserDepartment.user_id == EmployeeProfile.user_id
                ).filter(UserDepartment.department_id.in_(scope))
                department_query = department_query.filter(Department.id.in_(scope))
            organization = {
                "active_employees": employee_query.scalar() or 0,
                "departments": department_query.scalar() or 0,
            }

        expense_query = db.query(
            ExpenseClaim.status,
            func.count(ExpenseClaim.id),
            func.coalesce(func.sum(ExpenseClaim.total_amount), 0),
        ).filter(ExpenseClaim.created_at >= start_at, ExpenseClaim.created_at < end_at)
        if scope is not None:
            expense_query = expense_query.filter(ExpenseClaim.department_id.in_(scope))
        buckets = {
            item: {"count": 0, "amount": Decimal("0.00")}
            for item in EXPENSE_STATUSES
        }
        for expense_status, count, amount in expense_query.group_by(ExpenseClaim.status).all():
            buckets[expense_status] = {
                "count": count,
                "amount": Decimal(str(amount)).quantize(Decimal("0.01")),
            }

        approval_query = db.query(func.count(ApprovalInstance.id)).join(
            User, User.id == ApprovalInstance.requester_id
        ).filter(
            ApprovalInstance.status == "pending_approval",
            ApprovalInstance.submitted_at >= start_at,
            ApprovalInstance.submitted_at < end_at,
        )
        if scope is not None:
            approval_query = approval_query.filter(User.department_id.in_(scope))
        approvals = {"pending": approval_query.scalar() or 0}

        leave_query = db.query(func.count(LeaveRequest.id)).join(
            User, User.id == LeaveRequest.user_id
        ).filter(LeaveRequest.status == "pending")
        todo_query = db.query(func.count(Todo.id)).join(
            User, User.id == Todo.assignee_id
        ).filter(Todo.status.in_(("pending", "in_progress")))
        active_query = db.query(func.count(EmployeeProfile.user_id)).join(
            User, User.id == EmployeeProfile.user_id
        ).filter(EmployeeProfile.status.in_(("probation", "active")))
        attendance_query = db.query(func.count(func.distinct(AttendanceRecord.user_id))).join(
            User, User.id == AttendanceRecord.user_id
        ).filter(AttendanceRecord.attendance_date == date.today())
        if scope is not None:
            leave_query = leave_query.filter(User.department_id.in_(scope))
            todo_query = todo_query.filter(User.department_id.in_(scope))
            active_query = active_query.filter(User.department_id.in_(scope))
            attendance_query = attendance_query.filter(User.department_id.in_(scope))
        active_count = active_query.scalar() or 0
        attendance_count = attendance_query.scalar() or 0
        operations = {
            "pending_leave_requests": leave_query.scalar() or 0,
            "attendance_missing_today": max(active_count - attendance_count, 0),
            "unfinished_todos": todo_query.scalar() or 0,
        }

        monthly_query = db.query(
            func.strftime("%Y-%m", ExpenseClaim.created_at),
            func.count(ExpenseClaim.id),
            func.coalesce(func.sum(ExpenseClaim.total_amount), 0),
        ).filter(ExpenseClaim.created_at >= start_at, ExpenseClaim.created_at < end_at)
        if scope is not None:
            monthly_query = monthly_query.filter(ExpenseClaim.department_id.in_(scope))
        monthly = [
            {"month": month, "count": count, "amount": Decimal(str(amount)).quantize(Decimal("0.01"))}
            for month, count, amount in monthly_query.group_by(func.strftime("%Y-%m", ExpenseClaim.created_at)).order_by(func.strftime("%Y-%m", ExpenseClaim.created_at)).all()
        ]
        return {
            "period_start": start,
            "period_end": end,
            "timezone": "Asia/Shanghai",
            "organization": organization,
            "expenses": buckets,
            "approvals": approvals,
            "operations": operations,
            "monthly_expenses": monthly,
        }
