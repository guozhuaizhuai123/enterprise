"""Backfill organization records for users created before the ERP upgrade."""

from alembic import op
import sqlalchemy as sa


revision = "0003_backfill_employee_profiles"
down_revision = "0002_organization_and_roles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            INSERT INTO employee_profiles (
                user_id, full_name, phone, email, status, position, level,
                cost_center, notes, created_at, updated_at
            )
            SELECT
                users.id, users.username, '', '', 'active', '', '', '', '',
                users.created_at, users.created_at
            FROM users
            WHERE NOT EXISTS (
                SELECT 1 FROM employee_profiles
                WHERE employee_profiles.user_id = users.id
            )
            """
        )
    )
    connection.execute(
        sa.text(
            """
            INSERT INTO user_roles (id, user_id, role, department_id, created_at)
            SELECT
                'migration-role-' || users.id,
                users.id,
                'employee',
                NULL,
                users.created_at
            FROM users
            WHERE users.role = 'employee'
              AND NOT EXISTS (
                  SELECT 1 FROM user_roles
                  WHERE user_roles.user_id = users.id
                    AND user_roles.role = 'employee'
              )
            """
        )
    )
    connection.execute(
        sa.text(
            """
            UPDATE user_departments
            SET is_primary = CASE
                WHEN department_id = (
                    SELECT users.department_id FROM users
                    WHERE users.id = user_departments.user_id
                ) THEN 1
                ELSE 0
            END
            """
        )
    )


def downgrade() -> None:
    # Backfilled profiles may have accumulated business history after upgrade;
    # deliberately keep them rather than deleting user-owned data.
    pass
