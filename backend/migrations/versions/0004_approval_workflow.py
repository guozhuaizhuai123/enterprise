"""Add reusable approval workflow tables and expense approval definition."""

from alembic import op
import sqlalchemy as sa


revision = "0004_approval_workflow"
down_revision = "0003_backfill_employee_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_definitions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(80), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_workflow_definitions_code", "workflow_definitions", ["code"], unique=True)
    op.create_index("ix_workflow_definitions_active", "workflow_definitions", ["active"])

    op.create_table(
        "workflow_nodes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("definition_id", sa.String(36), sa.ForeignKey("workflow_definitions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("assignee_type", sa.String(16), nullable=False),
        sa.Column("assignee_role", sa.String(16), nullable=True),
        sa.Column("department_scoped", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint("assignee_type IN ('manager', 'role')", name="ck_workflow_nodes_assignee_type"),
        sa.UniqueConstraint("definition_id", "sequence", name="uq_workflow_node_sequence"),
    )
    op.create_index("ix_workflow_nodes_definition_id", "workflow_nodes", ["definition_id"])

    op.create_table(
        "approval_instances",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("definition_id", sa.String(36), sa.ForeignKey("workflow_definitions.id"), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("requester_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending_approval"),
        sa.Column("current_node_sequence", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("status IN ('pending_approval', 'approved', 'rejected', 'cancelled')", name="ck_approval_instances_status"),
    )
    for column in ("definition_id", "entity_type", "entity_id", "requester_id", "status"):
        op.create_index(f"ix_approval_instances_{column}", "approval_instances", [column])

    op.create_table(
        "approval_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("instance_id", sa.String(36), sa.ForeignKey("approval_instances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", sa.String(36), sa.ForeignKey("workflow_nodes.id"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("assignee_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("assignee_role", sa.String(16), nullable=True),
        sa.Column("department_id", sa.String(36), sa.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("acted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected', 'cancelled')", name="ck_approval_tasks_status"),
    )
    for column in ("instance_id", "status", "assignee_id", "assignee_role", "department_id"):
        op.create_index(f"ix_approval_tasks_{column}", "approval_tasks", [column])

    op.create_table(
        "approval_actions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("instance_id", sa.String(36), sa.ForeignKey("approval_instances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("approval_tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("comment", sa.String(1000), nullable=False, server_default=""),
        sa.Column("from_status", sa.String(24), nullable=False),
        sa.Column("to_status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("action IN ('submit', 'approve', 'reject', 'cancel')", name="ck_approval_actions_action"),
    )
    op.create_index("ix_approval_actions_instance_id", "approval_actions", ["instance_id"])
    op.create_index("ix_approval_actions_actor_id", "approval_actions", ["actor_id"])

    op.bulk_insert(
        sa.table(
            "workflow_definitions",
            sa.column("id", sa.String),
            sa.column("code", sa.String),
            sa.column("name", sa.String),
            sa.column("version", sa.Integer),
            sa.column("active", sa.Boolean),
        ),
        [{"id": "wf-expense-v1", "code": "expense_reimbursement_v1", "name": "费用报销两级审批", "version": 1, "active": True}],
    )
    op.bulk_insert(
        sa.table(
            "workflow_nodes",
            sa.column("id", sa.String),
            sa.column("definition_id", sa.String),
            sa.column("sequence", sa.Integer),
            sa.column("name", sa.String),
            sa.column("assignee_type", sa.String),
            sa.column("assignee_role", sa.String),
            sa.column("department_scoped", sa.Boolean),
        ),
        [
            {"id": "wf-expense-v1-manager", "definition_id": "wf-expense-v1", "sequence": 1, "name": "直属上级审批", "assignee_type": "manager", "assignee_role": None, "department_scoped": True},
            {"id": "wf-expense-v1-finance", "definition_id": "wf-expense-v1", "sequence": 2, "name": "财务复核", "assignee_type": "role", "assignee_role": "finance", "department_scoped": True},
        ],
    )


def downgrade() -> None:
    op.drop_table("approval_actions")
    op.drop_table("approval_tasks")
    op.drop_table("approval_instances")
    op.drop_table("workflow_nodes")
    op.drop_table("workflow_definitions")
