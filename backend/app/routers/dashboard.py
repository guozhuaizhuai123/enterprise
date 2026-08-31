from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.dashboard.service import DashboardService
from app.db import get_db
from app.deps import Principal, get_current_principal
from app.schemas import DashboardOverviewOut


router = APIRouter(prefix="/admin/dashboard", tags=["dashboard"])


def _period(
    start: date | None,
    end: date | None,
) -> tuple[date, date]:
    today = date.today()
    return start or today.replace(day=1), end or today


@router.get("/overview", response_model=DashboardOverviewOut)
def overview(
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    department_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    period_start, period_end = _period(start, end)
    return DashboardService.overview(db, principal, period_start, period_end, department_id)


@router.get("/expenses")
def expense_metrics(
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    department_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    period_start, period_end = _period(start, end)
    result = DashboardService.overview(db, principal, period_start, period_end, department_id)
    return {
        "period_start": result["period_start"],
        "period_end": result["period_end"],
        "timezone": result["timezone"],
        "expenses": result["expenses"],
        "monthly_expenses": result["monthly_expenses"],
    }


@router.get("/approvals")
def approval_metrics(
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    department_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    period_start, period_end = _period(start, end)
    result = DashboardService.overview(db, principal, period_start, period_end, department_id)
    return {
        "period_start": result["period_start"],
        "period_end": result["period_end"],
        "timezone": result["timezone"],
        "approvals": result["approvals"],
    }
