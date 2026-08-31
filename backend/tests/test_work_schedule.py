import unittest
from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.deps import Principal, get_current_principal
from app.models import Department, LeaveRequest, User, UserDepartment, WorkScheduleDay
from app.schedule.service import (
    LeaveConflictError,
    ScheduleValidationError,
    create_leave_request,
    get_schedule,
    replace_schedule,
    review_leave_request,
)
from app.schemas import ScheduleDayInput
from app.routers import schedule


class WorkScheduleServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.session.add_all(
            (
                Department(id="dept-1", name="法务部"),
                User(
                    id="employee-1",
                    username="employee",
                    password_encrypted="encrypted",
                    role="employee",
                    department_id="dept-1",
                ),
                User(
                    id="admin-1",
                    username="admin",
                    password_encrypted="encrypted",
                    role="admin",
                ),
                UserDepartment(user_id="employee-1", department_id="dept-1"),
            )
        )
        self.session.commit()

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_default_schedule_is_monday_to_friday(self):
        schedule = get_schedule(self.session, "employee-1")

        self.assertEqual([day.weekday for day in schedule if day.enabled], [1, 2, 3, 4, 5])
        self.assertEqual(schedule[0].start_time, "09:00")
        self.assertEqual(schedule[0].end_time, "18:00")

    def test_replace_schedule_requires_seven_unique_days_and_valid_times(self):
        with self.assertRaises(ScheduleValidationError):
            replace_schedule(
                self.session,
                "employee-1",
                [ScheduleDayInput(weekday=1, enabled=True, start_time="18:00", end_time="09:00")],
                "admin-1",
            )

    def test_replace_schedule_persists_custom_week(self):
        days = [
            ScheduleDayInput(
                weekday=weekday,
                enabled=weekday in (1, 3, 5),
                start_time="08:30",
                end_time="17:30",
            )
            for weekday in range(1, 8)
        ]

        replaced = replace_schedule(self.session, "employee-1", days, "admin-1")

        self.assertEqual([day.weekday for day in replaced if day.enabled], [1, 3, 5])
        self.assertEqual(self.session.query(WorkScheduleDay).count(), 7)

    def test_overlapping_pending_leave_is_rejected(self):
        create_leave_request(
            self.session,
            user_id="employee-1",
            leave_type="病假",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 2),
            reason="身体不适",
        )

        with self.assertRaises(LeaveConflictError):
            create_leave_request(
                self.session,
                user_id="employee-1",
                leave_type="事假",
                start_date=date(2026, 9, 2),
                end_date=date(2026, 9, 3),
                reason="个人事务",
            )

    def test_rejected_leave_no_longer_blocks_new_request(self):
        request = create_leave_request(
            self.session,
            user_id="employee-1",
            leave_type="年假",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 1),
            reason="休息",
        )
        reviewed = review_leave_request(
            self.session,
            request_id=request.id,
            status="rejected",
            reviewed_by="admin-1",
        )

        replacement = create_leave_request(
            self.session,
            user_id="employee-1",
            leave_type="病假",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 1),
            reason="身体不适",
        )

        self.assertEqual(reviewed.status, "rejected")
        self.assertEqual(replacement.status, "pending")
        self.assertEqual(self.session.query(LeaveRequest).count(), 2)


class WorkScheduleApiTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        with self.session_factory() as db:
            db.add_all(
                (
                    Department(id="dept-1", name="法务部"),
                    Department(id="dept-2", name="财务部"),
                    User(
                        id="employee-1",
                        username="alice",
                        password_encrypted="encrypted",
                        role="employee",
                        department_id="dept-1",
                    ),
                    User(
                        id="employee-2",
                        username="bob",
                        password_encrypted="encrypted",
                        role="employee",
                        department_id="dept-2",
                    ),
                    User(
                        id="admin-1",
                        username="admin",
                        password_encrypted="encrypted",
                        role="admin",
                    ),
                    UserDepartment(user_id="employee-1", department_id="dept-1"),
                    UserDepartment(user_id="employee-2", department_id="dept-2"),
                )
            )
            db.commit()

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _client(self, user_id="employee-1", role="employee", department_ids=("dept-1",)):
        app = FastAPI()
        app.include_router(schedule.me_router)
        app.include_router(schedule.admin_router)

        def override_db():
            db = self.session_factory()
            try:
                yield db
            finally:
                db.close()

        def override_principal():
            return Principal(
                user_id=user_id,
                username="admin" if role == "admin" else "alice",
                role=role,
                department_id=department_ids[0] if department_ids else None,
                department_ids=department_ids,
            )

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_principal] = override_principal
        return TestClient(app)

    def _create_leave(self, client):
        return client.post(
            "/me/leave-requests",
            json={
                "leave_type": "病假",
                "start_date": "2026-09-01",
                "end_date": "2026-09-02",
                "reason": "身体不适",
            },
        )

    def test_leave_preview_understands_type_and_date_range(self):
        response = self._client().post(
            "/me/leave-preview",
            json={"text": "我想请9月1日至3日病假", "today": "2026-08-30"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "is_leave_request": True,
                "leave_type": "病假",
                "start_date": "2026-09-01",
                "end_date": "2026-09-03",
                "reason": "我想请9月1日至3日病假",
            },
        )

    def test_policy_question_is_not_treated_as_leave_action(self):
        response = self._client().post(
            "/me/leave-preview",
            json={"text": "公司的病假制度是什么", "today": "2026-08-30"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["is_leave_request"])

    def test_leave_preview_understands_conversational_wedding_leave_and_weekday(self):
        response = self._client().post(
            "/me/leave-preview",
            json={"text": "周五弟弟结婚帮我请个假", "today": "2026-08-30"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["leave_type"], "婚假")
        self.assertEqual(response.json()["start_date"], "2026-09-04")
        self.assertEqual(response.json()["end_date"], "2026-09-04")

    def test_employee_sees_only_own_schedule_and_requests(self):
        employee = self._client()
        created = self._create_leave(employee)
        other = self._client("employee-2", department_ids=("dept-2",))

        self.assertEqual(created.status_code, 201)
        self.assertEqual(len(employee.get("/me/work-schedule").json()["leave_requests"]), 1)
        self.assertEqual(other.get("/me/work-schedule").json()["leave_requests"], [])

    def test_admin_can_replace_schedule_and_approve_request(self):
        created = self._create_leave(self._client())
        request_id = created.json()["id"]
        admin = self._client("admin-1", role="admin", department_ids=())
        days = [
            {
                "weekday": weekday,
                "enabled": weekday in (1, 3, 5),
                "start_time": "08:30",
                "end_time": "17:30",
            }
            for weekday in range(1, 8)
        ]

        schedule_response = admin.put(
            "/admin/employees/employee-1/work-schedule", json={"days": days}
        )
        approval = admin.patch(
            f"/admin/leave-requests/{request_id}", json={"status": "approved"}
        )
        employee_schedule = self._client().get("/me/work-schedule").json()

        self.assertEqual(schedule_response.status_code, 200)
        self.assertEqual(
            [day["weekday"] for day in schedule_response.json()["days"] if day["enabled"]],
            [1, 3, 5],
        )
        self.assertEqual(approval.status_code, 200)
        self.assertEqual(employee_schedule["leave_requests"][0]["status"], "approved")

    def test_employee_cannot_use_admin_schedule_endpoint(self):
        response = self._client().put(
            "/admin/employees/employee-1/work-schedule",
            json={
                "days": [
                    {
                        "weekday": weekday,
                        "enabled": weekday <= 5,
                        "start_time": "09:00",
                        "end_time": "18:00",
                    }
                    for weekday in range(1, 8)
                ]
            },
        )

        self.assertEqual(response.status_code, 403)

    def test_admin_has_global_schedule_and_leave_approval_lists(self):
        created = self._create_leave(self._client())
        self.assertEqual(created.status_code, 201)
        admin = self._client("admin-1", role="admin", department_ids=())

        schedules = admin.get("/admin/work-schedules")
        requests = admin.get("/admin/leave-requests")

        self.assertEqual(schedules.status_code, 200)
        self.assertEqual({item["username"] for item in schedules.json()}, {"alice", "bob"})
        self.assertEqual(requests.status_code, 200)
        self.assertEqual([item["username"] for item in requests.json()], ["alice"])


if __name__ == "__main__":
    unittest.main()
