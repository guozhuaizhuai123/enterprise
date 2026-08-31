import calendar
import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.expense.service import ExpenseService
from app.models import EmployeeProfile, PayrollLine, PayrollRun, PayrollSetting, User
from app.workflow.service import WorkflowService

MONEY = Decimal("0.01")


def parse_salary(value: str | None) -> Decimal | None:
    """Accept legacy values such as 18K, 18000, and 18,000."""
    raw = (value or "").strip().upper().replace(",", "")
    if not raw:
        return None
    multiplier = Decimal("1000") if raw.endswith("K") else Decimal("1")
    if raw.endswith("K"):
        raw = raw[:-1].strip()
    if not re.fullmatch(r"\d+(?:\.\d{1,2})?", raw):
        return None
    try:
        amount = (Decimal(raw) * multiplier).quantize(MONEY, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None
    return amount if amount > 0 else None


def _pay_date(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def _previous_period(pay_date: date) -> str:
    year, month = pay_date.year, pay_date.month - 1
    if month == 0:
        year, month = year - 1, 12
    return f"{year:04d}-{month:02d}"


class PayrollService:
    @staticmethod
    def get_settings(db: Session) -> PayrollSetting:
        setting = db.get(PayrollSetting, "default")
        if setting is None:
            setting = PayrollSetting(id="default", auto_enabled=True, pay_day=10, generation_lead_days=5)
            db.add(setting)
            db.flush()
        return setting

    @staticmethod
    def update_settings(db: Session, payload: dict, actor_id: str) -> PayrollSetting:
        setting = PayrollService.get_settings(db)
        pay_day = int(payload.get("pay_day", setting.pay_day))
        lead_days = int(payload.get("generation_lead_days", setting.generation_lead_days))
        if not 1 <= pay_day <= 28:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "发薪日必须在每月 1 至 28 日之间")
        if not 0 <= lead_days <= 31:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "提前生成天数必须在 0 至 31 天之间")
        setting.auto_enabled = bool(payload.get("auto_enabled", setting.auto_enabled))
        setting.pay_day = pay_day
        setting.generation_lead_days = lead_days
        setting.currency = "CNY"
        setting.approval_role = "finance"
        setting.updated_by = actor_id
        db.flush()
        return setting

    @staticmethod
    def due_period(today: date, setting: PayrollSetting) -> tuple[str, date, date] | None:
        current_pay = _pay_date(today.year, today.month, setting.pay_day)
        if today > current_pay:
            next_month = today.month + 1
            year = today.year + (1 if next_month == 13 else 0)
            month = 1 if next_month == 13 else next_month
            current_pay = _pay_date(year, month, setting.pay_day)
        generation_date = current_pay - timedelta(days=setting.generation_lead_days)
        if today < generation_date:
            return None
        return _previous_period(current_pay), current_pay, generation_date

    @staticmethod
    def generate_run(db: Session, actor_id: str, *, period: str | None = None, today: date | None = None) -> PayrollRun | None:
        setting = PayrollService.get_settings(db)
        today = today or date.today()
        if period:
            try:
                year, month = (int(part) for part in period.split("-"))
                if not 1 <= month <= 12:
                    raise ValueError
            except ValueError as exc:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "工资期间格式应为 YYYY-MM") from exc
            pay_year, pay_month = (year + 1, 1) if month == 12 else (year, month + 1)
            pay_date = _pay_date(pay_year, pay_month, setting.pay_day)
            generation_date = pay_date - timedelta(days=setting.generation_lead_days)
        else:
            due = PayrollService.due_period(today, setting)
            if due is None:
                return None
            period, pay_date, generation_date = due

        existing = db.query(PayrollRun).filter(PayrollRun.period == period).one_or_none()
        if existing is not None:
            return existing

        employees = (
            db.query(User, EmployeeProfile)
            .join(EmployeeProfile, EmployeeProfile.user_id == User.id)
            .filter(EmployeeProfile.status.in_(["active", "probation"]))
            .order_by(User.username)
            .all()
        )
        valid: list[tuple[User, EmployeeProfile, Decimal]] = []
        for user, profile in employees:
            salary = parse_salary(profile.salary)
            if salary is not None:
                valid.append((user, profile, salary))
        if not valid:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "没有配置有效工资的在职员工")

        run = PayrollRun(period=period, pay_date=pay_date, generation_date=generation_date, status="generated")
        db.add(run)
        db.flush()
        total = Decimal("0.00")
        expense_date = date.fromisoformat(f"{period}-01")
        for user, profile, salary in valid:
            name = profile.full_name or user.username
            db.add(PayrollLine(run_id=run.id, employee_id=user.id, employee_name=name, salary_input=profile.salary, gross_amount=salary, net_amount=salary))
            total += salary
        run.total_amount = total.quantize(MONEY)
        claim = ExpenseService.create_draft(
            db,
            requester_id=actor_id,
            title=f"{period} 工资费用单",
            purpose=f"自动生成 {period} 月工资，计划发薪日 {pay_date.isoformat()}",
            project_code="PAYROLL",
            currency=setting.currency,
            expected_total=run.total_amount,
            items=[
                {"expense_date": expense_date, "category": "工资", "description": f"{name} {period} 月工资", "vendor": name, "amount": salary, "tax_amount": Decimal("0.00")}
                for user, profile, salary in valid
                for name in [profile.full_name or user.username]
            ],
        )
        instance = WorkflowService.start(db, "payroll_run", run.id, actor_id, "payroll_approval_v1")
        claim.approval_instance_id = instance.id
        claim.submission_key = f"payroll-{period}"
        claim.status = "pending_approval"
        claim.submitted_at = datetime.now(UTC)
        claim.version += 1
        run.expense_claim_id = claim.id
        run.status = "pending_approval"
        run.generated_at = datetime.now(UTC)
        db.flush()
        # 工资批次由系统按已配置的规则生成，不需要人工重复确认；保留审批实例和审计记录，
        # 但自动完成唯一的财务节点，随后直接进入费用付款队列。
        WorkflowService.act(db, instance.id, actor_id, "approve", "系统自动审核工资批次", instance.version)
        return run

    @staticmethod
    def generate_due_runs(db: Session, actor_id: str, today: date | None = None) -> PayrollRun | None:
        setting = PayrollService.get_settings(db)
        if not setting.auto_enabled:
            return None
        return PayrollService.generate_run(db, actor_id, today=today)
