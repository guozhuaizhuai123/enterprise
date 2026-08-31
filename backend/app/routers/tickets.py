from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import Principal, get_current_principal, require_admin
from app.models import Department, Notification, Ticket, TicketEvent, TicketMessage, Todo, User, UserDepartment
from app.schemas import (
    TicketAction, TicketCreate, TicketDispatch, TicketEventOut, TicketMessageCreate, TicketMessageOut, TicketOut,
    TicketPreviewIn, TicketPreviewOut,
    TodoCreate, TodoOut, TodoUpdate,
    OwnerOptionOut, NotificationOut, DepartmentOut,
)
import re

employee_router = APIRouter(prefix="/tickets", tags=["tickets"])
todo_router = APIRouter(prefix="/todos", tags=["todos"])
notification_router = APIRouter(prefix="/notifications", tags=["notifications"])
admin_router = APIRouter(prefix="/admin", tags=["admin-tickets"], dependencies=[Depends(require_admin)])


def _user(db: Session, user_id: str | None) -> User | None:
    return db.get(User, user_id) if user_id else None


def _admin_user(db: Session) -> User:
    admin = db.query(User).filter(User.role == "admin").order_by(User.created_at).first()
    if admin is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "admin user not configured")
    return admin


def _ticket_out(db: Session, ticket: Ticket) -> TicketOut:
    requester, target = _user(db, ticket.requester_id), _user(db, ticket.target_user_id)
    dept = db.get(Department, ticket.department_id) if ticket.department_id else None
    req_dept = db.get(Department, ticket.requested_department_id) if ticket.requested_department_id else None
    return TicketOut(
        id=ticket.id, requester_id=ticket.requester_id, requester_name=requester.username if requester else "",
        target_user_id=ticket.target_user_id, target_user_name=target.username if target else "",
        department_id=ticket.department_id, department_name=dept.name if dept else "",
        requested_department_id=ticket.requested_department_id,
        requested_department_name=req_dept.name if req_dept else "",
        ticket_type=ticket.ticket_type, subject=ticket.subject, description=ticket.description,
        status=ticket.status, requires_admin=ticket.requires_admin, created_at=ticket.created_at,
        updated_at=ticket.updated_at, closed_at=ticket.closed_at,
    )


def _todo_out(db: Session, todo: Todo) -> TodoOut:
    assignee, creator = _user(db, todo.assignee_id), _user(db, todo.created_by)
    return TodoOut(
        id=todo.id, assignee_id=todo.assignee_id, assignee_name=assignee.username if assignee else "",
        created_by=todo.created_by, creator_name=creator.username if creator else "", ticket_id=todo.ticket_id,
        title=todo.title, description=todo.description, status=todo.status, due_at=todo.due_at,
        completed_at=todo.completed_at, created_at=todo.created_at, updated_at=todo.updated_at,
    )


def _message_out(db: Session, message: TicketMessage) -> TicketMessageOut:
    sender = _user(db, message.sender_id)
    return TicketMessageOut(id=message.id, ticket_id=message.ticket_id, sender_id=message.sender_id,
                            sender_name=sender.username if sender else "", content=message.content,
                            created_at=message.created_at)


def _event(db: Session, actor_id: str, event_type: str, detail: str = "", *, ticket_id: str | None = None, todo_id: str | None = None):
    db.add(TicketEvent(actor_id=actor_id, event_type=event_type, detail=detail, ticket_id=ticket_id, todo_id=todo_id))


def _notify(db: Session, recipient_id: str | None, content: str, *, kind: str, ticket_id: str | None = None, todo_id: str | None = None):
    if recipient_id:
        db.add(Notification(recipient_id=recipient_id, content=content, kind=kind, ticket_id=ticket_id, todo_id=todo_id))


def _same_department(db: Session, a: str, b: str) -> bool:
    return db.query(UserDepartment).filter(UserDepartment.user_id == a, UserDepartment.department_id.in_(
        db.query(UserDepartment.department_id).filter(UserDepartment.user_id == b)
    )).first() is not None


def _can_view(db: Session, principal: Principal, ticket: Ticket) -> bool:
    if principal.role == "admin":
        return True
    if ticket.requester_id == principal.user_id or ticket.target_user_id == principal.user_id:
        return True
    return ticket.target_user_id is None and ticket.department_id in principal.department_ids


