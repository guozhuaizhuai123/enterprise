from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.assistant.form_previews import preview_form
from app.config import get_settings
from app.db import get_db
from app.deps import Principal, get_current_principal
from app.expense.service import ExpenseService
from app.models import Department, ExpenseAttachment, ExpenseClaim, FileAsset, User
from app.schemas import (
    ExpenseAttachmentOut,
    ExpenseClaimCreate,
    ExpenseClaimOut,
    ExpenseClaimUpdate,
    ExpenseItemOut,
    ExpensePreviewIn,
    ExpensePreviewOut,
    ExpenseSubmitIn,
    PaymentCreate,
    PaymentOut,
)


router = APIRouter(prefix="/expenses", tags=["expenses"])
admin_router = APIRouter(prefix="/admin/expenses", tags=["expense-finance"])


def _attachment_out(attachment: ExpenseAttachment) -> ExpenseAttachmentOut:
    asset = attachment.file
    return ExpenseAttachmentOut(
        id=attachment.id,
        file_id=asset.id,
        original_name=asset.original_name,
        content_type=asset.content_type,
        size_bytes=asset.size_bytes,
        sha256=asset.sha256,
        created_at=attachment.created_at,
    )


def _claim_out(db: Session, claim: ExpenseClaim) -> ExpenseClaimOut:
    requester = db.get(User, claim.requester_id)
    department = db.get(Department, claim.department_id) if claim.department_id else None
    payment = claim.payment
    return ExpenseClaimOut(
        id=claim.id,
        claim_no=claim.claim_no,
        requester_id=claim.requester_id,
        requester_name=requester.username if requester else "",
        department_id=claim.department_id,
        department_name=department.name if department else "",
        title=claim.title,
        purpose=claim.purpose,
        project_code=claim.project_code,
        currency=claim.currency,
        total_amount=claim.total_amount,
        status=claim.status,
        approval_instance_id=claim.approval_instance_id,
        version=claim.version,
        submitted_at=claim.submitted_at,
        created_at=claim.created_at,
        updated_at=claim.updated_at,
        items=[
            ExpenseItemOut(
                id=item.id,
                expense_date=item.expense_date,
                category=item.category,
                description=item.description,
                vendor=item.vendor,
                invoice_no=item.invoice_no,
                amount=item.amount,
                tax_amount=item.tax_amount,
                sort_order=item.sort_order,
            )
            for item in claim.items
        ],
        attachments=[_attachment_out(item) for item in claim.attachments],
        payment=(
            PaymentOut(
                id=payment.id,
                paid_by=payment.paid_by,
                amount=payment.amount,
                currency=payment.currency,
                method=payment.method,
                reference=payment.reference,
                payment_date=payment.payment_date,
                created_at=payment.created_at,
            )
            if payment
            else None
        ),
    )


def _visible_claim(db: Session, claim_id: str, principal: Principal) -> ExpenseClaim:
    claim = db.get(ExpenseClaim, claim_id)
    if claim is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "expense claim not found")
    if not ExpenseService.can_view(db, claim, principal.user_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "expense claim is outside your scope")
    return claim


@router.get("", response_model=list[ExpenseClaimOut])
def my_expenses(
    db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)
):
    claims = (
        db.query(ExpenseClaim)
        .filter(ExpenseClaim.requester_id == principal.user_id)
        .order_by(ExpenseClaim.created_at.desc())
        .all()
    )
    return [_claim_out(db, claim) for claim in claims]


@router.post("/preview", response_model=ExpensePreviewOut)
def expense_preview(payload: ExpensePreviewIn):
    return ExpensePreviewOut.model_validate(preview_form("expense", payload.text))


@router.post("", response_model=ExpenseClaimOut, status_code=status.HTTP_201_CREATED)
def create_expense(
    payload: ExpenseClaimCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    claim = ExpenseService.create_draft(
        db,
        requester_id=principal.user_id,
        title=payload.title,
        purpose=payload.purpose,
        project_code=payload.project_code,
        currency=payload.currency,
        expected_total=payload.total_amount,
        items=[item.model_dump() for item in payload.items],
    )
    db.commit()
    db.refresh(claim)
    return _claim_out(db, claim)


@router.get("/{claim_id}", response_model=ExpenseClaimOut)
def get_expense(
    claim_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return _claim_out(db, _visible_claim(db, claim_id, principal))


@router.patch("/{claim_id}", response_model=ExpenseClaimOut)
def update_expense(
    claim_id: str,
    payload: ExpenseClaimUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    claim = ExpenseService.update_draft(
        db,
        claim_id,
        principal.user_id,
        title=payload.title,
        purpose=payload.purpose,
        project_code=payload.project_code,
        items=[item.model_dump() for item in payload.items] if payload.items is not None else None,
        expected_total=payload.total_amount,
    )
    db.commit()
    db.refresh(claim)
    return _claim_out(db, claim)


@router.delete("/{claim_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense(
    claim_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    ExpenseService.delete_draft(db, claim_id, principal.user_id)
    db.commit()


@router.post("/{claim_id}/submit", response_model=ExpenseClaimOut)
def submit_expense(
    claim_id: str,
    payload: ExpenseSubmitIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    claim = ExpenseService.submit(db, claim_id, principal.user_id, payload.idempotency_key)
    db.commit()
    db.refresh(claim)
    return _claim_out(db, claim)


@router.post("/{claim_id}/attachments", response_model=ExpenseAttachmentOut, status_code=status.HTTP_201_CREATED)
async def upload_receipt(
    claim_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    settings = get_settings()
    content = await file.read(settings.expense_upload_max_bytes + 1)
    attachment = ExpenseService.store_attachment(
        db,
        claim_id,
        principal.user_id,
        original_name=file.filename or "receipt",
        content_type=file.content_type or "application/octet-stream",
        content=content,
    )
    db.commit()
    db.refresh(attachment)
    return _attachment_out(attachment)


@router.get("/files/{file_id}/download")
def download_receipt(
    file_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    attachment = db.query(ExpenseAttachment).filter(ExpenseAttachment.file_id == file_id).first()
    if attachment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "receipt not found")
    _visible_claim(db, attachment.claim_id, principal)
    asset = db.get(FileAsset, file_id)
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "receipt not found")
    path = Path(get_settings().expense_storage_root) / asset.storage_key
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "receipt file is missing")
    return FileResponse(path, media_type=asset.content_type, filename=asset.original_name)


@admin_router.get("", response_model=list[ExpenseClaimOut])
def managed_expenses(
    db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)
):
    if not principal.has_role("admin", "hr", "manager", "finance"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "expense management role required")
    claims = db.query(ExpenseClaim).order_by(ExpenseClaim.created_at.desc()).all()
    return [
        _claim_out(db, claim)
        for claim in claims
        if ExpenseService.can_view(db, claim, principal.user_id)
    ]


@admin_router.post("/{claim_id}/pay", response_model=PaymentOut)
def pay_expense(
    claim_id: str,
    payload: PaymentCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    payment = ExpenseService.pay(
        db,
        claim_id,
        principal.user_id,
        payload.model_dump(exclude={"idempotency_key", "expected_version"}),
        payload.idempotency_key,
        payload.expected_version,
    )
    db.commit()
    db.refresh(payment)
    return PaymentOut.model_validate(payment, from_attributes=True)
