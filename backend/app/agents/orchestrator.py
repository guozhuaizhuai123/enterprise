"""Context-aware four-node chat pipeline with SSE-ready event dictionaries."""

import asyncio
import logging
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.agents import answer, faithfulness_check, sensitive_gate
from app.context.prompt import build_answer_messages
from app.context.query import (
    ensure_summary,
    merge_department_memories,
    needs_history,
    rewrite_followup,
)
from app.context.service import ChatHistory
from app.kb.retriever import RetrievedChunk, search_departments
from app.models import (
    DepartmentMemory,
    Document,
    Message,
    MessageContextFlag,
    SensitiveEvent,
    ThreadContextSetting,
    ThreadDocumentSelection,
)


logger = logging.getLogger(__name__)


def _event(node: str, status: str, **payload) -> dict:
    return {"node": node, "status": status, **payload}


def _citations_meta(chunks: list[RetrievedChunk], doc_titles: dict[str, str]) -> list[dict]:
    return [
        {
            "tag": f"C{i + 1}",
            "document_id": chunk.document_id,
            "title": doc_titles.get(chunk.document_id, "未知文档"),
            "snippet": chunk.text,
        }
        for i, chunk in enumerate(chunks)
    ]


def _persist_assistant(
    db: Session,
    *,
    thread_id: str,
    answer_text: str,
    citations: list[dict] | None = None,
    excluded_reason: str | None = None,
) -> Message:
    message = Message(
        thread_id=thread_id,
        role="assistant",
        content=answer_text,
        citations=citations or None,
    )
    db.add(message)
    db.flush()
    if excluded_reason is not None:
        db.add(
            MessageContextFlag(
                message_id=message.id,
                context_eligible=False,
                reason=excluded_reason,
            )
        )
    db.commit()
    return message


def _exclude_message(db: Session, message_id: str, reason: str) -> None:
    flag = db.get(MessageContextFlag, message_id)
    if flag is None:
        db.add(
            MessageContextFlag(
                message_id=message_id,
                context_eligible=False,
                reason=reason,
            )
        )
    else:
        flag.context_eligible = False
        flag.reason = reason


def _persist_failure_pair(
    db: Session,
    *,
    thread_id: str,
    current_message_id: str,
    reason: str,
    answer_text: str,
) -> None:
    _exclude_message(db, current_message_id, reason)
    _persist_assistant(
        db,
        thread_id=thread_id,
        answer_text=answer_text,
        excluded_reason=reason,
    )


def _persist_sensitive_block(
    db: Session,
    *,
    user_id: str,
    username: str,
    thread_id: str,
    current_message_id: str,
    department_names: tuple[str, ...],
    question: str,
    matched_keyword: str,
    reason: str,
    answer_text: str,
    exclude_current_message: bool = True,
) -> None:
    if exclude_current_message:
        _exclude_message(db, current_message_id, "sensitive_blocked")
    db.add(
        SensitiveEvent(
            user_id=user_id,
            username=username,
            department_name="、".join(department_names),
            question=question,
            matched_keyword=matched_keyword,
            reason=reason,
        )
    )
    _persist_assistant(
        db,
        thread_id=thread_id,
        answer_text=answer_text,
        excluded_reason="sensitive_blocked",
    )


def _sensitive_context(question: str, history: ChatHistory) -> str:
    prior_user_text = [
        message.get("content", "")
        for message in history.summary_messages
        if message.get("role") == "user" and message.get("content", "").strip()
    ]
    return "\n".join((question, *prior_user_text))


def _sensitive_block_answer(reason: str) -> str:
    return f"该问题涉及敏感信息，{reason}，不由系统自动作答。"


def _exclude_sensitive_history_matches(
    db: Session,
    *,
    thread_id: str,
    history: ChatHistory,
    sensitive_keywords: tuple[str, ...] | None,
) -> list[tuple[str, str, str]]:
    matches: list[tuple[str, str, str]] = []
    for history_message in history.summary_messages:
        if history_message.get("role") != "user":
            continue
        content = history_message.get("content", "")
        matched = sensitive_gate.matched_keyword(content, sensitive_keywords)
        message_id = history_message.get("id")
        if not matched:
            continue
        _, reason = sensitive_gate.check(content, sensitive_keywords)
        matches.append((content, matched, reason))
        if not isinstance(message_id, str):
            continue
        message = db.get(Message, message_id)
        if message is None or message.thread_id != thread_id or message.role != "user":
            continue
        _exclude_message(db, message.id, "sensitive_blocked")
        blocked_answer = _sensitive_block_answer(reason)
        companions = (
            db.query(Message)
            .filter(
                Message.thread_id == thread_id,
                Message.role == "assistant",
                Message.content == blocked_answer,
            )
            .all()
        )
        for companion in companions:
            _exclude_message(db, companion.id, "sensitive_blocked")
    return matches


