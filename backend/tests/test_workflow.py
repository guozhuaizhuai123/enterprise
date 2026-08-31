import unittest

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.deps import Principal, get_current_principal
from app.models import (
    ApprovalTask,
    Department,
    EmployeeProfile,
    User,
    UserDepartment,
    UserRole,
)
from app.workflow.service import WorkflowService
from app.routers import approvals


class WorkflowServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        self.db = self.session_factory()
        self.db.add(Department(id="d1", name="研发部", code="DEV"))
        self.db.add_all(
            [
                User(id="employee", username="alice", password_encrypted="x", department_id="d1"),
                User(id="manager", username="manager", password_encrypted="x", department_id="d1"),
                User(id="finance", username="finance", password_encrypted="x", department_id="d1"),
                User(id="outsider", username="outsider", password_encrypted="x", department_id="d1"),
            ]
        )
        self.db.flush()
        self.db.add_all(
            [
                UserDepartment(user_id="employee", department_id="d1", is_primary=True),
                UserDepartment(user_id="manager", department_id="d1", is_primary=True),
                UserDepartment(user_id="finance", department_id="d1", is_primary=True),
                UserDepartment(user_id="outsider", department_id="d1", is_primary=True),
                EmployeeProfile(user_id="employee", full_name="艾丽丝", manager_id="manager"),
                EmployeeProfile(user_id="manager", full_name="马经理"),
                EmployeeProfile(user_id="finance", full_name="方财务"),
                EmployeeProfile(user_id="outsider", full_name="路人"),
                UserRole(user_id="manager", role="manager", department_id="d1"),
                UserRole(user_id="finance", role="finance", department_id="d1"),
            ]
        )
        self.db.commit()
        WorkflowService.ensure_default_definitions(self.db)
        self.db.commit()
        self.current = Principal(
            "manager", "manager", "employee", "d1", ("d1",), ("employee", "manager")
        )
        app = FastAPI()
        app.include_router(approvals.router)

        def db_override():
            yield self.db

        app.dependency_overrides[get_db] = db_override
        app.dependency_overrides[get_current_principal] = lambda: self.current
        self.client = TestClient(app)

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def start(self, entity_id: str = "claim-1"):
        instance = WorkflowService.start(
            self.db,
            "expense_claim",
            entity_id,
            "employee",
            "expense_reimbursement_v1",
        )
        self.db.flush()
        return instance

    def test_manager_assignment_and_finance_next_step(self):
        instance = self.start()
        first = self.db.query(ApprovalTask).filter_by(instance_id=instance.id).one()
        self.assertEqual(first.assignee_id, "manager")

        WorkflowService.act(
            self.db, instance.id, "manager", "approve", "同意", instance.version
        )
        self.db.flush()
        self.assertEqual(instance.status, "pending_approval")
        next_task = (
            self.db.query(ApprovalTask)
            .filter_by(instance_id=instance.id, status="pending")
            .one()
        )
        self.assertEqual(next_task.assignee_role, "finance")
        self.assertEqual(next_task.department_id, "d1")

    def test_requester_cannot_be_assigned_to_approve_own_request(self):
        profile = self.db.get(EmployeeProfile, "employee")
        profile.manager_id = "employee"
        self.db.commit()

        with self.assertRaises(HTTPException) as context:
            self.start("claim-self-approval")

        self.assertEqual(context.exception.status_code, 422)
        self.assertEqual(context.exception.detail, "requester cannot approve own request")
        self.assertEqual(self.db.query(ApprovalTask).count(), 0)

    def test_rejection_finishes_instance(self):
        instance = self.start()
        WorkflowService.act(
            self.db, instance.id, "manager", "reject", "资料不完整", instance.version
        )
        self.assertEqual(instance.status, "rejected")

    def test_requester_can_cancel(self):
        instance = self.start()
        WorkflowService.act(
            self.db, instance.id, "employee", "cancel", "撤回", instance.version
        )
        self.assertEqual(instance.status, "cancelled")

    def test_duplicate_active_instance_is_rejected(self):
        self.start()
        with self.assertRaises(HTTPException) as context:
            self.start()
        self.assertEqual(context.exception.status_code, 409)

    def test_unauthorized_actor_is_rejected(self):
        instance = self.start()
        with self.assertRaises(HTTPException) as context:
            WorkflowService.act(
                self.db, instance.id, "outsider", "approve", "越权", instance.version
            )
        self.assertEqual(context.exception.status_code, 403)

    def test_stale_version_is_rejected(self):
        instance = self.start()
        with self.assertRaises(HTTPException) as context:
            WorkflowService.act(
                self.db, instance.id, "manager", "approve", "同意", instance.version + 1
            )
        self.assertEqual(context.exception.status_code, 409)

    def test_finance_role_scope_is_checked(self):
        instance = self.start()
        WorkflowService.act(
            self.db, instance.id, "manager", "approve", "同意", instance.version
        )
        current_version = instance.version
        WorkflowService.act(
            self.db, instance.id, "finance", "approve", "已核验", current_version
        )
        self.assertEqual(instance.status, "approved")

    def test_global_finance_role_sees_tasks_outside_own_department(self):
        self.db.add(Department(id="d2", name="财务部", code="FIN"))
        finance_role = self.db.query(UserRole).filter_by(user_id="finance", role="finance").one()
        finance_role.department_id = None
        finance_user = self.db.get(User, "finance")
        finance_user.department_id = "d2"
        self.db.commit()

        instance = self.start("claim-global-finance")
        WorkflowService.act(
            self.db, instance.id, "manager", "approve", "同意", instance.version
        )
        principal = Principal(
            "finance", "finance", "employee", "d2", ("d2",), ("employee", "finance")
        )

        inbox = WorkflowService.list_inbox(self.db, principal)

        self.assertEqual([task.instance_id for task in inbox], [instance.id])

        self.current = principal
        response = self.client.get(f"/approvals/{instance.id}")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["can_approve"])

    def test_approval_detail_exposes_complete_route_with_named_handlers(self):
        instance = self.start("claim-with-route")
        self.db.commit()

        response = self.client.get(f"/approvals/{instance.id}")

        self.assertEqual(response.status_code, 200)
        route = response.json()["approval_route"]
        self.assertEqual(
            [(step["name"], step["status"]) for step in route],
            [
                ("提交申请", "approved"),
                ("直属上级审批", "pending"),
                ("财务复核", "upcoming"),
                ("财务付款", "upcoming"),
            ],
        )
        self.assertEqual(route[0]["handlers"][0]["display_name"], "艾丽丝")
        self.assertEqual(route[1]["handlers"][0]["display_name"], "马经理")
        self.assertEqual(route[2]["handlers"][0]["display_name"], "方财务")
        self.assertEqual(route[3]["handlers"][0]["display_name"], "方财务")

    def test_approval_api_inbox_and_transition(self):
        instance = self.start("claim-api")
        self.db.commit()
        inbox = self.client.get("/approvals/inbox")
        self.assertEqual(inbox.status_code, 200)
        self.assertEqual(inbox.json()[0]["node_name"], "直属上级审批")
        response = self.client.post(
            f"/approvals/{instance.id}/approve",
            json={"expected_version": 1, "comment": "同意"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["version"], 2)
        self.current = Principal(
            "finance", "finance", "employee", "d1", ("d1",), ("employee", "finance")
        )
        finance_inbox = self.client.get("/approvals/inbox").json()
        self.assertEqual(len(finance_inbox), 1)
        self.assertEqual(finance_inbox[0]["assignee_role"], "finance")


if __name__ == "__main__":
    unittest.main()
