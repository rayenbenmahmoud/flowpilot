"""Ready-made workflow templates. Instantiating one copies it; it is never linked afterwards."""

from typing import Any

TEMPLATES: list[dict[str, Any]] = [
    {
        "key": "welcome-email",
        "name": "Welcome email for new customers",
        "description": "When a customer registers, send them a welcome email.",
        "trigger_event": "customer.registered",
        "match_mode": "all",
        "conditions": [],
        "actions": [
            {
                "type": "send_email",
                "config": {
                    "to": "{{ payload.email }}",
                    "subject": "Welcome to Northwind, {{ payload.name }}!",
                    "body": "Hi {{ payload.name }},\n\nYour account ({{ payload.customer_id }}) is ready. Reply to this email if you need a hand getting started.\n\nThe Northwind team",
                },
            }
        ],
    },
    {
        "key": "order-notification",
        "name": "Internal notification for new orders",
        "description": "Tell the team whenever an order comes in.",
        "trigger_event": "order.created",
        "match_mode": "all",
        "conditions": [],
        "actions": [
            {
                "type": "notify_internal",
                "config": {
                    "title": "New order {{ payload.order_id }}",
                    "body": "Order total: {{ payload.total }} {{ payload.currency | default:EUR }}",
                    "severity": "info",
                },
            }
        ],
    },
    {
        "key": "order-n8n-handoff",
        "name": "Hand orders to n8n for fulfilment",
        "description": "Send each order to an n8n workflow (for example: create a pick list, post to Slack).",
        "trigger_event": "order.created",
        "match_mode": "all",
        "conditions": [],
        "actions": [{"type": "trigger_n8n", "config": {"path": "flowpilot-order", "body": "{{ payload }}"}}],
    },
    {
        "key": "low-inventory-alert",
        "name": "Low inventory alert",
        "description": "Raise an alert when stock falls to or below the reorder level.",
        "trigger_event": "inventory.updated",
        "match_mode": "all",
        "conditions": [{"field": "quantity", "operator": "lte", "value": "{{ payload.reorder_level }}"}],
        "actions": [
            {
                "type": "create_alert",
                "config": {
                    "title": "Low stock: {{ payload.sku }}",
                    "body": "{{ payload.product_name | default:This product }} has {{ payload.quantity }} left (reorder level {{ payload.reorder_level }}).",
                    "severity": "warning",
                },
            }
        ],
    },
    {
        "key": "support-routing",
        "name": "Support ticket routing",
        "description": "Assign new tickets by priority and category. The first matching rule wins.",
        "trigger_event": "support.request.created",
        "match_mode": "all",
        "conditions": [],
        "actions": [
            {
                "type": "assign_ticket",
                "config": {
                    "rules": [
                        {
                            "name": "Urgent tickets go to escalations",
                            "when": [{"field": "priority", "operator": "eq", "value": "urgent"}],
                            "assignee": "oncall-escalations",
                            "team": "Escalations",
                        },
                        {
                            "name": "Billing questions go to finance support",
                            "when": [{"field": "category", "operator": "eq", "value": "billing"}],
                            "assignee": "billing-desk",
                            "team": "Billing",
                        },
                    ],
                    "default_assignee": "support-queue",
                    "default_team": "General support",
                },
            }
        ],
    },
    {
        "key": "failure-notification",
        "name": "Error notification for failed workflows",
        "description": "Whenever any workflow fails, notify the team with the error and execution ID.",
        "trigger_event": "workflow.failed",
        "match_mode": "all",
        "conditions": [],
        "actions": [
            {
                "type": "notify_internal",
                "config": {
                    "title": "Workflow failed: {{ payload.workflow_name }}",
                    "body": "{{ payload.error_message | default:No details were recorded. }} (code {{ payload.error_code | default:unknown }}, attempt {{ payload.attempt | default:1 }}). Execution {{ payload.execution_id }}.",
                    "severity": "error",
                },
            }
        ],
    },
]

BY_KEY = {t["key"]: t for t in TEMPLATES}
