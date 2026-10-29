"""Guided demo scenarios and seed data. Everything here is synthetic and clearly labelled as such."""

import random
import uuid
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from .engine.runner import dispatch_event
from .integrations.registry import ensure_settings_rows
from .models import (
    ActionEffect,
    Execution,
    ExecutionLog,
    IntegrationSetting,
    Notification,
    OutboxMessage,
    TicketAssignment,
    Workflow,
)
from .templates_catalog import TEMPLATES


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:6]}"


SCENARIOS: list[dict[str, Any]] = [
    {
        "key": "new-customer",
        "title": "Register a new customer",
        "event": "customer.registered",
        "explain": "A signup event arrives and the welcome-email workflow reacts.",
        "expect": "A welcome email appears in the demo mailbox. No real email is sent.",
        "payload": lambda: {
            "customer_id": _id("cus"),
            "name": "Leila Ben Salah",
            "email": f"leila.{uuid.uuid4().hex[:4]}@example.com",
            "plan": "starter",
        },
    },
    {
        "key": "new-order",
        "title": "Place an order",
        "event": "order.created",
        "explain": "One order event fans out to two workflows: an internal notification and an n8n hand-off.",
        "expect": "A team notification appears, and the n8n adapter records a simulated call.",
        "payload": lambda: {
            "order_id": _id("ORD"),
            "total": round(random.uniform(40, 420), 2),
            "currency": "EUR",
            "customer_email": "buyer@example.com",
        },
    },
    {
        "key": "low-stock",
        "title": "Stock drops below the reorder level",
        "event": "inventory.updated",
        "explain": "The rule compares quantity with reorder_level.",
        "expect": "A low-stock alert is created.",
        "payload": lambda: {
            "sku": _id("SKU"),
            "product_name": "Ceramic pour-over set",
            "quantity": 3,
            "reorder_level": 10,
        },
    },
    {
        "key": "stock-ok",
        "title": "Stock update that needs no action",
        "event": "inventory.updated",
        "explain": "Quantity is above the reorder level, so the condition does not match.",
        "expect": "The execution is marked Skipped, with the reason in its log. No alert is created.",
        "payload": lambda: {"sku": _id("SKU"), "product_name": "Linen tote bag", "quantity": 48, "reorder_level": 10},
    },
    {
        "key": "support-urgent",
        "title": "Urgent support request",
        "event": "support.request.created",
        "explain": "Routing rules are checked in order and the first match wins.",
        "expect": "The ticket is assigned to Escalations (rule 1).",
        "payload": lambda: {
            "ticket_id": _id("TCK"),
            "subject": "Checkout is down for all customers",
            "priority": "urgent",
            "category": "outage",
        },
    },
    {
        "key": "support-billing",
        "title": "Billing support request",
        "event": "support.request.created",
        "explain": "Not urgent, so rule 1 is skipped and the billing rule matches.",
        "expect": "The ticket is assigned to the Billing team (rule 2).",
        "payload": lambda: {
            "ticket_id": _id("TCK"),
            "subject": "Charged twice for one order",
            "priority": "normal",
            "category": "billing",
        },
    },
    {
        "key": "bounced-email",
        "title": "Welcome email that bounces",
        "event": "customer.registered",
        "explain": "The simulated mail server permanently rejects bounce.example.com addresses.",
        "expect": "The execution fails with a clear message and an error notification is created automatically.",
        "payload": lambda: {"customer_id": _id("cus"), "name": "Test Bounce", "email": "nobody@bounce.example.com"},
    },
    {
        "key": "flaky-email",
        "title": "Welcome email with a temporary failure",
        "event": "customer.registered",
        "explain": "The simulated mail server times out on the first attempt only.",
        "expect": "The first attempt fails. Open it in Executions and press Retry: attempt 2 succeeds.",
        "payload": lambda: {"customer_id": _id("cus"), "name": "Test Flaky", "email": "customer@flaky.example.com"},
    },
    {
        "key": "duplicate-event",
        "title": "The same event delivered twice",
        "event": "order.created",
        "explain": "Senders often deliver webhooks more than once. Both deliveries carry the same event ID.",
        "expect": "The second delivery is recognised as a duplicate and creates no new executions.",
        "payload": lambda: {"order_id": _id("ORD"), "total": 99.0, "currency": "EUR"},
        "twice": True,
    },
]
BY_KEY = {s["key"]: s for s in SCENARIOS}


def scenario_catalog() -> list[dict[str, str]]:
    return [{k: s[k] for k in ("key", "title", "event", "explain", "expect")} for s in SCENARIOS]


