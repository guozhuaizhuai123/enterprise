"""Add organization hierarchy, employee profiles, and scoped roles."""

from alembic import op
import sqlalchemy as sa


revision = "0002_organization_and_roles"
down_revision = "0001_ai_erp_phase1"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _column_names(table_name: str) -> set[str]:
    return {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def _index_names(table_name: str) -> set[str]:
    return {
        index["name"]
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
    }


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if column.name not in _column_names(table_name):
        op.add_column(table_name, column)


def _create_index_if_missing(
    index_name: str,
    table_name: str,
    columns: list[str],
    *,
    unique: bool = False,
) -> None:
    if index_name not in _index_names(table_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def upgrade() -> None:
    # SQLite executes ALTER TABLE statements outside Alembic's transaction.
    # Keep every step idempotent so an interrupted upgrade can safely resume.
    _add_column_if_missing(
        "departments", sa.Column("code", sa.String(length=32), nullable=True)
    )
    _add_column_if_missing(
        "departments", sa.Column("parent_id", sa.String(length=36), nullable=True)
    )
    _add_column_if_missing(
        "departments", sa.Column("manager_id", sa.String(length=36), nullable=True)
    )
    _add_column_if_missing(
        "departments",
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    # SQLite cannot add a column with CURRENT_TIMESTAMP as a default. Backfill
    # it after adding the nullable column; the ORM supplies values for new rows.
    _add_column_if_missing(
        "departments",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE departments "
            "SET updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)"
        )
    )
    _create_index_if_missing(
        "ix_departments_code", "departments", ["code"], unique=True
    )
    _create_index_if_missing(
        "ix_departments_parent_id", "departments", ["parent_id"]
    )
    _create_index_if_missing(
        "ix_departments_manager_id", "departments", ["manager_id"]
    )
    _create_index_if_missing("ix_departments_active", "departments", ["active"])

    _add_column_if_missing(
        "user_departments",
        sa.Column("is_primary", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    _add_column_if_missing(
        "user_departments", sa.Column("joined_at", sa.Date(), nullable=True)
    )
    _add_column_if_missing(
        "user_departments", sa.Column("left_at", sa.Date(), nullable=True)
    )

    if not _table_exists("employee_profiles"):
        op.create_table(
            "employee_profiles",
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("full_name", sa.String(length=100), server_default="", nullable=False),
            sa.Column("phone", sa.String(length=32), server_default="", nullable=False),
            sa.Column("email", sa.String(length=200), server_default="", nullable=False),
            sa.Column("hire_date", sa.Date(), nullable=True),
            sa.Column("termination_date", sa.Date(), nullable=True),
            sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
            sa.Column("position", sa.String(length=100), server_default="", nullable=False),
            sa.Column("level", sa.String(length=50), server_default="", nullable=False),
            sa.Column("manager_id", sa.String(length=36), nullable=True),
            sa.Column("cost_center", sa.String(length=64), server_default="", nullable=False),
            sa.Column("notes", sa.Text(), server_default="", nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.CheckConstraint(
                "status IN ('probation', 'active', 'suspended', 'terminated')",
                name="ck_employee_profiles_status",
            ),
            sa.ForeignKeyConstraint(["manager_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("user_id"),
        )
    _create_index_if_missing(
        "ix_employee_profiles_status", "employee_profiles", ["status"]
    )
    _create_index_if_missing(
        "ix_employee_profiles_manager_id", "employee_profiles", ["manager_id"]
    )

    if not _table_exists("employment_events"):
        op.create_table(
            "employment_events",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("event_type", sa.String(length=32), nullable=False),
            sa.Column("effective_date", sa.Date(), nullable=False),
            sa.Column("before_data", sa.JSON(), nullable=False),
            sa.Column("after_data", sa.JSON(), nullable=False),
            sa.Column("actor_id", sa.String(length=36), nullable=True),
            sa.Column("note", sa.String(length=500), server_default="", nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing(
        "ix_employment_events_user_id", "employment_events", ["user_id"]
    )
    _create_index_if_missing(
        "ix_employment_events_event_type", "employment_events", ["event_type"]
    )
    _create_index_if_missing(
        "ix_employment_events_effective_date", "employment_events", ["effective_date"]
    )

    if not _table_exists("user_roles"):
        op.create_table(
            "user_roles",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("role", sa.String(length=16), nullable=False),
            sa.Column("department_id", sa.String(length=36), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.CheckConstraint(
                "role IN ('admin', 'employee', 'hr', 'manager', 'finance')",
                name="ck_user_roles_role",
            ),
            sa.ForeignKeyConstraint(["department_id"], ["departments.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "role", "department_id", name="uq_user_role_scope"),
        )
    _create_index_if_missing("ix_user_roles_user_id", "user_roles", ["user_id"])
    _create_index_if_missing("ix_user_roles_role", "user_roles", ["role"])
    _create_index_if_missing(
        "ix_user_roles_department_id", "user_roles", ["department_id"]
    )


def downgrade() -> None:
    op.drop_table("user_roles")
    op.drop_table("employment_events")
    op.drop_table("employee_profiles")
    op.drop_column("user_departments", "left_at")
    op.drop_column("user_departments", "joined_at")
    op.drop_column("user_departments", "is_primary")
    op.drop_index("ix_departments_active", table_name="departments")
    op.drop_index("ix_departments_manager_id", table_name="departments")
    op.drop_index("ix_departments_parent_id", table_name="departments")
    op.drop_index("ix_departments_code", table_name="departments")
    op.drop_column("departments", "updated_at")
    op.drop_column("departments", "active")
    op.drop_column("departments", "manager_id")
    op.drop_column("departments", "parent_id")
    op.drop_column("departments", "code")
