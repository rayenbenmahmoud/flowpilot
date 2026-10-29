"""Rule evaluation. Condition fields are paths *inside the event payload* (``total``,
``customer.country``); ``value`` may itself be a placeholder such as ``{{ payload.reorder_level }}``."""

from typing import Any

from .templating import MISSING, get_path, render

OPERATORS: dict[str, str] = {
    "eq": "equals",
    "neq": "does not equal",
    "gt": "is greater than",
    "gte": "is at least",
    "lt": "is less than",
    "lte": "is at most",
    "contains": "contains",
    "not_contains": "does not contain",
    "in": "is one of",
    "not_in": "is not one of",
    "exists": "is present",
    "not_exists": "is missing",
}
_NUMERIC = {"gt", "gte", "lt", "lte"}


def _number(value: Any) -> float:
    if isinstance(value, bool) or value is None:
        raise ValueError("not a number")
    return float(value.strip() if isinstance(value, str) else value)


def _loosely_equal(a: Any, b: Any) -> bool:
    try:
        return _number(a) == _number(b)
    except (ValueError, TypeError):
        return str(a).strip().lower() == str(b).strip().lower()


def check_condition(condition: dict, context: dict) -> tuple[bool, str]:
    payload = context.get("payload", {})
    field = str(condition["field"]).removeprefix("payload.")
    operator = condition["operator"]
    actual = get_path(payload, field)
    present = actual is not MISSING and actual not in (None, "")
    if operator == "exists":
        return present, f"{field} {'is present' if present else 'is missing'}"
    if operator == "not_exists":
        return not present, f"{field} {'is missing' if not present else 'is present'}"
    if actual is MISSING:
        return False, f"{field} is missing from the event"
    expected = render(condition.get("value"), context, strict=False)
    label = f"{field} {OPERATORS[operator]} {expected!r} (was {actual!r})"
    try:
        if operator in _NUMERIC:
            a, b = _number(actual), _number(expected)
            result = {"gt": a > b, "gte": a >= b, "lt": a < b, "lte": a <= b}[operator]
        elif operator == "eq":
            result = _loosely_equal(actual, expected)
        elif operator == "neq":
            result = not _loosely_equal(actual, expected)
        elif operator in {"contains", "not_contains"}:
            if isinstance(actual, list):
                found = any(_loosely_equal(item, expected) for item in actual)
            else:
                found = str(expected).lower() in str(actual).lower()
            result = found if operator == "contains" else not found
        else:  # in / not_in
            options = expected if isinstance(expected, list) else [expected]
            found = any(_loosely_equal(actual, option) for option in options)
            result = found if operator == "in" else not found
    except (ValueError, TypeError):
        return False, f"{field} cannot be compared with {expected!r} (was {actual!r})"
    return result, label


def evaluate(conditions: list[dict], mode: str, context: dict) -> tuple[bool, list[str]]:
    """Return (matched, human-readable reasons). No conditions means "always run"."""
    if not conditions:
        return True, []
    outcomes = [check_condition(condition, context) for condition in conditions]
    results = [ok for ok, _ in outcomes]
    matched = all(results) if mode == "all" else any(results)
    return matched, [reason for _, reason in outcomes]