def _refresh_selected_scope(
    db: Session,
    *,
    thread_id: str,
    selected_document_ids: frozenset[str],
    authorized_department_ids: tuple[str, ...],
) -> tuple[frozenset[str], bool]:
    selection_rows = (
        db.query(ThreadDocumentSelection)
        .filter(ThreadDocumentSelection.thread_id == thread_id)
        .all()
    )
    persisted_ids = {row.document_id for row in selection_rows}
    valid_persisted_ids = {
        document.id
        for document in db.query(Document)
        .filter(
            Document.id.in_(persisted_ids),
            Document.department_id.in_(authorized_department_ids),
        )
        .all()
    }
    invalid_ids = persisted_ids - valid_persisted_ids
    if invalid_ids:
        db.query(ThreadDocumentSelection).filter(
            ThreadDocumentSelection.thread_id == thread_id,
            ThreadDocumentSelection.document_id.in_(invalid_ids),
        ).delete(synchronize_session=False)
        db.flush()
    effective_ids = frozenset(valid_persisted_ids.intersection(selected_document_ids))
    return effective_ids, bool(invalid_ids or effective_ids != selected_document_ids)


def _load_evidence_department_memories(
    db: Session,
    *,
    chunks: list[RetrievedChunk],
    authorized_department_ids: tuple[str, ...],
) -> tuple[dict[str, list[DepartmentMemory]], tuple[str, ...], tuple[str, ...]]:
    document_ids = {chunk.document_id for chunk in chunks}
    documents = (
        db.query(Document)
        .filter(
            Document.id.in_(document_ids),
            Document.department_id.in_(authorized_department_ids),
        )
        .all()
    )
    evidence_department_ids = tuple(sorted({document.department_id for document in documents}))
    if not evidence_department_ids:
        return {}, (), ()
    memories = (
        db.query(DepartmentMemory)
        .filter(
            DepartmentMemory.department_id.in_(evidence_department_ids),
            DepartmentMemory.enabled.is_(True),
        )
        .order_by(DepartmentMemory.department_id, DepartmentMemory.created_at, DepartmentMemory.id)
        .all()
    )
    by_department: dict[str, list[DepartmentMemory]] = {}
    for memory in memories:
        by_department.setdefault(memory.department_id, []).append(memory)
    return by_department, evidence_department_ids, tuple(memory.id for memory in memories)


def _log_conflicts(
    *,
    thread_id: str,
    department_ids: tuple[str, ...],
    memory_ids: tuple[str, ...],
    conflicts: list[dict[str, str]],
) -> None:
    for _conflict in conflicts:
        logger.warning(
            "department memory conflict thread_id=%s department_ids=%s memory_ids=%s reason=%s",
            thread_id,
            department_ids,
            memory_ids,
            "conservative merge selected",
        )


