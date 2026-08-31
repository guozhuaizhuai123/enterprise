"""Sensitive-topic gate: pure rule matching, zero LLM calls (PRD §5.3 step ①).

Kept intentionally simple — a keyword list, not an LLM classifier — because
that LLM-based classification step in the enterprise-kb-agent prototype
was the first link of its slow serial chain. Real deployments should
expand this list per department policy.
"""
SENSITIVE_KEYWORDS = [
    "薪酬", "工资", "调薪", "涉密", "绩效评级", "竞业限制", "赔偿金额",
    "合同条款", "离职补偿", "股权", "期权数量",
]


def matched_keyword(question: str, keywords: list[str] | tuple[str, ...] | None = None) -> str | None:
    active_keywords = SENSITIVE_KEYWORDS if keywords is None else keywords
    for kw in active_keywords:
        if kw in question:
            return kw
    return None


def check(question: str, keywords: list[str] | tuple[str, ...] | None = None) -> tuple[bool, str]:
    keyword = matched_keyword(question, keywords)
    if keyword:
        return True, f"问题包含敏感关键词「{keyword}」，已转交人工处理"
    return False, ""
