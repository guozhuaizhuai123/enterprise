import json
import re

from fastapi import APIRouter, Depends, HTTPException, status
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.orm import Session

from app.agents.orchestrator import run_ask
from app.access import resolve_department_scope
from app.db import SessionLocal, get_db
from app.deps import Principal, get_current_principal
from app.models import Department, Document, Message, SensitiveKeyword, Thread, UserChatSetting
from app.assistant.form_previews import preview_form
from app.assistant.intent_extractor import plan_conversation
from app.assistant.planner import (
    ActionPlan,
    ClarificationPlan,
    FormPreviewPlan,
    KnowledgePlan,
    NavigationPlan,
)
from app.assistant.service import cancel_action, confirm_action, create_preview, execute_low_risk_query
from app.assistant.schemas import ActionConfirmRequest, BusinessEvent
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


_ROUTE_LABELS = {
    "tickets": "工单中心",
    "expenses": "费用报销",
    "organization": "组织管理",
    "projects": "项目管理",
    "contracts": "合同管理",
    "knowledge": "知识库",
    "schedules": "排班与考勤",
    "payroll": "薪酬管理",
    "overview": "企业全景",
    "assistant": "管理助手",
}
_FORM_LABELS = {"leave": "请假", "ticket": "工单", "expense": "报销"}
_INLINE_SECRET_VALUE_PATTERNS = (
    re.compile(r"((?:密码|口令)\s*(?:是|为|=|:|：)\s*)([^\s,，。；;]{1,128})"),
    re.compile(
        r"(?i)(\b(?:password|passwd|pwd)\b\s*(?:(?:is)\s*|[=:：]\s*))([^\s,，。；;]{1,128})"
    ),
)


def _safe_user_message_content(question: str, plan: ActionPlan | object) -> str:
    """Keep password-bearing action input out of durable chat history."""
    content = question
    for pattern in _INLINE_SECRET_VALUE_PATTERNS:
        content = pattern.sub(lambda match: f"{match.group(1)}[REDACTED]", content)
    if isinstance(plan, ActionPlan):
        for field_name in plan.action.secret_fields:
            value = getattr(plan.input, field_name, None)
            if isinstance(value, str) and value:
                content = content.replace(value, "[REDACTED]")
    return content


def _business_event(
    node: str,
    status_value: str,
    *,
    intent: str,
    display: str,
    payload: dict,
    route_key: str | None = None,
    **compatibility: object,
) -> dict:
    base = {
        "node": node,
        "status": status_value,
        "kind": "business",
        "intent": intent,
        "display": display,
        "payload": payload,
    }
    if route_key is not None:
        base["route_key"] = route_key
    overlap = base.keys() & compatibility.keys()
    if overlap:
        raise ValueError(f"reserved business event field: {sorted(overlap)[0]}")
    return BusinessEvent.model_validate({**base, **compatibility}).model_dump(
        mode="json", exclude_none=True
    )


def _status_count(result: dict, status_name: str) -> int:
    counts = result.get("status_counts")
    value = counts.get(status_name) if isinstance(counts, dict) else None
    return value if isinstance(value, int) else 0


def _period_label(result: dict, fallback: str) -> str:
    if result.get("month"):
        return str(result["month"])
    start, end = result.get("period_start"), result.get("period_end")
    if start and end:
        return f"{start} 至 {end}"
    return fallback


def _query_summary(intent: str, result: dict) -> str:
    """Persist the numbers, not a placeholder: chat history is the audit trail."""
    if intent == "attendance_summary":
        status_text = (
            f"正常 {_status_count(result, 'present')}、迟到 {_status_count(result, 'late')}、"
            f"缺勤 {_status_count(result, 'absent')}、远程 {_status_count(result, 'remote')}。"
        )
        if result.get("date"):
            return (
                f"{result['date']} 考勤：应出勤 {result.get('active_employees', 0)} 人，"
                f"已登记 {result.get('recorded', 0)} 人，未登记 {result.get('missing', 0)} 人；" + status_text
            )
        return (
            f"{_period_label(result, '本期')} 考勤：在职员工 {result.get('active_employees', 0)} 人，"
            f"共 {result.get('records', 0)} 条记录，覆盖 {result.get('days_recorded', 0)} 天、"
            f"{result.get('employees_recorded', 0)} 人；" + status_text
        )
    if intent == "expense_summary":
        return (
            f"{_period_label(result, '本月')} 费用：共 {result.get('count', 0)} 笔，"
            f"合计 ¥{result.get('amount', '0.00')}；"
            f"草稿 {_status_count(result, 'draft')}、待审批 {_status_count(result, 'pending_approval')}、"
            f"待付款 {_status_count(result, 'payment_pending')}、已付款 {_status_count(result, 'paid')}。"
        )
    count = result.get("count")
    if isinstance(count, int):
        return f"查询完成，共找到 {count} 条结果。"
    return "查询完成，结果已返回。"


