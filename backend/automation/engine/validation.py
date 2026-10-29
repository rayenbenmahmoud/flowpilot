"""Validate workflow configuration before it is saved (clear, field-level messages)."""

from typing import Any

from ..events import EVENT_CATALOG
from .actions import _PATH_RE, ACTIONS
from .conditions import OPERATORS
from .templating import _PLACEHOLDER, TemplateError, is_valid_path, placeholder_paths, split_expression

MAX_ACTIONS = 10
MAX_CONDITIONS = 20


def validate_conditions(conditions: Any, label: str = "conditions") -> list[str]:
    if not isinstance(conditions, list):
        return [f"{label} must be a list."]
    if len(conditions) > MAX_CONDITIONS:
        return [f"{label} can contain at most {MAX_CONDITIONS} rules."]
    errors = []
    for i, cond in enumerate(conditions, start=1):
        if not isinstance(cond, dict) or not str(cond.get("field", "")).strip():
            errors.append(f"{label} #{i}: 'field' is required.")
            continue
        if cond.get("operator") not in OPERATORS:
            errors.append(f"{label} #{i}: operator must be one of {', '.join(OPERATORS)}.")
        elif cond["operator"] not in {"exists", "not_exists"} and "value" not in cond:
            errors.append(f"{label} #{i}: 'value' is required for '{cond['operator']}'.")
        if not is_valid_path(str(cond.get("field", "")).removeprefix("payload.")):
            errors.append(f"{label} #{i}: '{cond.get('field')}' is not a valid field path.")
    return errors


def _expressions(value: Any) -> list[str]:
    if isinstance(value, str):
        return _PLACEHOLDER.findall(value)
    if isinstance(value, list):
        return [e for item in value for e in _expressions(item)]
    if isinstance(value, dict):
        return [e for item in value.values() for e in _expressions(item)]
    return []


def validate_actions(actions: Any) -> list[str]:
    if not isinstance(actions, list) or not actions:
        return ["Add at least one action."]
    if len(actions) > MAX_ACTIONS:
        return [f"A workflow can have at most {MAX_ACTIONS} actions."]
    errors = []
    for i, action in enumerate(actions, start=1):
        if not isinstance(action, dict) or action.get("type") not in ACTIONS:
            errors.append(f"Action #{i}: type must be one of {', '.join(ACTIONS)}.")
            continue
        spec, config = ACTIONS[action["type"]], action.get("config")
        if not isinstance(config, dict):
            errors.append(f"Action #{i} ({spec.label}): 'config' must be an object.")
            continue
        for key in spec.required:
            if config.get(key) in (None, "", []):
                errors.append(f"Action #{i} ({spec.label}): '{key}' is required.")
        for expression in _expressions(config):
            try:
                split_expression(expression)
            except TemplateError as exc:
                errors.append(f"Action #{i} ({spec.label}): {exc}")
        for path in placeholder_paths(config):
            if not is_valid_path(path):
                errors.append(f"Action #{i} ({spec.label}): '{{{{ {path} }}}}' is not a valid placeholder.")
        if (
            action["type"] in {"trigger_n8n", "call_external_api"}
            and config.get("path")
            and not _PATH_RE.match(str(config["path"]))
        ):
            errors.append(f"Action #{i} ({spec.label}): 'path' contains characters that are not allowed.")
        if action["type"] == "assign_ticket":
            for j, rule in enumerate(config.get("rules", []) if isinstance(config.get("rules"), list) else [], start=1):
                if not isinstance(rule, dict) or not rule.get("assignee"):
                    errors.append(f"Action #{i} rule #{j}: 'assignee' is required.")
                    continue
                errors += validate_conditions(rule.get("when", []), f"Action #{i} rule #{j} 'when'")
    return errors


def validate_workflow(trigger_event: str, match_mode: str, conditions: Any, actions: Any) -> dict[str, list[str]]:
    problems: dict[str, list[str]] = {}
    if trigger_event not in EVENT_CATALOG:
        problems["trigger_event"] = [f"Unknown event. Choose one of: {', '.join(EVENT_CATALOG)}."]
    if match_mode not in {"all", "any"}:
        problems["match_mode"] = ["Must be 'all' or 'any'."]
    if errors := validate_conditions(conditions):
        problems["conditions"] = errors
    if errors := validate_actions(actions):
        problems["actions"] = errors
    return problems
