from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import Principal, get_current_principal, require_admin
from app.governance.service import GovernanceService
from app.models import Department, DepartmentMemory, UserChatSetting, UserMemory
from app.schemas import (
    DepartmentMemoryOut,
    MemoryCreate,
    MemoryOut,
    MemoryUpdate,
    UserChatSettingOut,
    UserChatSettingUpdate,
)

me_router = APIRouter(prefix="/me", tags=["memory"])
admin_memory_router = APIRouter(
    prefix="/admin", tags=["admin-memory"], dependencies=[Depends(require_admin)]
)


def _trim_memory_values(title: str | None, content: str | None) -> tuple[str | None, str | None]:
    title = title.strip() if title is not None else None
    content = content.strip() if content is not None else None
    if title == "" or content == "":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "memory title and content cannot be empty")
    return title, content


def _department_or_404(db: Session, department_id: str) -> Department:
    department = db.get(Department, department_id)
    if department is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "department not found")
    return department


@me_router.get("/memories", response_model=list[MemoryOut])
def list_memories(
    db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)
):
    return (
        db.query(UserMemory)
        .filter(UserMemory.user_id == principal.user_id)
        .order_by(UserMemory.created_at)
        .all()
    )


@me_router.post("/memories", response_model=MemoryOut, status_code=status.HTTP_201_CREATED)
def create_memory(
    payload: MemoryCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    title, content = _trim_memory_values(payload.title, payload.content)
    if db.query(UserMemory).filter(UserMemory.user_id == principal.user_id).count() >= get_settings().user_memory_limit:
        raise HTTPException(status.HTTP_409_CONFLICT, "user memory limit reached")
    memory = UserMemory(user_id=principal.user_id, title=title, content=content, enabled=payload.enabled)
    db.add(memory)
    db.commit()
    db.refresh(memory)
    return memory


@me_router.put("/memories/{memory_id}", response_model=MemoryOut)
def update_memory(
    memory_id: str,
    payload: MemoryUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    memory = (
        db.query(UserMemory)
        .filter(UserMemory.id == memory_id, UserMemory.user_id == principal.user_id)
        .first()
    )
    if memory is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "memory not found")
    title, content = _trim_memory_values(payload.title, payload.content)
    if title is not None:
        memory.title = title
    if content is not None:
        memory.content = content
    if payload.enabled is not None:
        memory.enabled = payload.enabled
    db.commit()
    db.refresh(memory)
    return memory


@me_router.delete("/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(
    memory_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    memory = (
        db.query(UserMemory)
        .filter(UserMemory.id == memory_id, UserMemory.user_id == principal.user_id)
        .first()
    )
    if memory is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "memory not found")
    db.delete(memory)
    db.commit()


@me_router.get("/chat-settings", response_model=UserChatSettingOut)
def get_chat_settings(
    db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)
):
    setting = db.get(UserChatSetting, principal.user_id)
    return UserChatSettingOut(default_memory_level=setting.default_memory_level if setting else 3)


@me_router.patch("/chat-settings", response_model=UserChatSettingOut)
def update_chat_settings(
    payload: UserChatSettingUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    setting = db.get(UserChatSetting, principal.user_id)
    if setting is None:
        setting = UserChatSetting(
            user_id=principal.user_id, default_memory_level=payload.default_memory_level
        )
        db.add(setting)
    else:
        setting.default_memory_level = payload.default_memory_level
    db.commit()
    return setting


@admin_memory_router.get(
    "/departments/{department_id}/memories", response_model=list[DepartmentMemoryOut]
)
def list_department_memories(department_id: str, db: Session = Depends(get_db)):
    _department_or_404(db, department_id)
    return (
        db.query(DepartmentMemory)
        .filter(DepartmentMemory.department_id == department_id)
        .order_by(DepartmentMemory.created_at)
        .all()
    )


@admin_memory_router.post(
    "/departments/{department_id}/memories",
    response_model=DepartmentMemoryOut,
    status_code=status.HTTP_201_CREATED,
)
def create_department_memory(
    department_id: str,
    payload: MemoryCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_admin),
):
    memory = GovernanceService.create_department_memory(
        db, department_id, payload, principal, settings=get_settings()
    )
    db.commit()
    db.refresh(memory)
    return memory


@admin_memory_router.put("/department-memories/{memory_id}", response_model=DepartmentMemoryOut)
def update_department_memory(
    memory_id: str,
    payload: MemoryUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_admin),
):
    memory = db.get(DepartmentMemory, memory_id)
    if memory is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "department memory not found")
    GovernanceService.update_department_memory(db, memory, payload, principal)
    db.commit()
    db.refresh(memory)
    return memory


@admin_memory_router.delete("/department-memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_department_memory(
    memory_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_admin),
):
    memory = db.get(DepartmentMemory, memory_id)
    if memory is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "department memory not found")
    GovernanceService.delete_department_memory(db, memory, principal)
    db.commit()
