from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.db import get_db
from app.models import EmployeeProfile, User, UserDepartment, UserRole
from app.security import decode_access_token
from sqlalchemy.orm import Session

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class Principal:
    user_id: str
    username: str
    role: str
    department_id: str | None
    department_ids: tuple[str, ...]
    roles: tuple[str, ...] = ()

    def has_role(self, *roles: str) -> bool:
        effective = set(self.roles) | {self.role}
        return bool(effective.intersection(roles))


def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Principal:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token") from exc
    user = db.get(User, payload["sub"])
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found")
    profile = db.get(EmployeeProfile, user.id)
    if profile is not None and profile.status in {"suspended", "terminated"}:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user account is inactive")
    department_ids = tuple(
        row.department_id
        for row in db.query(UserDepartment)
        .filter(UserDepartment.user_id == user.id)
        .order_by(UserDepartment.department_id)
        .all()
    )
    if not department_ids and user.department_id is not None:
        department_ids = (user.department_id,)
    assigned_roles = tuple(
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
    return Principal(
        user_id=user.id,
        username=user.username,
        role=user.role,
        department_id=user.department_id,
        department_ids=department_ids,
        roles=assigned_roles,
    )


def require_admin(principal: Principal = Depends(get_current_principal)) -> Principal:
    if principal.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin role required")
    return principal


def require_role(*allowed_roles: str):
    def dependency(principal: Principal = Depends(get_current_principal)) -> Principal:
        if not principal.has_role(*allowed_roles):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "required role: " + ", ".join(allowed_roles),
            )
        return principal

    return dependency
