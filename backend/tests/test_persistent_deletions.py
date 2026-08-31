import unittest
from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.deps import Principal, get_current_principal
from app.models import (
    AttendanceRecord,
    Department,
    Document,
    DocumentChunk,
    HolidayPeriod,
    LeaveRequest,
    SensitiveEvent,
    SensitiveKeyword,
    Thread,
    ThreadDocumentSelection,
    User,
    UserDepartment,
    UserMemory,
    WorkScheduleDay,
)
from app.routers import admin


class PersistentDeletionTest(unittest.TestCase):
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
                    User(
                        id="admin-1",
                        username="admin",
                        password_encrypted="encrypted",
                        role="admin",
                    ),
                    User(
                        id="employee-1",
                        username="alice",
                        password_encrypted="encrypted",
                        role="employee",
                        department_id="dept-1",
                    ),
                    UserDepartment(user_id="employee-1", department_id="dept-1"),
                )
            )
            db.commit()

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _admin_client(self):
        app = FastAPI()
        app.include_router(admin.router)

        def override_db():
            with self.session_factory() as db:
                yield db

        def override_principal():
            return Principal(
                user_id="admin-1",
                username="admin",
                role="admin",
                department_id=None,
                department_ids=(),
            )

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_principal] = override_principal
        return TestClient(app)

    def test_document_delete_api_removes_document_chunks_and_thread_selections_from_database(self):
        with self.session_factory() as db:
            document = Document(
                id="document-1",
                department_id="dept-1",
                title="制度",
                category="制度",
                content="需要从数据库完整删除的内容",
                uploaded_by="admin-1",
                owner_id="employee-1",
                owner_name="alice",
            )
            thread = Thread(id="thread-1", user_id="employee-1", department_id="dept-1")
            db.add_all((document, thread))
            db.flush()
            db.add_all(
                (
                    DocumentChunk(
                        id="chunk-1",
                        document_id=document.id,
                        department_id="dept-1",
                        chunk_index=0,
                        chunk_text=document.content,
                        tokens=["完整", "删除"],
                        embedding=[0.1, 0.2],
                    ),
                    ThreadDocumentSelection(
                        thread_id=thread.id,
                        document_id=document.id,
                    ),
                )
            )
            db.commit()

        response = self._admin_client().delete("/admin/documents/document-1")

        self.assertEqual(response.status_code, 204)
        with self.session_factory() as db:
            self.assertIsNone(db.get(Document, "document-1"))
            self.assertIsNone(db.get(DocumentChunk, "chunk-1"))
            self.assertIsNone(
                db.get(
                    ThreadDocumentSelection,
                    {"thread_id": "thread-1", "document_id": "document-1"},
                )
            )

    def test_sensitive_event_and_keyword_delete_are_committed_to_database(self):
        with self.session_factory() as db:
            db.add_all(
                (
                    SensitiveEvent(
                        id="event-1",
                        user_id="employee-1",
                        username="alice",
                        department_name="法务部",
                        question="敏感问题",
                        matched_keyword="敏感",
                        reason="测试",
                    ),
                    SensitiveKeyword(id="keyword-1", keyword="敏感", updated_by="admin-1"),
                )
            )
            db.commit()

        client = self._admin_client()
        event_response = client.delete("/admin/sensitive-events/event-1")
        keyword_response = client.delete("/admin/sensitive-keywords/keyword-1")

        self.assertEqual(event_response.status_code, 204)
        self.assertEqual(keyword_response.status_code, 204)
        with self.session_factory() as db:
            self.assertIsNone(db.get(SensitiveEvent, "event-1"))
            self.assertIsNone(db.get(SensitiveKeyword, "keyword-1"))

    def test_employee_delete_removes_personal_memory_schedule_and_leave_from_database(self):
        with self.session_factory() as db:
            db.add_all(
                (
                    UserMemory(
                        id="memory-1",
                        user_id="employee-1",
                        title="偏好",
                        content="回答严谨",
                    ),
                    WorkScheduleDay(
                        user_id="employee-1",
                        weekday=1,
                        enabled=True,
                        start_time="09:00",
                        end_time="18:00",
                        updated_by="admin-1",
                    ),
                    LeaveRequest(
                        id="leave-1",
                        user_id="employee-1",
                        leave_type="婚假",
                        start_date=date(2026, 9, 4),
                        end_date=date(2026, 9, 4),
                        reason="参加婚礼",
                    ),
                    AttendanceRecord(
                        id="attendance-1",
                        user_id="employee-1",
                        attendance_date=date(2026, 9, 1),
                        status="present",
                        note="正常",
                        recorded_by="admin-1",
                    ),
                )
            )
            db.commit()

        response = self._admin_client().delete("/admin/employees/employee-1")

        self.assertEqual(response.status_code, 204)
        with self.session_factory() as db:
            self.assertIsNone(db.get(User, "employee-1"))
            self.assertIsNone(db.get(UserMemory, "memory-1"))
            self.assertIsNone(
                db.get(WorkScheduleDay, {"user_id": "employee-1", "weekday": 1})
            )
            self.assertIsNone(db.get(LeaveRequest, "leave-1"))
            self.assertIsNone(db.get(AttendanceRecord, "attendance-1"))
            self.assertEqual(
                db.query(UserDepartment).filter(UserDepartment.user_id == "employee-1").count(),
                0,
            )

    def test_department_delete_removes_department_holidays_from_database(self):
        with self.session_factory() as db:
            db.add(
                HolidayPeriod(
                    id="holiday-1",
                    name="部门统一假期",
                    scope_type="department",
                    department_id="dept-1",
                    start_date=date(2026, 10, 1),
                    end_date=date(2026, 10, 2),
                    description="",
                    created_by="admin-1",
                )
            )
            db.commit()

        response = self._admin_client().delete("/admin/departments/dept-1")

        self.assertEqual(response.status_code, 204)
        with self.session_factory() as db:
            self.assertIsNone(db.get(Department, "dept-1"))
            self.assertIsNone(db.get(HolidayPeriod, "holiday-1"))


if __name__ == "__main__":
    unittest.main()
