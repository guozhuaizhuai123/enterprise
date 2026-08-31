"""Side-effect-free parsing for the controlled assistant action catalog."""
import json
import re
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.assistant.registry import ActionDefinition, get_action, list_actions
from app.deps import Principal

_ACTION_COMMAND = re.compile(r"^action:([a-z][a-z0-9_]*)\s+(\{.*\})$", re.DOTALL)
_CHINESE_READ_ALIASES = {
    "查询项目": "list_projects",
    "查看项目": "list_projects",
    "查询部门": "list_departments",
    "查看部门": "list_departments",
}
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


def plan_input(text: str, principal: Principal, db: Session | None) -> ActionPlan | ClarificationPlan:
    """Build a plan from a registered command or a strict Chinese alias without executing it."""
    del db
    normalized = text.strip()
    match = _ACTION_COMMAND.fullmatch(normalized)
    if match is not None:
        try:
            payload = json.loads(match.group(2))
        except json.JSONDecodeError:
            return _clarification("action payload must be a JSON object")
        return _plan_registered_action(match.group(1), payload, principal)

    alias_plan = _plan_chinese_alias(normalized, principal)
    if alias_plan is not None:
        return alias_plan
    return _clarification("an explicit registered action command or complete Chinese alias is required")
