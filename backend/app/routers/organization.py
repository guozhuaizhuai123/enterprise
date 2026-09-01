from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.access import can_manage_employee
from app.db import get_db
from app.deps import Principal, get_current_principal
from app.models import Department, EmployeeProfile, User, UserDepartment, UserRole
from app.organization.service import OrganizationService
from app.schemas import (
    AdminEmployeeCreate,
    AdminEmployeeUpdate,
    EmploymentEventCreate,
    EmploymentEventOut,
    OrgEmployeeOut,
    OrgMembershipOut,
    OrgUnitCreate,
    OrgUnitOut,
    OrgUnitUpdate,
    PasswordResetIn,
)


admin_router = APIRouter(prefix="/admin", tags=["organization"])
me_router = APIRouter(prefix="/me", tags=["organization"])


def _require(principal: Principal, *roles: str) -> None:
    if not principal.has_role(*roles):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "insufficient organization permission")


def _org_out(department: Department, db: Session) -> OrgUnitOut:
    manager = db.get(User, department.manager_id) if department.manager_id else None
    manager_profile = db.get(EmployeeProfile, manager.id) if manager else None
    manager_name = manager_profile.full_name if manager_profile and manager_profile.full_name else (manager.username if manager else "")
    return OrgUnitOut(
        id=department.id,
        name=department.name,
        code=department.code,
        parent_id=department.parent_id,
        manager_id=department.manager_id,
        manager_name=manager_name,
        active=department.active,
        created_at=department.created_at,
        updated_at=department.updated_at,
    )


def _employee_out(db: Session, user: User) -> OrgEmployeeOut:
    profile = db.get(EmployeeProfile, user.id)
    if profile is None:
        profile = EmployeeProfile(user_id=user.id, full_name=user.username, status="active")
        db.add(profile)
        db.flush()
    memberships = (
        db.query(UserDepartment)
        .filter(UserDepartment.user_id == user.id)
        .order_by(UserDepartment.is_primary.desc(), UserDepartment.department_id)
        .all()
    )
    manager = db.get(User, profile.manager_id) if profile.manager_id else None
    manager_profile = db.get(EmployeeProfile, manager.id) if manager else None
    roles = list(
        dict.fromkeys(
            [user.role]
            + [
                row.role
                for row in db.query(UserRole)
                .filter(UserRole.user_id == user.id)
                .order_by(UserRole.role)
                .all()
            ]
        )
    )
    return OrgEmployeeOut(
        id=user.id,
        username=user.username,
        full_name=profile.full_name,
        phone=profile.phone,
        email=profile.email,
        hire_date=profile.hire_date,
        termination_date=profile.termination_date,
        status=profile.status,
        position=profile.position,
        level=profile.level,
        manager_id=profile.manager_id,
        manager_name=(manager_profile.full_name if manager_profile else manager.username if manager else ""),
        salary=profile.salary,
        notes=profile.notes,
        department_id=user.department_id,
        departments=[
            OrgMembershipOut(
                department_id=row.department_id,
                department_name=row.department.name,
                position=row.position,
                is_primary=row.is_primary,
                joined_at=row.joined_at,
                left_at=row.left_at,
            )
            for row in memberships
        ],
        roles=roles,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@admin_router.get("/org-units", response_model=list[OrgUnitOut])
def list_org_units(
    db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)
):
    _require(principal, "admin", "hr", "manager")
    return [_org_out(item, db) for item in db.query(Department).order_by(Department.name).all()]


@admin_router.post("/org-units", response_model=OrgUnitOut, status_code=status.HTTP_201_CREATED)
def create_org_unit(
    payload: OrgUnitCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _require(principal, "admin", "hr")
    department = OrganizationService.create_org_unit(db, payload)
    db.commit()
    db.refresh(department)
    return _org_out(department, db)


@admin_router.patch("/org-units/{department_id}", response_model=OrgUnitOut)
def update_org_unit(
    department_id: str,
    payload: OrgUnitUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _require(principal, "admin", "hr")
    department = OrganizationService._department_or_404(db, department_id)
    OrganizationService.update_org_unit(db, department, payload)
    db.commit()
    db.refresh(department)
    return _org_out(department, db)


@admin_router.get("/employees", response_model=list[OrgEmployeeOut])
def list_employees(
    department_id: str | None = Query(default=None),
    employee_status: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _require(principal, "admin", "hr", "manager")
    query = db.query(User).join(EmployeeProfile, EmployeeProfile.user_id == User.id)
    if principal.has_role("manager") and not principal.has_role("admin", "hr"):
        query = query.filter(EmployeeProfile.manager_id == principal.user_id)
    if department_id:
        query = query.join(UserDepartment, UserDepartment.user_id == User.id).filter(
            UserDepartment.department_id == department_id
        )
    if employee_status:
        query = query.filter(EmployeeProfile.status == employee_status)
    return [_employee_out(db, item) for item in query.order_by(User.username).all()]


@admin_router.post("/employees", response_model=OrgEmployeeOut, status_code=status.HTTP_201_CREATED)
def create_employee(
    payload: AdminEmployeeCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _require(principal, "admin", "hr")
    user = OrganizationService.create_employee(db, payload)
    db.commit()
    return _employee_out(db, user)


@admin_router.get("/employees/{employee_id}", response_model=OrgEmployeeOut)
def get_employee(
    employee_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    user = db.get(User, employee_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "employee not found")
    if not can_manage_employee(db, principal, employee_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "employee is outside management scope")
    return _employee_out(db, user)


@admin_router.patch("/employees/{employee_id}", response_model=OrgEmployeeOut)
def update_employee(
    employee_id: str,
    payload: AdminEmployeeUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    user = db.get(User, employee_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "employee not found")
    if not can_manage_employee(db, principal, employee_id, write=True):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "employee is outside management scope")
    OrganizationService.update_employee(db, user, payload, principal.user_id)
    db.commit()
    return _employee_out(db, user)


@admin_router.post(
    "/employees/{employee_id}/events",
    response_model=EmploymentEventOut,
    status_code=status.HTTP_201_CREATED,
)
def create_employment_event(
    employee_id: str,
    payload: EmploymentEventCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _require(principal, "admin", "hr")
    user = db.get(User, employee_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "employee not found")
    event = OrganizationService.record_employment_event(db, user, payload, principal.user_id)
    db.commit()
    db.refresh(event)
    return event


@admin_router.post("/employees/{employee_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_employee_password(
    employee_id: str,
    payload: PasswordResetIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _require(principal, "admin", "hr")
    user = db.get(User, employee_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "employee not found")
    OrganizationService.reset_employee_password(db, user, payload)
    db.commit()


@me_router.get("/profile", response_model=OrgEmployeeOut)
def get_my_profile(
    db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)
):
    user = db.get(User, principal.user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "employee not found")
    return _employee_out(db, user)
