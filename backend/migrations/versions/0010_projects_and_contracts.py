"""Create projects and contracts tables (parallel assets; contracts weakly reference projects)."""

from alembic import op
import sqlalchemy as sa


revision = "0010_projects_and_contracts"
down_revision = "0009_rename_cost_center_to_salary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False, unique=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False, server_default="internal"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="preparing"),
        sa.Column("department_id", sa.String(length=36), nullable=True),
        sa.Column("manager_id", sa.String(length=36), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("budget", sa.Numeric(precision=16, scale=2), nullable=True),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["manager_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint("type IN ('internal', 'client', 'rd', 'other')", name="ck_projects_type"),
        sa.CheckConstraint(
            "status IN ('preparing', 'active', 'closed', 'paused', 'cancelled')",
            name="ck_projects_status",
        ),
    )
    op.create_index("ix_projects_department_id", "projects", ["department_id"])
    op.create_index("ix_projects_manager_id", "projects", ["manager_id"])

    op.create_table(
        "contracts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False, unique=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False, server_default="purchase"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("party_a", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("party_b", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("amount", sa.Numeric(precision=16, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="CNY"),
        sa.Column("sign_date", sa.Date(), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("owner_id", sa.String(length=36), nullable=True),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "type IN ('purchase', 'sales', 'service', 'lease', 'nda', 'other')",
            name="ck_contracts_type",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'reviewing', 'active', 'fulfilled', 'expired', 'terminated')",
            name="ck_contracts_status",
        ),
    )
    op.create_index("ix_contracts_project_id", "contracts", ["project_id"])
    op.create_index("ix_contracts_owner_id", "contracts", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_contracts_owner_id", table_name="contracts")
    op.drop_index("ix_contracts_project_id", table_name="contracts")
    op.drop_table("contracts")
    op.drop_index("ix_projects_manager_id", table_name="projects")
    op.drop_index("ix_projects_department_id", table_name="projects")
    op.drop_table("projects")
