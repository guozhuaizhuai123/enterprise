import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.deps import Principal, get_current_principal
from app.models import Department, User, UserDepartment
from app.routers import tickets


class TicketApiTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        with self.session_factory() as db:
            db.add_all([
                Department(id="d1", name="研发部"), Department(id="d2", name="法务部"),
                User(id="u1", username="alice", password_encrypted="x", role="employee", department_id="d1"),
                User(id="u2", username="bob", password_encrypted="x", role="employee", department_id="d2"),
                User(id="ad", username="admin", password_encrypted="x", role="admin"),
                UserDepartment(user_id="u1", department_id="d1"), UserDepartment(user_id="u2", department_id="d2"),
            ])
            db.commit()
        self.current = Principal("u1", "alice", "employee", "d1", ("d1",))
        self.app = FastAPI()
        self.app.include_router(tickets.employee_router)
        self.app.include_router(tickets.todo_router)
        self.app.include_router(tickets.notification_router)
        self.app.include_router(tickets.admin_router)

        def db_override():
            db = self.session_factory()
            try:
                yield db
            finally:
                db.close()

        self.app.dependency_overrides[get_db] = db_override
        self.app.dependency_overrides[get_current_principal] = lambda: self.current
        self.client = TestClient(self.app)

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_cross_department_defaults_to_admin_and_admin_accepts(self):
        # 跨部门协助指定协助部门后，默认发给管理员调度
        response = self.client.post("/tickets", json={"ticket_type": "cross_department", "subject": "合同支持", "description": "请协助审阅", "department_id": "d1", "requested_department_id": "d2"})
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["target_user_id"], "ad")
        self.assertEqual(data["status"], "pending_admin")
        self.assertTrue(data["requires_admin"])
        ticket_id = data["id"]
        self.current = Principal("ad", "admin", "admin", None, ())
        # 管理员在 pending_admin 阶段可直接「批准接手」
        self.assertEqual(self.client.post(f"/tickets/{ticket_id}/approve", json={}).status_code, 200)
        self.assertEqual(self.client.get(f"/tickets/{ticket_id}").json()["status"], "in_progress")
        todos = self.client.get("/admin/todos").json()
        self.assertEqual(len(todos), 1)
        self.assertEqual(todos[0]["assignee_id"], "ad")
        self.assertEqual(self.client.patch(f"/admin/todos/{todos[0]['id']}", json={"status": "completed"}).status_code, 200)
        self.assertEqual(self.client.get(f"/tickets/{ticket_id}").json()["status"], "completed")

    def test_cross_department_can_explicitly_select_admin(self):
        response = self.client.post("/tickets", json={"ticket_type": "cross_department", "subject": "合同支持", "description": "请协助审阅", "target_user_id": "admin", "department_id": "d1", "requested_department_id": "d2"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["target_user_id"], "ad")

    def test_same_department_ticket_rejects_other_department_target(self):
        response = self.client.post("/tickets", json={"ticket_type": "same_department", "subject": "协助", "description": "测试", "target_user_id": "u2", "department_id": "d1"})
        self.assertEqual(response.status_code, 400)

    def test_issue_to_admin_routes_to_pending_acceptance_and_admin_accepts(self):
        response = self.client.post("/tickets", json={"ticket_type": "issue", "subject": "反馈给管理员", "description": "需要管理员处理", "target_user_id": "admin", "department_id": "d1"})
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["status"], "pending_admin")
        self.assertTrue(data["requires_admin"])
        self.assertEqual(data["target_user_id"], "ad")
        self.current = Principal("ad", "admin", "admin", None, ())
        # issue 给管理员的工单初始状态是 pending_admin，管理员用 approve 批准接手
        self.assertEqual(self.client.post(f"/tickets/{data['id']}/approve", json={}).status_code, 200)
        self.assertEqual(self.client.get(f"/tickets/{data['id']}").json()["status"], "in_progress")
        todos = self.client.get("/admin/todos").json()
        self.assertEqual(len(todos), 1)
        self.assertEqual(todos[0]["assignee_id"], "ad")

    def test_same_department_rejects_admin_target(self):
        response = self.client.post("/tickets", json={"ticket_type": "same_department", "subject": "x", "description": "y", "target_user_id": "admin", "department_id": "d1"})
        self.assertEqual(response.status_code, 400)

    def test_cross_department_rejects_employee_target(self):
        response = self.client.post("/tickets", json={"ticket_type": "cross_department", "subject": "x", "description": "y", "target_user_id": "u2", "department_id": "d1", "requested_department_id": "d2"})
        self.assertEqual(response.status_code, 400)

    def test_cross_department_requires_assisting_department(self):
        # 跨部门协助必须指定「需要协助的部门」
        r = self.client.post("/tickets", json={"ticket_type": "cross_department", "subject": "x", "description": "y", "department_id": "d1"})
        self.assertEqual(r.status_code, 422)
        # 不能请求自己所在的部门
        r2 = self.client.post("/tickets", json={"ticket_type": "cross_department", "subject": "x", "description": "y", "department_id": "d1", "requested_department_id": "d1"})
        self.assertEqual(r2.status_code, 400)
        # 指定其他部门则成功，并记录协助部门
        ok = self.client.post("/tickets", json={"ticket_type": "cross_department", "subject": "x", "description": "y", "department_id": "d1", "requested_department_id": "d2"})
        self.assertEqual(ok.status_code, 201)
        self.assertEqual(ok.json()["requested_department_id"], "d2")
        self.assertEqual(ok.json()["requested_department_name"], "法务部")

    def test_dispatch_excludes_requester_and_wrong_department(self):
        ticket_id = self.client.post("/tickets", json={"ticket_type": "cross_department", "subject": "x", "description": "y", "department_id": "d1", "requested_department_id": "d2"}).json()["id"]
        self.current = Principal("ad", "admin", "admin", None, ())
        # 不能派发给发起人自己（alice=u1）
        self.assertEqual(self.client.post(f"/admin/tickets/{ticket_id}/dispatch", json={"assignee_id": "u1"}).status_code, 400)
        # 增加一个只属于 d1 的员工，不属于协助部门 d2，派发应被拒
        with self.session_factory() as db:
            db.add(User(id="u3", username="carol", password_encrypted="x", role="employee", department_id="d1"))
            db.add(UserDepartment(user_id="u3", department_id="d1"))
            db.commit()
        self.assertEqual(self.client.post(f"/admin/tickets/{ticket_id}/dispatch", json={"assignee_id": "u3"}).status_code, 400)
        # 只能派发给协助部门(d2)的人；bob(u2) 属于 d2，成功
        r = self.client.post(f"/admin/tickets/{ticket_id}/dispatch", json={"assignee_id": "u2"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["target_user_id"], "u2")

    def test_participants_return_only_employees(self):
        rows = self.client.get("/tickets/participants").json()
        self.assertTrue(all(r["role"] == "employee" for r in rows))

    def test_assigning_ticket_to_employee_creates_notification_for_target(self):
        # 把工单指派给员工 bob，bob 应收到一条未读通知
        response = self.client.post("/tickets", json={"ticket_type": "issue", "subject": "帮个忙", "description": "排个期", "target_user_id": "u2", "department_id": "d1"})
        self.assertEqual(response.status_code, 201)
        self.current = Principal("u2", "bob", "employee", "d2", ("d2",))
        notes = self.client.get("/notifications").json()
        self.assertEqual(len(notes), 1)
        self.assertIsNone(notes[0]["read_at"])
        self.assertEqual(notes[0]["kind"], "ticket_assigned")

    def test_admin_dispatches_ticket_to_specific_employee_and_they_can_talk(self):
        # alice 发起跨部门协助（指定协助部门 d2 法务部）→ 默认到管理员
        ticket_id = self.client.post("/tickets", json={"ticket_type": "cross_department", "subject": "法务支持", "description": "请审阅", "department_id": "d1", "requested_department_id": "d2"}).json()["id"]
        self.current = Principal("ad", "admin", "admin", None, ())
        # 管理员派发给 gjk(bob, d2 法务部)
        r = self.client.post(f"/admin/tickets/{ticket_id}/dispatch", json={"assignee_id": "u2"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["target_user_id"], "u2")
        self.assertEqual(r.json()["status"], "pending_acceptance")
        # bob 接收
        self.current = Principal("u2", "bob", "employee", "d2", ("d2",))
        self.assertEqual(self.client.post(f"/tickets/{ticket_id}/accept", json={}).status_code, 200)
        # alice 与 bob 可以在该工单内跨部门沟通
        self.assertEqual(self.client.post(f"/tickets/{ticket_id}/messages", json={"content": "你好，麻烦看下"}).status_code, 201)
        self.current = Principal("u1", "alice", "employee", "d1", ("d1",))
        self.assertEqual(self.client.post(f"/tickets/{ticket_id}/messages", json={"content": "收到，谢谢"}).status_code, 201)
        # 管理员可以看到两人的全部通信记录（含创建时写入的原始需求，共 3 条）
        self.current = Principal("ad", "admin", "admin", None, ())
        msgs = self.client.get(f"/tickets/{ticket_id}/messages").json()
        self.assertEqual(len(msgs), 3)
        self.assertEqual(msgs[0]["content"], "请审阅")

    def test_complete_freezes_communication(self):
        ticket_id = self.client.post("/tickets", json={"ticket_type": "cross_department", "subject": "法务支持", "description": "x", "department_id": "d1", "requested_department_id": "d2"}).json()["id"]
        self.current = Principal("ad", "admin", "admin", None, ())
        self.client.post(f"/admin/tickets/{ticket_id}/dispatch", json={"assignee_id": "u2"})
        self.current = Principal("u2", "bob", "employee", "d2", ("d2",))
        self.client.post(f"/tickets/{ticket_id}/accept", json={})
        # 管理员标记已完成 → 双方无法再沟通
        self.current = Principal("ad", "admin", "admin", None, ())
        r = self.client.post(f"/tickets/{ticket_id}/complete", json={})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "completed")
        self.current = Principal("u1", "alice", "employee", "d1", ("d1",))
        self.assertEqual(self.client.post(f"/tickets/{ticket_id}/messages", json={"content": "还能说话吗"}).status_code, 409)

    def test_requester_can_reopen_recent_completed_ticket(self):
        # SQLite 返回的 closed_at 不带 tzinfo，重开时仍应按 UTC 正确比较时间窗口。
        self.current = Principal("u1", "alice", "employee", "d1", ("d1",))
        ticket_id = self.client.post("/tickets", json={
            "ticket_type": "issue", "subject": "需要重开", "description": "继续跟进",
            "target_user_id": "u2", "department_id": "d1",
        }).json()["id"]
        self.current = Principal("u2", "bob", "employee", "d2", ("d2",))
        self.assertEqual(self.client.post(f"/tickets/{ticket_id}/accept", json={}).status_code, 200)
        self.assertEqual(self.client.post(f"/tickets/{ticket_id}/complete", json={}).status_code, 200)
        self.current = Principal("u1", "alice", "employee", "d1", ("d1",))
        reopened = self.client.post(f"/tickets/{ticket_id}/reopen", json={})
        self.assertEqual(reopened.status_code, 200)
        self.assertEqual(reopened.json()["status"], "in_progress")

    def test_cannot_dispatch_to_requester_or_finished_ticket(self):
        ticket_id = self.client.post("/tickets", json={"ticket_type": "cross_department", "subject": "x", "description": "y", "department_id": "d1", "requested_department_id": "d2"}).json()["id"]
        self.current = Principal("ad", "admin", "admin", None, ())
        # 不能派发给发起人自己
        self.assertEqual(self.client.post(f"/admin/tickets/{ticket_id}/dispatch", json={"assignee_id": "u1"}).status_code, 400)
        # 完成后的工单不能再派发
        self.client.post(f"/admin/tickets/{ticket_id}/dispatch", json={"assignee_id": "u2"})
        self.client.post(f"/tickets/{ticket_id}/complete", json={})
        self.assertEqual(self.client.post(f"/admin/tickets/{ticket_id}/dispatch", json={"assignee_id": "u2"}).status_code, 409)

    def test_reply_notifies_the_other_party(self):
        # alice 发起工单给 bob
        self.current = Principal("u1", "alice", "employee", "d1", ("d1",))
        ticket_id = self.client.post("/tickets", json={"ticket_type": "issue", "subject": "问题", "description": "详情", "target_user_id": "u2", "department_id": "d1"}).json()["id"]
        # bob 接收后再回复，alice 应收到回复通知
        self.current = Principal("u2", "bob", "employee", "d2", ("d2",))
        self.client.post(f"/tickets/{ticket_id}/accept", json={})
        self.client.post(f"/tickets/{ticket_id}/messages", json={"content": "已处理"})
        self.current = Principal("u1", "alice", "employee", "d1", ("d1",))
        notes = self.client.get("/notifications").json()
        self.assertTrue(any(n["kind"] == "ticket_replied" for n in notes))

    def test_admin_reject_works_at_pending_admin(self):
        # 回归：修复前工单初始状态错设为 pending_acceptance，而 admin-reject 要求
        # pending_admin，导致管理员的「驳回」入口永远 409。这里断言 pending_admin 下可驳回。
        ticket_id = self.client.post("/tickets", json={
            "ticket_type": "cross_department", "subject": "x", "description": "y",
            "department_id": "d1", "requested_department_id": "d2",
        }).json()["id"]
        self.current = Principal("ad", "admin", "admin", None, ())
        self.assertEqual(self.client.get(f"/tickets/{ticket_id}").json()["status"], "pending_admin")
        r = self.client.post(f"/tickets/{ticket_id}/admin-reject", json={"reason": "不在职责范围"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "rejected")
        # 普通员工即使作为发起人能看到该 pending_admin 工单，也不能 admin-reject：
        # 角色校验在 _action 中返回 409（非 404/403）
        self.current = Principal("u2", "bob", "employee", "d2", ("d2",))
        ticket2 = self.client.post("/tickets", json={
            "ticket_type": "issue", "subject": "员工发起给管理员", "description": "y",
            "target_user_id": "admin", "department_id": "d2",
        }).json()["id"]
        self.assertEqual(self.client.get(f"/tickets/{ticket2}").json()["status"], "pending_admin")
        self.assertEqual(self.client.post(f"/tickets/{ticket2}/admin-reject", json={"reason": ""}).status_code, 409)
