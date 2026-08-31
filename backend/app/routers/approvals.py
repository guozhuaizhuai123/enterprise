from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import Principal, get_current_principal
from app.models import (
    ApprovalAction,
    ApprovalInstance,
    ApprovalTask,
    EmployeeProfile,
    ExpenseClaim,
    User,
    UserRole,
    WorkflowDefinition,
    WorkflowNode,
)
from app.schemas import (
    ApprovalActionOut,
    ApprovalDecisionIn,
    ApprovalHandlerOut,
    ApprovalHistoryItemOut,
    ApprovalInstanceOut,
    ApprovalRouteStepOut,
    ApprovalTaskOut,
)
from app.workflow.service import WorkflowService


router = APIRouter(prefix="/approvals", tags=["approvals"])


def _handler_out(db: Session, user_id: str) -> ApprovalHandlerOut | None:
    user = db.get(User, user_id)
    if user is None:
        return None
    profile = db.get(EmployeeProfile, user.id)
    return ApprovalHandlerOut(
        id=user.id,
        username=user.username,
        display_name=(profile.full_name if profile and profile.full_name else user.username),
    )


def _role_handlers(
    db: Session,
    role: str,
    department_id: str | None,
) -> list[ApprovalHandlerOut]:
    query = db.query(UserRole).filter(UserRole.role == role)
    if department_id:
        query = query.filter(
            or_(
                UserRole.department_id == department_id,
                UserRole.department_id.is_(None),
            )
        )
    user_ids = list(dict.fromkeys(row.user_id for row in query.all()))
    handlers = [_handler_out(db, user_id) for user_id in user_ids]
    return sorted(
        [handler for handler in handlers if handler is not None],
        key=lambda handler: handler.username,
    )


def _approval_route(
    db: Session,
    instance: ApprovalInstance,
    tasks: list[ApprovalTask],
) -> list[ApprovalRouteStepOut]:
    requester = _handler_out(db, instance.requester_id)
    requester_department = WorkflowService._requester_department(db, instance.requester_id)
    task_by_sequence = {task.sequence: task for task in tasks}
    route = [
        ApprovalRouteStepOut(
            sequence=0,
            name="提交申请",
            status="approved",
            handlers=[requester] if requester else [],
        )
    ]
    nodes = (
        db.query(WorkflowNode)
        .filter(WorkflowNode.definition_id == instance.definition_id)
        .order_by(WorkflowNode.sequence)
        .all()
    )
    requester_profile = db.get(EmployeeProfile, instance.requester_id)
    for node in nodes:
        task = task_by_sequence.get(node.sequence)
        if task and task.assignee_id:
            handler = _handler_out(db, task.assignee_id)
            handlers = [handler] if handler else []
        elif node.assignee_type == "manager" and requester_profile and requester_profile.manager_id:
            handler = _handler_out(db, requester_profile.manager_id)
            handlers = [handler] if handler else []
        elif node.assignee_type == "role" and node.assignee_role:
            handlers = _role_handlers(
                db,
                node.assignee_role,
                requester_department if node.department_scoped else None,
            )
        else:
            handlers = []
        route.append(
            ApprovalRouteStepOut(
                sequence=node.sequence,
                name=node.name,
                status=task.status if task else "upcoming",
                handlers=handlers,
            )
        )

    if instance.entity_type == "expense_claim":
        claim = db.get(ExpenseClaim, instance.entity_id)
        payment_status = (
            "approved" if claim and claim.status == "paid"
            else "pending" if claim and claim.status == "payment_pending"
            else "cancelled" if claim and claim.status in {"rejected", "cancelled"}
            else "upcoming"
        )
        route.append(
            ApprovalRouteStepOut(
                sequence=(nodes[-1].sequence + 1) if nodes else 1,
                name="财务付款",
                status=payment_status,
                handlers=_role_handlers(db, "finance", requester_department),
            )
        )
    return route


def _task_out(db: Session, task: ApprovalTask) -> ApprovalTaskOut:
    instance = db.get(ApprovalInstance, task.instance_id)
    node = db.get(WorkflowNode, task.node_id)
    requester = db.get(User, instance.requester_id)
    return ApprovalTaskOut(
        id=task.id,
        instance_id=task.instance_id,
        entity_type=instance.entity_type,
        entity_id=instance.entity_id,
        requester_id=instance.requester_id,
        requester_name=requester.username if requester else "",
        node_name=node.name if node else "审批",
        sequence=task.sequence,
        status=task.status,
        assignee_id=task.assignee_id,
        assignee_role=task.assignee_role,
        department_id=task.department_id,
        instance_status=instance.status,
        version=instance.version,
        created_at=task.created_at,
        acted_at=task.acted_at,
    )


