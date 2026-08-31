"""Creates the tables and a default admin account on first startup."""
from app.config import get_settings
from app.db import Base, SessionLocal, engine
from app.agents.sensitive_gate import SENSITIVE_KEYWORDS
from app.models import (
    Document,
    EmployeeProfile,
    Message,
    MessageContextFlag,
    SensitiveEvent,
    SensitiveKeyword,
    Thread,
    User,
    UserDepartment,
    UserRole,
    PayrollSetting,
)
from app.security import hash_password
from app.workflow.service import WorkflowService
from sqlalchemy import inspect, text

settings = get_settings()


def _set_context_excluded(db, message_id: str) -> None:
    flag = db.get(MessageContextFlag, message_id)
    if flag is None:
        db.add(
            MessageContextFlag(
                message_id=message_id,
                context_eligible=False,
                reason="sensitive_blocked",
            )
        )
    else:
        flag.context_eligible = False
        flag.reason = "sensitive_blocked"


def _backfill_sensitive_context_flags(db) -> None:
    for event in db.query(SensitiveEvent).filter(SensitiveEvent.user_id.is_not(None)).all():
        messages = (
            db.query(Message)
            .join(Thread, Message.thread_id == Thread.id)
            .filter(
                Thread.user_id == event.user_id,
                Message.role == "user",
                Message.content == event.question,
            )
            .all()
        )
        for message in messages:
            _set_context_excluded(db, message.id)

            # Only this exact pipeline-generated text proves an assistant was a
            # sensitive block. Never infer a companion from adjacency alone.
            blocked_answer = f"该问题涉及敏感信息，{event.reason}，不由系统自动作答。"
            companions = (
                db.query(Message)
                .filter(
                    Message.thread_id == message.thread_id,
                    Message.role == "assistant",
                    Message.content == blocked_answer,
                )
                .all()
            )
            for companion in companions:
                _set_context_excluded(db, companion.id)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)

    # create_all does not alter an existing SQLite table, so add ownership
    # columns explicitly for databases created before document ownership.
    existing_columns = {column["name"] for column in inspect(engine).get_columns("documents")}

    # 跨部门协助需要记录「请求的协助部门」，为既有库补上该列。
    ticket_columns = {column["name"] for column in inspect(engine).get_columns("tickets")}
    if "requested_department_id" not in ticket_columns:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE tickets ADD COLUMN requested_department_id VARCHAR(36) "
                    "REFERENCES departments(id) ON DELETE SET NULL"
                )
            )
    with engine.begin() as connection:
        if "owner_id" not in existing_columns:
            connection.execute(
                text(
                    "ALTER TABLE documents ADD COLUMN owner_id VARCHAR(36) "
                    "REFERENCES users(id) ON DELETE SET NULL"
                )
            )
        if "owner_name" not in existing_columns:
            connection.execute(
                text("ALTER TABLE documents ADD COLUMN owner_name VARCHAR(64) NOT NULL DEFAULT ''")
            )
        if "project_id" not in existing_columns:
            connection.execute(
                text(
                    "ALTER TABLE documents ADD COLUMN project_id VARCHAR(36) "
                    "REFERENCES projects(id) ON DELETE SET NULL"
                )
            )
        if "contract_id" not in existing_columns:
            connection.execute(
                text(
                    "ALTER TABLE documents ADD COLUMN contract_id VARCHAR(36) "
                    "REFERENCES contracts(id) ON DELETE SET NULL"
                )
            )

    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.role == "admin").first()
        if admin is None:
            admin = User(
                username=settings.bootstrap_admin_username,
                password_encrypted=hash_password(settings.bootstrap_admin_password),
                role="admin",
                department_id=None,
            )
            db.add(admin)
            db.flush()

        # Existing documents belong to the bootstrap admin unless ownership
        # was already assigned by a previous run.
        db.query(Document).filter(Document.owner_id.is_(None)).update(
            {Document.owner_id: admin.id}, synchronize_session=False
        )
        db.query(Document).filter(
            (Document.owner_name.is_(None)) | (Document.owner_name == "")
        ).update({Document.owner_name: admin.username}, synchronize_session=False)

        # Seed the editable keyword list once. An empty table means this is
        # the first run; later deletions are intentional and must persist.
        if db.query(SensitiveKeyword).count() == 0:
            for keyword in SENSITIVE_KEYWORDS:
                db.add(SensitiveKeyword(keyword=keyword, updated_by=admin.id))

        # Backfill memberships for databases created before multi-department access.
        for user in db.query(User).filter(User.department_id.is_not(None)).all():
            membership = db.get(UserDepartment, (user.id, user.department_id))
            if membership is None:
                membership = UserDepartment(user_id=user.id, department_id=user.department_id)
                db.add(membership)
            membership.is_primary = True

        # Legacy accounts must immediately appear in the organization directory.
        for user in db.query(User).all():
            if db.get(EmployeeProfile, user.id) is None:
                db.add(
                    EmployeeProfile(
                        user_id=user.id,
                        full_name=user.username,
                        status="active",
                    )
                )
            if user.role == "employee" and not db.query(UserRole).filter(
                UserRole.user_id == user.id,
                UserRole.role == "employee",
            ).first():
                db.add(UserRole(user_id=user.id, role="employee"))
            if user.role == "admin" and not db.query(UserRole).filter(
                UserRole.user_id == user.id, UserRole.role == "finance"
            ).first():
                db.add(UserRole(user_id=user.id, role="finance"))

        # Sensitive content predating context flags must never be reintroduced
        # through history, query rewriting, or summaries. Match only user
        # messages in threads owned by the event's known user.
        _backfill_sensitive_context_flags(db)
        WorkflowService.ensure_default_definitions(db)
        if db.query(PayrollSetting).count() == 0:
            db.add(PayrollSetting(id="default", auto_enabled=True, pay_day=10, generation_lead_days=5))
        db.commit()
    finally:
        db.close()
