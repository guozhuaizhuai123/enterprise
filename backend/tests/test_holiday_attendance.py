import unittest
from datetime import date, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app import models
from app.db import Base, get_db
from app.deps import Principal, get_current_principal
from app.routers import schedule
from app.schedule import service
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


class HolidayAttendanceModelTest(unittest.TestCase):
    def test_models_define_persistent_holiday_and_attendance_fields(self):
        self.assertTrue(hasattr(models, "HolidayPeriod"))
        self.assertTrue(hasattr(models, "AttendanceRecord"))

        holiday_columns = models.HolidayPeriod.__table__.columns
        for name in (
            "name",
            "scope_type",
            "department_id",
            "start_date",
            "end_date",
            "description",
            "created_by",
        ):
            self.assertIn(name, holiday_columns)

        attendance_columns = models.AttendanceRecord.__table__.columns
        for name in ("user_id", "attendance_date", "status", "note", "recorded_by"):
            self.assertIn(name, attendance_columns)


class HolidayAttendanceServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)()
        self.session.add_all(
            (
                models.Department(id="dept-1", name="法务部"),
                models.Department(id="dept-2", name="财务部"),
                models.User(
                    id="employee-1",
                    username="alice",
                    password_encrypted="encrypted",
                    role="employee",
                    department_id="dept-1",
                ),
                models.User(
                    id="employee-2",
                    username="bob",
                    password_encrypted="encrypted",
                    role="employee",
                    department_id="dept-2",
                ),
                models.User(
                    id="admin-1",
                    username="admin",
                    password_encrypted="encrypted",
                    role="admin",
                ),
                models.UserDepartment(user_id="employee-1", department_id="dept-1"),
                models.UserDepartment(user_id="employee-2", department_id="dept-2"),
            )
        )
        self.session.commit()

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _holiday(self, holiday_id, name, scope_type, start_date, end_date, department_id=None):
        return models.HolidayPeriod(
            id=holiday_id,
            name=name,
            scope_type=scope_type,
            department_id=department_id,
            start_date=start_date,
            end_date=end_date,
            description="",
            created_by="admin-1",
        )

    def test_company_and_member_department_holidays_are_combined(self):
        self.session.add_all(
            (
                self._holiday(
                    "holiday-company",
                    "国庆节",
                    "company",
                    date(2026, 10, 1),
                    date(2026, 10, 7),
                ),
                self._holiday(
                    "holiday-legal",
                    "法务部调休",
                    "department",
                    date(2026, 10, 8),
                    date(2026, 10, 8),
                    "dept-1",
                ),
                self._holiday(
                    "holiday-finance",
                    "财务部调休",
                    "department",
                    date(2026, 10, 9),
                    date(2026, 10, 9),
                    "dept-2",
                ),
            )
        )
        self.session.commit()

        self.assertTrue(hasattr(service, "list_applicable_holidays"))
        holidays = service.list_applicable_holidays(self.session, "employee-1")

        self.assertEqual([item.name for item in holidays], ["国庆节", "法务部调休"])

    def test_history_counts_each_day_once_and_excludes_holidays_from_leave(self):
        self.session.add_all(
            (
                self._holiday(
                    "holiday-1",
                    "元旦",
                    "company",
                    date(2026, 1, 1),
                    date(2026, 1, 1),
                ),
                self._holiday(
                    "holiday-2",
                    "部门假期",
                    "department",
                    date(2026, 1, 2),
                    date(2026, 1, 2),
                    "dept-1",
                ),
                models.LeaveRequest(
                    id="leave-1",
                    user_id="employee-1",
                    leave_type="年假",
                    start_date=date(2026, 1, 2),
                    end_date=date(2026, 1, 5),
                    reason="休假",
                    status="approved",
                ),
                models.AttendanceRecord(
                    id="attendance-1",
                    user_id="employee-1",
                    attendance_date=date(2026, 1, 6),
                    status="present",
                    note="",
                    recorded_by="admin-1",
                ),
                models.AttendanceRecord(
                    id="attendance-2",
                    user_id="employee-1",
                    attendance_date=date(2026, 1, 7),
                    status="absent",
                    note="",
                    recorded_by="admin-1",
                ),
            )
        )
        self.session.commit()

        self.assertTrue(hasattr(service, "build_attendance_history"))
        history = service.build_attendance_history(
            self.session,
            "employee-1",
            2026,
            date(2026, 1, 7),
        )

        self.assertEqual(history.weekly_rest_days, 2)
        self.assertEqual(history.organization_holiday_days, 2)
        self.assertEqual(history.scheduled_work_days, 3)
        self.assertEqual(history.approved_leave_days, 1)
        self.assertEqual(history.expected_attendance_days, 2)
        self.assertEqual(history.recorded_attendance_days, 2)
        self.assertEqual(history.unrecorded_attendance_days, 0)
        self.assertEqual(history.present_days, 1)
        self.assertEqual(history.absent_days, 1)
        self.assertEqual(history.attendance_rate, 0.5)

    def test_no_attendance_records_do_not_become_absence(self):
        self.assertTrue(hasattr(service, "build_attendance_history"))
        history = service.build_attendance_history(
            self.session,
            "employee-2",
            2026,
            date(2026, 1, 2),
        )

        self.assertEqual(history.recorded_attendance_days, 0)
        self.assertEqual(history.unrecorded_attendance_days, 2)
        self.assertEqual(history.absent_days, 0)
        self.assertIsNone(history.attendance_rate)

    def test_rest_day_attendance_counts_as_recorded_coverage(self):
        rest_day = date(2026, 8, 30)  # Sunday under the default schedule.
        self.session.add(
            models.AttendanceRecord(
                id="attendance-rest-day",
                user_id="employee-1",
                attendance_date=rest_day,
                status="present",
                note="周末加班",
                recorded_by="employee-1",
            )
        )
        self.session.commit()

        history = service.build_attendance_history(
            self.session,
            "employee-1",
            2026,
            rest_day,
        )

        self.assertEqual(history.recorded_attendance_days, 1)
        self.assertEqual(history.present_days, 1)
        self.assertEqual(history.attendance_rate, 1.0)
        self.assertEqual(
            [record.id for record in history.attendance_records],
            ["attendance-rest-day"],
        )

    def test_holiday_creation_validates_scope_and_rejects_exact_duplicate(self):
        self.assertTrue(hasattr(service, "create_holiday"))
        created = service.create_holiday(
            self.session,
            name=" 国庆节 ",
            scope_type="company",
            department_id=None,
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 7),
            description=" 全国假期 ",
            created_by="admin-1",
        )

        self.assertEqual(created.name, "国庆节")
        self.assertEqual(created.description, "全国假期")
        with self.assertRaises(service.HolidayConflictError):
            service.create_holiday(
                self.session,
                name="国庆节",
                scope_type="company",
                department_id=None,
                start_date=date(2026, 10, 1),
                end_date=date(2026, 10, 7),
                description="不同说明仍是同一个假期",
                created_by="admin-1",
            )
        with self.assertRaises(service.HolidayValidationError):
            service.create_holiday(
                self.session,
                name="部门假期",
                scope_type="department",
                department_id=None,
                start_date=date(2026, 10, 1),
                end_date=date(2026, 10, 1),
                description="",
                created_by="admin-1",
            )

    def test_attendance_upsert_overwrites_same_employee_date(self):
        self.assertTrue(hasattr(service, "upsert_attendance"))
        created = service.upsert_attendance(
            self.session,
            user_id="employee-1",
            attendance_date=date(2026, 1, 6),
            status="present",
            note="正常",
            recorded_by="admin-1",
        )
        updated = service.upsert_attendance(
            self.session,
            user_id="employee-1",
            attendance_date=date(2026, 1, 6),
            status="late",
            note="迟到十分钟",
            recorded_by="admin-1",
        )

        self.assertEqual(updated.id, created.id)
        self.assertEqual(updated.status, "late")
        self.assertEqual(updated.note, "迟到十分钟")
        self.assertEqual(self.session.query(models.AttendanceRecord).count(), 1)


