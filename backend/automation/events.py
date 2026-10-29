"""Catalog of events FlowPilot accepts, with payload validation and sample data."""

import re
from typing import Any

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

RESERVED_EVENTS = {"workflow.failed"}  # emitted by the engine only, never accepted over the webhook

EVENT_CATALOG: dict[str, dict[str, Any]] = {
    "customer.registered": {
        "label": "Customer registered",
        "description": "A new customer created an account.",
        "fields": {
            "customer_id": {"type": "string", "required": True},
            "email": {"type": "email", "required": True},
            "name": {"type": "string", "required": True},
            "plan": {"type": "string", "required": False},
        },
        "sample": {
            "customer_id": "cus_1042",
            "email": "amira.haddad@example.com",
            "name": "Amira Haddad",
            "plan": "starter",
        },
    },
    "order.created": {
        "label": "Order created",
        "description": "A customer placed an order.",
        "fields": {
            "order_id": {"type": "string", "required": True},
            "total": {"type": "number", "required": True, "min": 0},
            "currency": {"type": "string", "required": False},
            "customer_email": {"type": "email", "required": False},
        },
        "sample": {
            "order_id": "ORD-7781",
            "total": 189.5,
            "currency": "EUR",
            "customer_email": "amira.haddad@example.com",
        },
    },
    "inventory.updated": {
        "label": "Inventory updated",
        "description": "Stock level of a product changed.",
        "fields": {
            "sku": {"type": "string", "required": True},
            "quantity": {"type": "integer", "required": True, "min": 0},
            "reorder_level": {"type": "integer", "required": True, "min": 0},
            "product_name": {"type": "string", "required": False},
        },
        "sample": {"sku": "SKU-2210", "product_name": "Ceramic pour-over set", "quantity": 4, "reorder_level": 10},
    },
    "support.request.created": {
        "label": "Support request created",
        "description": "A customer opened a support ticket.",
        "fields": {
            "ticket_id": {"type": "string", "required": True},
            "subject": {"type": "string", "required": True},
            "priority": {"type": "string", "required": True, "choices": ["low", "normal", "high", "urgent"]},
            "category": {"type": "string", "required": False},
            "customer_email": {"type": "email", "required": False},
        },
        "sample": {
            "ticket_id": "TCK-3301",
            "subject": "Charged twice for one order",
            "priority": "high",
            "category": "billing",
        },
    },
    "workflow.failed": {
        "label": "Workflow failed (system)",
        "description": "Emitted by FlowPilot itself whenever a workflow execution fails.",
        "fields": {
            "execution_id": {"type": "string", "required": True},
            "workflow_name": {"type": "string", "required": True},
            "error_code": {"type": "string", "required": False},
            "error_message": {"type": "string", "required": False},
        },
        "sample": {
            "execution_id": "00000000-0000-0000-0000-000000000000",
            "workflow_name": "Example",
            "error_code": "timeout",
            "error_message": "No response within 5s",
        },
    },
}

_MAX_STRING = 500


def validate_event_payload(event_type: str, payload: Any) -> list[str]:
    """Return a list of human-readable problems (empty list = valid)."""
    spec = EVENT_CATALOG[event_type]["fields"]
    if not isinstance(payload, dict):
        return ["The event body must be a JSON object."]
    problems = []
    for name, rule in spec.items():
        if name not in payload or payload[name] in (None, ""):
            if rule["required"]:
                problems.append(f"'{name}' is required.")
            continue
        value, kind = payload[name], rule["type"]
        if kind in {"string", "email"}:
            if not isinstance(value, str):
                problems.append(f"'{name}' must be a string.")
                continue
            if len(value) > _MAX_STRING:
                problems.append(f"'{name}' must be at most {_MAX_STRING} characters.")
            if kind == "email":
                try:
                    validate_email(value)
                except ValidationError:
                    problems.append(f"'{name}' must be a valid email address.")
            if "choices" in rule and value not in rule["choices"]:
                problems.append(f"'{name}' must be one of: {', '.join(rule['choices'])}.")
        elif kind in {"number", "integer"}:
            if isinstance(value, bool) or not isinstance(value, int if kind == "integer" else (int, float)):
                problems.append(f"'{name}' must be {'an integer' if kind == 'integer' else 'a number'}.")
            elif "min" in rule and value < rule["min"]:
                problems.append(f"'{name}' must be at least {rule['min']}.")
    return problems


def summarize_input(event_type: str, payload: dict) -> str:
    """One-line, human-readable description of the event for tables and logs."""
    templates = {
        "customer.registered": "{name} <{email}> ({customer_id})",
        "order.created": "Order {order_id}, total {total} {currency}",
        "inventory.updated": "{sku}: {quantity} in stock (reorder at {reorder_level})",
        "support.request.created": "{ticket_id} [{priority}] {subject}",
        "workflow.failed": "Failure in '{workflow_name}': {error_code}",
    }
    template = templates.get(event_type)
    if template:
        try:
            return re.sub(r"\s+", " ", template.format_map(_Safe(payload))).strip()[:300]
        except (ValueError, KeyError):  # pragma: no cover - defensive
            pass
    scalars = [f"{k}={v}" for k, v in payload.items() if isinstance(v, (str, int, float, bool))][:4]
    return ", ".join(scalars)[:300]


class _Safe(dict):
    def __missing__(self, key: str) -> str:
        return ""
