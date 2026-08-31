from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import Principal, get_current_principal
from app.models import EmployeeProfile, User, UserDepartment, UserRole
from app.schemas import DepartmentMembershipOut, LoginRequest, LoginResponse, MeOut
from app.security import create_access_token, decrypt_password, hash_password, is_hashed_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def _roles(db: Session, user: User) -> list[str]:
    return list(
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


def _memberships(db: Session, user_id: str) -> list[DepartmentMembershipOut]:
    rows = (
        db.query(UserDepartment)
        .filter(UserDepartment.user_id == user_id)
        .order_by(UserDepartment.department_id)
        .all()
    )
    return [
        DepartmentMembershipOut(
            id=row.department.id,
            name=row.department.name,
            position=row.position,
            access_level=row.access_level,
        )
        for row in rows
    ]


@router.get("/me", response_model=MeOut)
def me(db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    """返回当前令牌对应的用户信息；令牌失效时返回 401。

    前端切换已保存账号时用该接口判断会话是否仍然有效。
    """
    return MeOut(
        user_id=principal.user_id,
        username=principal.username,
        role=principal.role,
        department_id=principal.department_id,
        departments=_memberships(db, principal.user_id),
        roles=_roles(db, db.get(User, principal.user_id)),
    )


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid username or password")
    profile = db.get(EmployeeProfile, user.id)
    if profile is not None and profile.status in {"suspended", "terminated"}:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user account is inactive")
    password_matches = verify_password(payload.password, user.password_encrypted)
    legacy_password = False
    if not password_matches and not is_hashed_password(user.password_encrypted):
        try:
            password_matches = decrypt_password(user.password_encrypted) == payload.password
            legacy_password = password_matches
        except ValueError as exc:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "server key misconfigured") from exc
    if not password_matches:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid username or password")

    if legacy_password:
        user.password_encrypted = hash_password(payload.password)
        db.commit()

    token = create_access_token(
        user_id=user.id, username=user.username, role=user.role
    )
    return LoginResponse(
        access_token=token,
        user_id=user.id,
        role=user.role,
        department_id=user.department_id,
        departments=_memberships(db, user.id),
        roles=_roles(db, user),
        username=user.username,
    )
