from functools import lru_cache

import tiktoken

from app.config import get_settings


@lru_cache
def _encoding(model: str):
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("o200k_base")


def count_tokens(text: str, *, model: str | None = None) -> int:
    return len(_encoding(model or get_settings().llm_model).encode(text))


def select_recent_messages(
    messages: list[dict[str, str]],
    token_budget: int,
    exclude_message_id: str | None = None,
) -> list[dict[str, str]]:
    if token_budget <= 0:
        return []

    selected: list[dict[str, str]] = []
    used_tokens = 0
    for message in reversed(messages):
        if message.get("id") == exclude_message_id:
            continue
        message_tokens = count_tokens(message["content"])
        if used_tokens + message_tokens > token_budget:
            break
        selected.append(message)
        used_tokens += message_tokens
    selected.reverse()
    return selected
