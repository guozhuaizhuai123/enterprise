"""Link notifications to approval and expense detail pages."""

from alembic import op
import sqlalchemy as sa


revision = "0008_notification_links"
down_revision = "0007_audit_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notifications", sa.Column("approval_instance_id", sa.String(36), nullable=True))
    op.add_column("notifications", sa.Column("expense_claim_id", sa.String(36), nullable=True))
    op.create_index("ix_notifications_approval_instance_id", "notifications", ["approval_instance_id"])
    op.create_index("ix_notifications_expense_claim_id", "notifications", ["expense_claim_id"])


def downgrade() -> None:
    op.drop_index("ix_notifications_expense_claim_id", table_name="notifications")
    op.drop_index("ix_notifications_approval_instance_id", table_name="notifications")
    op.drop_column("notifications", "expense_claim_id")
    op.drop_column("notifications", "approval_instance_id")
