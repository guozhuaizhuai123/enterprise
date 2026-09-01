import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AttendanceRecord,
    Department,
    HolidayPeriod,
    LeaveRequest,
    UserDepartment,
    WorkScheduleDay,
)
from app.schemas import LeavePreviewOut, ScheduleDayInput


LEAVE_TYPES = ("年假", "病假", "事假", "调休", "婚假", "产假", "陪产假", "丧假", "其他")
ATTENDANCE_STATUSES = ("present", "late", "absent", "remote")


class ScheduleValidationError(ValueError):
    pass


class LeaveConflictError(ValueError):
    pass


class LeaveReviewError(ValueError):
    pass


class HolidayValidationError(ValueError):
    pass


class HolidayConflictError(ValueError):
    pass


class AttendanceValidationError(ValueError):
    pass


class AttendanceConflictError(ValueError):
    pass


@dataclass(frozen=True)
class AttendanceHistory:
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
    leave_requests: tuple[LeaveRequest, ...]
    holidays: tuple[HolidayPeriod, ...]
    attendance_records: tuple[AttendanceRecord, ...]


def create_holiday_in_transaction(
    db: Session,
    *,
    name: str,
    scope_type: str,
    department_id: str | None,
    start_date: date,
    end_date: date,
    description: str,
    created_by: str,
) -> HolidayPeriod:
    normalized_name = name.strip()
    if not normalized_name:
        raise HolidayValidationError("holiday name cannot be empty")
    if start_date > end_date:
        raise HolidayValidationError("holiday start date must not be after end date")
    if scope_type not in ("company", "department"):
        raise HolidayValidationError("invalid holiday scope")
    if scope_type == "company":
        if department_id is not None:
            raise HolidayValidationError("company holiday cannot have a department")
    elif department_id is None:
        raise HolidayValidationError("department holiday requires a department")
    elif db.get(Department, department_id) is None:
        raise HolidayValidationError("department not found")

    duplicate_query = db.query(HolidayPeriod).filter(
        HolidayPeriod.name == normalized_name,
        HolidayPeriod.scope_type == scope_type,
        HolidayPeriod.start_date == start_date,
        HolidayPeriod.end_date == end_date,
    )
    if department_id is None:
        duplicate_query = duplicate_query.filter(HolidayPeriod.department_id.is_(None))
    else:
        duplicate_query = duplicate_query.filter(HolidayPeriod.department_id == department_id)
    if duplicate_query.first() is not None:
        raise HolidayConflictError("holiday already exists")

    holiday = HolidayPeriod(
        name=normalized_name,
        scope_type=scope_type,
        department_id=department_id,
        start_date=start_date,
        end_date=end_date,
        description=description.strip(),
        created_by=created_by,
    )
    db.add(holiday)
    db.flush()
    return holiday


def create_holiday(
    db: Session,
    *,
    name: str,
    scope_type: str,
    department_id: str | None,
    start_date: date,
    end_date: date,
    description: str,
    created_by: str,
) -> HolidayPeriod:
    """Router-compatible holiday creation wrapper that owns its transaction."""
    holiday = create_holiday_in_transaction(
        db,
        name=name,
        scope_type=scope_type,
        department_id=department_id,
        start_date=start_date,
        end_date=end_date,
        description=description,
        created_by=created_by,
    )
    db.commit()
    db.refresh(holiday)
    return holiday


def delete_holiday_in_transaction(db: Session, holiday: HolidayPeriod) -> None:
    db.delete(holiday)


def delete_holiday(db: Session, holiday: HolidayPeriod) -> None:
    """Router-compatible holiday deletion wrapper that owns its transaction."""
    delete_holiday_in_transaction(db, holiday)
    db.commit()


def upsert_attendance_in_transaction(
    db: Session,
    *,
    user_id: str,
    attendance_date: date,
    status: str,
    note: str,
    recorded_by: str,
) -> AttendanceRecord:
    if status not in ATTENDANCE_STATUSES:
        raise AttendanceValidationError("invalid attendance status")
    record = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.user_id == user_id,
            AttendanceRecord.attendance_date == attendance_date,
        )
        .first()
    )
    if record is None:
        record = AttendanceRecord(
            user_id=user_id,
            attendance_date=attendance_date,
            status=status,
            note=note.strip(),
            recorded_by=recorded_by,
        )
        db.add(record)
    else:
        record.status = status
        record.note = note.strip()
        record.recorded_by = recorded_by
    db.flush()
    return record


