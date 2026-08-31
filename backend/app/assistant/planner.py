"""Side-effect-free parsing for the controlled assistant action catalog."""
import json
import re
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.assistant.registry import ActionDefinition, get_action, list_actions
from app.deps import Principal

_ACTION_COMMAND = re.compile(r"^action:([a-z][a-z0-9_]*)\s+(\{.*\})$", re.DOTALL)


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


def plan_input(text: str, principal: Principal, db: Session | None) -> ActionPlan | ClarificationPlan:
    """Validate an explicit ``action:<registered_name> {json}`` request without executing it."""
    match = _ACTION_COMMAND.fullmatch(text.strip())
    if match is None:
        return _clarification("an explicit registered action command is required")

    action = get_action(match.group(1))
    if action is None:
        return _clarification("action is not registered")
    if not principal.has_role(*action.required_roles):
        return _clarification("principal is not authorized for this action")

    try:
        payload = json.loads(match.group(2))
    except json.JSONDecodeError:
        return _clarification("action payload must be a JSON object")
    if not isinstance(payload, dict):
        return _clarification("action payload must be a JSON object")
    try:
        parsed_input = action.input_model.model_validate(payload)
    except ValidationError:
        return _clarification("action payload is invalid")
    return ActionPlan(action=action, input=parsed_input)
