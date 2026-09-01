"""Side-effect-free parsing for the controlled assistant action catalog."""
import json
import re
from dataclasses import dataclass
from typing import Literal, TypeAlias

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.assistant.registry import ActionDefinition, get_action, list_actions
from app.assistant.form_previews import is_reported_fault
from app.assistant.navigation import allowed_route_keys
from app.assistant.periods import Period, parse_period
from app.deps import Principal

_ACTION_COMMAND = re.compile(r"^action:([a-z][a-z0-9_]*)\s+(\{.*\})$", re.DOTALL)
_CHINESE_READ_ALIASES = {
    "查询项目": "list_projects",
    "查看项目": "list_projects",
    "查询部门": "list_departments",
    "查看部门": "list_departments",
}
_UNSAFE_FREE_TEXT = re.compile(
    r"(?:run_sql|drop\s+table|truncate\s+table|https?://|file://|javascript:)",
    re.IGNORECASE,
)
_AMBIGUOUS_WRITE = re.compile(
    r"^(?:帮我|请帮我)?(?:创建|新建|修改|更新|删除|清空|付款|审批|发薪|重置密码|离职|批量)"
)
_KNOWLEDGE_CUE = re.compile(r"(?:是什么|为什么|如何|怎么|制度|流程|规定|政策|说明|含义)")
# A live query must not swallow a policy question.  "怎么" is deliberately absent
# because "这个月支出怎么样" is a data question, not a policy one.
_POLICY_CUE = re.compile(r"(?:制度|流程|规定|政策|是什么|为什么|如何)")
_ATTENDANCE_SUBJECT = re.compile(r"(?:考勤|出勤|打卡)")
_EXPENSE_SUBJECT = re.compile(r"(?:费用|支出|流水|报销|开销|花费|花销)")
_SUMMARY_CUE = re.compile(
    r"(?:统计|汇总|多少|怎么样|情况|花了|花销|花费|一共|合计|总计|明细|概况)"
)
_NAVIGATION_ALIASES = (
    (re.compile(r"(?:工单|协作)"), "tickets"),
    (re.compile(r"(?:费用|报销|支出|流水)"), "expenses"),
    (re.compile(r"(?:组织|员工|部门管理)"), "organization"),
    (re.compile(r"项目"), "projects"),
    (re.compile(r"合同"), "contracts"),
    (re.compile(r"(?:知识|文档)"), "knowledge"),
    (re.compile(r"(?:排班|考勤|打卡)"), "schedules"),
    (re.compile(r"(?:薪酬|发薪)"), "payroll"),
    (re.compile(r"(?:企业全景|全景|驾驶舱)"), "overview"),
    (re.compile(r"管理助手"), "assistant"),
)
_CREATE_ORG_UNIT = re.compile(
    r"^创建组织部门[：:](?P<name>[^，,：:\s]{1,100})[，,]\s*编码[：:](?P<code>[A-Za-z0-9_-]{1,32})$"
)


@dataclass(frozen=True)
class ActionPlan:
    """A validated plan.  It has no execution path and carries server metadata."""

    action: ActionDefinition
    input: BaseModel


@dataclass(frozen=True)
class ClarificationPlan:
    """A safe response for prose, invalid payloads, and unauthorized actions."""

    reason: str
    available_actions: tuple[str, ...]


@dataclass(frozen=True)
class KnowledgePlan:
    question: str


@dataclass(frozen=True)
class FormPreviewPlan:
    form: Literal["leave", "ticket", "expense"]
    text: str


@dataclass(frozen=True)
class NavigationPlan:
    route_key: str


ConversationPlan: TypeAlias = ActionPlan | ClarificationPlan | KnowledgePlan | FormPreviewPlan | NavigationPlan


def _clarification(reason: str) -> ClarificationPlan:
    return ClarificationPlan(reason=reason, available_actions=tuple(action.name for action in list_actions()))


def _plan_registered_action(
    action_name: str, payload: object, principal: Principal
) -> ActionPlan | ClarificationPlan:
    action = get_action(action_name)
    if action is None:
        return _clarification("action is not registered")
    if not principal.has_role(*action.required_roles):
        return _clarification("principal is not authorized for this action")
    if not isinstance(payload, dict):
        return _clarification("action payload must be a JSON object")
    try:
        parsed_input = action.input_model.model_validate(payload)
    except ValidationError:
        return _clarification("action payload is invalid")
    return ActionPlan(action=action, input=parsed_input)


def _plan_chinese_alias(text: str, principal: Principal) -> ActionPlan | ClarificationPlan | None:
    action_name = _CHINESE_READ_ALIASES.get(text)
    if action_name is not None:
        return _plan_registered_action(action_name, {}, principal)

    match = _CREATE_ORG_UNIT.fullmatch(text)
    if match is not None:
        return _plan_registered_action(
            "create_org_unit",
            {"name": match.group("name"), "code": match.group("code")},
            principal,
        )
    return None