def upsert_attendance(
    db: Session,
    *,
    user_id: str,
    attendance_date: date,
    status: str,
    note: str,
    recorded_by: str,
) -> AttendanceRecord:
    """Router-compatible attendance save wrapper that owns its transaction."""
    record = upsert_attendance_in_transaction(
        db,
        user_id=user_id,
        attendance_date=attendance_date,
        status=status,
        note=note,
        recorded_by=recorded_by,
    )
    db.commit()
    db.refresh(record)
    return record


def create_attendance_once(
    db: Session,
    *,
    user_id: str,
    attendance_date: date,
    status: str,
    note: str,
) -> AttendanceRecord:
    if status not in ATTENDANCE_STATUSES:
        raise AttendanceValidationError("invalid attendance status")
    existing = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.user_id == user_id,
            AttendanceRecord.attendance_date == attendance_date,
        )
        .first()
    )
    if existing is not None:
        raise AttendanceConflictError("attendance already exists")

    record = AttendanceRecord(
        user_id=user_id,
        attendance_date=attendance_date,
        status=status,
        note=note.strip(),
        recorded_by=user_id,
    )
    db.add(record)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AttendanceConflictError("attendance already exists") from exc
    db.refresh(record)
    return record


def delete_attendance_in_transaction(db: Session, record: AttendanceRecord) -> None:
    db.delete(record)


def delete_attendance(db: Session, record: AttendanceRecord) -> None:
    """Router-compatible attendance deletion wrapper that owns its transaction."""
    delete_attendance_in_transaction(db, record)
    db.commit()


def list_applicable_holidays(
    db: Session,
    user_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[HolidayPeriod]:
    department_ids = [
        row.department_id
        for row in db.query(UserDepartment)
        .filter(UserDepartment.user_id == user_id)
        .all()
    ]
    scope_filter = HolidayPeriod.scope_type == "company"
    if department_ids:
        scope_filter = or_(
            scope_filter,
            HolidayPeriod.department_id.in_(department_ids),
        )
    query = db.query(HolidayPeriod).filter(scope_filter)
    if start_date is not None:
        query = query.filter(HolidayPeriod.end_date >= start_date)
    if end_date is not None:
        query = query.filter(HolidayPeriod.start_date <= end_date)
    return query.order_by(HolidayPeriod.start_date, HolidayPeriod.name, HolidayPeriod.id).all()


def build_attendance_history(
    db: Session,
    user_id: str,
    year: int,
    today: date,
) -> AttendanceHistory:
    if year > today.year:
        raise ScheduleValidationError("future attendance year is not allowed")
    period_start = date(year, 1, 1)
    period_end = today if year == today.year else date(year, 12, 31)
    dates = tuple(_date_range(period_start, period_end))
    enabled_weekdays = {day.weekday for day in get_schedule(db, user_id) if day.enabled}
    weekly_rest_dates = {day for day in dates if day.isoweekday() not in enabled_weekdays}
    scheduled_dates_before_holidays = {
        day for day in dates if day.isoweekday() in enabled_weekdays
    }

    holidays = list_applicable_holidays(db, user_id, period_start, period_end)
    holiday_dates: set[date] = set()
    for holiday in holidays:
        clipped_start = max(holiday.start_date, period_start)
        clipped_end = min(holiday.end_date, period_end)
        holiday_dates.update(_date_range(clipped_start, clipped_end))
    organization_holiday_dates = scheduled_dates_before_holidays & holiday_dates
    scheduled_work_dates = scheduled_dates_before_holidays - holiday_dates

    leave_requests = (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.user_id == user_id,
            LeaveRequest.start_date <= period_end,
            LeaveRequest.end_date >= period_start,
        )
        .order_by(LeaveRequest.start_date, LeaveRequest.created_at, LeaveRequest.id)
        .all()
    )
    approved_leave_dates: set[date] = set()
    for request in leave_requests:
        if request.status != "approved":
            continue
        clipped_start = max(request.start_date, period_start)
        clipped_end = min(request.end_date, period_end)
        approved_leave_dates.update(_date_range(clipped_start, clipped_end))
    approved_leave_dates &= scheduled_work_dates
    expected_attendance_dates = scheduled_work_dates - approved_leave_dates

    all_attendance_records = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.user_id == user_id,
            AttendanceRecord.attendance_date >= period_start,
            AttendanceRecord.attendance_date <= period_end,
        )
        .order_by(AttendanceRecord.attendance_date, AttendanceRecord.id)
        .all()
    )
    attendance_records = tuple(all_attendance_records)
    status_counts = {
        status: sum(record.status == status for record in attendance_records)
        for status in ("present", "late", "absent", "remote")
    }
    recorded_days = len(attendance_records)
    total_recorded_days = len(attendance_records)
    attended_days = status_counts["present"] + status_counts["late"] + status_counts["remote"]

    return AttendanceHistory(
        year=year,
        period_start=period_start,
        period_end=period_end,
        scheduled_work_days=len(scheduled_work_dates),
        organization_holiday_days=len(organization_holiday_dates),
        weekly_rest_days=len(weekly_rest_dates),
        approved_leave_days=len(approved_leave_dates),
        expected_attendance_days=len(expected_attendance_dates),
        recorded_attendance_days=recorded_days,
        unrecorded_attendance_days=max(0, len(expected_attendance_dates) - recorded_days),
        present_days=status_counts["present"],
        late_days=status_counts["late"],
        absent_days=status_counts["absent"],
        remote_days=status_counts["remote"],
        attendance_rate=(attended_days / total_recorded_days) if total_recorded_days else None,
        leave_requests=tuple(leave_requests),
        holidays=tuple(holidays),
        attendance_records=attendance_records,
    )


