import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.deps import Principal
from app.models import AuditLog, User


SECRET_FRAGMENTS = ("password", "secret", "token", "api_key", "apikey", "authorization")


def _safe(value: Any, key: str = "") -> Any:
    lowered = key.lower()
    if any(fragment in lowered for fragment in SECRET_FRAGMENTS):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(item_key): _safe(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class AuditService:
    @staticmethod
    def record(
        db: Session,
        principal: Principal | str | None,
        action: str,
        entity_type: str,
        entity_id: str,
        before: dict | None = None,
        after: dict | None = None,
        request_id: str | None = None,
    ) -> AuditLog:
        actor_id = principal.user_id if isinstance(principal, Principal) else principal
        department_id = principal.department_id if isinstance(principal, Principal) else None
        if actor_id and department_id is None:
            actor = db.get(User, actor_id)
            department_id = actor.department_id if actor else None
        row = AuditLog(
            actor_id=actor_id,
            department_id=department_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before_data=_safe(before or {}),
            after_data=_safe(after or {}),
            request_id=request_id or str(uuid.uuid4()),
        )
        db.add(row)
        db.flush()
        return row