class HolidayAttendanceApiTest(unittest.TestCase):
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
                    models.Department(id="dept-1", name="法务部"),
                    models.Department(id="dept-2", name="财务部"),
                    models.User(
                        id="employee-1",
                        username="alice",
                        password_encrypted="encrypted",
                        role="employee",
                        department_id="dept-1",
                    ),
                    models.User(
                        id="employee-2",
                        username="bob",
                        password_encrypted="encrypted",
                        role="employee",
                        department_id="dept-2",
                    ),
                    models.User(
                        id="admin-1",
                        username="admin",
                        password_encrypted="encrypted",
                        role="admin",
                    ),
                    models.UserDepartment(user_id="employee-1", department_id="dept-1"),
                    models.UserDepartment(user_id="employee-2", department_id="dept-2"),
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
            with self.session_factory() as db:
                yield db

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

    def _admin(self):
        return self._client("admin-1", role="admin", department_ids=())

    def test_admin_creates_company_and_department_holidays_with_filtered_list(self):
        admin = self._admin()
        company = admin.post(
            "/admin/holidays",
            json={
                "name": "国庆节",
                "scope_type": "company",
                "department_id": None,
                "start_date": "2026-10-01",
                "end_date": "2026-10-07",
                "description": "全公司休假",
            },
        )
        department = admin.post(
            "/admin/holidays",
            json={
                "name": "法务部调休",
                "scope_type": "department",
                "department_id": "dept-1",
                "start_date": "2026-10-08",
                "end_date": "2026-10-08",
                "description": "",
            },
        )
        filtered = admin.get("/admin/holidays", params={"department_id": "dept-2"})

        self.assertEqual(company.status_code, 201)
        self.assertEqual(company.json()["scope_type"], "company")
        self.assertEqual(department.status_code, 201)
        self.assertEqual(department.json()["department_name"], "法务部")
        self.assertEqual([item["name"] for item in filtered.json()], ["国庆节"])

    def test_expired_holidays_and_leave_are_hidden_from_activity_but_kept_in_history(self):
        today = date.today()
        with self.session_factory() as db:
            db.add_all(
                (
                    models.HolidayPeriod(
                        id="holiday-expired",
                        name="已结束假期",
                        scope_type="company",
                        start_date=today - timedelta(days=3),
                        end_date=today - timedelta(days=2),
                        description="",
                        created_by="admin-1",
                    ),
                    models.HolidayPeriod(
                        id="holiday-future",
                        name="即将放假",
                        scope_type="company",
                        start_date=today + timedelta(days=2),
                        end_date=today + timedelta(days=3),
                        description="",
                        created_by="admin-1",
                    ),
                    models.LeaveRequest(
                        id="leave-expired",
                        user_id="employee-1",
                        leave_type="年假",
                        start_date=today - timedelta(days=3),
                        end_date=today - timedelta(days=2),
                        reason="已结束",
                        status="approved",
                    ),
                    models.LeaveRequest(
                        id="leave-future",
                        user_id="employee-1",
                        leave_type="事假",
                        start_date=today + timedelta(days=1),
                        end_date=today + timedelta(days=1),
                        reason="未来",
                        status="pending",
                    ),
                )
            )
            db.commit()

        employee = self._client()
        active = employee.get("/me/work-schedule")
        history = employee.get("/me/attendance-history", params={"year": today.year})

        self.assertEqual(active.status_code, 200)
        self.assertIn("holidays", active.json())
        self.assertEqual([item["name"] for item in active.json()["holidays"]], ["即将放假"])
        self.assertEqual(
            [item["id"] for item in active.json()["leave_requests"]],
            ["leave-future"],
        )
        self.assertEqual(history.status_code, 200)
        self.assertIn("holiday-expired", [item["id"] for item in history.json()["holidays"]])
        self.assertIn("leave-expired", [item["id"] for item in history.json()["leave_requests"]])

    def test_admin_attendance_upsert_list_and_delete_persist_to_database(self):
        admin = self._admin()
        attendance_date = date.today().isoformat()
        created = admin.put(
            f"/admin/employees/employee-1/attendance/{attendance_date}",
            json={"status": "present", "note": "正常"},
        )
        updated = admin.put(
            f"/admin/employees/employee-1/attendance/{attendance_date}",
            json={"status": "late", "note": "迟到"},
        )
        listed = admin.get(
            "/admin/attendance",
            params={"department_id": "dept-1", "year": date.today().year},
        )
        deleted = admin.delete(
            f"/admin/employees/employee-1/attendance/{attendance_date}"
        )

        self.assertEqual(created.status_code, 200)
        self.assertEqual(updated.json()["status"], "late")
        self.assertEqual([item["username"] for item in listed.json()], ["alice"])
        self.assertEqual(deleted.status_code, 204)
        with self.session_factory() as db:
            self.assertEqual(db.query(models.AttendanceRecord).count(), 0)

    def test_employee_can_create_only_their_missing_attendance_for_today(self):
        employee = self._client()

        missing = employee.get("/me/attendance/today")
        created = employee.post(
            "/me/attendance/today",
            json={
                "status": "remote",
                "note": "居家办公",
                "attendance_date": (date.today() - timedelta(days=1)).isoformat(),
            },
        )
        current = employee.get("/me/attendance/today")

        self.assertEqual(missing.status_code, 200)
        self.assertIsNone(missing.json())
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["attendance_date"], date.today().isoformat())
        self.assertEqual(created.json()["recorded_by"], "employee-1")
        self.assertEqual(current.json()["status"], "remote")

    def test_employee_cannot_overwrite_existing_attendance_but_admin_can(self):
        employee = self._client()
        admin = self._admin()
        attendance_date = date.today().isoformat()

        first = employee.post(
            "/me/attendance/today",
            json={"status": "present", "note": "准时"},
        )
        duplicate = employee.post(
            "/me/attendance/today",
            json={"status": "late", "note": "员工尝试覆盖"},
        )
        admin_update = admin.put(
            f"/admin/employees/employee-1/attendance/{attendance_date}",
            json={"status": "late", "note": "管理员核定"},
        )
        employee_retry = employee.post(
            "/me/attendance/today",
            json={"status": "present", "note": "再次尝试覆盖"},
        )
        current = employee.get("/me/attendance/today")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(admin_update.status_code, 200)
        self.assertEqual(employee_retry.status_code, 409)
        self.assertEqual(current.json()["status"], "late")
        self.assertEqual(current.json()["note"], "管理员核定")
        self.assertEqual(current.json()["recorded_by"], "admin-1")

    def test_admin_cannot_use_employee_self_attendance_endpoint(self):
        admin = self._admin()

        response = admin.post(
            "/me/attendance/today",
            json={"status": "present", "note": ""},
        )

        self.assertEqual(response.status_code, 403)

    def test_admin_holiday_delete_is_persistent_and_employee_cannot_manage_holidays(self):
        with self.session_factory() as db:
            db.add(
                models.HolidayPeriod(
                    id="holiday-1",
                    name="测试假期",
                    scope_type="company",
                    start_date=date.today(),
                    end_date=date.today(),
                    description="",
                    created_by="admin-1",
                )
            )
            db.commit()

        forbidden = self._client().delete("/admin/holidays/holiday-1")
        deleted = self._admin().delete("/admin/holidays/holiday-1")

        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(deleted.status_code, 204)
        with self.session_factory() as db:
            self.assertIsNone(db.get(models.HolidayPeriod, "holiday-1"))


if __name__ == "__main__":
    unittest.main()
