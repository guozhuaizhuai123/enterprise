import unittest
from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.deps import Principal, get_current_principal
from app.models import Department, EmployeeProfile, User, UserDepartment, UserRole
from app.routers import organization


class OrganizationApiTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        with self.session_factory() as db:
            db.add_all(
                [
                    Department(id="d1", name="研发部", code="DEV", manager_id="manager"),
                    Department(id="d2", name="财务部", code="FIN"),
                    User(id="admin", username="admin", password_encrypted="x", role="admin"),
                    User(id="hr", username="hr", password_encrypted="x", role="employee", department_id="d1"),
                    User(id="manager", username="manager", password_encrypted="x", role="employee", department_id="d1"),
                    User(id="employee", username="alice", password_encrypted="x", role="employee", department_id="d1"),
                    User(id="finance", username="finance", password_encrypted="x", role="employee", department_id="d2"),
                ]
            )
            db.flush()
            db.add_all(
                [
                    UserDepartment(user_id="hr", department_id="d1", is_primary=True),
                    UserDepartment(user_id="manager", department_id="d1", is_primary=True),
                    UserDepartment(user_id="employee", department_id="d1", is_primary=True),
                    UserDepartment(user_id="finance", department_id="d2", is_primary=True),
                    EmployeeProfile(user_id="hr", full_name="何人事", status="active", hire_date=date(2026, 1, 1)),
                    EmployeeProfile(user_id="manager", full_name="马经理", status="active", hire_date=date(2026, 1, 1)),
                    EmployeeProfile(
                        user_id="employee",
                        full_name="艾丽丝",
                        status="active",
                        manager_id="manager",
                        hire_date=date(2026, 2, 1),
                    ),
                    EmployeeProfile(user_id="finance", full_name="方财务", status="active", hire_date=date(2026, 1, 1)),
                    UserRole(user_id="hr", role="hr"),
                    UserRole(user_id="manager", role="manager", department_id="d1"),
                    UserRole(user_id="finance", role="finance", department_id="d2"),
                ]
            )
            db.commit()

        self.current = Principal("admin", "admin", "admin", None, (), ("admin",))
        app = FastAPI()
        app.include_router(organization.admin_router)
        app.include_router(organization.me_router)

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

    def test_employee_can_read_own_profile(self):
        self.current = Principal("employee", "alice", "employee", "d1", ("d1",), ("employee",))
        response = self.client.get("/me/profile")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["full_name"], "艾丽丝")
        self.assertEqual(response.json()["manager_id"], "manager")

    def test_manager_can_read_direct_report_but_not_unrelated_employee(self):
        self.current = Principal(
            "manager", "manager", "employee", "d1", ("d1",), ("employee", "manager")
        )
        self.assertEqual(self.client.get("/admin/employees/employee").status_code, 200)
        self.assertEqual(self.client.get("/admin/employees/finance").status_code, 403)

    def test_finance_cannot_manage_employee_records(self):
        self.current = Principal(
            "finance", "finance", "employee", "d2", ("d2",), ("employee", "finance")
        )
        self.assertEqual(self.client.get("/admin/employees/employee").status_code, 403)
        self.assertEqual(
            self.client.patch("/admin/employees/employee", json={"level": "P7"}).status_code,
            403,
        )

    def test_hr_offboards_employee_without_deleting_history(self):
        self.current = Principal("hr", "hr", "employee", "d1", ("d1",), ("employee", "hr"))
        response = self.client.post(
            "/admin/employees/employee/events",
            json={
                "event_type": "offboard",
                "effective_date": "2026-08-30",
                "status": "terminated",
                "note": "合同结束",
            },
        )
        self.assertEqual(response.status_code, 201)
        with self.session_factory() as db:
            self.assertIsNotNone(db.get(User, "employee"))
            self.assertEqual(db.get(EmployeeProfile, "employee").status, "terminated")

    def test_admin_rejects_department_parent_cycle(self):
        response = self.client.patch("/admin/org-units/d1", json={"parent_id": "d1"})
        self.assertEqual(response.status_code, 409)

    def test_org_unit_manager_can_be_set_and_changed(self):
        # 部门负责人（manager_id）创建与更新时均可设置，不应创建即锁死
        create = self.client.post(
            "/admin/org-units", json={"name": "市场部", "code": "MKT", "manager_id": "manager"}
        )
        self.assertEqual(create.status_code, 201)
        body = create.json()
        self.assertEqual(body["manager_id"], "manager")
        self.assertEqual(body["manager_name"], "马经理")
        unit_id = body["id"]
        # 改派负责人为 hr（何人事）
        patch = self.client.patch(f"/admin/org-units/{unit_id}", json={"manager_id": "hr"})
        self.assertEqual(patch.status_code, 200)
        self.assertEqual(patch.json()["manager_id"], "hr")
        self.assertEqual(patch.json()["manager_name"], "何人事")
        # 取消负责人
        unset = self.client.patch(f"/admin/org-units/{unit_id}", json={"manager_id": None})
        self.assertEqual(unset.status_code, 200)
        self.assertIsNone(unset.json()["manager_id"])
        self.assertEqual(unset.json()["manager_name"], "")


if __name__ == "__main__":
    unittest.main()