@employee_router.get("", response_model=list[TicketOut])
def list_tickets(db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    if principal.role == "admin":
        rows = db.query(Ticket).order_by(Ticket.created_at.desc()).all()
    else:
        rows = db.query(Ticket).filter(or_(Ticket.requester_id == principal.user_id,
            Ticket.target_user_id == principal.user_id,
            (Ticket.target_user_id.is_(None) & Ticket.department_id.in_(principal.department_ids))
        )).order_by(Ticket.created_at.desc()).all()
    return [_ticket_out(db, row) for row in rows]


@employee_router.get("/departments", response_model=list[DepartmentOut])
def ticket_departments(db: Session = Depends(get_db)):
    """部门列表，供发起跨部门协助时选择「需要协助的部门」。"""
    return [DepartmentOut(id=row.id, name=row.name, created_at=row.created_at)
            for row in db.query(Department).order_by(Department.name).all()]


def _preview_ticket(text: str) -> TicketPreviewOut:
    """从自然语言中提取工单意图与字段。"""
    direct_request = bool(re.search(r"(?:帮我|替我|给我|我要|我想|我需要).{0,30}(?:发|提|创|建).{0,10}(?:工单|协助|请求|ticket)", text))
    question_request = bool(re.search(r"(?:问|咨询|询问).{0,20}(?:业务|问题|管理员|行政|财务|人事)", text))
    issue_request = bool(re.search(r"(?:反馈|报|反映).{0,20}(?:问题|bug|错误|异常)", text))
    cross_request = bool(re.search(r"(?:跨部门|别的部门|其他部门|别的组)", text))
    same_request = bool(re.search(r"(?:同部门|我们部门|本部门|部门内|同事|找|给).{0,15}(?:同事|同学|员工)", text))

    if not (direct_request or question_request or issue_request or cross_request or same_request):
        return TicketPreviewOut(is_ticket_request=False)

    # 主题：取「关于/帮我对接/请帮忙核对」后面的内容，或整句摘要
    subject = ""
    m = re.search(r"(?:关于|帮我对接|请帮忙核对|帮我核对|帮我确认|请协助|帮我联系|找)\s*(.{2,30}?)(?:，|,|。|\.\s|$)", text)
    if m:
        subject = m.group(1).strip().rstrip("，。.")
    if not subject:
        subject = text.strip()[:30]

    # 处理人：尝试匹配「给/找/让/让XXX处理」
    target_username = None
    for pat in [r"(?:给|找|让|叫|让).{0,2}([^，,。\s]{2,12})(?:处理|跟进|核对|看|办)", r"(?:处理人|负责人|协助人).{0,2}([^，,。\s]{2,12})", r"(?:同事|同学)([^，,。\s]{2,12})"]:
        m = re.search(pat, text)
        if m:
            target_username = m.group(1).strip()
            break

    # 部门：匹配「XX部门」
    department_name = None
    m = re.search(r"([^\s]{1,10}部门)", text)
    if m:
        department_name = m.group(1).strip()

    # 类型推断
    ticket_type = None
    if cross_request:
        ticket_type = "cross_department"
    elif question_request:
        ticket_type = "question"
    elif issue_request:
        ticket_type = "issue"
    elif same_request or direct_request:
        ticket_type = "same_department"

    return TicketPreviewOut(
        is_ticket_request=True,
        ticket_type=ticket_type,
        subject=subject or None,
        description=text.strip(),
        target_username=target_username,
        department_name=department_name,
    )


@employee_router.post("/preview", response_model=TicketPreviewOut)
def ticket_preview(payload: TicketPreviewIn):
    return _preview_ticket(payload.text)


@employee_router.get("/participants", response_model=list[OwnerOptionOut])
def participants(db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    rows = (
        db.query(User, UserDepartment, Department)
        .join(UserDepartment, UserDepartment.user_id == User.id, isouter=True)
        .join(Department, Department.id == UserDepartment.department_id, isouter=True)
        .filter(User.role == "employee", User.id != principal.user_id)
        .order_by(User.username)
        .all()
    )
    user_map: dict[str, User] = {}
    user_departments: dict[str, list[str]] = {}
    for user, user_department, department in rows:
        user_map.setdefault(user.id, user)
        if user_department and department:
            user_departments.setdefault(user.id, []).append(department.id)
    result = []
    for user in user_map.values():
        dept_ids = user_departments.get(user.id, [])
        result.append(OwnerOptionOut(
            id=user.id,
            username=user.username,
            role=user.role,
            department_name=user.department.name if user.department else "",
            departments=dept_ids,
        ))
    return result


@employee_router.post("", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
def create_ticket(payload: TicketCreate, db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    department_id = payload.department_id or principal.department_id
    if department_id not in principal.department_ids:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "department not accessible")

    # "admin" 是前端提供的特殊值，表示“指派给管理员”；跨部门协助未指定处理人时默认发给管理员。
    target_is_admin_sentinel = payload.target_user_id == "admin" or (
        payload.ticket_type == "cross_department" and not payload.target_user_id
    )

    if payload.ticket_type == "same_department" and not payload.target_user_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "同部门协助需要指定处理人")

    # 跨部门协助：处理人填的是「需要协助的部门」，管理员据此知道该调度给哪个部门。
    requested_department_id = None
    if payload.ticket_type == "cross_department":
        if not payload.requested_department_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "跨部门协助需要指定协助部门")
        if db.get(Department, payload.requested_department_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "requested department not found")
        if payload.requested_department_id in principal.department_ids:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "跨部门协助需要选择其他部门")
        requested_department_id = payload.requested_department_id
    if payload.ticket_type == "cross_department" and payload.target_user_id and not target_is_admin_sentinel:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "跨部门协助默认发送给管理员，处理人只能选择管理员")

    if target_is_admin_sentinel:
        target = _admin_user(db)
        resolved_target_id = target.id
    else:
        target = _user(db, payload.target_user_id)
        resolved_target_id = payload.target_user_id
        if payload.target_user_id and target is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "target user not found")

    target_is_admin = bool(target and target.role == "admin")

    if payload.ticket_type == "same_department":
        if target_is_admin:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "同部门协助只能发送给部门员工")
        if not _same_department(db, principal.user_id, target.id):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "同部门协助只能发送给同部门员工")

    if payload.ticket_type == "cross_department" and not target_is_admin:
        # 兜底：如果前面没走 sentinel 逻辑，确保跨部门协助一定指向管理员
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "跨部门协助只能发送给管理员")

    if target_is_admin:
        # 跨部门工单直达管理员：先进入「待管理员审批/派发」，管理员可批准、驳回或直接派发给具体人
        requires_admin = True
        initial = "pending_admin"
    else:
        requires_admin = False
        initial = "pending_acceptance" if payload.ticket_type in {"same_department", "issue"} else "answered"
    ticket = Ticket(requester_id=principal.user_id, target_user_id=resolved_target_id, department_id=department_id,
                    requested_department_id=requested_department_id,
                    ticket_type=payload.ticket_type, subject=payload.subject, description=payload.description,
                    status=initial, requires_admin=requires_admin)
    db.add(ticket); db.flush()
    _event(db, principal.user_id, "created", payload.subject, ticket_id=ticket.id)
    # 把原始需求作为第一条沟通记录：管理员/处理人打开「沟通记录」即可看到完整诉求
    if payload.description:
        db.add(TicketMessage(ticket_id=ticket.id, sender_id=principal.user_id, content=payload.description))
    # 指派给具体处理人（员工或管理员）时都通知对方，便于对方在协作中心收到消息提示
    if ticket.target_user_id:
        _notify(db, ticket.target_user_id, f"{principal.username} 向你发起了工单：{ticket.subject}", kind="ticket_assigned", ticket_id=ticket.id)
    db.commit(); db.refresh(ticket)
    return _ticket_out(db, ticket)