def run_scenario(key: str) -> dict[str, Any]:
    from .serializers import ExecutionListSerializer

    scenario = BY_KEY[key]
    payload = scenario["payload"]()
    event_id = f"demo-{uuid.uuid4().hex[:10]}"
    payload = {**payload, "event_id": event_id}
    deliveries = ["First delivery", "Same event delivered again"] if scenario.get("twice") else ["Delivery"]
    runs = []
    for label in deliveries:
        items = dispatch_event(scenario["event"], payload, source=Execution.Source.DEMO, idempotency_key=event_id)
        rows = []
        for item in items:
            item.execution.refresh_from_db()
            rows.append({**ExecutionListSerializer(item.execution).data, "duplicate": item.duplicate})
        runs.append({"label": label, "executions": rows})
    return {"scenario": key, "event": scenario["event"], "idempotency_key": event_id, "runs": runs}


# ---------------------------------------------------------------- seed data
_NAMES = [
    "Amira Haddad",
    "Youssef Trabelsi",
    "Sofia Marini",
    "Daniel Okafor",
    "Mei Tanaka",
    "Lucas Moreau",
    "Nadia Karim",
    "Oliver Stein",
]
_PRODUCTS = ["Ceramic pour-over set", "Linen tote bag", "Walnut desk tray", "Enamel camp mug", "Wool throw blanket"]
_SUBJECTS = [
    ("Cannot reset my password", "normal", "account"),
    ("Charged twice for one order", "high", "billing"),
    ("Parcel arrived damaged", "normal", "shipping"),
    ("Site is down", "urgent", "outage"),
    ("Invoice copy request", "low", "billing"),
]


def _history_event(rng: random.Random, workflow: Workflow) -> dict[str, Any]:
    n = rng.randint(1000, 9999)
    name = rng.choice(_NAMES)
    match workflow.trigger_event:
        case "customer.registered":
            return {
                "customer_id": f"cus_{n}",
                "name": name,
                "email": f"{name.split()[0].lower()}.{n}@example.com",
                "plan": rng.choice(["starter", "pro"]),
            }
        case "order.created":
            return {"order_id": f"ORD-{n}", "total": round(rng.uniform(25, 480), 2), "currency": "EUR"}
        case "inventory.updated":
            reorder = 10
            return {
                "sku": f"SKU-{n}",
                "product_name": rng.choice(_PRODUCTS),
                "quantity": rng.choice([2, 3, 6, 9, 14, 30, 52]),
                "reorder_level": reorder,
            }
        case _:
            subject, priority, category = rng.choice(_SUBJECTS)
            return {"ticket_id": f"TCK-{n}", "subject": subject, "priority": priority, "category": category}


