"""Initialize the AI ERP migration stream.

The original application creates its legacy tables during bootstrap. This
revision intentionally has no destructive operations; new domain tables are
added by later revisions after their ORM models are introduced.
"""

from alembic import op


revision = "0001_ai_erp_phase1"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
