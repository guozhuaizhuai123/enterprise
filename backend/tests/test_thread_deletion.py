import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.deps import Principal, get_current_principal
from app.models import Message, Thread, ThreadContextSetting, ThreadDocumentSelection
from app.routers import chat


class ThreadDeletionTest(unittest.TestCase):
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

    def _client(self, user_id: str) -> TestClient:
        app = FastAPI()
        app.include_router(chat.router)

        def override_db():
            db = self.session_factory()
            try:
                yield db
            finally:
                db.close()

        def override_principal() -> Principal:
            return Principal(
                user_id=user_id,
                username=user_id,
                role="employee",
                department_id="dept-1",
                department_ids=("dept-1",),
            )

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_principal] = override_principal
        return TestClient(app)

    def _create_thread_with_message(self, owner_id: str) -> str:
        with self.session_factory() as db:
            thread = Thread(user_id=owner_id, department_id="dept-1", title="待删除会话")
            db.add(thread)
            db.flush()
            db.add(Message(thread_id=thread.id, role="user", content="测试消息"))
            db.add(ThreadContextSetting(thread_id=thread.id, document_scope_mode="selected"))
            db.add_all(
                (
                    ThreadDocumentSelection(thread_id=thread.id, document_id="document-1"),
                    ThreadDocumentSelection(thread_id=thread.id, document_id="document-2"),
                )
            )
            db.commit()
            return thread.id

    def test_owner_can_delete_thread_and_its_messages(self):
        thread_id = self._create_thread_with_message("user-1")

        response = self._client("user-1").delete(f"/chat/threads/{thread_id}")

        self.assertEqual(response.status_code, 204)
        with self.session_factory() as db:
            self.assertIsNone(db.get(Thread, thread_id))
            self.assertEqual(db.query(Message).filter(Message.thread_id == thread_id).count(), 0)
            self.assertIsNone(db.get(ThreadContextSetting, thread_id))
            self.assertEqual(
                db.query(ThreadDocumentSelection)
                .filter(ThreadDocumentSelection.thread_id == thread_id)
                .count(),
                0,
            )

    def test_user_cannot_delete_another_users_thread(self):
        thread_id = self._create_thread_with_message("user-1")

        response = self._client("user-2").delete(f"/chat/threads/{thread_id}")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "thread not found"})
        with self.session_factory() as db:
            self.assertIsNotNone(db.get(Thread, thread_id))
            self.assertEqual(db.query(Message).filter(Message.thread_id == thread_id).count(), 1)


if __name__ == "__main__":
    unittest.main()
