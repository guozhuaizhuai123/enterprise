import json

from fastapi import APIRouter, Depends, HTTPException, status
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.orm import Session

from app.agents.orchestrator import run_ask
from app.access import resolve_department_scope
from app.db import SessionLocal, get_db
from app.deps import Principal, get_current_principal
from app.models import Department, Document, Message, SensitiveKeyword, Thread, UserChatSetting
from app.context.service import (
    ensure_thread_context_setting,
    get_thread_context,
    load_chat_history,
    load_enabled_user_memories,
    resolve_document_scope_state,
    update_thread_context,
)
from app.schemas import AskRequest, MessageOut, ThreadContextOut, ThreadContextUpdate, ThreadOut

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/ask")
async def ask(
    payload: AskRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    try:
        department_ids = resolve_department_scope(principal.department_ids, payload.department_ids)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc

    thread = None
    is_new_thread = payload.thread_id is None
    if payload.thread_id:
        thread = db.get(Thread, payload.thread_id)
        if thread is None or thread.user_id != principal.user_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "thread not found")
    if thread is None:
        if payload.document_scope_mode == "selected" and not payload.document_ids:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "selected scope requires at least one document",
            )
        thread = Thread(
            user_id=principal.user_id,
            department_id=department_ids[0],
            title=payload.question[:50],
        )
        db.add(thread)
        db.flush()
        user_setting = db.get(UserChatSetting, principal.user_id)
        default_context = get_thread_context(
            db,
            thread,
            default_level=user_setting.default_memory_level if user_setting else 3,
        )
        update_thread_context(
            db,
            thread=thread,
            principal=principal,
            payload=ThreadContextUpdate(
                memory_level=payload.memory_level or default_context.memory_level,
                document_scope_mode=payload.document_scope_mode or "all",
                document_ids=payload.document_ids if payload.document_scope_mode == "selected" else None,
            ),
        )
    elif not is_new_thread:
        ensure_thread_context_setting(db, thread)

    context = get_thread_context(db, thread)
    scope = resolve_document_scope_state(db, principal=principal, thread=thread)
    current_message = Message(thread_id=thread.id, role="user", content=payload.question)
    db.add(current_message)
    db.flush()
    history = load_chat_history(
        db,
        thread.id,
        memory_level=context.memory_level,
        current_message_id=current_message.id,
    )
    user_memories = load_enabled_user_memories(db, principal.user_id)
    thread_id = thread.id
    current_message_id = current_message.id
    question = payload.question

    doc_titles = {
        d.id: d.title
        for d in db.query(Document).filter(Document.department_id.in_(department_ids)).all()
    }
    department_names_by_id = {
        department.id: department.name
        for department in db.query(Department).filter(Department.id.in_(department_ids)).all()
    }
    department_names = tuple(
        department_names_by_id.get(department_id, department_id) for department_id in department_ids
    )
    sensitive_keywords = tuple(
        row.keyword
        for row in db.query(SensitiveKeyword)
        .filter(SensitiveKeyword.enabled.is_(True))
        .order_by(SensitiveKeyword.id)
        .all()
    )
    user_id = principal.user_id
    username = principal.username
    authorized_department_ids = tuple(principal.department_ids)
    document_scope_mode = context.document_scope_mode
    selected_document_ids = scope.document_ids
    scope_adjusted = scope.adjusted
    memory_level = context.memory_level
    db.commit()

    # The generator below runs after this request handler has already
    # returned (streaming happens outside the Depends(get_db) lifecycle),
    # so it must not touch `db` or any ORM object bound to it — it opens
    # its own session instead.
    async def event_generator():
        stream_db = SessionLocal()
        try:
            yield {
                "event": "message",
                "data": json.dumps({"node": "thread", "status": "ready", "thread_id": thread_id}, ensure_ascii=False),
            }
            async for evt in run_ask(
                stream_db,
                user_id=user_id,
                username=username,
                thread_id=thread_id,
                current_message_id=current_message_id,
                department_ids=department_ids,
                authorized_department_ids=authorized_department_ids,
                department_names=department_names,
                question=question,
                memory_level=memory_level,
                document_scope_mode=document_scope_mode,
                selected_document_ids=selected_document_ids,
                scope_adjusted=scope_adjusted,
                history=history,
                user_memories=user_memories,
                doc_titles=doc_titles,
                sensitive_keywords=sensitive_keywords,
            ):
                yield {"event": "message", "data": json.dumps(evt, ensure_ascii=False)}

            yield {"event": "message", "data": "[DONE]"}
        finally:
            stream_db.close()

    return EventSourceResponse(event_generator())


@router.get("/threads", response_model=list[ThreadOut])
def list_threads(db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    threads = (
        db.query(Thread)
        .filter(Thread.user_id == principal.user_id)
        .order_by(Thread.created_at.desc())
        .all()
    )
    return threads


@router.get("/threads/{thread_id}/messages", response_model=list[MessageOut])
def list_messages(
    thread_id: str, db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)
):
    thread = db.get(Thread, thread_id)
    if thread is None or thread.user_id != principal.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "thread not found")
    messages = (
        db.query(Message).filter(Message.thread_id == thread_id).order_by(Message.created_at).all()
    )
    return messages


@router.get("/threads/{thread_id}/context-settings", response_model=ThreadContextOut)
def get_context_settings(
    thread_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    thread = db.get(Thread, thread_id)
    if thread is None or thread.user_id != principal.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "thread not found")
    return get_thread_context(db, thread)


@router.patch("/threads/{thread_id}/context-settings", response_model=ThreadContextOut)
def patch_context_settings(
    thread_id: str,
    payload: ThreadContextUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    thread = db.get(Thread, thread_id)
    if thread is None or thread.user_id != principal.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "thread not found")
    context = update_thread_context(db, thread=thread, principal=principal, payload=payload)
    db.commit()
    return context


@router.delete("/threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_thread(
    thread_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    thread = db.get(Thread, thread_id)
    if thread is None or thread.user_id != principal.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "thread not found")
    db.delete(thread)
    db.commit()
