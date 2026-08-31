"""Async, streaming-first LLM gateway.

This is the fix for the enterprise-kb-agent prototype's main bottleneck
(app/llm.py there used a synchronous OpenAI client with no streaming,
blocking a worker thread for the full generation). Here every call is
async and the answer-generation call streams tokens as they arrive.
"""
import json
import re
from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from app.config import get_settings

settings = get_settings()

_client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)


async def stream_messages(
    messages: list[dict[str, str]], *, max_tokens: int = 1500
) -> AsyncIterator[str]:
    stream = await _client.chat.completions.create(
        model=settings.llm_model,
        max_completion_tokens=max_tokens,
        messages=messages,
        stream=True,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta.content if chunk.choices else None
        if delta:
            yield delta


async def stream_chat(system: str, user: str, *, max_tokens: int = 1500) -> AsyncIterator[str]:
    async for delta in stream_messages(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=max_tokens,
    ):
        yield delta


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(json)?", "", text).rsplit("```", 1)[0].strip()
    return json.loads(text)


async def call_json(system: str, user: str, *, max_tokens: int = 800) -> dict:
    resp = await _client.chat.completions.create(
        model=settings.llm_verify_model,
        max_completion_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    text = resp.choices[0].message.content or "{}"
    try:
        return _extract_json(text)
    except (json.JSONDecodeError, ValueError):
        return {}


async def call_text(system: str, user: str, *, max_tokens: int = 800) -> str:
    response = await _client.chat.completions.create(
        model=settings.llm_verify_model,
        max_completion_tokens=max_tokens,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    return (response.choices[0].message.content or "").strip()