async def run_ask(
    db: Session,
    *,
    user_id: str,
    username: str,
    thread_id: str,
    current_message_id: str,
    department_ids: tuple[str, ...],
    authorized_department_ids: tuple[str, ...],
    department_names: tuple[str, ...],
    question: str,
    memory_level: int,
    document_scope_mode: str,
    selected_document_ids: frozenset[str] | None,
    scope_adjusted: bool,
    history: ChatHistory,
    user_memories: tuple[str, ...],
    doc_titles: dict[str, str],
    sensitive_keywords: Sequence[str] | None = None,
) -> AsyncIterator[dict]:
    active_keywords = tuple(sensitive_keywords) if sensitive_keywords is not None else None
    safety_text = _sensitive_context(question, history)
    yield _event("sensitive_gate", "running")
    is_sensitive, reason = sensitive_gate.check(safety_text, active_keywords)
    matched_keyword = sensitive_gate.matched_keyword(safety_text, active_keywords) or ""
    yield _event(
        "sensitive_gate",
        "done",
        is_sensitive=is_sensitive,
        reason=reason,
        matched_keyword=matched_keyword,
    )
    if is_sensitive:
        history_matches = _exclude_sensitive_history_matches(
            db,
            thread_id=thread_id,
            history=history,
            sensitive_keywords=active_keywords,
        )
        current_sensitive, current_reason = sensitive_gate.check(question, active_keywords)
        if current_sensitive:
            audit_question = question
            audit_keyword = sensitive_gate.matched_keyword(question, active_keywords) or ""
            audit_reason = current_reason
        else:
            audit_question, audit_keyword, audit_reason = history_matches[0]
        answer_text = _sensitive_block_answer(audit_reason)
        _persist_sensitive_block(
            db,
            user_id=user_id,
            username=username,
            thread_id=thread_id,
            current_message_id=current_message_id,
            department_names=department_names,
            question=audit_question,
            matched_keyword=audit_keyword,
            reason=audit_reason,
            answer_text=answer_text,
            exclude_current_message=current_sensitive,
        )
        yield _event("final", "blocked", answer=answer_text)
        return

    document_ids: frozenset[str] | None = None
    if document_scope_mode == "selected":
        document_ids, adjusted_during_stream = _refresh_selected_scope(
            db,
            thread_id=thread_id,
            selected_document_ids=selected_document_ids or frozenset(),
            authorized_department_ids=authorized_department_ids,
        )
        scope_adjusted = scope_adjusted or adjusted_during_stream
        if not document_ids:
            answer_text = "所选文档已失效，请重新选择文档范围。"
            _persist_assistant(db, thread_id=thread_id, answer_text=answer_text)
            yield _event(
                "final",
                "blocked",
                error_code="document_scope_empty",
                answer=answer_text,
            )
            return
        if scope_adjusted:
            db.commit()
            yield _event("scope", "adjusted", document_ids=sorted(document_ids))

    summary = history.summary
    setting = db.get(ThreadContextSetting, thread_id)
    if memory_level >= 4 and setting is not None:
        summary = await ensure_summary(db, setting, history.summary_messages, memory_level)

    retrieval_query = question
    if memory_level >= 2 and needs_history(question) and (history.messages or summary):
        retrieval_query = await rewrite_followup(question, summary, history.messages)
        rewritten_sensitive, rewritten_reason = sensitive_gate.check(retrieval_query, active_keywords)
        rewritten_keyword = sensitive_gate.matched_keyword(retrieval_query, active_keywords) or ""
        if rewritten_sensitive:
            yield _event(
                "sensitive_gate",
                "done",
                is_sensitive=True,
                reason=rewritten_reason,
                matched_keyword=rewritten_keyword,
            )
            answer_text = _sensitive_block_answer(rewritten_reason)
            _persist_sensitive_block(
                db,
                user_id=user_id,
                username=username,
                thread_id=thread_id,
                current_message_id=current_message_id,
                department_names=department_names,
                question=question,
                matched_keyword=rewritten_keyword,
                reason=rewritten_reason,
                answer_text=answer_text,
            )
            yield _event("final", "blocked", answer=answer_text)
            return

    yield _event("retrieval", "running")
    chunks = search_departments(
        db,
        department_ids=department_ids,
        query=retrieval_query,
        document_ids=document_ids,
    )
    yield _event(
        "retrieval",
        "done",
        matched=[
            {"document_id": chunk.document_id, "score": round(chunk.combined_score, 3)}
            for chunk in chunks
        ],
    )
    if not chunks:
        answer_text = "知识库中未找到与该问题相关的内容，建议联系相关部门人工确认。"
        _persist_assistant(db, thread_id=thread_id, answer_text=answer_text)
        yield _event("final", "blocked", answer=answer_text)
        return

    memories_by_department, evidence_department_ids, memory_ids = _load_evidence_department_memories(
        db,
        chunks=chunks,
        authorized_department_ids=authorized_department_ids,
    )
    department_memories, conflicts = await merge_department_memories(memories_by_department)
    if conflicts:
        _log_conflicts(
            thread_id=thread_id,
            department_ids=evidence_department_ids,
            memory_ids=memory_ids,
            conflicts=conflicts,
        )

    citations = _citations_meta(chunks, doc_titles)
    yield _event("answer", "running", citations_meta=citations)
    evidence = "\n\n".join(f"[C{i + 1}]\n{chunk.text}" for i, chunk in enumerate(chunks))
    messages = build_answer_messages(
        question=question,
        evidence=evidence,
        request_time=datetime.now(UTC),
        department_memories=department_memories,
        user_memories=list(user_memories),
        summary=summary,
        history=history.messages,
    )
    full_answer = ""
    try:
        async for delta in answer.run(messages):
            full_answer += delta
            yield _event("answer", "streaming", delta=delta)
    except asyncio.CancelledError:
        _persist_failure_pair(
            db,
            thread_id=thread_id,
            current_message_id=current_message_id,
            reason="answer_generation_failed",
            answer_text="回答生成失败，请稍后重试。",
        )
        raise
    except Exception:
        failure_answer = "回答生成失败，请稍后重试。"
        _persist_failure_pair(
            db,
            thread_id=thread_id,
            current_message_id=current_message_id,
            reason="answer_generation_failed",
            answer_text=failure_answer,
        )
        yield _event(
            "final",
            "blocked",
            error_code="answer_generation_failed",
            answer=failure_answer,
        )
        return
    full_answer = answer.clean_output(full_answer)
    yield _event("answer", "done", answer=full_answer)

    yield _event("faithfulness_check", "running")
    check_task = asyncio.create_task(faithfulness_check.run(question, full_answer, chunks))
    try:
        result = await check_task
    except Exception as exc:
        logger.warning("faithfulness check unavailable: %s", type(exc).__name__)
        _persist_assistant(db, thread_id=thread_id, answer_text=full_answer, citations=citations)
        yield _event("final", "completed", answer=full_answer, citations=citations)
        yield _event(
            "faithfulness_check",
            "done",
            available=False,
            faithful=None,
            concern="大模型溯源核查已完毕，未发现明显问题",
        )
        return
    _persist_assistant(db, thread_id=thread_id, answer_text=full_answer, citations=citations)
    yield _event("final", "completed", answer=full_answer, citations=citations)
    yield _event(
        "faithfulness_check",
        "done",
        available=True,
        faithful=result["faithful"],
        concern=result["concern"],
    )
