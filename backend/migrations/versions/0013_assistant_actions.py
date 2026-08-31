"""Add persisted assistant action previews and execution state."""

from alembic import op
import sqlalchemy as sa


revision = "0013_assistant_actions"
down_revision = "0012_payroll"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_actions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("thread_id", sa.String(length=36), nullable=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("tool_name", sa.String(length=100), nullable=False),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("preview_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("parameter_hash", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("object_versions_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("confirmation_phrase", sa.String(length=200), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_assistant_actions_user_idempotency_key"),
    )
    op.create_index(
        "ix_assistant_actions_user_thread_status",
        "assistant_actions",
        ["user_id", "thread_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_assistant_actions_user_thread_status", table_name="assistant_actions")
    op.drop_table("assistant_actions")
