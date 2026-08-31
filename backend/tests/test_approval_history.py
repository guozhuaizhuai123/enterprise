import unittest

from fastapi import FastAPI
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


class ApprovalHistoryTest(unittest.TestCase):
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

        app = FastAPI()
        app.include_router(approvals.router)

        def db_override():
            yield self.db

        app.dependency_overrides[get_db] = db_override
        self.app = app
        self.act_as("manager", "manager", "employee", ("employee", "manager"))
        self.client = TestClient(app)

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def act_as(self, user_id: str, username: str, role: str, roles: tuple[str, ...]):
        self.app.dependency_overrides[get_current_principal] = lambda: Principal(
            user_id, username, role, "d1", ("d1",), roles
        )
        self.current_user_id = user_id

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

    def test_history_is_reachable_and_not_shadowed_by_instance_route(self):
        # `/approvals/history` 必须定义在 `/approvals/{instance_id}` 之前，
        # 否则 "history" 会被当成 instance_id 解析成 404。
        response = self.client.get("/approvals/history")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_history_records_my_approve_action(self):
        instance = self.start()
        WorkflowService.act(
            self.db, instance.id, "manager", "approve", "同意报销", instance.version
        )
        self.db.commit()

        self.act_as("manager", "manager", "employee", ("employee", "manager"))
        history = self.client.get("/approvals/history").json()

        self.assertEqual(len(history), 1)
        item = history[0]
        self.assertEqual(item["instance_id"], instance.id)
        self.assertEqual(item["action"], "approve")
        self.assertEqual(item["comment"], "同意报销")
        self.assertEqual(item["node_name"], "直属上级审批")
        self.assertEqual(item["sequence"], 1)
        self.assertEqual(item["requester_id"], "employee")
        self.assertEqual(item["requester_name"], "alice")
        self.assertEqual(item["actor_name"], "manager")
        self.assertEqual(item["entity_type"], "expense_claim")
        self.assertEqual(item["entity_id"], "claim-1")
        self.assertEqual(item["from_status"], "pending_approval")
        self.assertEqual(item["to_status"], "pending_approval")
        self.assertEqual(item["instance_status"], "pending_approval")

    def test_history_only_contains_my_own_actions(self):
        instance = self.start()
        WorkflowService.act(
            self.db, instance.id, "manager", "approve", "同意", instance.version
        )
        self.db.commit()

        # 非处理人看不到别人的审批动作
        self.act_as("outsider", "outsider", "employee", ("employee",))
        self.assertEqual(self.client.get("/approvals/history").json(), [])

        # 申请人自己只提交过，没有审批动作
        self.act_as("employee", "alice", "employee", ("employee",))
        self.assertEqual(self.client.get("/approvals/history").json(), [])

    def test_history_excludes_submit_action(self):
        instance = self.start()
        self.db.commit()
        self.act_as("employee", "alice", "employee", ("employee",))
        actions = self.client.get("/approvals/history").json()
        self.assertTrue(all(item["action"] != "submit" for item in actions))
        self.assertEqual(actions, [])

    def test_history_includes_reject_and_cancel(self):
        rejected = self.start("claim-reject")
        WorkflowService.act(
            self.db, rejected.id, "manager", "reject", "金额不符", rejected.version
        )
        self.db.commit()

        cancelled = self.start("claim-cancel")
        WorkflowService.act(
            self.db, cancelled.id, "employee", "cancel", "我不报了", cancelled.version
        )
        self.db.commit()

        self.act_as("manager", "manager", "employee", ("employee", "manager"))
        manager_history = self.client.get("/approvals/history").json()
        self.assertEqual([item["action"] for item in manager_history], ["reject"])
        self.assertEqual(manager_history[0]["comment"], "金额不符")
        self.assertEqual(manager_history[0]["to_status"], "rejected")
        self.assertEqual(manager_history[0]["instance_status"], "rejected")

        # 撤回由申请人自己执行，因此出现在申请人的历史里
        self.act_as("employee", "alice", "employee", ("employee",))
        employee_history = self.client.get("/approvals/history").json()
        self.assertEqual([item["action"] for item in employee_history], ["cancel"])
        self.assertEqual(employee_history[0]["instance_status"], "cancelled")

    def test_history_sorted_newest_first(self):
        first = self.start("claim-a")
        WorkflowService.act(self.db, first.id, "manager", "approve", "第一单", first.version)
        self.db.commit()
        second = self.start("claim-b")
        WorkflowService.act(self.db, second.id, "manager", "approve", "第二单", second.version)
        self.db.commit()

        self.act_as("manager", "manager", "employee", ("employee", "manager"))
        history = self.client.get("/approvals/history").json()
        self.assertEqual([item["entity_id"] for item in history], ["claim-b", "claim-a"])

    def test_history_covers_multi_step_approvals(self):
        instance = self.start()
        WorkflowService.act(self.db, instance.id, "manager", "approve", "同意", instance.version)
        self.db.flush()
        second_task = (
            self.db.query(ApprovalTask)
            .filter(ApprovalTask.instance_id == instance.id, ApprovalTask.sequence == 2)
            .one()
        )
        self.assertEqual(second_task.assignee_role, "finance")

        self.act_as("finance", "finance", "employee", ("employee", "finance"))
        latest = self.client.get(f"/approvals/{instance.id}").json()
        WorkflowService.act(
            self.db, instance.id, "finance", "approve", "已复核", latest["version"]
        )
        self.db.commit()

        finance_history = self.client.get("/approvals/history").json()
        self.assertEqual(len(finance_history), 1)
        self.assertEqual(finance_history[0]["node_name"], "财务复核")
        self.assertEqual(finance_history[0]["sequence"], 2)
        self.assertEqual(finance_history[0]["instance_status"], "approved")

        # 每个审批人只看到自己那一步
        self.act_as("manager", "manager", "employee", ("employee", "manager"))
        manager_history = self.client.get("/approvals/history").json()
        self.assertEqual(len(manager_history), 1)
        self.assertEqual(manager_history[0]["node_name"], "直属上级审批")


if __name__ == "__main__":
    unittest.main()