@employee_router.get("/{ticket_id}", response_model=TicketOut)
def get_ticket(ticket_id: str, db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    ticket = db.get(Ticket, ticket_id)
    if ticket is None or not _can_view(db, principal, ticket):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ticket not found")
    return _ticket_out(db, ticket)


@employee_router.post("/{ticket_id}/messages", response_model=TicketMessageOut, status_code=status.HTTP_201_CREATED)
def add_message(ticket_id: str, payload: TicketMessageCreate, db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    ticket = db.get(Ticket, ticket_id)
    if ticket is None or not _can_view(db, principal, ticket):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ticket not found")
    # completed 也算收口：管理员/处理人标记完成后，双方无法再继续沟通
    if ticket.status in {"closed", "cancelled", "rejected", "completed"}:
        raise HTTPException(status.HTTP_409_CONFLICT, "ticket is closed")
    message = TicketMessage(ticket_id=ticket.id, sender_id=principal.user_id, content=payload.content)
    db.add(message); _event(db, principal.user_id, "message_added", "", ticket_id=ticket.id)
    if ticket.ticket_type == "question": ticket.status = "answered"
    # 通知工单的另一端（发起人或处理人），让对方实时知道有新回复
    other = ticket.target_user_id if ticket.requester_id == principal.user_id else ticket.requester_id
    if other and other != principal.user_id:
        _notify(db, other, f"{principal.username} 在工单“{ticket.subject}”中回复了你", kind="ticket_replied", ticket_id=ticket.id)
    db.commit(); db.refresh(message)
    return _message_out(db, message)


@employee_router.get("/{ticket_id}/messages", response_model=list[TicketMessageOut])
def list_messages(ticket_id: str, db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    ticket = db.get(Ticket, ticket_id)
    if ticket is None or not _can_view(db, principal, ticket):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ticket not found")
    return [_message_out(db, item) for item in db.query(TicketMessage).filter(TicketMessage.ticket_id == ticket_id).order_by(TicketMessage.created_at).all()]


def _action(ticket: Ticket, action: str, principal: Principal, db: Session, reason: str = ""):
    if action == "accept":
        if ticket.target_user_id != principal.user_id or ticket.status != "pending_acceptance": raise HTTPException(status.HTTP_409_CONFLICT, "ticket cannot be accepted")
        ticket.status = "in_progress"
    elif action == "reject":
        if ticket.target_user_id != principal.user_id or ticket.status != "pending_acceptance": raise HTTPException(status.HTTP_409_CONFLICT, "ticket cannot be rejected")
        ticket.status = "rejected"
    elif action == "approve":
        if principal.role != "admin" or ticket.status != "pending_admin": raise HTTPException(status.HTTP_409_CONFLICT, "ticket cannot be approved")
        ticket.status = "in_progress"
    elif action == "admin_reject":
        if principal.role != "admin" or ticket.status != "pending_admin": raise HTTPException(status.HTTP_409_CONFLICT, "ticket cannot be rejected")
        ticket.status = "rejected"
    elif action == "close":
        if principal.role != "admin" and principal.user_id not in {ticket.requester_id, ticket.target_user_id}: raise HTTPException(status.HTTP_403_FORBIDDEN, "not allowed")
        ticket.status, ticket.closed_at = "closed", datetime.now(UTC)
    elif action == "complete":
        # 管理员或处理人标记完成；完成后工单冻结，双方不能再继续沟通
        if principal.role != "admin" and principal.user_id not in {ticket.requester_id, ticket.target_user_id}: raise HTTPException(status.HTTP_403_FORBIDDEN, "not allowed")
        ticket.status, ticket.closed_at = "completed", datetime.now(UTC)
    elif action == "reopen":
        closed_at = ticket.closed_at
        if closed_at is not None and closed_at.tzinfo is None:
            # SQLite drops timezone information when reading DateTime columns.
            closed_at = closed_at.replace(tzinfo=UTC)
        if closed_at is None or datetime.now(UTC) - closed_at > timedelta(days=3) or principal.user_id != ticket.requester_id: raise HTTPException(status.HTTP_409_CONFLICT, "reopen window expired")
        ticket.status, ticket.closed_at = "in_progress", None
    else: raise HTTPException(status.HTTP_400_BAD_REQUEST, "unsupported action")
    _event(db, principal.user_id, action, reason, ticket_id=ticket.id)


for _name, _action_name in (("accept", "accept"), ("reject", "reject"), ("approve", "approve"), ("admin-reject", "admin_reject"), ("close", "close"), ("complete", "complete"), ("reopen", "reopen")):
    def _make(action_name):
        def endpoint(ticket_id: str, payload: TicketAction = TicketAction(), db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
            ticket = db.get(Ticket, ticket_id)
            if ticket is None or not _can_view(db, principal, ticket): raise HTTPException(status.HTTP_404_NOT_FOUND, "ticket not found")
            _action(ticket, action_name, principal, db, payload.reason)
            if action_name == "approve" and ticket.target_user_id:
                todo = Todo(assignee_id=ticket.target_user_id, created_by=principal.user_id, ticket_id=ticket.id, title=ticket.subject, description=ticket.description)
                db.add(todo); db.flush(); _notify(db, ticket.target_user_id, f"你有新的待办：{ticket.subject}", kind="todo_created", ticket_id=ticket.id, todo_id=todo.id)
            elif action_name == "accept":
                todo = Todo(assignee_id=principal.user_id, created_by=ticket.requester_id, ticket_id=ticket.id, title=ticket.subject, description=ticket.description)
                db.add(todo); db.flush(); _notify(db, principal.user_id, f"已生成待办：{ticket.subject}", kind="todo_created", ticket_id=ticket.id, todo_id=todo.id)
            db.commit(); db.refresh(ticket); return _ticket_out(db, ticket)
        endpoint.__name__ = f"ticket_{action_name}"
        return endpoint
    employee_router.post(f"/{{ticket_id}}/{_name}", response_model=TicketOut)(_make(_action_name))


@todo_router.get("", response_model=list[TodoOut])
def list_todos(db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    rows = db.query(Todo).filter(Todo.assignee_id == principal.user_id).order_by(Todo.created_at.desc()).all()
    return [_todo_out(db, item) for item in rows]


@todo_router.patch("/{todo_id}", response_model=TodoOut)
def update_todo(todo_id: str, payload: TodoUpdate, db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    todo = db.get(Todo, todo_id)
    if todo is None or (todo.assignee_id != principal.user_id and principal.role != "admin"): raise HTTPException(status.HTTP_404_NOT_FOUND, "todo not found")
    todo.status = payload.status
    if payload.status == "completed": todo.completed_at = datetime.now(UTC)
    if payload.status == "completed" and todo.ticket_id:
        ticket = db.get(Ticket, todo.ticket_id)
        if ticket and ticket.status not in {"closed", "cancelled", "rejected"}:
            ticket.status = "completed"
            _notify(db, ticket.requester_id, f"工单“{ticket.subject}”已完成", kind="ticket_completed", ticket_id=ticket.id, todo_id=todo.id)
    _event(db, principal.user_id, "todo_updated", payload.status, todo_id=todo.id, ticket_id=todo.ticket_id)
    db.commit(); db.refresh(todo); return _todo_out(db, todo)


@admin_router.get("/tickets", response_model=list[TicketOut])
def admin_tickets(db: Session = Depends(get_db)):
    return [_ticket_out(db, item) for item in db.query(Ticket).order_by(Ticket.created_at.desc()).all()]


@admin_router.post("/tickets/{ticket_id}/dispatch", response_model=TicketOut)
def admin_dispatch_ticket(ticket_id: str, payload: TicketDispatch, db: Session = Depends(get_db), principal: Principal = Depends(require_admin)):
    """把工单进一步派发给协助部门的具体个人。

    派发后工单处理人变为该员工，发起人与该员工即可在本工单内跨部门沟通；
    管理员始终可以查看他们的通信记录，并可随时标记「已完成」收口。
    """
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ticket not found")
    if ticket.status in {"completed", "closed", "cancelled", "rejected"}:
        raise HTTPException(status.HTTP_409_CONFLICT, "ticket is finished")
    assignee = _user(db, payload.assignee_id)
    if assignee is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assignee not found")
    # 协助人是来帮忙的，不能是提出问题的人自己
    if assignee.id == ticket.requester_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能派发给工单发起人自己")
    # 若工单指定了协助部门，被派发人必须属于该部门
    if ticket.requested_department_id:
        in_dept = db.query(UserDepartment).filter(
            UserDepartment.user_id == assignee.id,
            UserDepartment.department_id == ticket.requested_department_id,
        ).first()
        if in_dept is None:
            requested = db.get(Department, ticket.requested_department_id)
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"{assignee.username} 不属于请求的协助部门（{requested.name if requested else ''}）",
            )
    ticket.target_user_id = assignee.id
    ticket.status = "pending_acceptance"
    ticket.requires_admin = True
    db.flush()
    _event(db, principal.user_id, "dispatched", f"派发给 {assignee.username}", ticket_id=ticket.id)
    _notify(db, assignee.id, f"管理员派发了跨部门协作工单：{ticket.subject}", kind="ticket_assigned", ticket_id=ticket.id)
    db.commit(); db.refresh(ticket)
    return _ticket_out(db, ticket)


@admin_router.post("/todos", response_model=TodoOut, status_code=status.HTTP_201_CREATED)
def admin_create_todo(payload: TodoCreate, db: Session = Depends(get_db), principal: Principal = Depends(require_admin)):
    if _user(db, payload.assignee_id) is None: raise HTTPException(status.HTTP_404_NOT_FOUND, "assignee not found")
    todo = Todo(assignee_id=payload.assignee_id, created_by=principal.user_id, ticket_id=payload.ticket_id, title=payload.title, description=payload.description, due_at=payload.due_at)
    db.add(todo); db.flush(); _event(db, principal.user_id, "todo_created", payload.title, todo_id=todo.id, ticket_id=payload.ticket_id)
    _notify(db, todo.assignee_id, f"管理员分发了新待办：{todo.title}", kind="todo_created", ticket_id=todo.ticket_id, todo_id=todo.id)
    db.commit(); db.refresh(todo); return _todo_out(db, todo)


@admin_router.get("/todos", response_model=list[TodoOut])
def admin_list_todos(db: Session = Depends(get_db)):
    return [_todo_out(db, item) for item in db.query(Todo).order_by(Todo.created_at.desc()).all()]


@admin_router.patch("/todos/{todo_id}", response_model=TodoOut)
def admin_update_todo(todo_id: str, payload: TodoUpdate, db: Session = Depends(get_db), principal: Principal = Depends(require_admin)):
    return update_todo(todo_id, payload, db, principal)


@admin_router.get("/ticket-events", response_model=list[TicketEventOut])
def admin_events(db: Session = Depends(get_db)):
    rows = db.query(TicketEvent).order_by(TicketEvent.created_at.desc()).limit(300).all()
    return [TicketEventOut(id=row.id, ticket_id=row.ticket_id, todo_id=row.todo_id, actor_id=row.actor_id,
        actor_name=_user(db, row.actor_id).username if _user(db, row.actor_id) else "", event_type=row.event_type,
        detail=row.detail, created_at=row.created_at) for row in rows]


@notification_router.get("", response_model=list[NotificationOut])
def list_notifications(db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    rows = db.query(Notification).filter(Notification.recipient_id == principal.user_id).order_by(Notification.created_at.desc()).limit(100).all()
    return [NotificationOut(id=row.id, ticket_id=row.ticket_id, todo_id=row.todo_id, approval_instance_id=row.approval_instance_id, expense_claim_id=row.expense_claim_id, kind=row.kind, content=row.content, read_at=row.read_at, created_at=row.created_at) for row in rows]


@notification_router.patch("/{notification_id}/read", response_model=NotificationOut)
def mark_notification_read(notification_id: str, db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    row = db.get(Notification, notification_id)
    if row is None or row.recipient_id != principal.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "notification not found")
    row.read_at = datetime.now(UTC)
    db.commit(); db.refresh(row)
    return NotificationOut(id=row.id, ticket_id=row.ticket_id, todo_id=row.todo_id, approval_instance_id=row.approval_instance_id, expense_claim_id=row.expense_claim_id, kind=row.kind, content=row.content, read_at=row.read_at, created_at=row.created_at)


@notification_router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
def mark_all_notifications_read(db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    now = datetime.now(UTC)
    db.query(Notification).filter(
        Notification.recipient_id == principal.user_id,
        Notification.read_at.is_(None),
    ).update({Notification.read_at: now}, synchronize_session=False)
    db.commit()
