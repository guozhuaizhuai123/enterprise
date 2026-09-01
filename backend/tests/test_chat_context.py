import asyncio
import json
import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.agents import faithfulness_check
from app.config import Settings
from app.context.service import ChatHistory, load_chat_history
from app.context.prompt import build_answer_messages
from app.context.query import (
    ensure_summary,
    merge_department_memories,
    needs_history,
    rewrite_followup,
)
from app.context.tokens import count_tokens, select_recent_messages
from app.db import Base
from app.db import get_db
from app.deps import Principal, get_current_principal
from app.kb.retriever import RetrievedChunk
from app.models import (
    Department,
    DepartmentMemory,
    Document,
    Message,
    MessageContextFlag,
    Thread,
    ThreadContextSetting,
    ThreadDocumentSelection,
    UserChatSetting,
    UserMemory,
)
from app.routers import chat
from app.schemas import AskRequest


class ChatContextModelTest(unittest.TestCase):
    def test_first_ask_schema_accepts_multiple_documents(self):
        payload = AskRequest(
            question="审批流程是什么？",
            memory_level=3,
            document_scope_mode="selected",
            document_ids=["doc-1", "doc-2"],
        )

        self.assertEqual(payload.document_ids, ["doc-1", "doc-2"])

    def test_chat_context_models_have_expected_columns(self):
        expected = {
            UserMemory: {"id", "user_id", "title", "content", "enabled", "created_at", "updated_at"},
            DepartmentMemory: {
                "id", "department_id", "title", "content", "enabled",
                "created_by", "updated_by", "created_at", "updated_at",
            },
            UserChatSetting: {"user_id", "default_memory_level", "updated_at"},
            ThreadContextSetting: {
                "thread_id", "memory_level", "document_scope_mode", "summary_text",
                "summary_through_message_id", "summary_token_count", "summary_updated_at", "updated_at",
            },
            ThreadDocumentSelection: {"thread_id", "document_id", "created_at"},
            MessageContextFlag: {"message_id", "context_eligible", "reason", "created_at"},
        }

        for model, columns in expected.items():
            self.assertEqual(set(model.__table__.columns.keys()), columns)

    def test_memory_budgets_are_parsed(self):
        settings = Settings(memory_token_budgets="0,2000,6000,12000,24000")

        self.assertEqual(settings.memory_budgets, (0, 2000, 6000, 12000, 24000))

    def test_document_deletion_removes_thread_selections(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        try:
            thread = Thread(user_id="user-1")
            document = Document(
                department_id="dept-1",
                title="Selected document",
                content="content",
                uploaded_by="user-1",
            )
            session.add_all((thread, document))
            session.flush()
            session.add(ThreadDocumentSelection(thread_id=thread.id, document_id=document.id))
            session.commit()

            session.delete(document)
            session.commit()

            self.assertIsNone(session.get(ThreadDocumentSelection, (thread.id, document.id)))
        finally:
            session.close()
            Base.metadata.drop_all(engine)
            engine.dispose()


class ChatHistoryAndPromptTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_level_one_budget_selects_no_history(self):
        messages = [
            {"id": "m1", "role": "user", "content": "older question"},
            {"id": "m2", "role": "assistant", "content": "older answer"},
        ]

        self.assertEqual(select_recent_messages(messages, token_budget=0), [])

    def test_current_message_is_excluded_from_history(self):
        messages = [
            {"id": "m1", "role": "user", "content": "older question"},
            {"id": "current", "role": "user", "content": "current question"},
        ]

        selected = select_recent_messages(messages, token_budget=2000, exclude_message_id="current")

        self.assertEqual([item["id"] for item in selected], ["m1"])

    def test_whole_message_budget_keeps_chronological_order(self):
        messages = [
            {"id": "m1", "role": "user", "content": "first message"},
            {"id": "m2", "role": "assistant", "content": "second message"},
            {"id": "m3", "role": "user", "content": "third message"},
        ]
        budget = count_tokens(messages[1]["content"]) + count_tokens(messages[2]["content"])

        selected = select_recent_messages(messages, token_budget=budget)

        self.assertEqual([item["id"] for item in selected], ["m2", "m3"])

    def test_ineligible_flags_are_excluded_but_unflagged_messages_remain(self):
        thread = Thread(user_id="user-1")
        self.session.add(thread)
        self.session.flush()
        base_time = datetime(2026, 8, 30, tzinfo=UTC)
        allowed = Message(thread_id=thread.id, role="user", content="allowed", created_at=base_time)
        blocked = Message(
            thread_id=thread.id,
            role="assistant",
            content="blocked",
            created_at=base_time + timedelta(seconds=1),
        )
        self.session.add_all((allowed, blocked))
        self.session.flush()
        self.session.add(
            MessageContextFlag(
                message_id=blocked.id,
                context_eligible=False,
                reason="sensitive_blocked",
            )
        )
        self.session.commit()

        history = load_chat_history(
            self.session,
            thread.id,
            memory_level=2,
            current_message_id=None,
        )

        self.assertEqual(history.messages, [{"role": "user", "content": "allowed"}])
        self.assertEqual(
            history.summary_messages,
            [{"id": allowed.id, "role": "user", "content": "allowed"}],
        )

    def test_summary_is_returned_only_for_levels_three_through_five(self):
        thread = Thread(user_id="user-1")
        self.session.add(thread)
        self.session.flush()
        self.session.add(
            ThreadContextSetting(
                thread_id=thread.id,
                memory_level=3,
                summary_text="cached discussion",
            )
        )
        self.session.commit()

        summaries = [
            load_chat_history(self.session, thread.id, level, current_message_id=None).summary
            for level in range(1, 6)
        ]

        self.assertEqual(summaries, ["", "", "cached discussion", "cached discussion", "cached discussion"])

    def test_assembled_messages_preserve_priority_and_end_with_question_and_evidence(self):
        result = build_answer_messages(
            question="Who approves it?",
            evidence="[C1] Legal lead approval is required.",
            request_time=datetime(2026, 8, 30, 8, 0, tzinfo=UTC),
            department_memories=["State risks."],
            user_memories=["Include the current time."],
            summary="The team discussed contract approval.",
            history=[{"role": "user", "content": "What is the contract process?"}],
        )
        text = "\n".join(str(item["content"]) for item in result)

        self.assertLess(text.index("State risks."), text.index("Include the current time."))
        self.assertLess(text.index("Include the current time."), text.index("The team discussed contract approval."))
        self.assertLess(text.index("The team discussed contract approval."), text.index("What is the contract process?"))
        self.assertEqual(result[-1]["role"], "user")
        self.assertIn("Who approves it?", result[-1]["content"])
        self.assertIn("[C1] Legal lead approval is required.", result[-1]["content"])

    def test_context_settings_enforce_database_constraints(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        try:
            for setting in (
                UserChatSetting(user_id="user-invalid", default_memory_level=0),
                ThreadContextSetting(thread_id="thread-invalid-level", memory_level=6),
                ThreadContextSetting(
                    thread_id="thread-invalid-scope", document_scope_mode="department"
                ),
            ):
                session.add(setting)
                with self.assertRaises(IntegrityError):
                    session.commit()
                session.rollback()
        finally:
            session.close()
            Base.metadata.drop_all(engine)
            engine.dispose()


class ContextIntelligenceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_pronoun_and_short_followups_need_history(self):
        self.assertTrue(needs_history("那需要谁审批？"))
        self.assertTrue(needs_history("好吗"))
        self.assertFalse(needs_history("公司的办公时间是什么？"))

    async def test_rewrite_returns_standalone_query_and_falls_back_after_model_error(self):
        history = [{"role": "user", "content": "合同流程是什么？"}]
        with patch(
            "app.context.query.call_json",
            new=AsyncMock(return_value={"query": "合同审批需要由谁完成？"}),
        ):
            result = await rewrite_followup("那需要谁审批？", "讨论合同流程", history)
        self.assertEqual(result, "合同审批需要由谁完成？")

        with patch("app.context.query.call_json", new=AsyncMock(side_effect=RuntimeError("offline"))):
            fallback = await rewrite_followup("那需要谁审批？", "讨论合同流程", history)
        self.assertEqual(fallback, "合同流程是什么？\n那需要谁审批？")

    async def test_levels_one_through_three_never_generate_summary(self):
        setting = ThreadContextSetting(thread_id="thread-summary-low", summary_text="cached")
        self.session.add(setting)
        self.session.commit()
        history = [{"id": "m1", "role": "user", "content": "older context"}]

        with patch("app.context.query.call_json", new=AsyncMock()) as call_json:
            for level in range(1, 4):
                self.assertEqual(await ensure_summary(self.session, setting, history, level), "cached")
        call_json.assert_not_awaited()

    async def test_level_four_summary_updates_after_threshold_and_failure_preserves_old_fields(self):
        setting = ThreadContextSetting(
            thread_id="thread-summary-high",
            summary_text="old summary",
            summary_through_message_id="old",
            summary_token_count=7,
            summary_updated_at=datetime(2026, 8, 1, tzinfo=UTC),
        )
        self.session.add(setting)
        self.session.commit()
        history = [{"id": "m2", "role": "user", "content": "new context " * 9000}]

        with patch("app.context.query.get_settings") as get_settings, patch(
            "app.context.query.call_json", new=AsyncMock(return_value={"summary": "new summary"})
        ) as call_json:
            get_settings.return_value.summary_trigger_tokens = 1
            self.assertEqual(await ensure_summary(self.session, setting, history, 4), "new summary")
        call_json.assert_awaited_once()
        self.assertEqual(setting.summary_text, "new summary")
        self.assertEqual(setting.summary_through_message_id, "m2")
        self.assertIsNotNone(setting.summary_updated_at)

        old_fields = (
            setting.summary_text,
            setting.summary_through_message_id,
            setting.summary_token_count,
            setting.summary_updated_at,
        )
        history.append({"id": "m3", "role": "assistant", "content": "later context " * 9000})
        with patch("app.context.query.get_settings") as get_settings, patch(
            "app.context.query.call_json", new=AsyncMock(return_value={})
        ):
            get_settings.return_value.summary_trigger_tokens = 1
            self.assertEqual(await ensure_summary(self.session, setting, history, 4), "new summary")
        self.assertEqual(
            (
                setting.summary_text,
                setting.summary_through_message_id,
                setting.summary_token_count,
                setting.summary_updated_at,
            ),
            old_fields,
        )

    async def test_zero_and_one_department_memory_merges_avoid_model(self):
        with patch("app.context.query.call_json", new=AsyncMock()) as call_json:
            self.assertEqual(await merge_department_memories({}), ([], []))
            self.assertEqual(
                await merge_department_memories({"legal": ["strict", "enabled"]}),
                (["strict", "enabled"], []),
            )
        call_json.assert_not_awaited()

    async def test_record_memories_are_ordered_by_created_at_then_id(self):
        legal_memories = [
            {"id": "z", "content": "legal late", "created_at": datetime(2026, 8, 2, tzinfo=UTC)},
            SimpleNamespace(
                id="b",
                content="legal early b",
                enabled=True,
                created_at=datetime(2026, 8, 1, tzinfo=UTC),
            ),
            {"id": "a", "content": "legal early a", "created_at": datetime(2026, 8, 1, tzinfo=UTC)},
        ]
        self.assertEqual(
            await merge_department_memories({"legal": legal_memories}),
            (["legal early a", "legal early b", "legal late"], []),
        )

        with patch("app.context.query.call_json", new=AsyncMock(return_value={})):
            merged, _ = await merge_department_memories(
                {"sales": [{"id": "s", "content": "sales", "created_at": datetime(2026, 8, 1, tzinfo=UTC)}], "legal": legal_memories}
            )
        self.assertEqual(merged, ["legal early a", "legal early b", "legal late", "sales"])

    async def test_two_department_merge_uses_strict_result_and_malformed_output_falls_back(self):
        memories = {"sales": ["brief"], "legal": ["complete risks"]}
        with patch(
            "app.context.query.call_json",
            new=AsyncMock(
                return_value={
                    "merged_instructions": ["Complete risks, but concise."],
                    "conflicts": [{"reason": "detail", "winner": "strict"}],
                }
            ),
        ):
            merged, conflicts = await merge_department_memories(memories)
        self.assertEqual(merged, ["Complete risks, but concise."])
        self.assertEqual(conflicts, [{"reason": "detail", "winner": "strict"}])

        with patch(
            "app.context.query.call_json",
            new=AsyncMock(
                return_value={
                    "merged_instructions": ["Complete risks."],
                    "conflicts": [],
                }
            ),
        ):
            merged, conflicts = await merge_department_memories(memories)
        self.assertEqual(merged, ["Complete risks."])
        self.assertEqual(conflicts, [])

        with patch("app.context.query.call_json", new=AsyncMock(return_value={"merged_instructions": "bad"})):
            merged, conflicts = await merge_department_memories(memories)
        self.assertEqual(merged, ["complete risks", "brief"])
        self.assertEqual(conflicts[0]["winner"], "strict")

        with patch(
            "app.context.query.call_json",
            new=AsyncMock(return_value={"merged_instructions": [], "conflicts": []}),
        ):
            merged, conflicts = await merge_department_memories(memories)
        self.assertEqual(merged, ["complete risks", "brief"])
        self.assertEqual(conflicts[0]["winner"], "strict")

    async def test_faithfulness_rejects_empty_and_wrongly_typed_model_results(self):
        malformed_results = (
            {},
            {"faithful": "true", "concern": ""},
            {"faithful": True, "concern": None},
        )

        for result in malformed_results:
            with self.subTest(result=result), patch(
                "app.agents.faithfulness_check.call_json",
                new=AsyncMock(return_value=result),
            ):
                with self.assertRaises(ValueError):
                    await faithfulness_check.run("question", "answer", [])


class ChatAskPreparationTest(unittest.TestCase):
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

    def _client(self, user_id="user-1", department_ids=("dept-1",), role="employee"):
        app = FastAPI()
        app.include_router(chat.router)

        def override_db():
            with self.session_factory() as db:
                yield db

        def override_principal():
            return Principal(
                user_id=user_id,
                username=user_id,
                role=role,
                department_id=department_ids[0] if department_ids else None,
                department_ids=department_ids,
                roles=(role,),
            )

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_principal] = override_principal
        return TestClient(app)

    def test_low_risk_natural_language_query_executes_and_returns_result_event(self):
        """Leaving a low-risk action at preview would make the management assistant show no answer."""
        from app.assistant.adapters import install_production_adapters
        from app.models import Project
        from sse_starlette.sse import AppStatus

        AppStatus.should_exit_event = None
        with self.session_factory() as db:
            db.add(Department(id="dept-1", name="研发", code="RND"))
            db.add(Project(id="project-1", code="P-1", name="知识库项目", department_id="dept-1"))
            db.commit()
        install_production_adapters()

        with patch.object(chat, "SessionLocal", self.session_factory), patch.object(
            chat, "run_ask", side_effect=AssertionError("management query must not call document RAG")
        ):
            with self._client(user_id="root", department_ids=(), role="admin") as client:
                response = client.post("/chat/ask", json={"question": "查询一下最近的项目"})

        self.assertEqual(response.status_code, 200)
        events = [
            json.loads(line.removeprefix("data: "))
            for line in response.text.splitlines()
            if line.startswith("data: {")
        ]
        result_event = next(event for event in events if event["node"] == "query_result")
        self.assertEqual(result_event["status"], "completed")
        self.assertEqual(result_event["tool_name"], "list_projects")
        self.assertEqual(result_event["result"]["items"][0]["name"], "知识库项目")
        self.assertFalse(any(event["node"] == "action_preview" for event in events))

    def _document(self, document_id, department_id="dept-1"):
        with self.session_factory() as db:
            db.add(
                Document(
                    id=document_id,
                    department_id=department_id,
                    title=document_id,
                    content="content",
                    uploaded_by="uploader",
                )
            )
            db.commit()

    def _post_with_capture(self, payload):
        from sse_starlette.sse import AppStatus

        AppStatus.should_exit_event = None
        captured = {}

        async def fake_run_ask(db, **kwargs):
            captured.update(kwargs)
            yield {"node": "final", "status": "completed", "answer": "ok", "citations": []}

        with patch.object(chat, "SessionLocal", self.session_factory), patch.object(
            chat, "run_ask", new=fake_run_ask
        ):
            with self._client() as client:
                response = client.post("/chat/ask", json=payload)
        self.assertEqual(response.status_code, 200)
        return captured

    def test_first_ask_persists_initial_context_and_passes_owned_memory(self):
        self._document("doc-1")
        self._document("doc-2")
        with self.session_factory() as db:
            db.add_all(
                (
                    UserMemory(user_id="user-1", title="mine", content="my preference", enabled=True),
                    UserMemory(user_id="user-2", title="other", content="private other", enabled=True),
                )
            )
            db.commit()

        captured = self._post_with_capture(
            {
                "question": "审批流程是什么？",
                "memory_level": 4,
                "document_scope_mode": "selected",
                "document_ids": ["doc-1", "doc-2"],
            }
        )

        self.assertEqual(captured["memory_level"], 4)
        self.assertEqual(captured["document_scope_mode"], "selected")
        self.assertEqual(captured["selected_document_ids"], frozenset({"doc-1", "doc-2"}))
        self.assertEqual(captured["user_memories"], ("my preference",))
        self.assertEqual(captured["history"].messages, [])
        self.assertNotIn(
            captured["current_message_id"],
            [message.get("id") for message in captured["history"].summary_messages],
        )
        with self.session_factory() as db:
            setting = db.get(ThreadContextSetting, captured["thread_id"])
            self.assertEqual((setting.memory_level, setting.document_scope_mode), (4, "selected"))
            self.assertEqual(
                {
                    row.document_id
                    for row in db.query(ThreadDocumentSelection)
                    .filter(ThreadDocumentSelection.thread_id == captured["thread_id"])
                    .all()
                },
                {"doc-1", "doc-2"},
            )

    def test_existing_thread_ignores_ask_context_overrides(self):
        self._document("doc-kept")
        self._document("doc-ignored")
        with self.session_factory() as db:
            thread = Thread(user_id="user-1", department_id="dept-1")
            db.add(thread)
            db.flush()
            db.add(ThreadContextSetting(thread_id=thread.id, memory_level=5, document_scope_mode="selected"))
            db.add(ThreadDocumentSelection(thread_id=thread.id, document_id="doc-kept"))
            db.commit()
            thread_id = thread.id

        captured = self._post_with_capture(
            {
                "question": "继续",
                "thread_id": thread_id,
                "memory_level": 1,
                "document_scope_mode": "all",
                "document_ids": ["doc-ignored"],
            }
        )

        self.assertEqual(captured["memory_level"], 5)
        self.assertEqual(captured["document_scope_mode"], "selected")
        self.assertEqual(captured["selected_document_ids"], frozenset({"doc-kept"}))
        with self.session_factory() as db:
            setting = db.get(ThreadContextSetting, thread_id)
            self.assertEqual((setting.memory_level, setting.document_scope_mode), (5, "selected"))

    def test_existing_thread_ignores_empty_selected_override(self):
        with self.session_factory() as db:
            thread = Thread(user_id="user-1", department_id="dept-1")
            db.add(thread)
            db.flush()
            db.add(ThreadContextSetting(thread_id=thread.id, memory_level=3, document_scope_mode="all"))
            db.commit()
            thread_id = thread.id

        captured = self._post_with_capture(
            {
                "question": "existing question",
                "thread_id": thread_id,
                "document_scope_mode": "selected",
                "document_ids": [],
            }
        )

        self.assertEqual(captured["document_scope_mode"], "all")
        self.assertIsNone(captured["selected_document_ids"])

    def test_legacy_thread_persists_level_three_independent_of_user_default(self):
        with self.session_factory() as db:
            thread = Thread(user_id="user-1", department_id="dept-1")
            db.add(thread)
            db.add(UserChatSetting(user_id="user-1", default_memory_level=5))
            db.commit()
            thread_id = thread.id

        captured = self._post_with_capture({"question": "legacy question", "thread_id": thread_id})

        self.assertEqual(captured["memory_level"], 3)
        with self.session_factory() as db:
            setting = db.get(ThreadContextSetting, thread_id)
            self.assertIsNotNone(setting)
            self.assertEqual(setting.memory_level, 3)
            self.assertEqual(setting.document_scope_mode, "all")

    def test_new_thread_uses_user_default_memory_level(self):
        with self.session_factory() as db:
            db.add(UserChatSetting(user_id="user-1", default_memory_level=5))
            db.commit()

        captured = self._post_with_capture({"question": "new default question"})

        self.assertEqual(captured["memory_level"], 5)
        with self.session_factory() as db:
            self.assertEqual(
                db.get(ThreadContextSetting, captured["thread_id"]).memory_level,
                5,
            )

    def test_new_thread_rejects_empty_selected_scope(self):
        from sse_starlette.sse import AppStatus

        AppStatus.should_exit_event = None
        with self._client() as client:
            response = client.post(
                "/chat/ask",
                json={
                    "question": "new question",
                    "document_scope_mode": "selected",
                    "document_ids": [],
                },
            )

        self.assertEqual(response.status_code, 422)
        with self.session_factory() as db:
            self.assertEqual(db.query(Thread).count(), 0)

    def test_router_passes_prior_history_without_current_message(self):
        with self.session_factory() as db:
            thread = Thread(user_id="user-1", department_id="dept-1")
            db.add(thread)
            db.flush()
            db.add(ThreadContextSetting(thread_id=thread.id, memory_level=3, document_scope_mode="all"))
            db.add(Message(thread_id=thread.id, role="user", content="prior question"))
            db.add_all(
                (
                    UserMemory(user_id="user-1", title="mine", content="only mine", enabled=True),
                    UserMemory(user_id="user-2", title="other", content="must not leak", enabled=True),
                )
            )
            db.commit()
            thread_id = thread.id

        captured = self._post_with_capture({"question": "current question", "thread_id": thread_id})

        self.assertEqual(captured["history"].messages, [{"role": "user", "content": "prior question"}])
        self.assertEqual(captured["user_memories"], ("only mine",))
        self.assertNotIn("current question", [item["content"] for item in captured["history"].messages])

    def test_level_one_passes_no_prior_messages(self):
        with self.session_factory() as db:
            thread = Thread(user_id="user-1", department_id="dept-1")
            db.add(thread)
            db.flush()
            db.add(ThreadContextSetting(thread_id=thread.id, memory_level=1, document_scope_mode="all"))
            db.add(Message(thread_id=thread.id, role="user", content="prior question"))
            db.commit()
            thread_id = thread.id

        captured = self._post_with_capture({"question": "current question", "thread_id": thread_id})

        self.assertEqual(captured["history"].messages, [])


class OrchestratorContextTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)()
        self.thread = Thread(user_id="user-1", department_id="dept-1")
        self.session.add(self.thread)
        self.session.flush()
        self.current = Message(thread_id=self.thread.id, role="user", content="question")
        self.session.add(self.current)
        self.session.commit()

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _kwargs(self, **overrides):
        values = {
            "user_id": "user-1",
            "username": "user-1",
            "thread_id": self.thread.id,
            "current_message_id": self.current.id,
            "department_ids": ("dept-1", "dept-2"),
            "authorized_department_ids": ("dept-1", "dept-2"),
            "department_names": ("Dept 1", "Dept 2"),
            "question": "question",
            "memory_level": 3,
            "document_scope_mode": "all",
            "selected_document_ids": None,
            "scope_adjusted": False,
            "history": ChatHistory(summary="", messages=[], summary_messages=[]),
            "user_memories": (),
            "doc_titles": {},
            "sensitive_keywords": ("secret",),
        }
        values.update(overrides)
        return values

    async def test_empty_selected_scope_emits_exact_block_without_retrieval_or_model(self):
        from app.agents.orchestrator import run_ask

        with patch("app.agents.orchestrator.search_departments") as search, patch(
            "app.agents.orchestrator.answer.run"
        ) as answer_run:
            events = [
                event
                async for event in run_ask(
                    self.session,
                    **self._kwargs(
                        document_scope_mode="selected",
                        selected_document_ids=frozenset(),
                    ),
                )
            ]

        self.assertEqual(
            [(event["node"], event["status"]) for event in events[:2]],
            [("sensitive_gate", "running"), ("sensitive_gate", "done")],
        )
        self.assertEqual(
            events[-1],
            {
                "node": "final",
                "status": "blocked",
                "error_code": "document_scope_empty",
                "answer": "所选文档已失效，请重新选择文档范围。",
            },
        )
        search.assert_not_called()
        answer_run.assert_not_called()

    async def test_scope_adjustment_emits_only_retained_authorized_ids(self):
        from app.agents.orchestrator import run_ask

        self.session.add(
            Document(
                id="doc-kept",
                department_id="dept-1",
                title="kept",
                content="content",
                uploaded_by="uploader",
            )
        )
        self.session.add(ThreadContextSetting(thread_id=self.thread.id, document_scope_mode="selected"))
        self.session.add_all(
            (
                ThreadDocumentSelection(thread_id=self.thread.id, document_id="doc-kept"),
                ThreadDocumentSelection(thread_id=self.thread.id, document_id="doc-gone"),
            )
        )
        self.session.commit()

        with patch("app.agents.orchestrator.search_departments", return_value=[]):
            events = [
                event
                async for event in run_ask(
                    self.session,
                    **self._kwargs(
                        document_scope_mode="selected",
                        selected_document_ids=frozenset({"doc-kept", "doc-gone"}),
                    ),
                )
            ]

        self.assertIn(
            {"node": "scope", "status": "adjusted", "document_ids": ["doc-kept"]},
            events,
        )
        with self.session.no_autoflush:
            self.assertIsNone(
                self.session.get(ThreadDocumentSelection, (self.thread.id, "doc-gone"))
            )

    async def test_department_memory_is_loaded_only_for_evidence_departments(self):
        from app.agents.orchestrator import run_ask

        self.session.add_all(
            (
                Document(
                    id="doc-legal",
                    department_id="dept-1",
                    title="legal",
                    content="content",
                    uploaded_by="uploader",
                ),
                Document(
                    id="doc-sales",
                    department_id="dept-2",
                    title="sales",
                    content="content",
                    uploaded_by="uploader",
                ),
                DepartmentMemory(
                    department_id="dept-1",
                    title="legal style",
                    content="legal instruction",
                    created_by="admin",
                    updated_by="admin",
                ),
                DepartmentMemory(
                    department_id="dept-2",
                    title="sales style",
                    content="sales instruction",
                    created_by="admin",
                    updated_by="admin",
                ),
            )
        )
        self.session.commit()
        chunk = RetrievedChunk("chunk", "doc-legal", "evidence", 1.0, 1.0, 1.0)
        captured = {}

        def capture_messages(**kwargs):
            captured.update(kwargs)
            return [{"role": "user", "content": "answer"}]

        async def fake_answer(messages):
            yield "answer"

        with patch("app.agents.orchestrator.search_departments", return_value=[chunk]), patch(
            "app.agents.orchestrator.build_answer_messages", side_effect=capture_messages
        ), patch("app.agents.orchestrator.answer.run", new=fake_answer), patch(
            "app.agents.orchestrator.faithfulness_check.run",
            new=AsyncMock(return_value={"faithful": True, "concern": ""}),
        ):
            events = [event async for event in run_ask(self.session, **self._kwargs())]

        self.assertEqual(captured["department_memories"], ["legal instruction"])
        self.assertNotIn("sales instruction", captured["department_memories"])
        self.assertTrue(any(event.get("status") == "completed" for event in events))

    async def test_verifier_failure_preserves_answer_and_reports_unavailable_warning(self):
        from app.agents.orchestrator import run_ask

        self.session.add(
            Document(
                id="doc-legal",
                department_id="dept-1",
                title="legal",
                content="content",
                uploaded_by="uploader",
            )
        )
        self.session.commit()
        chunk = RetrievedChunk("chunk", "doc-legal", "evidence", 1.0, 1.0, 1.0)
        events = []

        async def fake_answer(messages):
            yield "<think>Clarifying snippet duration and citation requirements</think>\nanswer"

        with patch("app.agents.orchestrator.search_departments", return_value=[chunk]), patch(
            "app.agents.orchestrator.answer.run", new=fake_answer
        ), patch(
            "app.agents.faithfulness_check.call_json",
            new=AsyncMock(return_value={}),
        ):
            try:
                async for event in run_ask(self.session, **self._kwargs()):
                    events.append(event)
            except RuntimeError as exc:
                self.fail(f"verifier failure escaped the stream: {exc}")

        self.assertIn(
            {
                "node": "final",
                "status": "completed",
                "answer": "answer",
                "citations": [
                    {
                        "tag": "C1",
                        "document_id": "doc-legal",
                        "title": "未知文档",
                        "snippet": "evidence",
                    }
                ],
            },
            events,
        )
        self.assertEqual(
            events[-1],
            {
                "node": "faithfulness_check",
                "status": "done",
                "available": False,
                "faithful": None,
                "concern": "大模型溯源核查已完毕，未发现明显问题",
            },
        )
        assistants = (
            self.session.query(Message)
            .filter(Message.thread_id == self.thread.id, Message.role == "assistant")
            .all()
        )
        self.assertEqual([message.content for message in assistants], ["answer"])
        self.assertIsNone(self.session.get(MessageContextFlag, self.current.id))
        self.assertIsNone(self.session.get(MessageContextFlag, assistants[0].id))
        reopened = load_chat_history(
            self.session,
            self.thread.id,
            memory_level=3,
            current_message_id=None,
        )
        self.assertEqual([message["content"] for message in reopened.messages], ["question", "answer"])

    async def test_answer_stream_failure_persists_excluded_failure_pair_and_emits_blocked_final(self):
        from app.agents.orchestrator import run_ask

        self.session.add(
            Document(
                id="doc-legal",
                department_id="dept-1",
                title="legal",
                content="content",
                uploaded_by="uploader",
            )
        )
        self.session.commit()
        chunk = RetrievedChunk("chunk", "doc-legal", "evidence", 1.0, 1.0, 1.0)
        events = []

        async def failing_answer(messages):
            yield "partial answer"
            raise RuntimeError("answer unavailable")

        with patch("app.agents.orchestrator.search_departments", return_value=[chunk]), patch(
            "app.agents.orchestrator.answer.run", new=failing_answer
        ), patch("app.agents.orchestrator.faithfulness_check.run", new=AsyncMock()) as verifier:
            try:
                async for event in run_ask(self.session, **self._kwargs()):
                    events.append(event)
            except RuntimeError as exc:
                self.fail(f"answer failure escaped the stream: {exc}")

        self.assertIn(
            {"node": "answer", "status": "streaming", "delta": "partial answer"},
            events,
        )
        self.assertEqual(
            events[-1],
            {
                "node": "final",
                "status": "blocked",
                "error_code": "answer_generation_failed",
                "answer": "回答生成失败，请稍后重试。",
            },
        )
        verifier.assert_not_awaited()
        assistants = (
            self.session.query(Message)
            .filter(Message.thread_id == self.thread.id, Message.role == "assistant")
            .all()
        )
        self.assertEqual([message.content for message in assistants], ["回答生成失败，请稍后重试。"])
        for message_id in (self.current.id, assistants[0].id):
            flag = self.session.get(MessageContextFlag, message_id)
            self.assertIsNotNone(flag)
            self.assertFalse(flag.context_eligible)
            self.assertEqual(flag.reason, "answer_generation_failed")
        reopened = load_chat_history(
            self.session,
            self.thread.id,
            memory_level=3,
            current_message_id=None,
        )
        self.assertEqual(reopened.messages, [])

    async def test_answer_stream_cancellation_persists_cleanup_and_propagates(self):
        from app.agents.orchestrator import run_ask

        self.session.add(
            Document(
                id="doc-legal",
                department_id="dept-1",
                title="legal",
                content="content",
                uploaded_by="uploader",
            )
        )
        self.session.commit()
        chunk = RetrievedChunk("chunk", "doc-legal", "evidence", 1.0, 1.0, 1.0)

        async def cancelled_answer(messages):
            yield "partial answer"
            raise asyncio.CancelledError()

        with patch("app.agents.orchestrator.search_departments", return_value=[chunk]), patch(
            "app.agents.orchestrator.answer.run", new=cancelled_answer
        ), patch("app.agents.orchestrator.faithfulness_check.run", new=AsyncMock()) as verifier:
            with self.assertRaises(asyncio.CancelledError):
                async for _event in run_ask(self.session, **self._kwargs()):
                    pass

        verifier.assert_not_awaited()
        assistant = (
            self.session.query(Message)
            .filter(Message.thread_id == self.thread.id, Message.role == "assistant")
            .one()
        )
        self.assertEqual(assistant.content, "回答生成失败，请稍后重试。")
        for message_id in (self.current.id, assistant.id):
            flag = self.session.get(MessageContextFlag, message_id)
            self.assertIsNotNone(flag)
            self.assertFalse(flag.context_eligible)
            self.assertEqual(flag.reason, "answer_generation_failed")


if __name__ == "__main__":
    unittest.main()
