import unittest
from unittest.mock import AsyncMock, patch

from app.agents.sensitive_gate import matched_keyword
from app.context.service import ChatHistory
from app.db import Base
from app.models import (
    Message,
    MessageContextFlag,
    SensitiveEvent,
    SensitiveKeyword,
    Thread,
)
from app.context.service import load_chat_history
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


class SensitiveEventTest(unittest.TestCase):
    def test_sensitive_message_flag_defaults_to_excluded(self):
        flag = MessageContextFlag(message_id="message-1", reason="sensitive_blocked")

        self.assertFalse(flag.context_eligible)

    def test_sensitive_event_has_audit_fields(self):
        columns = SensitiveEvent.__table__.columns
        for name in ("username", "department_name", "question", "matched_keyword", "reason", "created_at"):
            self.assertIn(name, columns)

    def test_sensitive_keyword_has_editable_fields(self):
        columns = SensitiveKeyword.__table__.columns
        for name in ("keyword", "enabled", "updated_by", "updated_at"):
            self.assertIn(name, columns)

    def test_matched_keyword_is_available_for_audit(self):
        self.assertEqual(matched_keyword("请告诉我 gjk 工资是多少"), "工资")
        self.assertIsNone(matched_keyword("公司的办公时间是什么"))

    def test_gate_can_use_custom_keywords(self):
        self.assertEqual(matched_keyword("内部红线问题", ["红线"]), "红线")
        self.assertIsNone(matched_keyword("内部红线问题", ["工资"]))


class SensitiveBootstrapTest(unittest.TestCase):
    def test_backfill_flags_exact_user_match_and_only_exact_blocked_assistant(self):
        from app import bootstrap

        backfill = getattr(bootstrap, "_backfill_sensitive_context_flags", None)
        self.assertIsNotNone(backfill)
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        try:
            thread = Thread(user_id="user-1")
            session.add(thread)
            session.flush()
            reason = "问题包含敏感关键词「secret」，已转交人工处理"
            blocked_answer = f"该问题涉及敏感信息，{reason}，不由系统自动作答。"
            user_message = Message(thread_id=thread.id, role="user", content="prior secret")
            blocked_assistant = Message(thread_id=thread.id, role="assistant", content=blocked_answer)
            unrelated_assistant = Message(thread_id=thread.id, role="assistant", content="arbitrary answer")
            session.add_all((user_message, blocked_assistant, unrelated_assistant))
            session.add(
                SensitiveEvent(
                    user_id="user-1",
                    username="employee",
                    department_name="Legal",
                    question="prior secret",
                    matched_keyword="secret",
                    reason=reason,
                )
            )
            session.commit()

            backfill(session)
            session.flush()

            self.assertIsNotNone(session.get(MessageContextFlag, user_message.id))
            self.assertIsNotNone(session.get(MessageContextFlag, blocked_assistant.id))
            self.assertIsNone(session.get(MessageContextFlag, unrelated_assistant.id))
        finally:
            session.close()
            Base.metadata.drop_all(engine)
            engine.dispose()


