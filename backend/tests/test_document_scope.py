import unittest
from unittest.mock import patch

import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.deps import Principal, get_current_principal
from app.kb import retriever
from app.models import Document, Thread, ThreadContextSetting, ThreadDocumentSelection
from app.routers import chat


class _Index:
    def __init__(self):
        self.chunk_ids = ["chunk-a", "chunk-b"]
        self.document_ids = ["doc-a", "doc-b"]
        self.texts = ["alpha", "beta"]
        self.vectors = np.array([[1.0, 0.0], [0.0, 1.0]])
        self.bm25 = None


class DocumentScopeTest(unittest.TestCase):
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

    def _client(self, user_id="user-1", department_ids=("dept-1",)):
        app = FastAPI()
        app.include_router(chat.router)

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
                role="employee",
                department_id=department_ids[0] if department_ids else None,
                department_ids=department_ids,
            )

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_principal] = override_principal
        return TestClient(app)

    def _thread(self, user_id="user-1"):
        with self.session_factory() as db:
            thread = Thread(user_id=user_id, department_id="dept-1", title="Scoped thread")
            db.add(thread)
            db.commit()
            return thread.id

    def _document(self, document_id, department_id):
        with self.session_factory() as db:
            db.add(
                Document(
                    id=document_id,
                    department_id=department_id,
                    title=document_id,
                    content="content",
                    uploaded_by="user-1",
                )
            )
            db.commit()

    def test_owner_saves_multiple_authorized_documents(self):
        thread_id = self._thread()
        self._document("doc-1", "dept-1")
        self._document("doc-2", "dept-1")

        response = self._client().patch(
            f"/chat/threads/{thread_id}/context-settings",
            json={"document_scope_mode": "selected", "document_ids": ["doc-1", "doc-2", "doc-1"]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "memory_level": 3,
            "document_scope_mode": "selected",
            "document_ids": ["doc-1", "doc-2"],
        })

    def test_mixed_authorized_and_unauthorized_documents_rejects_entire_update(self):
        thread_id = self._thread()
        self._document("doc-old", "dept-1")
        self._document("doc-ok", "dept-1")
        self._document("doc-forbidden", "dept-2")
        with self.session_factory() as db:
            db.add(ThreadContextSetting(thread_id=thread_id, document_scope_mode="selected"))
            db.add(ThreadDocumentSelection(thread_id=thread_id, document_id="doc-old"))
            db.commit()

        response = self._client().patch(
            f"/chat/threads/{thread_id}/context-settings",
            json={"document_scope_mode": "selected", "document_ids": ["doc-ok", "doc-forbidden"]},
        )

        self.assertEqual(response.status_code, 403)
        with self.session_factory() as db:
            self.assertEqual(
                [row.document_id for row in db.query(ThreadDocumentSelection)
                 .filter(ThreadDocumentSelection.thread_id == thread_id).all()],
                ["doc-old"],
            )

    def test_selected_scope_rejects_zero_documents(self):
        thread_id = self._thread()

        response = self._client().patch(
            f"/chat/threads/{thread_id}/context-settings",
            json={"document_scope_mode": "selected", "document_ids": []},
        )

        self.assertEqual(response.status_code, 422)

    def test_selected_scope_rejects_empty_partial_update_and_preserves_selection(self):
        thread_id = self._thread()
        self._document("doc-existing", "dept-1")
        with self.session_factory() as db:
            db.add(ThreadContextSetting(thread_id=thread_id, document_scope_mode="selected"))
            db.add(ThreadDocumentSelection(thread_id=thread_id, document_id="doc-existing"))
            db.commit()

        response = self._client().patch(
            f"/chat/threads/{thread_id}/context-settings",
            json={"document_ids": []},
        )

        self.assertEqual(response.status_code, 422)
        with self.session_factory() as db:
            self.assertEqual(
                [row.document_id for row in db.query(ThreadDocumentSelection)
                 .filter(ThreadDocumentSelection.thread_id == thread_id).all()],
                ["doc-existing"],
            )

    def test_other_users_thread_is_not_found(self):
        thread_id = self._thread("user-1")

        response = self._client("user-2").get(f"/chat/threads/{thread_id}/context-settings")

        self.assertEqual(response.status_code, 404)

    def test_resolved_empty_selected_scope_never_becomes_all_documents(self):
        thread_id = self._thread()
        with self.session_factory() as db:
            db.add(ThreadContextSetting(thread_id=thread_id, document_scope_mode="selected"))
            db.add(ThreadDocumentSelection(thread_id=thread_id, document_id="missing-document"))
            db.commit()

            from app.context.service import resolve_document_scope

            result = resolve_document_scope(
                db,
                principal=Principal("user-1", "user-1", "employee", "dept-1", ("dept-1",)),
                thread=db.get(Thread, thread_id),
            )

        self.assertEqual(result, frozenset())

    def test_retriever_filters_before_ranking_and_empty_scope_returns_no_chunks(self):
        index = _Index()
        with patch.object(retriever.department_index_cache, "get", return_value=index), patch.object(
            retriever, "embed_query", return_value=[1.0, 0.0]
        ):
            selected = retriever.search(
                None, department_id="dept-1", query="alpha", document_ids=frozenset({"doc-b"})
            )
            empty = retriever.search(
                None, department_id="dept-1", query="alpha", document_ids=frozenset()
            )

        self.assertEqual([chunk.document_id for chunk in selected], ["doc-b"])
        self.assertEqual(empty, [])


if __name__ == "__main__":
    unittest.main()
