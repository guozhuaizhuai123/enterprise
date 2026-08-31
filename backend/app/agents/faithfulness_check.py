"""Faithfulness check agent: runs after the answer is already fully shown
to the user, asynchronously (PRD §5.3 step ④). Unlike the enterprise-kb-agent
prototype's critic+repair loop (which blocked the user waiting for another
LLM round trip), this only ever appends a risk flag — it never triggers a
regeneration, so it can never slow down what the user already sees.
"""
from app.kb.retriever import RetrievedChunk
from app.llm import call_json

SYSTEM = """你是企业知识库问答系统的独立事实核查员，采用宽松但可靠的核查标准。
只有出现以下情况才判定 faithful=false：回答与证据明确矛盾；编造了证据中没有的具体数字、制度或审批要求；核心结论完全没有证据支持。
正常概括、同义改写、格式调整，以及明确标注为谨慎推断或信息不足的内容，不应判为不忠实。
不要因为措辞与原文不完全相同而否定回答。输出 JSON：{"faithful": true|false, "concern": "仅在存在明确风险时，用一句话指出具体问题；否则留空"}
"""


async def run(question: str, answer: str, chunks: list[RetrievedChunk]) -> dict:
    evidence_text = "\n\n".join(f"[C{i + 1}] {c.text}" for i, c in enumerate(chunks))
    user_prompt = f"用户问题：{question}\n\n回答：{answer}\n\n可用文档片段：\n{evidence_text}"
    result = await call_json(SYSTEM, user_prompt)
    if (
        not isinstance(result, dict)
        or type(result.get("faithful")) is not bool
        or not isinstance(result.get("concern"), str)
    ):
        raise ValueError("malformed faithfulness result")
    return result
