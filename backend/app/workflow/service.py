from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.deps import Principal
from app.models import (
    ApprovalAction,
    ApprovalInstance,
    ApprovalTask,
    EmployeeProfile,
    ExpenseClaim,
    Notification,
    User,
    UserDepartment,
    UserRole,
    PayrollRun,
    WorkflowDefinition,
    WorkflowNode,
)
from app.audit.service import AuditService


def _now() -> datetime:
    return datetime.now(UTC)


class WorkflowService:
    @staticmethod
    def ensure_default_definitions(db: Session) -> WorkflowDefinition:
        definition = (
            db.query(WorkflowDefinition)
            .filter(WorkflowDefinition.code == "expense_reimbursement_v1")
            .one_or_none()
        )
        if definition is None:
            definition = WorkflowDefinition(
                code="expense_reimbursement_v1",
                name="费用报销两级审批",
                version=1,
                active=True,
            )
            db.add(definition)
            db.flush()
            db.add_all(
                [
                    WorkflowNode(
                        definition_id=definition.id,
                        sequence=1,
                        name="直属上级审批",
                        assignee_type="manager",
                        department_scoped=True,
                    ),
                    WorkflowNode(
                        definition_id=definition.id,
                        sequence=2,
                        name="财务复核",
                        assignee_type="role",
                        assignee_role="finance",
                        department_scoped=True,
                    ),
                ]
            )
            db.flush()

        payroll = db.query(WorkflowDefinition).filter(WorkflowDefinition.code == "payroll_approval_v1").one_or_none()
        if payroll is None:
            payroll = WorkflowDefinition(code="payroll_approval_v1", name="工资发放财务审批", version=1, active=True)
            db.add(payroll)
            db.flush()
            db.add(WorkflowNode(
                definition_id=payroll.id,
                sequence=1,
                name="财务审批",
                assignee_type="role",
                assignee_role="finance",
                department_scoped=False,
            ))
            db.flush()
        return definition

    @staticmethod
    def _requester_department(db: Session, requester_id: str) -> str | None:
        membership = (
            db.query(UserDepartment)
            .filter(
                UserDepartment.user_id == requester_id,
                UserDepartment.is_primary.is_(True),
            )
            .first()
        )
        if membership is not None:
            return membership.department_id
        user = db.get(User, requester_id)
        return user.department_id if user else None

    @staticmethod
    def _create_task(
        db: Session,
        instance: ApprovalInstance,
        node: WorkflowNode,
    ) -> ApprovalTask:
        assignee_id: str | None = None
        assignee_role: str | None = None
        department_id = WorkflowService._requester_department(db, instance.requester_id)
        if node.assignee_type == "manager":
            profile = db.get(EmployeeProfile, instance.requester_id)
            assignee_id = profile.manager_id if profile else None
            if not assignee_id:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "requester has no direct manager configured",
                )
            if assignee_id == instance.requester_id:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "requester cannot approve own request",
                )
        elif node.assignee_type == "role":
            assignee_role = node.assignee_role
        else:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "invalid workflow node")
        task = ApprovalTask(
            instance_id=instance.id,
            node_id=node.id,
            sequence=node.sequence,
            assignee_id=assignee_id,
            assignee_role=assignee_role,
            department_id=department_id if node.department_scoped else None,
        )
        db.add(task)
        db.flush()
        WorkflowService._notify_assignees(db, task)
        return task

    @staticmethod
    def _notify_assignees(db: Session, task: ApprovalTask) -> None:
        recipient_ids: set[str] = set()
        if task.assignee_id:
            recipient_ids.add(task.assignee_id)
        elif task.assignee_role:
            role_rows = db.query(UserRole).filter(UserRole.role == task.assignee_role)
            if task.department_id:
                role_rows = role_rows.filter(
                    or_(
                        UserRole.department_id == task.department_id,
                        UserRole.department_id.is_(None),
                    )
                )
            recipient_ids.update(row.user_id for row in role_rows.all())
        for recipient_id in recipient_ids:
            db.add(
                Notification(
                    recipient_id=recipient_id,
                    kind="approval_assigned",
                    content="你有一条新的审批任务待处理",
                    approval_instance_id=task.instance_id,
                )
            )

    @staticmethod
    def start(
        db: Session,
        entity_type: str,
        entity_id: str,
        requester_id: str,
        workflow_code: str,
    ) -> ApprovalInstance:
        duplicate = (
            db.query(ApprovalInstance)
            .filter(
                ApprovalInstance.entity_type == entity_type,
                ApprovalInstance.entity_id == entity_id,
                ApprovalInstance.status == "pending_approval",
            )
            .first()
        )
        if duplicate is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "entity already has an active approval")
        definition = (
            db.query(WorkflowDefinition)
            .filter(
                WorkflowDefinition.code == workflow_code,
                WorkflowDefinition.active.is_(True),
            )
            .one_or_none()
        )
        if definition is None:
            if workflow_code == "expense_reimbursement_v1":
                definition = WorkflowService.ensure_default_definitions(db)
            else:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "workflow definition not found")
        first_node = (
            db.query(WorkflowNode)
            .filter(WorkflowNode.definition_id == definition.id)
            .order_by(WorkflowNode.sequence)
            .first()
        )
        if first_node is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "workflow has no approval nodes")
        instance = ApprovalInstance(
            definition_id=definition.id,
            entity_type=entity_type,
            entity_id=entity_id,
            requester_id=requester_id,
            status="pending_approval",
            current_node_sequence=first_node.sequence,
            version=1,
        )
        db.add(instance)
        db.flush()
        WorkflowService._create_task(db, instance, first_node)
        db.add(
            ApprovalAction(
                instance_id=instance.id,
                actor_id=requester_id,
                action="submit",
                comment="提交审批",
                from_status="draft",
                to_status="pending_approval",
            )
        )
        return instance

    @staticmethod
    def _actor_can_process(db: Session, task: ApprovalTask, actor_id: str) -> bool:
        if task.assignee_id:
            return task.assignee_id == actor_id
        if not task.assignee_role:
            return False
        actor = db.get(User, actor_id)
        if actor is None:
            return False
        if actor.role == "admin" and task.assignee_role in {"finance", "hr", "manager"}:
            return True
        if actor.role == task.assignee_role and (
            task.department_id is None or actor.department_id == task.department_id
        ):
            return True
        query = db.query(UserRole).filter(
            UserRole.user_id == actor_id,
            UserRole.role == task.assignee_role,
        )
        if task.department_id:
            query = query.filter(
                or_(
                    UserRole.department_id == task.department_id,
                    UserRole.department_id.is_(None),
                )
            )
        return query.first() is not None

    @staticmethod
    def act(
        db: Session,
        instance_id: str,
        actor_id: str,
        action: str,
        comment: str,
        expected_version: int,
    ) -> ApprovalInstance:
        instance = db.get(ApprovalInstance, instance_id)
        if instance is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "approval instance not found")
        if instance.version != expected_version:
            raise HTTPException(status.HTTP_409_CONFLICT, "approval version is stale")
        if instance.status != "pending_approval":
            raise HTTPException(status.HTTP_409_CONFLICT, "approval is already completed")

        task = (
            db.query(ApprovalTask)
            .filter(
                ApprovalTask.instance_id == instance.id,
                ApprovalTask.status == "pending",
            )
            .order_by(ApprovalTask.sequence)
            .first()
        )
        from_status = instance.status
        if action == "cancel":
            if actor_id != instance.requester_id:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "only requester can cancel")
            if task:
                task.status = "cancelled"
                task.acted_at = _now()
            instance.status = "cancelled"
            instance.completed_at = _now()
        elif action in {"approve", "reject"}:
            if task is None:
                raise HTTPException(status.HTTP_409_CONFLICT, "no pending approval task")
            if not WorkflowService._actor_can_process(db, task, actor_id):
                raise HTTPException(status.HTTP_403_FORBIDDEN, "actor is not assigned to this task")
            task.status = "approved" if action == "approve" else "rejected"
            task.acted_at = _now()
            if action == "reject":
                instance.status = "rejected"
                instance.completed_at = _now()
            else:
                next_node = (
                    db.query(WorkflowNode)
                    .filter(
                        WorkflowNode.definition_id == instance.definition_id,
                        WorkflowNode.sequence > task.sequence,
                    )
                    .order_by(WorkflowNode.sequence)
                    .first()
                )
                if next_node is None:
                    instance.status = "approved"
                    instance.completed_at = _now()
                else:
                    instance.current_node_sequence = next_node.sequence
                    WorkflowService._create_task(db, instance, next_node)
        else:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid approval action")

        instance.version += 1
        instance.updated_at = _now()
        if instance.entity_type == "expense_claim":
            # Local import avoids coupling the generic workflow module at import time.
            from app.expense.service import ExpenseService

            ExpenseService.sync_from_approval(db, instance)
        elif instance.entity_type == "payroll_run":
            run = db.get(PayrollRun, instance.entity_id)
            if run is not None:
                next_run_status = {
                    "pending_approval": "pending_approval",
                    "approved": "approved",
                    "rejected": "rejected",
                    "cancelled": "rejected",
                }.get(instance.status, run.status)
                run.status = next_run_status
                if run.expense_claim_id:
                    claim = db.get(ExpenseClaim, run.expense_claim_id)
                    if claim is not None:
                        claim.status = "payment_pending" if instance.status == "approved" else (
                            "rejected" if instance.status in {"rejected", "cancelled"} else "pending_approval"
                        )
                        claim.version += 1
        AuditService.record(
            db,
            actor_id,
            f"approval.{action}",
            "approval_instance",
            instance.id,
            {"status": from_status, "version": expected_version},
            {"status": instance.status, "version": instance.version, "comment": comment},
        )
        db.add(
            ApprovalAction(
                instance_id=instance.id,
                # 撤回也记录被终止的那一步，便于在审批历史里看出是在哪个环节撤下的。
                task_id=task.id if task else None,
                actor_id=actor_id,
                action=action,
                comment=comment,
                from_status=from_status,
                to_status=instance.status,
            )
        )
        db.add(
            Notification(
                recipient_id=instance.requester_id,
                kind=f"approval_{action}",
                content=f"你的审批已执行操作：{action}",
                approval_instance_id=instance.id,
            )
        )
        db.flush()
        return instance

    @staticmethod
    def list_inbox(db: Session, principal: Principal) -> list[ApprovalTask]:
        effective_roles = set(principal.roles) | {principal.role}
        role_rows = (
            db.query(UserRole)
            .filter(
                UserRole.user_id == principal.user_id,
                UserRole.role.in_(effective_roles),
            )
            .all()
        )
        global_roles = {row.role for row in role_rows if row.department_id is None}
        scoped_departments: dict[str, set[str]] = {}
        for row in role_rows:
            if row.department_id is not None:
                scoped_departments.setdefault(row.role, set()).add(row.department_id)

        role_filters = []
        for role in effective_roles:
            if role in global_roles:
                role_filters.append(ApprovalTask.assignee_role == role)
                continue

            allowed_departments = set(principal.department_ids)
            allowed_departments.update(scoped_departments.get(role, set()))
            role_filters.append(
                and_(
                    ApprovalTask.assignee_role == role,
                    or_(
                        ApprovalTask.department_id.is_(None),
                        ApprovalTask.department_id.in_(allowed_departments or {""}),
                    ),
                )
            )
        ownership = [ApprovalTask.assignee_id == principal.user_id, *role_filters]
        return (
            db.query(ApprovalTask)
            .join(ApprovalInstance, ApprovalInstance.id == ApprovalTask.instance_id)
            .filter(
                ApprovalTask.status == "pending",
                ApprovalInstance.status == "pending_approval",
                or_(*ownership),
            )
            .order_by(ApprovalTask.created_at.desc())
            .all()
        )
