import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.deps import Principal, get_current_principal
from app.models import Contract, Department, Document, Project, User
from app.routers import admin, projects
from app.routers import kb


class ProjectDocumentLinksTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        with self.session_factory() as db:
            db.add_all([
                Department(id="d1", name="交付部", code="DELIVERY"),
                Department(id="d2", name="法务部", code="LEGAL"),
                User(id="admin", username="admin", password_encrypted="x", role="admin"),
                Project(id="p1", code="PRJ-1", name="项目一", department_id="d1", created_by="admin"),
                Project(id="p2", code="PRJ-2", name="项目二", department_id="d2", created_by="admin"),
                Contract(id="c1", code="CTR-1", name="合同一", project_id="p1", created_by="admin"),
                Contract(id="c2", code="CTR-2", name="合同二", project_id="p2", created_by="admin"),
                Document(
                    id="doc-1", department_id="d1", title="项目一方案", content="方案内容",
                    uploaded_by="admin", owner_id="admin", owner_name="admin", project_id="p1", contract_id="c1",
                ),
                Document(
                    id="doc-2", department_id="d1", title="通用制度", content="制度内容",
                    uploaded_by="admin", owner_id="admin", owner_name="admin",
                ),
            ])
            db.commit()

        self.current = Principal("admin", "admin", "admin", None, (), ("admin",))
        app = FastAPI()
        app.include_router(admin.router)
        app.include_router(projects.project_router)

        def db_override():
            db = self.session_factory()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = db_override
        app.dependency_overrides[get_current_principal] = lambda: self.current
        self.client = TestClient(app)

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_project_workspace_contains_related_contracts_and_documents(self):
        response = self.client.get("/projects/p1/workspace")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["project"]["id"], "p1")
        self.assertEqual([item["id"] for item in response.json()["contracts"]], ["c1"])
        self.assertEqual([item["id"] for item in response.json()["documents"]], ["doc-1"])

    def test_admin_can_filter_documents_by_project_and_contract(self):
        response = self.client.get("/admin/documents", params={"project_id": "p1", "contract_id": "c1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json()], ["doc-1"])

    def test_document_rejects_contract_from_another_project(self):
        response = self.client.put("/admin/documents/doc-1", json={"project_id": "p1", "contract_id": "c2"})
        self.assertEqual(response.status_code, 400)

    def test_employee_cannot_infer_unauthorized_project_from_contract(self):
        with self.session_factory() as db:
            with self.assertRaises(Exception):
                kb._resolve_employee_links(
                    db,
                    Principal("employee", "employee", "employee", "d1", ("d1",), ("employee",)),
                    None,
                    "c2",
                )


if __name__ == "__main__":
    unittest.main()