def _short_business_stream(thread_id: str, event: dict) -> EventSourceResponse:
    async def events():
        yield {
            "event": "message",
            "data": json.dumps(
                {"node": "thread", "status": "ready", "thread_id": thread_id},
                ensure_ascii=False,
            ),
        }
        yield {"event": "message", "data": json.dumps(event, ensure_ascii=False)}
        yield {"event": "message", "data": "[DONE]"}

    return EventSourceResponse(events())


@router.post("/ask")
async def ask(
    payload: AskRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    try:
        department_ids = resolve_department_scope(principal.department_ids, payload.department_ids, is_root=principal.role == "admin", db=db)
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

    plan = await plan_conversation(payload.question, principal, db)
    safe_question = _safe_user_message_content(payload.question, plan)
    if is_new_thread:
        thread.title = safe_question[:50]
    current_message = Message(
        thread_id=thread.id,
        role="user",
        content=safe_question,
    )
    db.add(current_message)
    db.flush()
    thread_id = thread.id

    if isinstance(plan, NavigationPlan):
        label = _ROUTE_LABELS[plan.route_key]
        summary = f"正在打开{label}。"
        event = _business_event(
            "navigation",
            "ready",
            intent="navigation",
            display=summary,
            payload={"route_key": plan.route_key},
            route_key=plan.route_key,
        )
        db.add(Message(thread_id=thread_id, role="assistant", content=summary))
        db.commit()
        return _short_business_stream(thread_id, event)

    if isinstance(plan, FormPreviewPlan):
        preview = preview_form(plan.form, plan.text)
        display = f"已整理{_FORM_LABELS[plan.form]}表单预览，请确认内容后再提交。"
        event = _business_event(
            "form_preview",
            "ready",
            intent="form_preview",
            display=display,
            payload={"form": plan.form, "preview": preview},
            form=plan.form,
            preview=preview,
        )
        db.add(Message(thread_id=thread_id, role="assistant", content=display))
        db.commit()
        return _short_business_stream(thread_id, event)

    if isinstance(plan, ActionPlan) and plan.action.risk_level == "low":
        result = execute_low_risk_query(db, principal, plan)
        summary = _query_summary(plan.action.name, result)
        event = _business_event(
            "query_result",
            "completed",
            intent=plan.action.name,
            display=summary,
            payload=result,
            tool_name=plan.action.name,
            result=result,
        )
        db.add(Message(thread_id=thread_id, role="assistant", content=summary))
        db.commit()
        return _short_business_stream(thread_id, event)

    if isinstance(plan, ActionPlan):
        preview = create_preview(db, principal, thread_id, plan)
        preview_payload = preview.model_dump(mode="json")
        display = "操作预览已生成，请确认后执行。"
        event = _business_event(
            "action_preview",
            "ready",
            intent=plan.action.name,
            display=display,
            payload=preview_payload,
            **preview_payload,
        )
        db.add(Message(thread_id=thread_id, role="assistant", content=display))
        db.commit()
        return _short_business_stream(thread_id, event)

    if isinstance(plan, ClarificationPlan):
        summary = "请补充要办理的具体业务和必要信息。"
        event = _business_event(
            "clarification",
            "ready",
            intent="clarification",
            display=summary,
            payload={"reason": plan.reason},
        )
        db.add(Message(thread_id=thread_id, role="assistant", content=summary))
        db.commit()
        return _short_business_stream(thread_id, event)

    assert isinstance(plan, KnowledgePlan)
    context = get_thread_context(db, thread)
    scope = resolve_document_scope_state(db, principal=principal, thread=thread)
    history = load_chat_history(
        db,
        thread.id,
        memory_level=context.memory_level,
        current_message_id=current_message.id,
    )
    user_memories = load_enabled_user_memories(db, principal.user_id)
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
    authorized_department_ids = tuple(department_ids)
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

@router.post("/actions/{action_id}/confirm")
def confirm_assistant_action(action_id: str, payload: ActionConfirmRequest, db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    result = confirm_action(db, principal, action_id, payload)
    db.commit()
    return result

@router.post("/actions/{action_id}/cancel")
def cancel_assistant_action(action_id: str, db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    result = cancel_action(db, principal, action_id)
    db.commit()
    return result


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