def _parse_leave_dates(text: str, today: date) -> tuple[date | None, date | None]:
    relative_dates = []
    for label, offset in (("今天", 0), ("明天", 1), ("后天", 2)):
        if label in text:
            relative_dates.append(today + timedelta(days=offset))
    if relative_dates:
        return relative_dates[0], relative_dates[-1]

    weekday_values = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7}
    weekday_matches = list(re.finditer(r"(下周|本周|这周|周|星期)([一二三四五六日天])", text))
    if weekday_matches:
        parsed_weekdays: list[date] = []
        for match in weekday_matches[:2]:
            prefix, label = match.groups()
            target_weekday = weekday_values[label]
            if prefix == "下周":
                offset = 7 - today.isoweekday() + target_weekday
            else:
                offset = (target_weekday - today.isoweekday()) % 7
            resolved = today + timedelta(days=offset)
            if parsed_weekdays and resolved < parsed_weekdays[0]:
                resolved += timedelta(days=7)
            parsed_weekdays.append(resolved)
        return parsed_weekdays[0], parsed_weekdays[-1]

    iso_matches = re.findall(r"(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})", text)
    if iso_matches:
        parsed = [date(int(year), int(month), int(day)) for year, month, day in iso_matches[:2]]
        return parsed[0], parsed[-1]

    same_month_range = re.search(
        r"(?:(20\d{2})年)?(\d{1,2})月(\d{1,2})日?(?:到|至|[-~—])(\d{1,2})日?",
        text,
    )
    if same_month_range:
        year, month, start_day, end_day = same_month_range.groups()
        resolved_year = int(year) if year else today.year
        return (
            date(resolved_year, int(month), int(start_day)),
            date(resolved_year, int(month), int(end_day)),
        )

    chinese_matches = re.findall(r"(?:(20\d{2})年)?(\d{1,2})月(\d{1,2})日?", text)
    if chinese_matches:
        parsed = [
            date(int(year) if year else today.year, int(month), int(day))
            for year, month, day in chinese_matches[:2]
        ]
        return parsed[0], parsed[-1]
    return None, None


def preview_leave(text: str, today: date) -> LeavePreviewOut:
    leave_type = next((name for name in LEAVE_TYPES if name != "其他" and name in text), None)
    if leave_type is None:
        inferred_types = (
            (("结婚", "婚礼"), "婚假"),
            (("生病", "看病", "就医", "医院"), "病假"),
            (("丧事", "葬礼"), "丧假"),
            (("生产", "待产"), "产假"),
        )
        leave_type = next(
            (resolved for keywords, resolved in inferred_types if any(keyword in text for keyword in keywords)),
            None,
        )
    policy_question = bool(re.search(r"制度|规定|政策|流程|怎么|如何|多久|多少|是否|最长|最少|销假", text))
    direct_request = bool(
        re.search(r"(?:帮我|替我|给我|我要|我想|我需要).{0,30}请(?:个|一下)?假", text)
        or re.search(r"(?:申请|请)(?:个|一下)?(?:年假|病假|事假|调休|婚假|产假|陪产假|丧假)", text)
        or re.search(r"(?:我要|我想|我需要).{0,30}(?:年假|病假|事假|调休|婚假|产假|陪产假|丧假)", text)
    )
    action_language = bool(
        direct_request
        or (re.search(r"请(?:个|一下)?假", text) and not policy_question)
    )
    if not action_language:
        return LeavePreviewOut(is_leave_request=False)
    start_date, end_date = _parse_leave_dates(text, today)
    return LeavePreviewOut(
        is_leave_request=True,
        leave_type=leave_type or "其他",
        start_date=start_date,
        end_date=end_date,
        reason=text.strip(),
    )


def _default_schedule(user_id: str) -> list[WorkScheduleDay]:
    return [
        WorkScheduleDay(
            user_id=user_id,
            weekday=weekday,
            enabled=weekday <= 5,
            start_time="09:00",
            end_time="18:00",
        )
        for weekday in range(1, 8)
    ]


