from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.assistant.schemas import ActionChange, ActionPreview, ActionResult
from app.models import AssistantAction


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_action_preview_stores_hash_and_expires(db):
    """Removing a preview's hash or expiry must break confirmation preconditions."""
    action = AssistantAction(
        id="act-1",
        thread_id="thread-1",
        user_id="admin",
        tool_name="create_project",
        risk_level="high",
        status="preview",
        payload_json={"name": "研发平台"},
        preview_json={"summary": "新建研发平台"},
        parameter_hash="sha256:expected",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        idempotency_key="idem-act-1",
    )
    db.add(action)
    db.commit()

    assert action.status == "preview"
    assert action.parameter_hash == "sha256:expected"
    assert action.expires_at is not None


def test_idempotency_key_is_unique_per_user(db):
    """Dropping user-scoped idempotency would allow duplicate business execution."""
    first = AssistantAction(
        id="act-1",
        user_id="admin",
        tool_name="create_project",
        risk_level="high",
        status="preview",
        idempotency_key="same-key",
    )
    second = AssistantAction(
        id="act-2",
        user_id="admin",
        tool_name="create_project",
        risk_level="high",
        status="preview",
        idempotency_key="same-key",
    )
    db.add_all([first, second])

    with pytest.raises(IntegrityError):
        db.commit()


def test_action_protocol_rejects_unknown_risk_levels():
    """Relaxing the public risk enum would let callers bypass confirmation policy."""
    preview = ActionPreview(
        action_id="act-1",
        tool_name="create_project",
        risk_level="high",
        summary="新建研发平台",
        changes=[ActionChange(field="name", before=None, after="研发平台")],
    )
    assert preview.risk_level == "high"

    with pytest.raises(ValueError):
        ActionPreview(
            action_id="act-2",
            tool_name="create_project",
            risk_level="unrestricted",
            summary="新建研发平台",
        )


def test_action_result_exposes_terminal_status_and_error():
    """Removing result status or error code would hide an action's execution outcome."""
    result = ActionResult(
        action_id="act-1",
        status="failed",
        error_code="version_conflict",
    )
    assert result.status == "failed"
    assert result.error_code == "version_conflict"
