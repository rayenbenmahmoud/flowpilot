"""Action handlers. Each takes (context, config) and returns a small JSON-safe result dict.

Handlers are the only place that touches adapters or writes business output rows, and the
runner wraps each one in a transaction together with its ``ActionEffect`` ledger entry."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..integrations.base import AdapterError
from ..integrations.registry import get_adapter
from ..models import Execution, Notification, OutboxMessage, TicketAssignment
from .conditions import OPERATORS, evaluate
from .templating import MISSING, get_path, render


class ActionError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code, self.message, self.retryable = code, message, retryable

    @classmethod
    def from_adapter(cls, exc: AdapterError) -> "ActionError":
        return cls(exc.code, exc.message, exc.retryable)


@dataclass
class ActionContext:
    execution: Execution
    step_index: int
    dedupe_key: str
    template_context: dict[str, Any]

    @property
    def payload(self) -> dict:
        return self.template_context["payload"]


_PATH_RE = re.compile(r"^[A-Za-z0-9_\-/.]{1,200}$")


def send_email(ctx: ActionContext, config: dict) -> dict:
    values = render(config, ctx.template_context)
    try:
        sent = get_adapter("email").send(
            to=str(values["to"]).strip(),
            subject=str(values["subject"]),
            body=str(values["body"]),
            attempt=ctx.execution.attempt,
            idempotency_key=ctx.dedupe_key,
        )
    except AdapterError as exc:
        raise ActionError.from_adapter(exc) from None
    OutboxMessage.objects.create(
        to_address=str(values["to"]).strip(),
        subject=str(values["subject"])[:200],
        body=str(values["body"]),
        mode=sent["mode"],
        status="sent",
        provider_message_id=sent["message_id"],
        execution=ctx.execution,
    )
    return {"to": values["to"], "mode": sent["mode"], "message_id": sent["message_id"]}


def _notify(kind: str, default_severity: str):
    def handler(ctx: ActionContext, config: dict) -> dict:
        values = render(config, ctx.template_context)
        severity = values.get("severity", default_severity)
        if severity not in {"info", "warning", "error"}:
            raise ActionError("invalid_config", f"Severity must be info, warning or error (got '{severity}').")
        note = Notification.objects.create(
            kind=kind,
            severity=severity,
            title=str(values["title"])[:200],
            body=str(values.get("body", "")),
            execution=ctx.execution,
        )
        return {"notification_id": note.id, "kind": kind, "severity": severity}

    return handler


def assign_ticket(ctx: ActionContext, config: dict) -> dict:
    assignee = team = ""
    matched = ""
    for index, rule in enumerate(config.get("rules", []), start=1):
        ok, _ = evaluate(rule.get("when", []), rule.get("match_mode", "all"), ctx.template_context)
        if ok:
            assignee, team = rule["assignee"], rule.get("team", "")
            matched = f"Rule {index}: {rule.get('name') or describe_conditions(rule.get('when', []))}"
            break
    if not assignee:
        assignee, team = config.get("default_assignee", ""), config.get("default_team", "")
        matched = "Default assignment (no rule matched)"
    if not assignee:
        raise ActionError("no_assignee", "No routing rule matched this ticket and no default assignee is configured.")

    def field(name: str) -> str:
        found = get_path(ctx.payload, name)
        return "" if found is MISSING or found is None else str(found)

    record = TicketAssignment.objects.create(
        ticket_id=field("ticket_id"),
        subject=field("subject")[:300],
        priority=field("priority"),
        category=field("category"),
        assignee=assignee,
        team=team,
        matched_rule=matched[:200],
        execution=ctx.execution,
    )
    return {"assignment_id": record.id, "assignee": assignee, "team": team, "matched_rule": matched}


def trigger_n8n(ctx: ActionContext, config: dict) -> dict:
    body = render(config.get("body", "{{ payload }}"), ctx.template_context)
    try:
        return get_adapter("n8n").trigger(path=str(config["path"]), body=body, idempotency_key=ctx.dedupe_key)
    except AdapterError as exc:
        raise ActionError.from_adapter(exc) from None


def call_external_api(ctx: ActionContext, config: dict) -> dict:
    body = render(config.get("body", "{{ payload }}"), ctx.template_context)
    try:
        return get_adapter("http").call(path=str(config["path"]), body=body, idempotency_key=ctx.dedupe_key)
    except AdapterError as exc:
        raise ActionError.from_adapter(exc) from None


def describe_conditions(conditions: list[dict]) -> str:
    if not conditions:
        return "always"
    return " and ".join(
        f"{c['field']} {OPERATORS.get(c['operator'], c['operator'])} {c.get('value', '')}".strip() for c in conditions
    )


@dataclass(frozen=True)
class ActionSpec:
    type: str
    label: str
    description: str
    required: tuple[str, ...]
    example: dict[str, Any]
    handler: Callable[[ActionContext, dict], dict]


ACTIONS: dict[str, ActionSpec] = {
    spec.type: spec
    for spec in (
        ActionSpec(
            "send_email",
            "Send email",
            "Send an email through the email adapter.",
            ("to", "subject", "body"),
            {
                "to": "{{ payload.email }}",
                "subject": "Welcome, {{ payload.name }}",
                "body": "Hi {{ payload.name }}, thanks for signing up.",
            },
            send_email,
        ),
        ActionSpec(
            "notify_internal",
            "Notify the team",
            "Create an internal notification.",
            ("title",),
            {"title": "New order {{ payload.order_id }}", "body": "Total: {{ payload.total }}", "severity": "info"},
            _notify("notification", "info"),
        ),
        ActionSpec(
            "create_alert",
            "Create alert",
            "Raise an alert that needs attention.",
            ("title",),
            {
                "title": "Low stock: {{ payload.sku }}",
                "body": "Only {{ payload.quantity }} left.",
                "severity": "warning",
            },
            _notify("alert", "warning"),
        ),
        ActionSpec(
            "assign_ticket",
            "Assign ticket",
            "Route a support ticket using ordered rules; the first match wins.",
            ("rules",),
            {
                "rules": [
                    {
                        "name": "Urgent tickets",
                        "when": [{"field": "priority", "operator": "eq", "value": "urgent"}],
                        "assignee": "oncall-escalations",
                        "team": "Escalations",
                    }
                ],
                "default_assignee": "support-queue",
                "default_team": "Support",
            },
            assign_ticket,
        ),
        ActionSpec(
            "trigger_n8n",
            "Trigger n8n workflow",
            "POST the event to an n8n production webhook.",
            ("path",),
            {"path": "flowpilot-order", "body": "{{ payload }}"},
            trigger_n8n,
        ),
        ActionSpec(
            "call_external_api",
            "Call external API",
            "POST JSON to a configured partner API.",
            ("path",),
            {"path": "v1/orders", "body": "{{ payload }}"},
            call_external_api,
        ),
    )
}
