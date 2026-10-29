"""A deliberately tiny template language: ``{{ payload.order.total }}`` plus an optional
fallback for optional fields: ``{{ payload.currency | default:EUR }}``.

No expressions, no attribute access on objects, no code execution — only dictionary and list
lookups — so workflow configuration can never run arbitrary code.
"""

import json
import re
from typing import Any

MISSING = object()
_PLACEHOLDER = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
_PATH = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z0-9_]+|\[\d+\])*$")


class TemplateError(ValueError):
    """A placeholder points at data that does not exist or is malformed."""


def is_valid_path(path: str) -> bool:
    return bool(_PATH.match(path))


def get_path(data: Any, path: str) -> Any:
    current = data
    for part in re.findall(r"[^.\[\]]+", path):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return MISSING
    return current


def split_expression(expression: str) -> tuple[str, str | None]:
    """``"payload.x | default:n/a"`` -> (``"payload.x"``, ``"n/a"``). Only ``default`` is supported."""
    path, _, filter_part = expression.partition("|")
    path, filter_part = path.strip(), filter_part.strip()
    if not filter_part:
        return path, None
    name, _, argument = filter_part.partition(":")
    if name.strip() != "default":
        raise TemplateError(f"Unknown filter '{name.strip()}'. Only 'default' is supported.")
    return path, argument.strip().strip("\"'")


def placeholder_paths(value: Any) -> list[str]:
    """All placeholder paths used anywhere inside a (nested) config value."""
    if isinstance(value, str):
        paths = []
        for m in _PLACEHOLDER.findall(value):
            try:
                paths.append(split_expression(m)[0])
            except TemplateError:
                paths.append(m.strip())  # reported as invalid by the validator
        return paths
    if isinstance(value, list):
        return [p for item in value for p in placeholder_paths(item)]
    if isinstance(value, dict):
        return [p for item in value.values() for p in placeholder_paths(item)]
    return []


def _text(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return "" if value is None else str(value)


def _render_string(text: str, context: dict, strict: bool) -> Any:
    whole = _PLACEHOLDER.fullmatch(text.strip())
    if whole:  # a lone placeholder keeps the original type (numbers stay numbers)
        path, fallback = split_expression(whole.group(1))
        if not is_valid_path(path):
            raise TemplateError(f"Invalid placeholder '{{{{ {path} }}}}'.")
        found = get_path(context, path)
        if found is MISSING and fallback is not None:
            return fallback
        if found is MISSING:
            if strict:
                raise TemplateError(f"Missing value for '{{{{ {path} }}}}' in the event data.")
            return None
        return found

    def substitute(match: re.Match) -> str:
        path, fallback = split_expression(match.group(1))
        if not is_valid_path(path):
            raise TemplateError(f"Invalid placeholder '{{{{ {path} }}}}'.")
        found = get_path(context, path)
        if found is MISSING and fallback is not None:
            return fallback
        if found is MISSING:
            if strict:
                raise TemplateError(f"Missing value for '{{{{ {path} }}}}' in the event data.")
            return ""
        return _text(found)

    return _PLACEHOLDER.sub(substitute, text)


def render(value: Any, context: dict, strict: bool = True) -> Any:
    if isinstance(value, str):
        return _render_string(value, context, strict)
    if isinstance(value, list):
        return [render(item, context, strict) for item in value]
    if isinstance(value, dict):
        return {key: render(item, context, strict) for key, item in value.items()}
    return value