class SensitivePipelineTest(unittest.IsolatedAsyncioTestCase):
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

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _current_message(self, question):
        message = Message(thread_id=self.thread.id, role="user", content=question)
        self.session.add(message)
        self.session.commit()
        return message

    def _kwargs(self, current, *, question, history, memory_level=3):
        return {
            "user_id": "user-1",
            "username": "employee",
            "thread_id": self.thread.id,
            "current_message_id": current.id,
            "department_ids": ("dept-1",),
            "authorized_department_ids": ("dept-1",),
            "department_names": ("Legal",),
            "question": question,
            "memory_level": memory_level,
            "document_scope_mode": "all",
            "selected_document_ids": None,
            "scope_adjusted": False,
            "history": history,
            "user_memories": ("private preference",),
            "doc_titles": {},
            "sensitive_keywords": ("secret",),
        }

    def _assert_both_messages_flagged(self, current_message_id):
        messages = (
            self.session.query(Message)
            .filter(Message.thread_id == self.thread.id)
            .order_by(Message.created_at, Message.id)
            .all()
        )
        assistant = next(message for message in messages if message.role == "assistant")
        for message_id in (current_message_id, assistant.id):
            flag = self.session.get(MessageContextFlag, message_id)
            self.assertIsNotNone(flag)
            self.assertFalse(flag.context_eligible)
            self.assertEqual(flag.reason, "sensitive_blocked")

    async def _run_with_external_guards(self, kwargs, *, rewritten_query=None):
        from app.agents.orchestrator import run_ask

        rewrite = AsyncMock(return_value=rewritten_query) if rewritten_query is not None else AsyncMock()
        with patch("app.agents.orchestrator.rewrite_followup", new=rewrite), patch(
            "app.agents.orchestrator.ensure_summary", new=AsyncMock()
        ) as ensure_summary, patch("app.agents.orchestrator.search_departments") as search, patch(
            "app.agents.orchestrator.answer.run"
        ) as answer_run:
            events = [event async for event in run_ask(self.session, **kwargs)]
        return events, rewrite, ensure_summary, search, answer_run

    async def test_sensitive_current_question_blocks_before_all_external_calls(self):
        current = self._current_message("contains secret")

        events, rewrite, ensure_summary, search, answer_run = await self._run_with_external_guards(
            self._kwargs(
                current,
                question=current.content,
                history=ChatHistory(summary="", messages=[], summary_messages=[]),
            )
        )

        rewrite.assert_not_awaited()
        ensure_summary.assert_not_awaited()
        search.assert_not_called()
        answer_run.assert_not_called()
        self.assertEqual(events[-1]["status"], "blocked")
        self.assertEqual(self.session.query(SensitiveEvent).count(), 1)
        self._assert_both_messages_flagged(current.id)

    async def test_sensitive_eligible_history_blocks_before_all_external_calls(self):
        prior = Message(thread_id=self.thread.id, role="user", content="prior secret")
        self.session.add(prior)
        self.session.commit()
        current = self._current_message("benign follow-up")
        history = ChatHistory(
            summary="",
            messages=[{"role": "user", "content": prior.content}],
            summary_messages=[{"id": prior.id, "role": "user", "content": prior.content}],
        )

        events, rewrite, ensure_summary, search, answer_run = await self._run_with_external_guards(
            self._kwargs(current, question=current.content, history=history)
        )

        rewrite.assert_not_awaited()
        ensure_summary.assert_not_awaited()
        search.assert_not_called()
        answer_run.assert_not_called()
        self.assertEqual(events[-1]["status"], "blocked")
        self.assertIsNone(self.session.get(MessageContextFlag, current.id))
        assistant = (
            self.session.query(Message)
            .filter(Message.thread_id == self.thread.id, Message.role == "assistant")
            .one()
        )
        self.assertIsNotNone(self.session.get(MessageContextFlag, assistant.id))

    async def test_sensitive_rewrite_blocks_before_retrieval_and_answer_calls(self):
        prior = Message(thread_id=self.thread.id, role="user", content="合同流程")
        self.session.add(prior)
        self.session.commit()
        current = self._current_message("那怎么办？")
        history = ChatHistory(
            summary="",
            messages=[{"role": "user", "content": prior.content}],
            summary_messages=[{"id": prior.id, "role": "user", "content": prior.content}],
        )

        events, rewrite, ensure_summary, search, answer_run = await self._run_with_external_guards(
            self._kwargs(current, question=current.content, history=history),
            rewritten_query="standalone secret query",
        )

        rewrite.assert_awaited_once()
        ensure_summary.assert_not_awaited()
        search.assert_not_called()
        answer_run.assert_not_called()
        self.assertEqual(events[-1]["status"], "blocked")
        self._assert_both_messages_flagged(current.id)

    async def test_sensitive_question_wins_over_empty_selected_scope(self):
        current = self._current_message("contains secret")

        events, rewrite, ensure_summary, search, answer_run = await self._run_with_external_guards(
            {
                **self._kwargs(
                    current,
                    question=current.content,
                    history=ChatHistory(summary="", messages=[], summary_messages=[]),
                ),
                "document_scope_mode": "selected",
                "selected_document_ids": frozenset(),
            }
        )

        rewrite.assert_not_awaited()
        ensure_summary.assert_not_awaited()
        search.assert_not_called()
        answer_run.assert_not_called()
        self.assertEqual(self.session.query(SensitiveEvent).count(), 1)
        self.assertNotEqual(events[-1].get("error_code"), "document_scope_empty")
        self._assert_both_messages_flagged(current.id)

    async def test_sensitive_history_culprit_is_excluded_and_does_not_reblock_next_turn(self):
        reason = "问题包含敏感关键词「secret」，已转交人工处理"
        blocked_answer = f"该问题涉及敏感信息，{reason}，不由系统自动作答。"
        culprit = Message(thread_id=self.thread.id, role="user", content="prior secret")
        companion = Message(thread_id=self.thread.id, role="assistant", content=blocked_answer)
        self.session.add_all((culprit, companion))
        self.session.commit()
        first_current = self._current_message("first benign follow-up")
        first_history = ChatHistory(
            summary="",
            messages=[
                {"role": "user", "content": culprit.content},
                {"role": "assistant", "content": companion.content},
            ],
            summary_messages=[
                {"id": culprit.id, "role": "user", "content": culprit.content},
                {"id": companion.id, "role": "assistant", "content": companion.content},
            ],
        )

        await self._run_with_external_guards(
            self._kwargs(first_current, question=first_current.content, history=first_history)
        )

        for message_id in (culprit.id, companion.id):
            flag = self.session.get(MessageContextFlag, message_id)
            self.assertIsNotNone(flag)
            self.assertFalse(flag.context_eligible)
        self.assertIsNone(self.session.get(MessageContextFlag, first_current.id))
        event = self.session.query(SensitiveEvent).one()
        self.assertEqual(event.question, culprit.content)
        self.assertEqual(event.matched_keyword, "secret")
        blocked_assistants = (
            self.session.query(Message)
            .filter(
                Message.thread_id == self.thread.id,
                Message.role == "assistant",
                Message.content == blocked_answer,
            )
            .all()
        )
        self.assertGreaterEqual(len(blocked_assistants), 2)
        for assistant in blocked_assistants:
            self.assertIsNotNone(self.session.get(MessageContextFlag, assistant.id))

        second_current = self._current_message("second benign question")
        second_history = load_chat_history(
            self.session,
            self.thread.id,
            memory_level=3,
            current_message_id=second_current.id,
        )
        with patch("app.agents.orchestrator.search_departments", return_value=[]), patch(
            "app.agents.orchestrator.rewrite_followup", new=AsyncMock()
        ) as rewrite, patch(
            "app.agents.orchestrator.ensure_summary", new=AsyncMock()
        ) as ensure_summary, patch("app.agents.orchestrator.answer.run") as answer_run:
            from app.agents.orchestrator import run_ask

            events = [
                event
                async for event in run_ask(
                    self.session,
                    **self._kwargs(
                        second_current,
                        question=second_current.content,
                        history=second_history,
                    ),
                )
            ]

        self.assertFalse(events[1]["is_sensitive"])
        self.assertEqual(self.session.query(SensitiveEvent).count(), 1)
        rewrite.assert_not_awaited()
        ensure_summary.assert_not_awaited()
        answer_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
