"""Rule-first asynchronous planning with a closed LLM trust boundary."""

import json
import re

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.assistant.navigation import allowed_route_keys
from app.assistant.planner import (
    ActionPlan,
    ClarificationPlan,
    ConversationPlan,
    FormPreviewPlan,
    KnowledgePlan,
    NavigationPlan,
    plan_input,
)
from app.assistant.registry import get_action, list_actions
from app.deps import Principal
from app.llm import call_json


_BUSINESS_OPERATION = re.compile(
    r"(?:创建|新建|修改|更新|删除|清空|付款|审批|发薪|重置|离职|批量|办理|提交|派发)"
)
_BUSINESS_SUBJECT = re.compile(
    r"(?:业务|记录|组织|部门|员工|用户|项目|合同|文档|费用|报销|审批|付款|薪酬|工资|工单|待办|"
    r"排班|考勤|请假|节假日|密码|关键词|敏感|记忆)"
)
_KNOWLEDGE_CUE = re.compile(r"(?:是什么|为什么|如何|怎么|制度|流程|规定|政策|说明|含义)")
_SENSITIVE_PROMPT_CUE = re.compile(
    r"(?:password|passwd|secret|token|salary|database|数据库|密码|口令|薪资|工资)",
    re.IGNORECASE,
)
_PROMPT_FIELD_DENYLIST = frozenset(
    {
        "password",
        "password_encrypted",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "salary",
        "risk",
        "risk_level",
        "handler",
        "http_method",
        "url",
        "sql",
    }
)


def _authorized_actions(principal: Principal):
    return tuple(
        action for action in list_actions() if principal.has_role(*action.required_roles)
    )


def _clarification(principal: Principal, reason: str) -> ClarificationPlan:
    return ClarificationPlan(
        reason=reason,
        available_actions=tuple(action.name for action in _authorized_actions(principal)),
    )


def _is_eligible(text: str, rule_plan: ConversationPlan) -> bool:
    is_business_operation = (
        _BUSINESS_OPERATION.search(text) is not None
        and _BUSINESS_SUBJECT.search(text) is not None
    )
    if isinstance(rule_plan, ClarificationPlan):
        return (
            rule_plan.reason == "business instruction is incomplete or ambiguous"
            and is_business_operation
        )
    return (
        isinstance(rule_plan, KnowledgePlan)
        and is_business_operation
        and _KNOWLEDGE_CUE.search(text) is None
    )


def _build_prompt(text: str, principal: Principal) -> tuple[str, str]:
    catalog = [
        {
            "name": action.name,
            "input_fields": [
                field_name
                for field_name in action.input_model.model_fields
                if field_name.lower() not in _PROMPT_FIELD_DENYLIST
            ],
        }
        for action in _authorized_actions(principal)
    ]
    routes = sorted(allowed_route_keys(principal))
    system = (
        "Select at most one authorized business action or navigation target. "
        "Return one JSON object using only kind, name, arguments, and route_key. "
        f"Authorized catalog: {json.dumps(catalog, ensure_ascii=False)}. "
        f"Allowed route keys: {json.dumps(routes, ensure_ascii=False)}."
    )
    return system, text


def _validate_candidate(candidate: object, principal: Principal) -> ConversationPlan:
    if not isinstance(candidate, dict):
        return _clarification(principal, "structured intent is invalid")

    kind = candidate.get("kind")
    if kind == "action":
        name = candidate.get("name")
        arguments = candidate.get("arguments")
        if not isinstance(name, str) or not isinstance(arguments, dict):
            return _clarification(principal, "structured action is invalid")
        action = get_action(name)
        if action is None:
            return _clarification(principal, "action is not registered")
        if not principal.has_role(*action.required_roles):
            return _clarification(principal, "principal is not authorized for this action")
        try:
            parsed_input = action.input_model.model_validate(arguments)
        except ValidationError:
            return _clarification(principal, "action payload is invalid")
        return ActionPlan(action=action, input=parsed_input)

    if kind == "navigation":
        route_key = candidate.get("route_key")
        if not isinstance(route_key, str) or route_key not in allowed_route_keys(principal):
            return _clarification(principal, "navigation target is not allowed")
        return NavigationPlan(route_key=route_key)

    return _clarification(principal, "structured intent kind is invalid")


async def plan_conversation(
    text: str, principal: Principal, db: Session | None
) -> ConversationPlan:
    """Plan with deterministic rules first and revalidate any model candidate."""
    rule_plan = plan_input(text, principal, db)
    if isinstance(rule_plan, (ActionPlan, FormPreviewPlan, NavigationPlan)):
        return rule_plan
    if not _is_eligible(text, rule_plan):
        return rule_plan
    if _SENSITIVE_PROMPT_CUE.search(text):
        return _clarification(principal, "sensitive business input requires an explicit workflow")

    try:
        system, user = _build_prompt(text, principal)
        candidate = await call_json(system, user)
        return _validate_candidate(candidate, principal)
    except Exception:
        if isinstance(rule_plan, ClarificationPlan):
            return rule_plan
        return _clarification(principal, "business instruction could not be safely structured")
