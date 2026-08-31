from datetime import date

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import (
    Department,
    EmployeeProfile,
    EmploymentEvent,
    User,
    UserDepartment,
    UserRole,
)
from app.schemas import (
    AdminEmployeeCreate,
    AdminEmployeeUpdate,
    EmploymentEventCreate,
    OrgUnitCreate,
    OrgUnitUpdate,
)
from app.security import hash_password
from app.audit.service import AuditService


def _profile_snapshot(profile: EmployeeProfile) -> dict:
    return {
        "status": profile.status,
        "position": profile.position,
        "level": profile.level,
        "manager_id": profile.manager_id,
        "termination_date": profile.termination_date.isoformat() if profile.termination_date else None,
    }


class OrganizationService:
    @staticmethod
    def _department_or_404(db: Session, department_id: str) -> Department:
        department = db.get(Department, department_id)
        if department is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "organization unit not found")
        return department

    @staticmethod
    def _validate_manager(db: Session, manager_id: str | None, *, employee_id: str | None = None) -> None:
        if manager_id is None:
            return
        if manager_id == employee_id:
            raise HTTPException(status.HTTP_409_CONFLICT, "employee cannot manage themselves")
        manager = db.get(User, manager_id)
        profile = db.get(EmployeeProfile, manager_id)
        if manager is None or (profile is not None and profile.status in {"suspended", "terminated"}):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "manager is not active")

    @classmethod
    def create_org_unit(cls, db: Session, payload: OrgUnitCreate) -> Department:
        if db.query(Department).filter(Department.code == payload.code).first():
            raise HTTPException(status.HTTP_409_CONFLICT, "organization code already exists")
        if db.query(Department).filter(Department.name == payload.name).first():
            raise HTTPException(status.HTTP_409_CONFLICT, "organization name already exists")
        if payload.parent_id:
            cls._department_or_404(db, payload.parent_id)
        cls._validate_manager(db, payload.manager_id)
        department = Department(
            name=payload.name.strip(),
            code=payload.code.strip().upper(),
            parent_id=payload.parent_id,
            manager_id=payload.manager_id,
            active=True,
        )
        db.add(department)
        db.flush()
        return department

    @classmethod
    def update_org_unit(cls, db: Session, department: Department, payload: OrgUnitUpdate) -> Department:
        fields = payload.model_fields_set
        if "parent_id" in fields:
            parent_id = payload.parent_id
            if parent_id == department.id:
                raise HTTPException(status.HTTP_409_CONFLICT, "organization parent cycle")
            cursor = db.get(Department, parent_id) if parent_id else None
            while cursor is not None:
                if cursor.id == department.id:
                    raise HTTPException(status.HTTP_409_CONFLICT, "organization parent cycle")
                cursor = db.get(Department, cursor.parent_id) if cursor.parent_id else None
            department.parent_id = parent_id
        if "manager_id" in fields:
            cls._validate_manager(db, payload.manager_id)
            department.manager_id = payload.manager_id
        if payload.name is not None:
            duplicate = db.query(Department).filter(
                Department.name == payload.name.strip(), Department.id != department.id
            ).first()
            if duplicate:
                raise HTTPException(status.HTTP_409_CONFLICT, "organization name already exists")
            department.name = payload.name.strip()
        if payload.code is not None:
            code = payload.code.strip().upper()
            duplicate = db.query(Department).filter(
                Department.code == code, Department.id != department.id
            ).first()
            if duplicate:
                raise HTTPException(status.HTTP_409_CONFLICT, "organization code already exists")
            department.code = code
        if payload.active is not None:
            department.active = payload.active
        db.flush()
        return department

    @classmethod
    def _replace_memberships(
        cls,
        db: Session,
        user: User,
        department_ids: list[str],
        primary_department_id: str,
        position: str,
        joined_at: date | None,
    ) -> None:
        selected = list(dict.fromkeys(department_ids))
        if primary_department_id not in selected:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "primary department must be selected")
        departments = db.query(Department).filter(Department.id.in_(selected)).all()
        if len(departments) != len(selected) or any(not item.active for item in departments):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "one or more departments are unavailable")
        db.query(UserDepartment).filter(UserDepartment.user_id == user.id).delete(
            synchronize_session=False
        )
        for department_id in selected:
            db.add(
                UserDepartment(
                    user_id=user.id,
                    department_id=department_id,
                    position=position,
                    is_primary=department_id == primary_department_id,
                    joined_at=joined_at,
                )
            )
        user.department_id = primary_department_id

    @staticmethod
    def _replace_roles(db: Session, user: User, roles: list[str]) -> None:
        normalized = list(dict.fromkeys(["employee", *roles]))
        db.query(UserRole).filter(UserRole.user_id == user.id).delete(synchronize_session=False)
        for role in normalized:
            if role != user.role:
                db.add(UserRole(user_id=user.id, role=role, department_id=None))

    @classmethod
    def create_employee(cls, db: Session, payload: AdminEmployeeCreate) -> User:
        if db.query(User).filter(User.username == payload.username.strip()).first():
            raise HTTPException(status.HTTP_409_CONFLICT, "username already exists")
        cls._validate_manager(db, payload.manager_id)
        user = User(
            username=payload.username.strip(),
            password_encrypted=hash_password(payload.password),
            role="employee",
            department_id=payload.primary_department_id,
        )
        db.add(user)
        db.flush()
        profile = EmployeeProfile(
            user_id=user.id,
            full_name=payload.full_name.strip(),
            phone=payload.phone.strip(),
            email=payload.email.strip(),
            hire_date=payload.hire_date,
            status=payload.status,
            position=payload.position.strip(),
            level=payload.level.strip(),
            manager_id=payload.manager_id,
            salary=payload.salary.strip(),
        )
        db.add(profile)
        cls._replace_memberships(
            db,
            user,
            payload.department_ids,
            payload.primary_department_id,
            payload.position,
            payload.hire_date,
        )
        cls._replace_roles(db, user, payload.roles)
        db.add(
            EmploymentEvent(
                user_id=user.id,
                event_type="onboard",
                effective_date=payload.hire_date or date.today(),
                before_data={},
                after_data={"status": payload.status, "department_id": payload.primary_department_id},
                actor_id=None,
            )
        )
        db.flush()
        return user

    @classmethod
    def update_employee(
        cls, db: Session, user: User, payload: AdminEmployeeUpdate, actor_id: str
    ) -> EmployeeProfile:
        profile = db.get(EmployeeProfile, user.id)
        if profile is None:
            profile = EmployeeProfile(user_id=user.id, full_name=user.username, status="active")
            db.add(profile)
            db.flush()
        before = _profile_snapshot(profile)
        fields = payload.model_fields_set
        if "manager_id" in fields:
            cls._validate_manager(db, payload.manager_id, employee_id=user.id)
            profile.manager_id = payload.manager_id
        for field in (
            "full_name",
            "phone",
            "email",
            "hire_date",
            "termination_date",
            "status",
            "position",
            "level",
            "salary",
            "notes",
        ):
            if field in fields:
                setattr(profile, field, getattr(payload, field))
        if payload.department_ids is not None:
            primary_id = payload.primary_department_id or user.department_id
            if primary_id is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "primary department is required")
            cls._replace_memberships(
                db,
                user,
                payload.department_ids,
                primary_id,
                profile.position,
                profile.hire_date,
            )
        elif payload.primary_department_id is not None:
            memberships = [
                row.department_id
                for row in db.query(UserDepartment).filter(UserDepartment.user_id == user.id).all()
            ]
            cls._replace_memberships(
                db,
                user,
                memberships,
                payload.primary_department_id,
                profile.position,
                profile.hire_date,
            )
        if payload.roles is not None:
            cls._replace_roles(db, user, payload.roles)
        after = _profile_snapshot(profile)
        if before != after:
            db.add(
                EmploymentEvent(
                    user_id=user.id,
                    event_type="profile_update",
                    effective_date=date.today(),
                    before_data=before,
                    after_data=after,
                    actor_id=actor_id,
                )
            )
            AuditService.record(
                db,
                actor_id,
                "employee.update",
                "employee",
                user.id,
                before,
                after,
            )
        db.flush()
        return profile

    @classmethod
    def record_employment_event(
        cls,
        db: Session,
        user: User,
        payload: EmploymentEventCreate,
        actor_id: str,
    ) -> EmploymentEvent:
        profile = db.get(EmployeeProfile, user.id)
        if profile is None:
            profile = EmployeeProfile(user_id=user.id, full_name=user.username, status="active")
            db.add(profile)
            db.flush()
        before = _profile_snapshot(profile)
        if payload.manager_id is not None:
            cls._validate_manager(db, payload.manager_id, employee_id=user.id)
            profile.manager_id = payload.manager_id
        if payload.position is not None:
            profile.position = payload.position
        if payload.level is not None:
            profile.level = payload.level
        if payload.status is not None:
            profile.status = payload.status
        if payload.event_type == "offboard":
            profile.status = "terminated"
            profile.termination_date = payload.effective_date
            for membership in db.query(UserDepartment).filter(UserDepartment.user_id == user.id).all():
                membership.left_at = payload.effective_date
        if payload.department_ids is not None:
            primary_id = payload.primary_department_id or user.department_id
            if primary_id is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "primary department is required")
            cls._replace_memberships(
                db,
                user,
                payload.department_ids,
                primary_id,
                profile.position,
                profile.hire_date,
            )
        event = EmploymentEvent(
            user_id=user.id,
            event_type=payload.event_type,
            effective_date=payload.effective_date,
            before_data=before,
            after_data=_profile_snapshot(profile),
            actor_id=actor_id,
            note=payload.note,
        )
        db.add(event)
        db.flush()
        return event
