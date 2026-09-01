import hashlib
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import exists, or_, select, true
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    ApprovalInstance,
    EmployeeProfile,
    ExpenseAttachment,
    ExpenseClaim,
    ExpenseItem,
    FileAsset,
    Notification,
    PaymentRecord,
    User,
    UserDepartment,
    UserRole,
    PayrollRun,
)
from app.workflow.service import WorkflowService
from app.audit.service import AuditService


MONEY = Decimal("0.01")
ALLOWED_UPLOAD_TYPES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/heic": ".heic",
    "image/heif": ".heic",
}


def _money(value: object) -> Decimal:
    try:
        amount = Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid expense amount") from exc
    if amount <= 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "expense amount must be positive")
    return amount


def _nonnegative_money(value: object) -> Decimal:
    try:
        amount = Decimal(str(value or "0")).quantize(MONEY, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid tax amount") from exc
    if amount < 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "tax amount cannot be negative")
    return amount


class ExpenseService:
    @staticmethod
    def _department_id(db: Session, user_id: str) -> str | None:
        primary = (
            db.query(UserDepartment)
            .filter(UserDepartment.user_id == user_id, UserDepartment.is_primary.is_(True))
            .first()
        )
        if primary:
            return primary.department_id
        user = db.get(User, user_id)
        return user.department_id if user else None

    @staticmethod
    def _claim_no() -> str:
        return f"BX-{datetime.now(UTC):%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"

    @staticmethod
    def _replace_items(db: Session, claim: ExpenseClaim, items: list[dict]) -> Decimal:
        if not items:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "at least one expense item is required")
        claim.items.clear()
        total = Decimal("0.00")
        today = date.today()
        for index, item in enumerate(items):
            category = str(item.get("category", "")).strip()
            if not category:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "expense category is required")
            expense_date = item.get("expense_date")
            if isinstance(expense_date, str):
                try:
                    expense_date = date.fromisoformat(expense_date)
                except ValueError as exc:
                    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid expense date") from exc
            if not isinstance(expense_date, date) or expense_date > today:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "expense date cannot be in the future")
            amount = _money(item.get("amount"))
            claim.items.append(
                ExpenseItem(
                    expense_date=expense_date,
                    category=category,
                    description=str(item.get("description", "")).strip(),
                    vendor=str(item.get("vendor", "")).strip(),
                    invoice_no=str(item.get("invoice_no", "")).strip(),
                    amount=amount,
                    tax_amount=_nonnegative_money(item.get("tax_amount", "0")),
                    sort_order=index,
                )
            )
            total += amount
        claim.total_amount = total.quantize(MONEY)
        db.flush()
        return claim.total_amount

    @staticmethod
    def create_draft(
        db: Session,
        *,
        requester_id: str,
        title: str,
        purpose: str,
        items: list[dict],
        currency: str = "CNY",
        project_code: str = "",
        expected_total: Decimal | None = None,
    ) -> ExpenseClaim:
        if not title.strip():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "claim title is required")
        if currency != "CNY":
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "only CNY is supported in phase one")
        claim = ExpenseClaim(
            claim_no=ExpenseService._claim_no(),
            requester_id=requester_id,
            department_id=ExpenseService._department_id(db, requester_id),
            title=title.strip(),
            purpose=purpose.strip(),
            project_code=project_code.strip(),
            currency=currency,
            status="draft",
        )
        db.add(claim)
        db.flush()
        actual = ExpenseService._replace_items(db, claim, items)
        if expected_total is not None and _money(expected_total) != actual:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "submitted total does not match item total")
        return claim

    @staticmethod
    def _owned_draft(db: Session, claim_id: str, actor_id: str) -> ExpenseClaim:
        claim = db.get(ExpenseClaim, claim_id)
        if claim is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "expense claim not found")
        if claim.requester_id != actor_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "only requester can edit this claim")
        if claim.status != "draft":
            raise HTTPException(status.HTTP_409_CONFLICT, "only a draft claim can be changed")
        return claim

    @staticmethod
    def update_draft(
        db: Session,
        claim_id: str,
        actor_id: str,
        *,
        title: str | None = None,
        purpose: str | None = None,
        project_code: str | None = None,
        items: list[dict] | None = None,
        expected_total: Decimal | None = None,
    ) -> ExpenseClaim:
        claim = ExpenseService._owned_draft(db, claim_id, actor_id)
        if title is not None:
            if not title.strip():
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "claim title is required")
            claim.title = title.strip()
        if purpose is not None:
            claim.purpose = purpose.strip()
        if project_code is not None:
            claim.project_code = project_code.strip()
        if items is not None:
            actual = ExpenseService._replace_items(db, claim, items)
            if expected_total is not None and _money(expected_total) != actual:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "submitted total does not match item total")
        claim.version += 1
        return claim

    @staticmethod
    def delete_draft(db: Session, claim_id: str, actor_id: str) -> None:
        claim = ExpenseService._owned_draft(db, claim_id, actor_id)
        db.delete(claim)

    @staticmethod
    def submit(db: Session, claim_id: str, actor_id: str, idempotency_key: str) -> ExpenseClaim:
        claim = db.get(ExpenseClaim, claim_id)
        if claim is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "expense claim not found")
        if claim.requester_id != actor_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "only requester can submit this claim")
        if claim.submission_key == idempotency_key and claim.approval_instance_id:
            return claim
        if claim.status != "draft":
            raise HTTPException(status.HTTP_409_CONFLICT, "claim has already been submitted")
        if not idempotency_key.strip():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "idempotency key is required")
        if not claim.items:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "claim has no expense items")
        instance = WorkflowService.start(
            db,
            "expense_claim",
            claim.id,
            actor_id,
            "expense_reimbursement_v1",
        )
        claim.approval_instance_id = instance.id
        claim.submission_key = idempotency_key
        claim.status = "pending_approval"
        claim.submitted_at = datetime.now(UTC)
        claim.version += 1
        AuditService.record(
            db,
            actor_id,
            "expense.submit",
            "expense_claim",
            claim.id,
            {"status": "draft"},
            {"status": claim.status, "total_amount": claim.total_amount},
        )
        db.flush()
        return claim

    @staticmethod
    def can_view(db: Session, claim: ExpenseClaim, actor_id: str) -> bool:
        """Use the same predicate as bounded list reads for one claim."""
        return (
            db.query(ExpenseClaim.id)
            .filter(
                ExpenseClaim.id == claim.id,
                ExpenseService.visibility_predicate(db, actor_id),
            )
            .first()
            is not None
        )

    @staticmethod
    def visibility_predicate(db: Session, actor_id: str):
        """Return the canonical SQL visibility policy for expense claims.

        Callers can apply this predicate to a bounded list query; ``can_view``
        uses it for a single record so both paths cannot drift.
        """
        actor = db.get(User, actor_id)
        requester_owns_claim = ExpenseClaim.requester_id == actor_id
        if actor is None:
            return requester_owns_claim
        if actor.role == "admin":
            return true()
        requester_reports_to_actor = ExpenseClaim.requester_id.in_(
            select(EmployeeProfile.user_id).where(EmployeeProfile.manager_id == actor_id)
        )
        privileged_role_scope = exists().where(
            UserRole.user_id == actor_id,
            UserRole.role.in_(("hr", "finance")),
            or_(
                UserRole.department_id.is_(None),
                UserRole.department_id == ExpenseClaim.department_id,
            ),
        )
        return or_(requester_owns_claim, requester_reports_to_actor, privileged_role_scope)

    @staticmethod
    def _is_finance(db: Session, actor_id: str, department_id: str | None) -> bool:
        actor = db.get(User, actor_id)
        if actor and actor.role == "admin":
            return True
        query = db.query(UserRole).filter(UserRole.user_id == actor_id, UserRole.role == "finance")
        if department_id:
            query = query.filter(
                (UserRole.department_id == department_id) | UserRole.department_id.is_(None)
            )
        return query.first() is not None

    @staticmethod
    def pay(
        db: Session,
        claim_id: str,
        actor_id: str,
        payment: dict,
        idempotency_key: str,
        expected_version: int,
    ) -> PaymentRecord:
        claim = db.get(ExpenseClaim, claim_id)
        if claim is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "expense claim not found")
        if not ExpenseService._is_finance(db, actor_id, claim.department_id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "finance role required")
        existing = (
            db.query(PaymentRecord)
            .filter(PaymentRecord.idempotency_key == idempotency_key)
            .one_or_none()
        )
        if existing:
            if existing.claim_id != claim.id:
                raise HTTPException(status.HTTP_409_CONFLICT, "payment key belongs to another claim")
            return existing
        if claim.version != expected_version:
            raise HTTPException(status.HTTP_409_CONFLICT, "expense claim version is stale")
        if claim.status != "payment_pending":
            raise HTTPException(status.HTTP_409_CONFLICT, "claim is not ready for payment")
        payment_date = payment.get("payment_date")
        if isinstance(payment_date, str):
            payment_date = date.fromisoformat(payment_date)
        if not isinstance(payment_date, date):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "payment date is required")
        method = str(payment.get("method", "")).strip()
        if not method:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "payment method is required")
        record = PaymentRecord(
            claim_id=claim.id,
            paid_by=actor_id,
            amount=claim.total_amount,
            currency=claim.currency,
            method=method,
            reference=str(payment.get("reference", "")).strip(),
            payment_date=payment_date,
            idempotency_key=idempotency_key,
        )
        db.add(record)
        claim.status = "paid"
        claim.version += 1
        payroll_run = db.query(PayrollRun).filter(PayrollRun.expense_claim_id == claim.id).one_or_none()
        if payroll_run is not None:
            payroll_run.status = "paid"
        AuditService.record(
            db,
            actor_id,
            "expense.pay",
            "expense_claim",
            claim.id,
            {"status": "payment_pending"},
            {"status": "paid", "payment_reference": record.reference},
        )
        db.add(
            Notification(
                recipient_id=claim.requester_id,
                kind="expense_paid",
                content=f"报销单 {claim.claim_no} 已付款",
                expense_claim_id=claim.id,
            )
        )
        db.flush()
        return record

    @staticmethod
    def sync_from_approval(db: Session, instance: ApprovalInstance) -> None:
        if instance.entity_type != "expense_claim":
            return
        claim = db.get(ExpenseClaim, instance.entity_id)
        if claim is None:
            return
        next_status = {
            "pending_approval": "pending_approval",
            "approved": "payment_pending",
            "rejected": "rejected",
            "cancelled": "cancelled",
        }[instance.status]
        if claim.status != next_status:
            claim.status = next_status
            claim.version += 1

    @staticmethod
    def store_attachment(
        db: Session,
        claim_id: str,
        actor_id: str,
        *,
        original_name: str,
        content_type: str,
        content: bytes,
    ) -> ExpenseAttachment:
        claim = ExpenseService._owned_draft(db, claim_id, actor_id)
        settings = get_settings()
        if content_type not in ALLOWED_UPLOAD_TYPES:
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "unsupported receipt file type")
        if not content or len(content) > settings.expense_upload_max_bytes:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "receipt must be between 1 byte and 10 MB")
        storage_root = Path(settings.expense_storage_root)
        storage_root.mkdir(parents=True, exist_ok=True)
        storage_key = f"{uuid.uuid4().hex}{ALLOWED_UPLOAD_TYPES[content_type]}"
        target = storage_root / storage_key
        target.write_bytes(content)
        asset = FileAsset(
            owner_id=actor_id,
            storage_key=storage_key,
            original_name=Path(original_name).name[:255] or "receipt",
            content_type=content_type,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        )
        db.add(asset)
        db.flush()
        attachment = ExpenseAttachment(claim_id=claim.id, file_id=asset.id)
        db.add(attachment)
        db.flush()
        return attachment
