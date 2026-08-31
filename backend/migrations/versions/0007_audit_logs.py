"""Add immutable business audit log."""

from alembic import op
import sqlalchemy as sa


revision = "0007_audit_logs"
down_revision = "0006_expense_item_details"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("department_id", sa.String(36), sa.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("before_data", sa.JSON(), nullable=False),
        sa.Column("after_data", sa.JSON(), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    for column in ("actor_id", "department_id", "action", "entity_type", "entity_id", "request_id", "created_at"):
        op.create_index(f"ix_audit_logs_{column}", "audit_logs", [column])


def downgrade() -> None:
    op.drop_table("audit_logs")