def get_schedule(db: Session, user_id: str) -> list[WorkScheduleDay]:
    rows = (
        db.query(WorkScheduleDay)
        .filter(WorkScheduleDay.user_id == user_id)
        .order_by(WorkScheduleDay.weekday)
        .all()
    )
    return rows if len(rows) == 7 else _default_schedule(user_id)


def replace_schedule_in_transaction(
    db: Session,
    user_id: str,
    days: list[ScheduleDayInput],
    updated_by: str,
) -> list[WorkScheduleDay]:
    weekdays = [day.weekday for day in days]
    if len(days) != 7 or set(weekdays) != set(range(1, 8)):
        raise ScheduleValidationError("schedule must contain each weekday exactly once")
    if not any(day.enabled for day in days):
        raise ScheduleValidationError("schedule must contain at least one working day")
    if any(day.enabled and day.start_time >= day.end_time for day in days):
        raise ScheduleValidationError("start time must be before end time")

    db.query(WorkScheduleDay).filter(WorkScheduleDay.user_id == user_id).delete(
        synchronize_session=False
    )
    db.add_all(
        WorkScheduleDay(
            user_id=user_id,
            weekday=day.weekday,
            enabled=day.enabled,
            start_time=day.start_time,
            end_time=day.end_time,
            updated_by=updated_by,
        )
        for day in days
    )
    db.flush()
    return get_schedule(db, user_id)


def replace_schedule(
    db: Session,
    user_id: str,
    days: list[ScheduleDayInput],
    updated_by: str,
) -> list[WorkScheduleDay]:
    """Router-compatible schedule replacement wrapper that owns its transaction."""
    rows = replace_schedule_in_transaction(db, user_id, days, updated_by)
    db.commit()
    return rows


def _date_range(start_date: date, end_date: date):
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def _contains_working_day(db: Session, user_id: str, start_date: date, end_date: date) -> bool:
    enabled_weekdays = {day.weekday for day in get_schedule(db, user_id) if day.enabled}
    return any(day.isoweekday() in enabled_weekdays for day in _date_range(start_date, end_date))


def create_leave_request_in_transaction(
    db: Session,
    *,
    user_id: str,
    leave_type: str,
    start_date: date,
    end_date: date,
    reason: str,
) -> LeaveRequest:
    if leave_type not in LEAVE_TYPES:
        raise ScheduleValidationError("unsupported leave type")
    if start_date > end_date:
        raise ScheduleValidationError("start date must not be after end date")
    if not _contains_working_day(db, user_id, start_date, end_date):
        raise ScheduleValidationError("leave range contains no working day")
    conflict = (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.user_id == user_id,
            LeaveRequest.status.in_(("pending", "approved")),
            LeaveRequest.start_date <= end_date,
            LeaveRequest.end_date >= start_date,
        )
        .first()
    )
    if conflict is not None:
        raise LeaveConflictError("leave request overlaps an existing request")

    request = LeaveRequest(
        user_id=user_id,
        leave_type=leave_type,
        start_date=start_date,
        end_date=end_date,
        reason=reason.strip(),
    )
    db.add(request)
    db.flush()
    return request


def create_leave_request(
    db: Session,
    *,
    user_id: str,
    leave_type: str,
    start_date: date,
    end_date: date,
    reason: str,
) -> LeaveRequest:
    """Router-compatible leave-request wrapper that owns its transaction."""
    request = create_leave_request_in_transaction(
        db,
        user_id=user_id,
        leave_type=leave_type,
        start_date=start_date,
        end_date=end_date,
        reason=reason,
    )
    db.commit()
    db.refresh(request)
    return request


def review_leave_request_in_transaction(
    db: Session,
    *,
    request_id: str,
    status: str,
    reviewed_by: str,
) -> LeaveRequest:
    request = db.get(LeaveRequest, request_id)
    if request is None:
        raise LeaveReviewError("leave request not found")
    if request.status != "pending":
        raise LeaveReviewError("leave request has already been reviewed")
    if status not in ("approved", "rejected"):
        raise LeaveReviewError("invalid review status")
    request.status = status
    request.reviewed_by = reviewed_by
    request.reviewed_at = datetime.now(UTC)
    db.flush()
    return request


def review_leave_request(
    db: Session,
    *,
    request_id: str,
    status: str,
    reviewed_by: str,
) -> LeaveRequest:
    """Router-compatible leave-review wrapper that owns its transaction."""
    request = review_leave_request_in_transaction(
        db,
        request_id=request_id,
        status=status,
        reviewed_by=reviewed_by,
    )
    db.commit()
    db.refresh(request)
    return request
