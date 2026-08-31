from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import Principal, get_current_principal, require_admin
from app.models import PayrollLine, PayrollRun
from app.payroll.service import PayrollService
from app.schemas import PayrollGenerateIn, PayrollLineOut, PayrollRunOut, PayrollSettingOut, PayrollSettingUpdate

router = APIRouter(prefix="/admin/payroll", tags=["payroll"], dependencies=[Depends(require_admin)])


def _run_out(run: PayrollRun) -> PayrollRunOut:
    return PayrollRunOut(
        id=run.id,
        period=run.period,
        pay_date=run.pay_date,
        generation_date=run.generation_date,
        status=run.status,
        expense_claim_id=run.expense_claim_id,
        total_amount=run.total_amount,
        generated_at=run.generated_at,
        created_at=run.created_at,
        lines=[PayrollLineOut.model_validate(line, from_attributes=True) for line in run.lines],
    )


@router.get("/settings", response_model=PayrollSettingOut)
def get_payroll_settings(db: Session = Depends(get_db)):
    return PayrollService.get_settings(db)


@router.put("/settings", response_model=PayrollSettingOut)
def update_payroll_settings(
    payload: PayrollSettingUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    setting = PayrollService.update_settings(db, payload.model_dump(), principal.user_id)
    db.commit()
    db.refresh(setting)
    return setting


@router.get("/runs", response_model=list[PayrollRunOut])
def list_payroll_runs(db: Session = Depends(get_db)):
    return db.query(PayrollRun).order_by(PayrollRun.period.desc()).limit(24).all()


@router.post("/generate", response_model=PayrollRunOut, status_code=status.HTTP_201_CREATED)
def generate_payroll(
    payload: PayrollGenerateIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    run = PayrollService.generate_run(db, principal.user_id, period=payload.period)
    if run is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "当前尚未达到工资账单生成时间")
    db.commit()
    db.refresh(run)
    return run
