"""Shared collaboration mutations that never own the surrounding transaction."""

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.deps import Principal
from app.models import Department, Notification, Ticket, TicketEvent, TicketMessage, Todo, User, UserDepartment
from app.schemas import TicketCreate, TicketDispatch, TodoCreate, TodoUpdate


class CollaborationService:
    @staticmethod
    def _user(db: Session, user_id: str | None) -> User | None:
        return db.get(User, user_id) if user_id else None

    @classmethod
    def _admin_user(cls, db: Session) -> User:
        admin = db.query(User).filter(User.role == "admin").order_by(User.created_at).first()
        if admin is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "admin user not configured")
        return admin

    @staticmethod
    def _event(
        db: Session,
        actor_id: str,
        event_type: str,
        detail: str = "",
        *,
        ticket_id: str | None = None,
        todo_id: str | None = None,
    ) -> None:
        db.add(
            TicketEvent(
                actor_id=actor_id,
                event_type=event_type,
                detail=detail,
                ticket_id=ticket_id,
                todo_id=todo_id,
            )
        )

    @staticmethod
    def _notify(
        db: Session,
        recipient_id: str | None,
        content: str,
        *,
        kind: str,
        ticket_id: str | None = None,
        todo_id: str | None = None,
    ) -> None:
        if recipient_id:
            db.add(
                Notification(
                    recipient_id=recipient_id,
                    content=content,
                    kind=kind,
                    ticket_id=ticket_id,
                    todo_id=todo_id,
                )
            )

    @staticmethod
    def _same_department(db: Session, first_user_id: str, second_user_id: str) -> bool:
        return (
            db.query(UserDepartment)
            .filter(
                UserDepartment.user_id == first_user_id,
                UserDepartment.department_id.in_(
                    db.query(UserDepartment.department_id).filter(
                        UserDepartment.user_id == second_user_id
                    )
                ),
            )
            .first()
            is not None
        )

    @classmethod
    def create_ticket(cls, db: Session, payload: TicketCreate, principal: Principal) -> Ticket:
        """Create a ticket with the same routing, event and notification rules as the API."""
        department_id = payload.department_id or principal.department_id
        if department_id not in principal.department_ids:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "department not accessible")

        target_is_admin_sentinel = payload.target_user_id == "admin" or (
            payload.ticket_type == "cross_department" and not payload.target_user_id
        )
        if payload.ticket_type == "same_department" and not payload.target_user_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "同部门协助需要指定处理人")

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
            target = cls._admin_user(db)
            resolved_target_id = target.id
        else:
            target = cls._user(db, payload.target_user_id)
            resolved_target_id = payload.target_user_id
            if payload.target_user_id and target is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "target user not found")

        target_is_admin = bool(target and target.role == "admin")
        if payload.ticket_type == "same_department":
            if target_is_admin:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "同部门协助只能发送给部门员工")
            if target is None or not cls._same_department(db, principal.user_id, target.id):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "同部门协助只能发送给同部门员工")
        if payload.ticket_type == "cross_department" and not target_is_admin:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "跨部门协助只能发送给管理员")

        requires_admin = target_is_admin
        initial_status = "pending_admin" if target_is_admin else (
            "pending_acceptance" if payload.ticket_type in {"same_department", "issue"} else "answered"
        )
        ticket = Ticket(
            requester_id=principal.user_id,
            target_user_id=resolved_target_id,
            department_id=department_id,
            requested_department_id=requested_department_id,
            ticket_type=payload.ticket_type,
            subject=payload.subject,
            description=payload.description,
            status=initial_status,
            requires_admin=requires_admin,
        )
        db.add(ticket)
        db.flush()
        cls._event(db, principal.user_id, "created", payload.subject, ticket_id=ticket.id)
        if payload.description:
            db.add(TicketMessage(ticket_id=ticket.id, sender_id=principal.user_id, content=payload.description))
        if ticket.target_user_id:
            cls._notify(
                db,
                ticket.target_user_id,
                f"{principal.username} 向你发起了工单：{ticket.subject}",
                kind="ticket_assigned",
                ticket_id=ticket.id,
            )
        db.flush()
        return ticket

    @classmethod
    def dispatch_ticket(
        cls, db: Session, ticket: Ticket, payload: TicketDispatch, principal: Principal
    ) -> Ticket:
        """Assign a live ticket to an eligible employee without committing."""
        if not principal.has_role("admin"):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "admin role required")
        if ticket.status in {"completed", "closed", "cancelled", "rejected"}:
            raise HTTPException(status.HTTP_409_CONFLICT, "ticket is finished")
        assignee = cls._user(db, payload.assignee_id)
        if assignee is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "assignee not found")
        if assignee.id == ticket.requester_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能派发给工单发起人自己")
        if ticket.requested_department_id:
            in_department = (
                db.query(UserDepartment)
                .filter(
                    UserDepartment.user_id == assignee.id,
                    UserDepartment.department_id == ticket.requested_department_id,
                )
                .first()
            )
            if in_department is None:
                requested = db.get(Department, ticket.requested_department_id)
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"{assignee.username} 不属于请求的协助部门（{requested.name if requested else ''}）",
                )
        ticket.target_user_id = assignee.id
        ticket.status = "pending_acceptance"
        ticket.requires_admin = True
        cls._event(db, principal.user_id, "dispatched", f"派发给 {assignee.username}", ticket_id=ticket.id)
        cls._notify(
            db,
            assignee.id,
            f"管理员派发了跨部门协作工单：{ticket.subject}",
            kind="ticket_assigned",
            ticket_id=ticket.id,
        )
        db.flush()
        return ticket

    @classmethod
    def create_todo(cls, db: Session, payload: TodoCreate, principal: Principal) -> Todo:
        """Create an administrative todo with its event and recipient notification."""
        if not principal.has_role("admin"):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "admin role required")
        if cls._user(db, payload.assignee_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "assignee not found")
        todo = Todo(
            assignee_id=payload.assignee_id,
            created_by=principal.user_id,
            ticket_id=payload.ticket_id,
            title=payload.title,
            description=payload.description,
            due_at=payload.due_at,
        )
        db.add(todo)
        db.flush()
        cls._event(db, principal.user_id, "todo_created", payload.title, todo_id=todo.id, ticket_id=payload.ticket_id)
        cls._notify(
            db,
            todo.assignee_id,
            f"管理员分发了新待办：{todo.title}",
            kind="todo_created",
            ticket_id=todo.ticket_id,
            todo_id=todo.id,
        )
        db.flush()
        return todo

    @classmethod
    def update_todo(cls, db: Session, todo: Todo, payload: TodoUpdate, principal: Principal) -> Todo:
        """Update an own/admin todo and complete its linked ticket when appropriate."""
        if todo.assignee_id != principal.user_id and not principal.has_role("admin"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "todo not found")
        todo.status = payload.status
        if payload.status == "completed":
            todo.completed_at = datetime.now(UTC)
        if payload.status == "completed" and todo.ticket_id:
            ticket = db.get(Ticket, todo.ticket_id)
            if ticket and ticket.status not in {"closed", "cancelled", "rejected"}:
                ticket.status = "completed"
                cls._notify(
                    db,
                    ticket.requester_id,
                    f"工单“{ticket.subject}”已完成",
                    kind="ticket_completed",
                    ticket_id=ticket.id,
                    todo_id=todo.id,
                )
        cls._event(db, principal.user_id, "todo_updated", payload.status, todo_id=todo.id, ticket_id=todo.ticket_id)
        db.flush()
        return todo

    @staticmethod
    def delete_ticket(db: Session, ticket: Ticket, principal: Principal) -> None:
        """Perform the intentional high-risk hard delete within the caller's transaction."""
        if not principal.has_role("admin"):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "admin role required")
        # Make the declared database cascade/set-null semantics explicit so the
        # action has the same result on SQLite test sessions and production DBs.
        db.query(Notification).filter(Notification.ticket_id == ticket.id).delete(
            synchronize_session=False
        )
        db.query(TicketMessage).filter(TicketMessage.ticket_id == ticket.id).delete(
            synchronize_session=False
        )
        db.query(TicketEvent).filter(TicketEvent.ticket_id == ticket.id).delete(
            synchronize_session=False
        )
        db.query(Todo).filter(Todo.ticket_id == ticket.id).update(
            {Todo.ticket_id: None}, synchronize_session=False
        )
        db.delete(ticket)
        db.flush()
