"""Add project, vendor, invoice, and tax fields to expenses."""

from alembic import op
import sqlalchemy as sa


revision = "0006_expense_item_details"
down_revision = "0005_expense_reimbursement"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("expense_claims", sa.Column("project_code", sa.String(80), nullable=False, server_default=""))
    op.add_column("expense_items", sa.Column("vendor", sa.String(120), nullable=False, server_default=""))
    op.add_column("expense_items", sa.Column("invoice_no", sa.String(100), nullable=False, server_default=""))
    op.add_column("expense_items", sa.Column("tax_amount", sa.Numeric(12, 2), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("expense_items", "tax_amount")
    op.drop_column("expense_items", "invoice_no")
    op.drop_column("expense_items", "vendor")
    op.drop_column("expense_claims", "project_code")
