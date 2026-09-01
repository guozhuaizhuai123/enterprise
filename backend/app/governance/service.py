"""Shared sensitive-keyword, event and department-memory mutations."""

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.deps import Principal
from app.models import Department, DepartmentMemory, SensitiveEvent, SensitiveKeyword
from app.schemas import MemoryCreate, MemoryUpdate, SensitiveKeywordCreate, SensitiveKeywordUpdate


class GovernanceService:
    @staticmethod
    def _require_admin(principal: Principal) -> None:
        if not principal.has_role("admin"):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "admin role required")

    @staticmethod
    def _trim_memory_values(title: str | None, content: str | None) -> tuple[str | None, str | None]:
        normalized_title = title.strip() if title is not None else None
        normalized_content = content.strip() if content is not None else None
        if normalized_title == "" or normalized_content == "":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "memory title and content cannot be empty")
        return normalized_title, normalized_content

    @staticmethod
    def _department_or_404(db: Session, department_id: str) -> Department:
        department = db.get(Department, department_id)
        if department is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "department not found")
        return department

    @classmethod
    def create_sensitive_keyword(
        cls, db: Session, payload: SensitiveKeywordCreate, principal: Principal
    ) -> SensitiveKeyword:
        cls._require_admin(principal)
        keyword = payload.keyword.strip()
        if not keyword:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "keyword cannot be empty")
        if db.query(SensitiveKeyword).filter(SensitiveKeyword.keyword == keyword).first():
            raise HTTPException(status.HTTP_409_CONFLICT, "keyword already exists")
        item = SensitiveKeyword(keyword=keyword, enabled=payload.enabled, updated_by=principal.user_id)
        db.add(item)
        db.flush()
        return item

    @classmethod
    def update_sensitive_keyword(
        cls,
        db: Session,
        item: SensitiveKeyword,
        payload: SensitiveKeywordUpdate,
        principal: Principal,
    ) -> SensitiveKeyword:
        cls._require_admin(principal)
        if payload.keyword is not None:
            keyword = payload.keyword.strip()
            if not keyword:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "keyword cannot be empty")
            duplicate = (
                db.query(SensitiveKeyword)
                .filter(SensitiveKeyword.keyword == keyword, SensitiveKeyword.id != item.id)
                .first()
            )
            if duplicate:
                raise HTTPException(status.HTTP_409_CONFLICT, "keyword already exists")
            item.keyword = keyword
        if payload.enabled is not None:
            item.enabled = payload.enabled
        item.updated_by = principal.user_id
        db.flush()
        return item

    @classmethod
    def delete_sensitive_keyword(
        cls, db: Session, item: SensitiveKeyword, principal: Principal
    ) -> None:
        cls._require_admin(principal)
        db.delete(item)
        db.flush()

    @classmethod
    def delete_sensitive_event(cls, db: Session, event: SensitiveEvent, principal: Principal) -> None:
        cls._require_admin(principal)
        db.delete(event)
        db.flush()

    @classmethod
    def create_department_memory(
        cls,
        db: Session,
        department_id: str,
        payload: MemoryCreate,
        principal: Principal,
        *,
        settings: Any | None = None,
    ) -> DepartmentMemory:
        cls._require_admin(principal)
        cls._department_or_404(db, department_id)
        title, content = cls._trim_memory_values(payload.title, payload.content)
        effective_settings = settings or get_settings()
        if (
            db.query(DepartmentMemory)
            .filter(DepartmentMemory.department_id == department_id)
            .count()
            >= effective_settings.department_memory_limit
        ):
            raise HTTPException(status.HTTP_409_CONFLICT, "department memory limit reached")
        memory = DepartmentMemory(
            department_id=department_id,
            title=title,
            content=content,
            enabled=payload.enabled,
            created_by=principal.user_id,
            updated_by=principal.user_id,
        )
        db.add(memory)
        db.flush()
        return memory

    @classmethod
    def update_department_memory(
        cls,
        db: Session,
        memory: DepartmentMemory,
        payload: MemoryUpdate,
        principal: Principal,
    ) -> DepartmentMemory:
        cls._require_admin(principal)
        title, content = cls._trim_memory_values(payload.title, payload.content)
        if title is not None:
            memory.title = title
        if content is not None:
            memory.content = content
        if payload.enabled is not None:
            memory.enabled = payload.enabled
        memory.updated_by = principal.user_id
        db.flush()
        return memory

    @classmethod
    def delete_department_memory(
        cls, db: Session, memory: DepartmentMemory, principal: Principal
    ) -> None:
        cls._require_admin(principal)
        db.delete(memory)
        db.flush()