def _form_preview_plan(text: str) -> FormPreviewPlan | None:
    if re.search(r"(?:我要|我想|我需要|帮我|申请|请帮我).{0,12}(?:请假|休假)", text):
        return FormPreviewPlan(form="leave", text=text)
    if "报销" in text and not re.search(r"(?:制度|流程|规定|政策|如何|怎么)", text):
        if re.search(r"^(?:帮我|请帮我|我要|我想|申请|提交)?\s*报销", text) or re.search(r"\d+(?:\.\d{1,2})?\s*(?:元|块)", text):
            return FormPreviewPlan(form="expense", text=text)
    if re.search(r"(?:有问题|故障|异常|bug|错误).*(?:帮我|麻烦|请).*(?:找|处理|协助)", text, re.IGNORECASE):
        return FormPreviewPlan(form="ticket", text=text)
    if is_reported_fault(text):
        return FormPreviewPlan(form="ticket", text=text)
    if re.search(r"(?:帮我|请帮我|我要|我想).{0,20}(?:创建|提交|发起|提).{0,8}(?:工单|协助|请求)", text):
        return FormPreviewPlan(form="ticket", text=text)
    return None


def _period_payload(period: Period, *, day_field: str | None) -> dict[str, object]:
    """Bind exactly one period shape so the query can never widen silently."""
    if day_field is not None and period.day is not None:
        return {day_field: period.day.isoformat()}
    if period.month is not None:
        return {"month": period.month}
    if period.start is not None and period.end is not None:
        return {"start_date": period.start.isoformat(), "end_date": period.end.isoformat()}
    return {}


def _has_period(period: Period) -> bool:
    return period.day is not None or period.month is not None or period.start is not None


def _attendance_query_plan(
    text: str, principal: Principal, period: Period
) -> ActionPlan | ClarificationPlan | None:
    if _ATTENDANCE_SUBJECT.search(text) is None or _POLICY_CUE.search(text) is not None:
        return None
    if not _has_period(period) and _SUMMARY_CUE.search(text) is None:
        return None
    return _plan_registered_action(
        "attendance_summary", _period_payload(period, day_field="attendance_date"), principal
    )


def _expense_query_plan(
    text: str, principal: Principal, period: Period
) -> ActionPlan | ClarificationPlan | None:
    if _EXPENSE_SUBJECT.search(text) is None or _POLICY_CUE.search(text) is not None:
        return None
    if not _has_period(period) and _SUMMARY_CUE.search(text) is None:
        return None
    # 费用只按区间聚合，所以"昨天的费用"用当天所在的月份。
    return _plan_registered_action("expense_summary", _period_payload(period, day_field=None), principal)


def _live_query_plan(text: str, principal: Principal) -> ActionPlan | ClarificationPlan | None:
    if "工单" in text and re.search(r"(?:未完成|待处理|有哪些|列表|我的|最近|状态|进度)", text):
        return _plan_registered_action("list_tickets", {}, principal)
    period = parse_period(text)
    attendance = _attendance_query_plan(text, principal, period)
    if attendance is not None:
        return attendance
    expenses = _expense_query_plan(text, principal, period)
    if expenses is not None:
        return expenses
    if "项目" in text and re.search(r"(?:查询|查看|看看|列出|最近|有哪些)", text):
        return _plan_registered_action("list_projects", {}, principal)
    if "部门" in text and re.search(r"(?:查询|查看|看看|列出|有哪些)", text):
        return _plan_registered_action("list_departments", {}, principal)
    if "合同" in text and re.search(r"(?:查询|查看|看看|列出|最近|有哪些)", text):
        return _plan_registered_action("list_contracts", {}, principal)
    return None


def _navigation_plan(text: str, principal: Principal) -> NavigationPlan | ClarificationPlan | None:
    if not re.search(r"^(?:帮我)?(?:查看|打开|进入|去|前往)", text):
        return None
    for pattern, route_key in _NAVIGATION_ALIASES:
        if pattern.search(text):
            if route_key not in allowed_route_keys(principal):
                return _clarification("principal is not authorized for this navigation target")
            return NavigationPlan(route_key=route_key)
    return None


def plan_input(text: str, principal: Principal, db: Session | None) -> ConversationPlan:
    """Build a side-effect-free plan from rules and the closed server catalog."""
    del db
    normalized = text.strip()
    match = _ACTION_COMMAND.fullmatch(normalized)
    if match is not None:
        try:
            payload = json.loads(match.group(2))
        except json.JSONDecodeError:
            return _clarification("action payload must be a JSON object")
        return _plan_registered_action(match.group(1), payload, principal)

    if _UNSAFE_FREE_TEXT.search(normalized):
        return _clarification("unsafe free-form tool or URL input is not allowed")

    alias_plan = _plan_chinese_alias(normalized, principal)
    if alias_plan is not None:
        return alias_plan

    form_plan = _form_preview_plan(normalized)
    if form_plan is not None:
        return form_plan

    live_query = _live_query_plan(normalized, principal)
    if live_query is not None:
        return live_query

    navigation = _navigation_plan(normalized, principal)
    if navigation is not None:
        return navigation

    if normalized in {"帮我处理一下", "帮忙处理一下", "处理一下"} or (
        _AMBIGUOUS_WRITE.search(normalized) and not _KNOWLEDGE_CUE.search(normalized)
    ):
        return _clarification("business instruction is incomplete or ambiguous")
    return KnowledgePlan(question=normalized)
