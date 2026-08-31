"""Answer agent: the single mandatory LLM call in the pipeline (PRD §5.3
step ③). Streams tokens as they arrive and asks the model to mark claims
with lightweight [[Cn]] tags instead of full citation URLs/markdown — this
keeps citation resolution independent of the model's markdown formatting,
unlike a scheme that scrapes [citation:x](url) out of streamed text.
"""
import re
from collections.abc import AsyncIterator

from app.llm import stream_messages

SYSTEM = """你是企业知识库问答助手。基于提供的文档片段回答用户问题，要求：
1. 只使用文档中明确提到的内容作答，不要编造文档未提及的规则或数字。
2. 每条关键结论后面用 [[C编号]] 标注引用来源，例如 [[C1]]，编号对应下面给出的文档片段编号。
3. 如果文档不足以完整回答问题，明确指出哪部分信息缺失，不要臆测。
4. 不要输出思考过程、内部推理、<think> 标签或类似内容。
直接输出回答正文，不要输出JSON或其他包裹结构。"""


def clean_output(text: str) -> str:
    cleaned = re.sub(r"<think\b[^>]*>[\s\S]*?</think\s*>", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"<think\b[^>]*>[\s\S]*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</?think\b[^>]*>", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


async def run(messages: list[dict[str, str]]) -> AsyncIterator[str]:
    async for delta in stream_messages(messages):
        yield delta
