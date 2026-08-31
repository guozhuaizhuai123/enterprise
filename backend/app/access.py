from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.deps import Principal
from app.models import Department, EmployeeProfile


def resolve_department_scope(
    allowed_department_ids: Iterable[str],
    requested_department_ids: Iterable[str] | None,
    *,
    is_root: bool = False,
    db: Session | None = None,
) -> tuple[str, ...]:
    allowed = tuple(dict.fromkeys(allowed_department_ids))
    if is_root:
        if db is None:
            raise ValueError("database session is required for root department scope")
        if requested_department_ids is None:
            return tuple(row.id for row in db.query(Department).order_by(Department.id).all())

        requested = tuple(sorted(dict.fromkeys(requested_department_ids)))
        if not requested:
            raise PermissionError("requested department is not accessible")
        existing = {
            row.id
            for row in db.query(Department.id).filter(Department.id.in_(requested)).all()
        }
        if set(requested) != existing:
            raise PermissionError("requested department is not accessible")
        return requested

    if not allowed:
        raise ValueError("user has no department memberships")
    if requested_department_ids is None:
        return allowed

    requested = tuple(dict.fromkeys(requested_department_ids))
    if not requested or not set(requested).issubset(allowed):
        raise PermissionError("requested department is not accessible")
    return requested


def can_manage_employee(
    db: Session, principal: Principal, employee_id: str, *, write: bool = False
) -> bool:
    if principal.has_role("admin", "hr"):
        return True
    if principal.has_role("manager"):
        profile = db.get(EmployeeProfile, employee_id)
        return profile is not None and profile.manager_id == principal.user_id
    return False
