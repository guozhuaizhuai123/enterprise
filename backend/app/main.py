from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import threading
import time

from app.bootstrap import init_db
from app.db import SessionLocal
from app.models import ApprovalInstance, ApprovalTask, User
from app.payroll.service import PayrollService
from app.workflow.service import WorkflowService
from app.routers import admin, approvals, auth, chat, dashboard, expenses, kb, memory, organization, payroll, projects, schedule, tickets

app = FastAPI(title="企业智能检索系统")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(kb.router)
app.include_router(chat.router)
app.include_router(memory.me_router)
app.include_router(memory.admin_memory_router)
app.include_router(schedule.me_router)
app.include_router(schedule.admin_router)
app.include_router(tickets.employee_router)
app.include_router(tickets.todo_router)
app.include_router(tickets.notification_router)
app.include_router(tickets.admin_router)
app.include_router(organization.admin_router)
app.include_router(organization.me_router)
app.include_router(approvals.router)
app.include_router(expenses.router)
app.include_router(expenses.admin_router)
app.include_router(dashboard.router)
app.include_router(projects.project_router)
app.include_router(projects.contract_router)
app.include_router(payroll.router)


@app.on_event("startup")
def on_startup() -> None:
    from app.config import get_settings

    get_settings().require_runtime_secrets()
    init_db()
    from app.assistant.adapters import install_production_adapters
    install_production_adapters()
    thread = threading.Thread(target=_payroll_loop, name="payroll-scheduler", daemon=True)
    thread.start()


def _payroll_loop() -> None:
    # A small built-in scheduler keeps the development deployment self-contained.
    while True:
        db = SessionLocal()
        try:
            admin = db.query(User).filter(User.role == "admin").first()
            if admin:
                _process_internal_expense_approvals(db, admin.id)
                PayrollService.generate_due_runs(db, admin.id)
                db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
        time.sleep(60)


def _process_internal_expense_approvals(db, actor_id: str) -> None:
    """审批中心已内置化：后台按既有审批节点完成普通费用单流转。"""
    instances = db.query(ApprovalInstance).filter(
        ApprovalInstance.entity_type == "expense_claim",
        ApprovalInstance.status == "pending_approval",
    ).all()
    for instance in instances:
        while instance.status == "pending_approval":
            task = db.query(ApprovalTask).filter(
                ApprovalTask.instance_id == instance.id,
                ApprovalTask.status == "pending",
            ).order_by(ApprovalTask.sequence).first()
            if task is None:
                break
            # 有明确的直属上级时使用该任务的指派账号；角色任务则由系统管理员完成。
            task_actor_id = task.assignee_id or actor_id
            WorkflowService.act(db, instance.id, task_actor_id, "approve", "系统自动审核费用单", instance.version)


@app.get("/health")
def health():
    return {"status": "ok"}
