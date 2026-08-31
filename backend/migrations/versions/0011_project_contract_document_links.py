"""Link knowledge documents to projects and contracts."""

from alembic import op
import sqlalchemy as sa


revision = "0011_project_contract_document_links"
down_revision = "0010_projects_and_contracts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("documents") as batch:
        batch.add_column(sa.Column("project_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("contract_id", sa.String(length=36), nullable=True))
        batch.create_foreign_key(
            "fk_documents_project_id_projects",
            "projects",
            ["project_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_documents_contract_id_contracts",
            "contracts",
            ["contract_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_documents_project_id", "documents", ["project_id"])
    op.create_index("ix_documents_contract_id", "documents", ["contract_id"])


def downgrade() -> None:
    op.drop_index("ix_documents_contract_id", table_name="documents")
    op.drop_index("ix_documents_project_id", table_name="documents")
    with op.batch_alter_table("documents") as batch:
        batch.drop_constraint("fk_documents_contract_id_contracts", type_="foreignkey")
        batch.drop_constraint("fk_documents_project_id_projects", type_="foreignkey")
        batch.drop_column("contract_id")
        batch.drop_column("project_id")
