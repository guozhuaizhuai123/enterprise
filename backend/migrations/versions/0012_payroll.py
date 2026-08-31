"""Add payroll settings, runs, and salary snapshots."""

from alembic import op
import sqlalchemy as sa


revision = "0012_payroll"
down_revision = "0011_project_contract_document_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payroll_settings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("auto_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("pay_day", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("generation_lead_days", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="CNY"),
        sa.Column("approval_role", sa.String(length=16), nullable=False, server_default="finance"),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_table(
        "payroll_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("period", sa.String(length=7), nullable=False),
        sa.Column("pay_date", sa.Date(), nullable=False),
        sa.Column("generation_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="scheduled"),
        sa.Column("expense_claim_id", sa.String(length=36), nullable=True),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["expense_claim_id"], ["expense_claims.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("period", name="uq_payroll_runs_period"),
        sa.UniqueConstraint("expense_claim_id", name="uq_payroll_runs_expense_claim"),
    )
    op.create_index("ix_payroll_runs_period", "payroll_runs", ["period"])
    op.create_index("ix_payroll_runs_status", "payroll_runs", ["status"])
    op.create_table(
        "payroll_lines",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("employee_id", sa.String(length=36), nullable=False),
        sa.Column("employee_name", sa.String(length=100), nullable=False),
        sa.Column("salary_input", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("gross_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("net_amount", sa.Numeric(12, 2), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["payroll_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("run_id", "employee_id", name="uq_payroll_lines_employee"),
    )
    op.create_index("ix_payroll_lines_run_id", "payroll_lines", ["run_id"])
    op.create_index("ix_payroll_lines_employee_id", "payroll_lines", ["employee_id"])


def downgrade() -> None:
    op.drop_index("ix_payroll_lines_employee_id", table_name="payroll_lines")
    op.drop_index("ix_payroll_lines_run_id", table_name="payroll_lines")
    op.drop_table("payroll_lines")
    op.drop_index("ix_payroll_runs_status", table_name="payroll_runs")
    op.drop_index("ix_payroll_runs_period", table_name="payroll_runs")
    op.drop_table("payroll_runs")
    op.drop_table("payroll_settings")