def seed_demo(rng_seed: int = 42) -> dict[str, int]:
    """Create demo user, integrations, six template workflows and ~7 days of plausible history."""
    from .engine.runner import FAILURE_EVENT  # noqa: F401  (documented dependency)
    from .events import summarize_input

    rng = random.Random(rng_seed)
    User = get_user_model()
    user, created = User.objects.get_or_create(
        username="demo", defaults={"is_staff": True, "email": "demo@example.com"}
    )
    if created:
        user.set_password(settings.FLOWPILOT_DEMO_USER_PASSWORD)
        user.save()
    ensure_settings_rows()

    workflows = {}
    for template in TEMPLATES:
        workflow, _ = Workflow.objects.get_or_create(
            template_key=template["key"],
            defaults={
                k: template[k] for k in ("name", "description", "trigger_event", "match_mode", "conditions", "actions")
            }
            | {"status": Workflow.Status.ACTIVE},
        )
        workflows[template["key"]] = workflow
    Workflow.objects.get_or_create(
        name="Legacy order export (replaced by n8n hand-off)",
        defaults={
            "description": "Archived example. Kept for history, no longer runs.",
            "trigger_event": "order.created",
            "status": Workflow.Status.ARCHIVED,
            "archived_at": timezone.now() - timedelta(days=20),
            "actions": [{"type": "call_external_api", "config": {"path": "v1/orders", "body": "{{ payload }}"}}],
        },
    )
    if Execution.objects.exists():
        return {"workflows": Workflow.objects.count(), "executions": Execution.objects.count()}

    now = timezone.now()
    runnable = [w for k, w in workflows.items() if k != "failure-notification"]
    weights = [3, 4, 2, 3, 2][: len(runnable)]
    created_count = 0
    for i in range(72):
        workflow = rng.choices(runnable, weights=weights + [1] * (len(runnable) - len(weights)))[0]
        ts = now - timedelta(days=rng.uniform(0.05, 6.9))
        payload = _history_event(rng, workflow)
        duration = rng.randint(40, 900) if workflow.trigger_event != "order.created" else rng.randint(120, 1400)
        failed = rng.random() < 0.11 and workflow.template_key in {"welcome-email", "order-n8n-handoff"}
        skipped = workflow.template_key == "low-inventory-alert" and payload["quantity"] > payload["reorder_level"]
        status = "failed" if failed else "skipped" if skipped else "success"
        error = {}
        if failed:
            error = (
                {
                    "error_code": "smtp_timeout",
                    "error_message": "The mail server did not answer within 10 seconds.",
                    "retryable": True,
                }
                if workflow.template_key == "welcome-email"
                else {
                    "error_code": "connection_error",
                    "error_message": "Could not connect to the service. Is it running and reachable?",
                    "retryable": True,
                }
            )
            duration = 5000 + rng.randint(0, 300)
        execution = Execution.objects.create(
            workflow=workflow,
            workflow_name=workflow.name,
            workflow_version=1,
            event_type=workflow.trigger_event,
            status=status,
            source=Execution.Source.WEBHOOK,
            idempotency_key=f"seed-{i}",
            attempt=1,
            root_id=uuid.uuid4(),
            payload=payload,
            input_summary=summarize_input(workflow.trigger_event, payload),
            duration_ms=duration,
            **error,
        )
        Execution.objects.filter(pk=execution.pk).update(
            root_id=execution.pk, created_at=ts, started_at=ts, finished_at=ts + timedelta(milliseconds=duration)
        )
        ExecutionLog.objects.create(
            execution=execution, step="start", message=f"Started attempt 1 of '{workflow.name}'."
        )
        ExecutionLog.objects.create(
            execution=execution,
            step="finish",
            level="error" if failed else "info",
            message=f"Failed: {error['error_message']}"
            if failed
            else "Skipped: conditions not met."
            if skipped
            else "All actions completed.",
        )
        ExecutionLog.objects.filter(execution=execution).update(created_at=ts)
        created_count += 1
        _seed_outputs(workflow, execution, payload, status, ts)
        if failed:
            Notification.objects.filter(
                pk=Notification.objects.create(
                    severity="error",
                    title=f"Workflow failed: {workflow.name}",
                    body=f"{error['error_message']} (code {error['error_code']}, attempt 1).",
                    execution=execution,
                ).pk
            ).update(created_at=ts + timedelta(seconds=6))
            if ts < now - timedelta(days=3):  # older failures were already retried successfully
                retry = Execution.objects.create(
                    workflow=workflow,
                    workflow_name=workflow.name,
                    event_type=workflow.trigger_event,
                    status="success",
                    source="retry",
                    idempotency_key=f"seed-{i}:retry:2",
                    attempt=2,
                    root_id=execution.pk,
                    retry_of=execution,
                    payload=payload,
                    input_summary=execution.input_summary,
                    duration_ms=210,
                )
                rts = ts + timedelta(hours=1)
                Execution.objects.filter(pk=retry.pk).update(
                    created_at=rts, started_at=rts, finished_at=rts + timedelta(milliseconds=210)
                )
                _seed_outputs(workflow, retry, payload, "success", rts)
    return {"workflows": Workflow.objects.count(), "executions": Execution.objects.count()}


def _seed_outputs(workflow: Workflow, execution: Execution, payload: dict, status: str, ts) -> None:
    if status != "success":
        return
    match workflow.template_key:
        case "welcome-email":
            obj = OutboxMessage.objects.create(
                to_address=payload["email"],
                subject=f"Welcome to Northwind, {payload['name']}!",
                body=f"Hi {payload['name']}, your account is ready.",
                mode="demo",
                provider_message_id=f"demo-{uuid.uuid4().hex[:10]}",
                execution=execution,
            )
        case "order-notification":
            obj = Notification.objects.create(
                title=f"New order {payload['order_id']}",
                body=f"Order total: {payload['total']} {payload.get('currency', 'EUR')}",
                execution=execution,
            )
        case "low-inventory-alert":
            obj = Notification.objects.create(
                kind="alert",
                severity="warning",
                title=f"Low stock: {payload['sku']}",
                body=f"{payload['product_name']} has {payload['quantity']} left.",
                execution=execution,
            )
        case "support-routing":
            urgent, billing = payload["priority"] == "urgent", payload["category"] == "billing"
            assignee, team, rule = (
                ("oncall-escalations", "Escalations", "Rule 1: Urgent tickets go to escalations")
                if urgent
                else ("billing-desk", "Billing", "Rule 2: Billing questions go to finance support")
                if billing
                else ("support-queue", "General support", "Default assignment (no rule matched)")
            )
            obj = TicketAssignment.objects.create(
                ticket_id=payload["ticket_id"],
                subject=payload["subject"],
                priority=payload["priority"],
                category=payload["category"],
                assignee=assignee,
                team=team,
                matched_rule=rule,
                execution=execution,
            )
        case _:
            return
    type(obj).objects.filter(pk=obj.pk).update(created_at=ts + timedelta(milliseconds=300))


def reset_demo() -> dict[str, int]:
    for model in (ActionEffect, Notification, OutboxMessage, TicketAssignment, Execution, Workflow, IntegrationSetting):
        model.objects.all().delete()
    return seed_demo()
