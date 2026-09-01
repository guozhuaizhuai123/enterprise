from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import Principal, get_current_principal, require_admin
from app.models import (
    AttendanceRecord,
    Department,
    HolidayPeriod,
    LeaveRequest,
    User,
    UserDepartment,
)
from app.schedule.service import (
    AttendanceConflictError,
    AttendanceValidationError,
    HolidayConflictError,
    HolidayValidationError,
    LeaveConflictError,
    LeaveReviewError,
    ScheduleValidationError,
    build_attendance_history,
    create_attendance_once,
    create_holiday,
    create_leave_request,
    delete_attendance,
    delete_holiday,
    get_schedule,
    list_applicable_holidays,
    replace_schedule,
    review_leave_request,
    upsert_attendance,
)
from app.assistant.form_previews import preview_form
from app.schemas import (
    AttendanceHistoryOut,
    AttendanceRecordOut,
    AttendanceUpdate,
    EmployeeWorkScheduleOut,
    HolidayCreate,
    HolidayOut,
    LeavePreviewIn,
    LeavePreviewOut,
    LeaveRequestCreate,
    LeaveRequestOut,
    LeaveRequestReview,
    MyWorkScheduleOut,
    ScheduleDayOut,
    WorkScheduleUpdate,
)


me_router = APIRouter(prefix="/me", tags=["work-schedule"])
admin_router = APIRouter(
    prefix="/admin",
    tags=["admin-work-schedule"],
    dependencies=[Depends(require_admin)],
)


def _leave_out(request: LeaveRequest, username: str = "") -> LeaveRequestOut:
    return LeaveRequestOut(
        id=request.id,
        user_id=request.user_id,
        username=username or (request.user.username if request.user else ""),
        leave_type=request.leave_type,
        start_date=request.start_date,
        end_date=request.end_date,
        reason=request.reason,
        status=request.status,
        reviewed_by=request.reviewed_by,
        reviewed_at=request.reviewed_at,
        created_at=request.created_at,
    )


def _holiday_out(holiday: HolidayPeriod) -> HolidayOut:
    return HolidayOut(
        id=holiday.id,
        name=holiday.name,
        scope_type=holiday.scope_type,
        department_id=holiday.department_id,
        department_name=holiday.department.name if holiday.department else "",
        start_date=holiday.start_date,
        end_date=holiday.end_date,
        description=holiday.description,
        created_by=holiday.created_by,
        created_at=holiday.created_at,
        updated_at=holiday.updated_at,
    )


def _attendance_out(record: AttendanceRecord, username: str = "") -> AttendanceRecordOut:
    return AttendanceRecordOut(
        id=record.id,
        user_id=record.user_id,
        username=username or (record.user.username if record.user else ""),
        attendance_date=record.attendance_date,
        status=record.status,
        note=record.note,
        recorded_by=record.recorded_by,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _employee_or_404(db: Session, employee_id: str) -> User:
    user = db.get(User, employee_id)
    if user is None or user.role != "employee":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "employee not found")
    return user


def _employee_schedule_out(db: Session, employee: User) -> EmployeeWorkScheduleOut:
    return EmployeeWorkScheduleOut(
        user_id=employee.id,
        username=employee.username,
        days=[ScheduleDayOut.model_validate(day) for day in get_schedule(db, employee.id)],
    )


@me_router.get("/work-schedule", response_model=MyWorkScheduleOut)
def my_work_schedule(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    today = date.today()
    requests = (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.user_id == principal.user_id,
            LeaveRequest.status.in_(("pending", "approved")),
            LeaveRequest.end_date >= today,
        )
        .order_by(LeaveRequest.start_date, LeaveRequest.created_at)
        .all()
    )
    return MyWorkScheduleOut(
        days=[ScheduleDayOut.model_validate(day) for day in get_schedule(db, principal.user_id)],
        leave_requests=[_leave_out(request, principal.username) for request in requests],
        holidays=[
            _holiday_out(holiday)
            for holiday in list_applicable_holidays(
                db,
                principal.user_id,
                start_date=today,
            )
        ],
    )


@me_router.get("/attendance/today", response_model=AttendanceRecordOut | None)
def my_attendance_today(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    if principal.role != "employee":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "employee role required")
    record = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.user_id == principal.user_id,
            AttendanceRecord.attendance_date == date.today(),
        )
        .first()
    )
    return _attendance_out(record, principal.username) if record is not None else None


