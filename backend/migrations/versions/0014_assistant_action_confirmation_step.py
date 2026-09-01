"""Add an atomic confirmation-step counter for assistant actions."""

from alembic import op
import sqlalchemy as sa


revision = "0014_assistant_action_confirmation_step"
down_revision = "0013_assistant_actions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assistant_actions",
        sa.Column("confirmation_step", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("assistant_actions", "confirmation_step")