def _instance_out(
    db: Session,
    instance: ApprovalInstance,
    principal: Principal | None = None,
) -> ApprovalInstanceOut:
    definition = db.get(WorkflowDefinition, instance.definition_id)
    requester = db.get(User, instance.requester_id)
    tasks = (
        db.query(ApprovalTask)
        .filter(ApprovalTask.instance_id == instance.id)
        .order_by(ApprovalTask.sequence)
        .all()
    )
    actions = (
        db.query(ApprovalAction)
        .filter(ApprovalAction.instance_id == instance.id)
        .order_by(ApprovalAction.created_at, ApprovalAction.id)
        .all()
    )
    pending_task = next((task for task in tasks if task.status == "pending"), None)
    can_process = bool(
        principal
        and pending_task
        and WorkflowService._actor_can_process(db, pending_task, principal.user_id)
    )
    return ApprovalInstanceOut(
        id=instance.id,
        workflow_code=definition.code if definition else "",
        workflow_name=definition.name if definition else "",
        entity_type=instance.entity_type,
        entity_id=instance.entity_id,
        requester_id=instance.requester_id,
        requester_name=requester.username if requester else "",
        status=instance.status,
        current_node_sequence=instance.current_node_sequence,
        version=instance.version,
        submitted_at=instance.submitted_at,
        completed_at=instance.completed_at,
        updated_at=instance.updated_at,
        tasks=[_task_out(db, task) for task in tasks],
        actions=[
            ApprovalActionOut(
                id=action.id,
                task_id=action.task_id,
                actor_id=action.actor_id,
                actor_name=(db.get(User, action.actor_id).username if db.get(User, action.actor_id) else ""),
                action=action.action,
                comment=action.comment,
                from_status=action.from_status,
                to_status=action.to_status,
                created_at=action.created_at,
            )
            for action in actions
        ],
        approval_route=_approval_route(db, instance, tasks),
        can_approve=can_process,
        can_reject=can_process,
        can_cancel=bool(
            principal
            and instance.status == "pending_approval"
            and instance.requester_id == principal.user_id
        ),
    )


def _can_view(db: Session, instance: ApprovalInstance, principal: Principal) -> bool:
    if instance.requester_id == principal.user_id or principal.has_role("admin", "hr"):
        return True
    return any(
        task.instance_id == instance.id
        for task in WorkflowService.list_inbox(db, principal)
    ) or (
        db.query(ApprovalTask)
        .filter(
            ApprovalTask.instance_id == instance.id,
            ApprovalTask.assignee_id == principal.user_id,
        )
        .first()
        is not None
    )


@router.get("/inbox", response_model=list[ApprovalTaskOut])
def approval_inbox(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return [_task_out(db, task) for task in WorkflowService.list_inbox(db, principal)]


@router.get("/submitted", response_model=list[ApprovalInstanceOut])
def submitted_approvals(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    rows = (
        db.query(ApprovalInstance)
        .filter(ApprovalInstance.requester_id == principal.user_id)
        .order_by(ApprovalInstance.submitted_at.desc())
        .all()
    )
    return [_instance_out(db, instance, principal) for instance in rows]


@router.get("/history", response_model=list[ApprovalHistoryItemOut])
def approval_history(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """“我的审批历史”：只返回当前用户亲自处理过的审批动作。

    动作本人天然可见，因此无需走 `_can_view`（它对每条记录都会重算一次
    待办归属，历史列表里属于无谓开销）。
    """
    rows = (
        db.query(ApprovalAction)
        .join(ApprovalInstance, ApprovalInstance.id == ApprovalAction.instance_id)
        .filter(
            ApprovalAction.actor_id == principal.user_id,
            ApprovalAction.action.in_(("approve", "reject", "cancel")),
        )
        .order_by(ApprovalAction.created_at.desc(), ApprovalAction.id.desc())
        .all()
    )
    items: list[ApprovalHistoryItemOut] = []
    for action in rows:
        instance = db.get(ApprovalInstance, action.instance_id)
        if instance is None:
            continue
        task = db.get(ApprovalTask, action.task_id) if action.task_id else None
        node = db.get(WorkflowNode, task.node_id) if task else None
        requester = db.get(User, instance.requester_id)
        actor = db.get(User, action.actor_id)
        items.append(
            ApprovalHistoryItemOut(
                id=action.id,
                instance_id=instance.id,
                entity_type=instance.entity_type,
                entity_id=instance.entity_id,
                node_name=node.name if node else "审批",
                sequence=task.sequence if task else 0,
                requester_id=instance.requester_id,
                requester_name=requester.username if requester else "",
                action=action.action,
                comment=action.comment,
                actor_name=actor.username if actor else "",
                from_status=action.from_status,
                to_status=action.to_status,
                instance_status=instance.status,
                created_at=action.created_at,
            )
        )
    return items


@router.get("/{instance_id}", response_model=ApprovalInstanceOut)
def approval_detail(
    instance_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    instance = db.get(ApprovalInstance, instance_id)
    if instance is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "approval instance not found")
    if not _can_view(db, instance, principal):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "approval is outside your scope")
    return _instance_out(db, instance, principal)


def _act(
    instance_id: str,
    action: str,
    payload: ApprovalDecisionIn,
    db: Session,
    principal: Principal,
) -> ApprovalInstanceOut:
    instance = WorkflowService.act(
        db,
        instance_id,
        principal.user_id,
        action,
        payload.comment,
        payload.expected_version,
    )
    db.commit()
    db.refresh(instance)
    return _instance_out(db, instance, principal)


@router.post("/{instance_id}/approve", response_model=ApprovalInstanceOut)
def approve(
    instance_id: str,
    payload: ApprovalDecisionIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return _act(instance_id, "approve", payload, db, principal)


@router.post("/{instance_id}/reject", response_model=ApprovalInstanceOut)
def reject(
    instance_id: str,
    payload: ApprovalDecisionIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return _act(instance_id, "reject", payload, db, principal)


@router.post("/{instance_id}/cancel", response_model=ApprovalInstanceOut)
def cancel(
    instance_id: str,
    payload: ApprovalDecisionIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return _act(instance_id, "cancel", payload, db, principal)
