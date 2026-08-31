"""Rename employee cost_center column to salary (label / semantics)."""

from alembic import op
import sqlalchemy as sa


revision = "0009_rename_cost_center_to_salary"
down_revision = "0008_notification_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("employee_profiles") as batch_op:
        batch_op.alter_column(
            "cost_center",
            new_column_name="salary",
            existing_type=sa.String(length=64),
            existing_nullable=False,
            existing_server_default="",
        )


def downgrade() -> None:
    with op.batch_alter_table("employee_profiles") as batch_op:
        batch_op.alter_column(
            "salary",
            new_column_name="cost_center",
            existing_type=sa.String(length=64),
            existing_nullable=False,
            existing_server_default="",
        )
