from dataclasses import dataclass, field

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.deps import Principal
from app.context.tokens import select_recent_messages
from app.models import (
    Document,
    Message,
    MessageContextFlag,
    Thread,
    ThreadContextSetting,
    ThreadDocumentSelection,
    UserMemory,
)
from app.schemas import ThreadContextOut, ThreadContextUpdate


@dataclass(frozen=True)
class ChatHistory:
    summary: str
    messages: list[dict[str, str]]
    summary_messages: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class DocumentScopeResolution:
    document_ids: frozenset[str] | None
    adjusted: bool = False


def _selection_ids(db: Session, thread_id: str) -> list[str]:
    return [
        row.document_id
        for row in db.query(ThreadDocumentSelection)
        .filter(ThreadDocumentSelection.thread_id == thread_id)
        .order_by(ThreadDocumentSelection.document_id)
        .all()
    ]


def get_thread_context(db: Session, thread: Thread, *, default_level: int = 3) -> ThreadContextOut:
    setting = db.get(ThreadContextSetting, thread.id)
    if setting is None:
        return ThreadContextOut(
            memory_level=default_level,
            document_scope_mode="all",
            document_ids=[],
        )
    return ThreadContextOut(
        memory_level=setting.memory_level,
        document_scope_mode=setting.document_scope_mode,
        document_ids=_selection_ids(db, thread.id) if setting.document_scope_mode == "selected" else [],
    )


def ensure_thread_context_setting(db: Session, thread: Thread) -> ThreadContextSetting:
    setting = db.get(ThreadContextSetting, thread.id)
    if setting is not None:
        return setting
    setting = ThreadContextSetting(
        thread_id=thread.id,
        memory_level=3,
        document_scope_mode="all",
    )
    db.add(setting)
    db.flush()
    return setting


def update_thread_context(
    db: Session,
    *,
    thread: Thread,
    principal: Principal,
    payload: ThreadContextUpdate,
) -> ThreadContextOut:
    setting = db.get(ThreadContextSetting, thread.id)
    current = get_thread_context(db, thread)
    mode = payload.document_scope_mode or current.document_scope_mode

    selected_ids = list(dict.fromkeys(payload.document_ids or []))
    replacing_selection = payload.document_ids is not None or payload.document_scope_mode == "all"
    effective_selection = selected_ids if payload.document_ids is not None else current.document_ids
    if mode == "selected" and not effective_selection:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "selected scope requires documents")
    if mode == "selected" and payload.document_ids is not None:
        documents = db.query(Document).filter(Document.id.in_(selected_ids)).all()
        documents_by_id = {document.id: document for document in documents}
        if len(documents_by_id) != len(selected_ids) or any(
            documents_by_id[document_id].department_id not in principal.department_ids
            for document_id in selected_ids
        ):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "document not found or unauthorized")

    if setting is None:
        setting = ThreadContextSetting(
            thread_id=thread.id,
            memory_level=current.memory_level,
            document_scope_mode=current.document_scope_mode,
        )
        db.add(setting)
    if payload.memory_level is not None:
        setting.memory_level = payload.memory_level
    setting.document_scope_mode = mode

    if replacing_selection:
        db.query(ThreadDocumentSelection).filter(
            ThreadDocumentSelection.thread_id == thread.id
        ).delete(synchronize_session=False)
        if mode == "selected":
            db.add_all(
                ThreadDocumentSelection(thread_id=thread.id, document_id=document_id)
                for document_id in selected_ids
            )
    db.flush()
    return get_thread_context(db, thread)


def resolve_document_scope_state(
    db: Session, *, principal: Principal, thread: Thread
) -> DocumentScopeResolution:
    setting = db.get(ThreadContextSetting, thread.id)
    if setting is None or setting.document_scope_mode == "all":
        return DocumentScopeResolution(None)
    selected_ids = _selection_ids(db, thread.id)
    if not selected_ids:
        return DocumentScopeResolution(frozenset())
    valid_ids = {
        document.id
        for document in db.query(Document)
        .filter(Document.id.in_(selected_ids), Document.department_id.in_(principal.department_ids))
        .all()
    }
    invalid_ids = set(selected_ids) - valid_ids
    if invalid_ids:
        db.query(ThreadDocumentSelection).filter(
            ThreadDocumentSelection.thread_id == thread.id,
            ThreadDocumentSelection.document_id.in_(invalid_ids),
        ).delete(synchronize_session=False)
        db.flush()
    return DocumentScopeResolution(frozenset(valid_ids), adjusted=bool(invalid_ids))


def resolve_document_scope(db: Session, *, principal: Principal, thread: Thread) -> frozenset[str] | None:
    return resolve_document_scope_state(db, principal=principal, thread=thread).document_ids


def load_enabled_user_memories(db: Session, user_id: str) -> tuple[str, ...]:
    rows = (
        db.query(UserMemory)
        .filter(UserMemory.user_id == user_id, UserMemory.enabled.is_(True))
        .order_by(UserMemory.created_at, UserMemory.id)
        .all()
    )
    return tuple(row.content.strip() for row in rows if row.content.strip())


def load_chat_history(
    db: Session,
    thread_id: str,
    memory_level: int,
    current_message_id: str | None,
) -> ChatHistory:
    setting = db.get(ThreadContextSetting, thread_id)
    summary = (setting.summary_text or "") if setting and memory_level >= 3 else ""
    query = (
        db.query(Message)
        .outerjoin(MessageContextFlag)
        .filter(
            Message.thread_id == thread_id,
            or_(
                MessageContextFlag.context_eligible.is_(None),
                MessageContextFlag.context_eligible.is_(True),
            ),
        )
    )
    if current_message_id is not None:
        query = query.filter(Message.id != current_message_id)
    candidates = [
        {"id": message.id, "role": message.role, "content": message.content}
        for message in query.order_by(Message.created_at, Message.id).all()
    ]
    budget = get_settings().memory_budgets[memory_level - 1]
    selected = select_recent_messages(candidates, budget, exclude_message_id=current_message_id)
    return ChatHistory(
        summary=summary,
        messages=[{"role": message["role"], "content": message["content"]} for message in selected],
        summary_messages=candidates,
    )
