import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db import Base, get_db
from app.deps import Principal, get_current_principal
from app.models import Department, DepartmentMemory, UserMemory
from app.routers import memory


class MemoryApiTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _client(self, user_id="user-1", role="employee", user_limit=20, department_limit=50):
        app = FastAPI()
        app.include_router(memory.me_router)
        app.include_router(memory.admin_memory_router)

        def override_db():
            db = self.session_factory()
            try:
                yield db
            finally:
                db.close()

        def override_principal():
            return Principal(
                user_id=user_id,
                username=user_id,
                role=role,
                department_id="dept-1",
                department_ids=("dept-1",),
            )

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_principal] = override_principal
        settings = Settings(user_memory_limit=user_limit, department_memory_limit=department_limit)
        return TestClient(app), patch("app.routers.memory.get_settings", return_value=settings)

    def _add_user_memory(self, user_id, title="Preference"):
        with self.session_factory() as db:
            item = UserMemory(user_id=user_id, title=title, content="Remember this")
            db.add(item)
            db.commit()
            return item.id

    def _add_department(self, department_id="dept-1"):
        with self.session_factory() as db:
            db.add(Department(id=department_id, name=department_id))
            db.commit()

    def test_user_lists_only_own_memories(self):
        own_id = self._add_user_memory("user-1", "Mine")
        self._add_user_memory("user-2", "Theirs")
        client, settings_patch = self._client()

        with settings_patch:
            response = client.get("/me/memories")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json()], [own_id])

    def test_user_cannot_update_another_users_memory(self):
        memory_id = self._add_user_memory("user-2")
        client, settings_patch = self._client("user-1")

        with settings_patch:
            response = client.put(f"/me/memories/{memory_id}", json={"title": "Changed"})

        self.assertEqual(response.status_code, 404)

    def test_user_memory_delete_is_committed_to_database(self):
        memory_id = self._add_user_memory("user-1")
        client, settings_patch = self._client("user-1")

        with settings_patch:
            response = client.delete(f"/me/memories/{memory_id}")

        self.assertEqual(response.status_code, 204)
        with self.session_factory() as db:
            self.assertIsNone(db.get(UserMemory, memory_id))

    def test_admin_cannot_update_another_users_memory_through_me(self):
        memory_id = self._add_user_memory("user-2")
        client, settings_patch = self._client("admin-1", role="admin")

        with settings_patch:
            response = client.put(f"/me/memories/{memory_id}", json={"title": "Changed"})

        self.assertEqual(response.status_code, 404)

    def test_user_memory_limit_returns_conflict(self):
        self._add_user_memory("user-1")
        client, settings_patch = self._client(user_limit=1)

        with settings_patch:
            response = client.post("/me/memories", json={"title": "Second", "content": "Too many"})

        self.assertEqual(response.status_code, 409)

    def test_user_memory_rejects_values_empty_after_trim(self):
        client, settings_patch = self._client()

        with settings_patch:
            response = client.post("/me/memories", json={"title": "  ", "content": "  "})

        self.assertEqual(response.status_code, 400)

    def test_chat_setting_defaults_to_three_and_patch_persists_value(self):
        client, settings_patch = self._client()

        with settings_patch:
            initial = client.get("/me/chat-settings")
            updated = client.patch("/me/chat-settings", json={"default_memory_level": 5})
            persisted = client.get("/me/chat-settings")

        self.assertEqual(initial.json(), {"default_memory_level": 3})
        self.assertEqual(updated.json(), {"default_memory_level": 5})
        self.assertEqual(persisted.json(), {"default_memory_level": 5})

    def test_employee_cannot_create_department_memory(self):
        self._add_department()
        client, settings_patch = self._client(role="employee")

        with settings_patch:
            response = client.post(
                "/admin/departments/dept-1/memories", json={"title": "Policy", "content": "Internal"}
            )

        self.assertEqual(response.status_code, 403)

    def test_admin_can_manage_department_memory_with_authenticated_attribution(self):
        self._add_department()
        client, settings_patch = self._client("admin-1", role="admin")

        with settings_patch:
            created = client.post(
                "/admin/departments/dept-1/memories", json={"title": " Policy ", "content": " Internal "}
            )
            memory_id = created.json()["id"]
            listed = client.get("/admin/departments/dept-1/memories")
        updating_client, updating_settings_patch = self._client("admin-2", role="admin")
        with updating_settings_patch:
            updated = updating_client.put(f"/admin/department-memories/{memory_id}", json={"enabled": False})
            deleted = updating_client.delete(f"/admin/department-memories/{memory_id}")

        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["title"], "Policy")
        self.assertEqual(created.json()["created_by"], "admin-1")
        self.assertEqual([item["id"] for item in listed.json()], [memory_id])
        self.assertEqual(updated.json()["enabled"], False)
        self.assertEqual(updated.json()["updated_by"], "admin-2")
        self.assertEqual(deleted.status_code, 204)
        with self.session_factory() as db:
            self.assertIsNone(db.get(DepartmentMemory, memory_id))

    def test_admin_department_memory_missing_resources_return_not_found(self):
        client, settings_patch = self._client(role="admin")

        with settings_patch:
            missing_department = client.get("/admin/departments/missing/memories")
            missing_memory = client.delete("/admin/department-memories/missing")

        self.assertEqual(missing_department.status_code, 404)
        self.assertEqual(missing_memory.status_code, 404)

    def test_department_memory_limit_returns_conflict(self):
        self._add_department()
        with self.session_factory() as db:
            db.add(
                DepartmentMemory(
                    department_id="dept-1",
                    title="First",
                    content="Already stored",
                    created_by="admin-1",
                    updated_by="admin-1",
                )
            )
            db.commit()
        client, settings_patch = self._client(role="admin", department_limit=1)

        with settings_patch:
            response = client.post(
                "/admin/departments/dept-1/memories", json={"title": "Second", "content": "Too many"}
            )

        self.assertEqual(response.status_code, 409)


if __name__ == "__main__":
    unittest.main()