@me_router.post(
    "/attendance/today",
    response_model=AttendanceRecordOut,
    status_code=status.HTTP_201_CREATED,
)
def create_my_attendance_today(
    payload: AttendanceUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    if principal.role != "employee":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "employee role required")
    try:
        record = create_attendance_once(
            db,
            user_id=principal.user_id,
            attendance_date=date.today(),
            status=payload.status,
            note=payload.note,
        )
    except AttendanceConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except AttendanceValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return _attendance_out(record, principal.username)


@me_router.get("/attendance-history", response_model=AttendanceHistoryOut)
def my_attendance_history(
    year: int = Query(default_factory=lambda: date.today().year, ge=2000, le=9999),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    try:
        history = build_attendance_history(db, principal.user_id, year, date.today())
    except ScheduleValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return AttendanceHistoryOut(
        year=history.year,
        period_start=history.period_start,
        period_end=history.period_end,
        scheduled_work_days=history.scheduled_work_days,
        organization_holiday_days=history.organization_holiday_days,
        weekly_rest_days=history.weekly_rest_days,
        approved_leave_days=history.approved_leave_days,
        expected_attendance_days=history.expected_attendance_days,
        recorded_attendance_days=history.recorded_attendance_days,
        unrecorded_attendance_days=history.unrecorded_attendance_days,
        present_days=history.present_days,
        late_days=history.late_days,
        absent_days=history.absent_days,
        remote_days=history.remote_days,
        attendance_rate=history.attendance_rate,
        leave_requests=[_leave_out(request, principal.username) for request in history.leave_requests],
        holidays=[_holiday_out(holiday) for holiday in history.holidays],
        attendance_records=[
            _attendance_out(record, principal.username) for record in history.attendance_records
        ],
    )


@me_router.get("/leave-requests", response_model=list[LeaveRequestOut])
def my_leave_requests(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    requests = (
        db.query(LeaveRequest)
        .filter(LeaveRequest.user_id == principal.user_id)
        .order_by(LeaveRequest.created_at.desc())
        .all()
    )
    return [_leave_out(request, principal.username) for request in requests]


@me_router.post("/leave-preview", response_model=LeavePreviewOut)
def leave_preview(
    payload: LeavePreviewIn,
    principal: Principal = Depends(get_current_principal),
):
    del principal
    return LeavePreviewOut.model_validate(preview_form("leave", payload.text, payload.today or date.today()))


@me_router.post(
    "/leave-requests",
    response_model=LeaveRequestOut,
    status_code=status.HTTP_201_CREATED,
)
def submit_leave_request(
    payload: LeaveRequestCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    try:
        request = create_leave_request(
            db,
            user_id=principal.user_id,
            leave_type=payload.leave_type,
            start_date=payload.start_date,
            end_date=payload.end_date,
            reason=payload.reason,
        )
    except LeaveConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except ScheduleValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return _leave_out(request, principal.username)


@admin_router.get(
    "/departments/{department_id}/work-schedules",
    response_model=list[EmployeeWorkScheduleOut],
)
def department_work_schedules(department_id: str, db: Session = Depends(get_db)):
    if db.get(Department, department_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "department not found")
    employees = (
        db.query(User)
        .join(UserDepartment, UserDepartment.user_id == User.id)
        .filter(UserDepartment.department_id == department_id, User.role == "employee")
        .order_by(User.username)
        .all()
    )
    return [
        _employee_schedule_out(db, employee)
        for employee in employees
    ]


@admin_router.get("/work-schedules", response_model=list[EmployeeWorkScheduleOut])
def all_work_schedules(db: Session = Depends(get_db)):
    employees = db.query(User).filter(User.role == "employee").order_by(User.username).all()
    return [_employee_schedule_out(db, employee) for employee in employees]


@admin_router.put(
    "/employees/{employee_id}/work-schedule",
    response_model=EmployeeWorkScheduleOut,
)
def update_employee_work_schedule(
    employee_id: str,
    payload: WorkScheduleUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_admin),
):
    employee = _employee_or_404(db, employee_id)
    try:
        days = replace_schedule(db, employee.id, payload.days, principal.user_id)
    except ScheduleValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return EmployeeWorkScheduleOut(
        user_id=employee.id,
        username=employee.username,
        days=[ScheduleDayOut.model_validate(day) for day in days],
    )


@admin_router.get(
    "/departments/{department_id}/leave-requests",
    response_model=list[LeaveRequestOut],
)
def department_leave_requests(department_id: str, db: Session = Depends(get_db)):
    if db.get(Department, department_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "department not found")
    requests = (
        db.query(LeaveRequest)
        .join(UserDepartment, UserDepartment.user_id == LeaveRequest.user_id)
        .filter(UserDepartment.department_id == department_id)
        .order_by(LeaveRequest.created_at.desc())
        .all()
    )
    return [_leave_out(request) for request in requests]


@admin_router.get("/leave-requests", response_model=list[LeaveRequestOut])
def all_leave_requests(db: Session = Depends(get_db)):
    requests = db.query(LeaveRequest).order_by(LeaveRequest.created_at.desc()).all()
    return [_leave_out(request) for request in requests]


@admin_router.get("/holidays", response_model=list[HolidayOut])
def list_holidays(
    department_id: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(HolidayPeriod)
    if department_id is not None:
        if db.get(Department, department_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "department not found")
        query = query.filter(
            or_(
                HolidayPeriod.scope_type == "company",
                HolidayPeriod.department_id == department_id,
            )
        )
    holidays = query.order_by(HolidayPeriod.start_date, HolidayPeriod.name).all()
    return [_holiday_out(holiday) for holiday in holidays]


@admin_router.post("/holidays", response_model=HolidayOut, status_code=status.HTTP_201_CREATED)
def add_holiday(
    payload: HolidayCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_admin),
):
    try:
        holiday = create_holiday(
            db,
            name=payload.name,
            scope_type=payload.scope_type,
            department_id=payload.department_id,
            start_date=payload.start_date,
            end_date=payload.end_date,
            description=payload.description,
            created_by=principal.user_id,
        )
    except HolidayConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except HolidayValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return _holiday_out(holiday)


@admin_router.delete("/holidays/{holiday_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_holiday(holiday_id: str, db: Session = Depends(get_db)):
    holiday = db.get(HolidayPeriod, holiday_id)
    if holiday is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "holiday not found")
    delete_holiday(db, holiday)


@admin_router.get("/attendance", response_model=list[AttendanceRecordOut])
def list_attendance(
    year: int = Query(default_factory=lambda: date.today().year, ge=2000, le=9999),
    department_id: str | None = None,
    db: Session = Depends(get_db),
):
    if year > date.today().year:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "future attendance year is not allowed")
    query = (
        db.query(AttendanceRecord)
        .join(User, User.id == AttendanceRecord.user_id)
        .filter(
            AttendanceRecord.attendance_date >= date(year, 1, 1),
            AttendanceRecord.attendance_date <= date(year, 12, 31),
            User.role == "employee",
        )
    )
    if department_id is not None:
        if db.get(Department, department_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "department not found")
        query = query.join(UserDepartment, UserDepartment.user_id == User.id).filter(
            UserDepartment.department_id == department_id
        )
    records = query.order_by(AttendanceRecord.attendance_date.desc(), User.username).all()
    return [_attendance_out(record) for record in records]


@admin_router.put(
    "/employees/{employee_id}/attendance/{attendance_date}",
    response_model=AttendanceRecordOut,
)
def save_employee_attendance(
    employee_id: str,
    attendance_date: date,
    payload: AttendanceUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_admin),
):
    employee = _employee_or_404(db, employee_id)
    if attendance_date > date.today():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "future attendance is not allowed")
    try:
        record = upsert_attendance(
            db,
            user_id=employee.id,
            attendance_date=attendance_date,
            status=payload.status,
            note=payload.note,
            recorded_by=principal.user_id,
        )
    except AttendanceValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return _attendance_out(record, employee.username)


@admin_router.delete(
    "/employees/{employee_id}/attendance/{attendance_date}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_employee_attendance(
    employee_id: str,
    attendance_date: date,
    db: Session = Depends(get_db),
):
    _employee_or_404(db, employee_id)
    record = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.user_id == employee_id,
            AttendanceRecord.attendance_date == attendance_date,
        )
        .first()
    )
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "attendance record not found")
    delete_attendance(db, record)


@admin_router.patch("/leave-requests/{request_id}", response_model=LeaveRequestOut)
def review_employee_leave_request(
    request_id: str,
    payload: LeaveRequestReview,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_admin),
):
    try:
        request = review_leave_request(
            db,
            request_id=request_id,
            status=payload.status,
            reviewed_by=principal.user_id,
        )
    except LeaveReviewError as exc:
        message = str(exc)
        code = status.HTTP_404_NOT_FOUND if message == "leave request not found" else status.HTTP_409_CONFLICT
        raise HTTPException(code, message) from exc
    return _leave_out(request)
