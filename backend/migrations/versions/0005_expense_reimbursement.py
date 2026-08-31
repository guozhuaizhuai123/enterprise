"""Add expense claims, receipt assets, and payment records."""

from alembic import op
import sqlalchemy as sa


revision = "0005_expense_reimbursement"
down_revision = "0004_approval_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "expense_claims",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("claim_no", sa.String(40), nullable=False, unique=True),
        sa.Column("requester_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("department_id", sa.String(36), sa.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("purpose", sa.String(1000), nullable=False, server_default=""),
        sa.Column("currency", sa.String(3), nullable=False, server_default="CNY"),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("approval_instance_id", sa.String(36), sa.ForeignKey("approval_instances.id", ondelete="SET NULL"), nullable=True, unique=True),
        sa.Column("submission_key", sa.String(100), nullable=True, unique=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("status IN ('draft', 'pending_approval', 'rejected', 'payment_pending', 'paid', 'cancelled')", name="ck_expense_claims_status"),
        sa.CheckConstraint("total_amount >= 0", name="ck_expense_claims_total_amount"),
    )
    for column in ("claim_no", "requester_id", "department_id", "status"):
        op.create_index(f"ix_expense_claims_{column}", "expense_claims", [column], unique=column == "claim_no")

    op.create_table(
        "expense_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("claim_id", sa.String(36), sa.ForeignKey("expense_claims.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expense_date", sa.Date(), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("description", sa.String(500), nullable=False, server_default=""),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("amount > 0", name="ck_expense_items_amount"),
    )
    op.create_index("ix_expense_items_claim_id", "expense_items", ["claim_id"])
    op.create_index("ix_expense_items_expense_date", "expense_items", ["expense_date"])

    op.create_table(
        "file_assets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("storage_key", sa.String(120), nullable=False, unique=True),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_file_assets_owner_id", "file_assets", ["owner_id"])
    op.create_index("ix_file_assets_sha256", "file_assets", ["sha256"])

    op.create_table(
        "expense_attachments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("claim_id", sa.String(36), sa.ForeignKey("expense_claims.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_id", sa.String(36), sa.ForeignKey("file_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("claim_id", "file_id", name="uq_expense_attachment_file"),
    )
    op.create_index("ix_expense_attachments_claim_id", "expense_attachments", ["claim_id"])
    op.create_index("ix_expense_attachments_file_id", "expense_attachments", ["file_id"])

    op.create_table(
        "payment_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("claim_id", sa.String(36), sa.ForeignKey("expense_claims.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("paid_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="CNY"),
        sa.Column("method", sa.String(32), nullable=False),
        sa.Column("reference", sa.String(100), nullable=False, server_default=""),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("amount > 0", name="ck_payment_records_amount"),
    )
    op.create_index("ix_payment_records_claim_id", "payment_records", ["claim_id"], unique=True)
    op.create_index("ix_payment_records_paid_by", "payment_records", ["paid_by"])


def downgrade() -> None:
    op.drop_table("payment_records")
    op.drop_table("expense_attachments")
    op.drop_table("file_assets")
    op.drop_table("expense_items")
    op.drop_table("expense_claims")
