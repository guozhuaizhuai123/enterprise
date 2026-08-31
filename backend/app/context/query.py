"""Safe context transformations used before authorized retrieval."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.context.tokens import count_tokens
from app.llm import call_json
from app.models import ThreadContextSetting


_HISTORY_MARKERS = ("它", "那", "这个", "上述", "继续", "前面提到", "然后呢", "还有呢")


def needs_history(question: str) -> bool:
    """Return whether a question has a cheap, local follow-up signal."""
    stripped = question.strip()
    return any(marker in stripped for marker in _HISTORY_MARKERS) or (
        len(stripped) <= 6 and stripped.endswith(("呢", "吗"))
    )


def _fallback_query(question: str, history: list[dict[str, str]]) -> str:
    for message in reversed(history):
        if message.get("role") == "user" and message.get("content", "").strip():
            return f"{message['content'].strip()}\n{question}"[:2000]
    return question


async def rewrite_followup(question: str, summary: str, history: list[dict[str, str]]) -> str:
    """Ask the verifier for a standalone retrieval query, with a local fallback."""
    try:
        response = await call_json(
            "Rewrite the follow-up into one standalone retrieval query. Return JSON only: {\"query\": \"...\"}.",
            (
                f"Conversation summary:\n{summary}\n\n"
                f"Recent history:\n{history}\n\n"
                f"Current question:\n{question}"
            ),
        )
        query = response.get("query") if isinstance(response, dict) else None
        if isinstance(query, str) and query.strip():
            return query.strip()
    except Exception:
        pass
    return _fallback_query(question, history)


def _unsummarized_messages(
    setting: ThreadContextSetting, history_messages: list[dict[str, str]]
) -> list[dict[str, str]]:
    through_id = setting.summary_through_message_id
    if not through_id:
        return history_messages
    for index, message in enumerate(history_messages):
        if message.get("id") == through_id:
            return history_messages[index + 1 :]
    return history_messages


async def ensure_summary(
    db: Session,
    setting: ThreadContextSetting,
    history_messages: list[dict[str, str]],
    memory_level: int,
) -> str:
    """Refresh high-level summaries lazily without committing the caller's transaction."""
    del db  # The setting is session-managed; this function must not commit it.
    existing_summary = setting.summary_text or ""
    if memory_level <= 3:
        return existing_summary

    unsummarized = _unsummarized_messages(setting, history_messages)
    unsummarized_tokens = sum(count_tokens(message.get("content", "")) for message in unsummarized)
    if unsummarized_tokens <= get_settings().summary_trigger_tokens or not unsummarized:
        return existing_summary

    try:
        response = await call_json(
            "Summarize the prior summary and new eligible conversation history. "
            "Return JSON only: {\"summary\": \"...\"}.",
            f"Existing summary:\n{existing_summary}\n\nNew history:\n{unsummarized}",
        )
        summary = response.get("summary") if isinstance(response, dict) else None
        if not isinstance(summary, str) or not summary.strip():
            return existing_summary
    except Exception:
        return existing_summary

    setting.summary_text = summary.strip()[:6000]
    setting.summary_through_message_id = unsummarized[-1].get("id")
    setting.summary_token_count = unsummarized_tokens
    setting.summary_updated_at = datetime.now(UTC)
    return setting.summary_text


def _memory_field(memory: Any, name: str, default: Any = None) -> Any:
    if isinstance(memory, dict):
        return memory.get(name, default)
    return getattr(memory, name, default)


def _ordered_memories(memories: list[Any]) -> list[Any]:
    if all(isinstance(memory, str) for memory in memories):
        return memories
    return sorted(
        memories,
        key=lambda memory: (
            str(_memory_field(memory, "created_at", "")),
            str(_memory_field(memory, "id", "")),
        ),
    )


def _enabled_contents(memories: list[Any]) -> list[str]:
    contents: list[str] = []
    for memory in _ordered_memories(memories):
        if isinstance(memory, str):
            content, enabled = memory, True
        else:
            content = _memory_field(memory, "content")
            enabled = _memory_field(memory, "enabled", True)
        if enabled and isinstance(content, str) and content.strip():
            contents.append(content.strip())
    return contents


def _fallback_merge(memories_by_department: dict[str, list[Any]]) -> tuple[list[str], list[dict[str, str]]]:
    merged = [
        content
        for department_id in sorted(memories_by_department)
        for content in _enabled_contents(memories_by_department[department_id])
    ]
    return merged, [{"reason": "merge unavailable; follow stricter instruction", "winner": "strict"}]


def _normalize_merge(
    response: Any,
    *,
    require_instructions: bool,
) -> tuple[list[str], list[dict[str, str]]] | None:
    if not isinstance(response, dict):
        return None
    merged, conflicts = response.get("merged_instructions"), response.get("conflicts")
    if not isinstance(merged, list) or not isinstance(conflicts, list):
        return None
    if require_instructions and not merged:
        return None
    if not all(isinstance(item, str) and item.strip() for item in merged):
        return None
    if not all(isinstance(item, dict) for item in conflicts):
        return None
    normalized_conflicts = [
        {str(key): str(value) for key, value in item.items() if isinstance(key, (str, int, float, bool))}
        for item in conflicts
    ]
    return [item.strip() for item in merged], normalized_conflicts


async def merge_department_memories(
    memories_by_department: dict[str, list[Any]],
) -> tuple[list[str], list[dict[str, str]]]:
    """Merge instructions only; callers retain authorization and evidence boundaries."""
    if not memories_by_department:
        return [], []
    if len(memories_by_department) == 1:
        return _enabled_contents(next(iter(memories_by_department.values()))), []

    enabled_by_department = {
        department_id: _enabled_contents(memories)
        for department_id, memories in memories_by_department.items()
    }
    try:
        response = await call_json(
            "Merge department answer-style instructions conservatively. Resolve conflicts using "
            "the stricter instruction. Return JSON only with list fields merged_instructions and conflicts.",
            str(enabled_by_department),
        )
        normalized = _normalize_merge(
            response,
            require_instructions=any(enabled_by_department.values()),
        )
        if normalized is not None:
            return normalized
    except Exception:
        pass
    return _fallback_merge(memories_by_department)
