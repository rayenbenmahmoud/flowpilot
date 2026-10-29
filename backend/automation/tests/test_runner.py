import pytest

from automation.engine.runner import RetryBlocked, dispatch_event, retry_execution
from automation.models import (
    ActionEffect,
    Execution,
    Notification,
    OutboxMessage,
    TicketAssignment,
    Workflow,
)

pytestmark = pytest.mark.django_db(transaction=True)


def run(event, payload, key="k1"):
    items = dispatch_event(event, payload, source="webhook", idempotency_key=key)
    for i in items:
        i.execution.refresh_from_db()
    return items


class TestTemplates:
    def test_welcome_email(self, make_workflow, integration_rows):
        make_workflow("welcome-email")
        [item] = run("customer.registered", {"customer_id": "c1", "email": "a@example.com", "name": "Amira"})
        assert item.execution.status == "success"
        mail = OutboxMessage.objects.get()
        assert mail.to_address == "a@example.com" and "Amira" in mail.subject and mail.mode == "demo"

    def test_order_notification(self, make_workflow, integration_rows):
        make_workflow("order-notification")
        run("order.created", {"order_id": "O1", "total": 20, "currency": "EUR"})
        assert Notification.objects.get().title == "New order O1"

    def test_low_inventory_creates_alert_only_below_reorder_level(self, make_workflow, integration_rows):
        make_workflow("low-inventory-alert")
        [low] = run(
            "inventory.updated", {"sku": "S1", "quantity": 3, "reorder_level": 10, "product_name": "Mug"}, key="a"
        )
        [fine] = run(
            "inventory.updated", {"sku": "S2", "quantity": 30, "reorder_level": 10, "product_name": "Mug"}, key="b"
        )
        assert low.execution.status == "success" and fine.execution.status == "skipped"
        assert Notification.objects.filter(kind="alert").count() == 1
        assert any("Skipped" in log.message for log in fine.execution.logs.all())

    @pytest.mark.parametrize(
        "payload,assignee,rule",
        [
            ({"priority": "urgent", "category": "billing"}, "oncall-escalations", "Rule 1"),
            ({"priority": "normal", "category": "billing"}, "billing-desk", "Rule 2"),
            ({"priority": "low", "category": "other"}, "support-queue", "Default"),
        ],
    )
    def test_support_routing_first_match_wins(self, make_workflow, integration_rows, payload, assignee, rule):
        make_workflow("support-routing")
        run("support.request.created", {"ticket_id": "T1", "subject": "Help", **payload})
        ticket = TicketAssignment.objects.get()
        assert ticket.assignee == assignee and ticket.matched_rule.startswith(rule)

    def test_failed_workflow_creates_error_notification(self, make_workflow, integration_rows):
        make_workflow("welcome-email")
        make_workflow("failure-notification")
        [item] = run("customer.registered", {"customer_id": "c1", "email": "x@bounce.example.com", "name": "Bounce"})
        ex = item.execution
        assert ex.status == "failed" and ex.error_code == "recipient_rejected" and ex.retryable is False
        assert "Simulated bounce" in ex.error_message
        note = Notification.objects.get(severity="error")
        assert "Welcome email" in note.title and str(ex.id) in note.body
        # the error workflow ran as its own execution and did not loop
        assert Execution.objects.filter(event_type="workflow.failed", status="success").count() == 1
        assert Execution.objects.count() == 2

    def test_failure_event_has_no_listener_is_harmless(self, make_workflow, integration_rows):
        make_workflow("welcome-email")
        [item] = run("customer.registered", {"customer_id": "c1", "email": "x@bounce.example.com", "name": "B"})
        assert item.execution.status == "failed" and Notification.objects.count() == 0

    def test_missing_template_data_fails_with_clear_message(self, make_workflow, integration_rows):
        make_workflow(
            "welcome-email",
            actions=[
                {
                    "type": "send_email",
                    "config": {"to": "{{ payload.email }}", "subject": "Hi {{ payload.nickname }}", "body": "x"},
                }
            ],
        )
        [item] = run("customer.registered", {"customer_id": "c1", "email": "a@example.com", "name": "A"})
        assert item.execution.status == "failed" and "payload.nickname" in item.execution.error_message


class TestIdempotency:
    def test_duplicate_event_creates_no_second_execution(self, make_workflow, integration_rows):
        make_workflow("welcome-email")
        payload = {"customer_id": "c1", "email": "a@example.com", "name": "A"}
        first = run("customer.registered", payload, key="evt-9")
        second = run("customer.registered", payload, key="evt-9")
        assert [i.duplicate for i in first] == [False] and [i.duplicate for i in second] == [True]
        assert Execution.objects.count() == 1 and OutboxMessage.objects.count() == 1

    def test_same_key_is_scoped_per_workflow(self, make_workflow, integration_rows):
        make_workflow("order-notification")
        make_workflow("order-n8n-handoff")
        items = run("order.created", {"order_id": "O1", "total": 5}, key="evt-1")
        assert len(items) == 2 and not any(i.duplicate for i in items)

    def test_disabled_and_archived_workflows_do_not_run(self, make_workflow, integration_rows):
        make_workflow("order-notification", status="disabled")
        make_workflow("order-n8n-handoff", status="archived")
        assert run("order.created", {"order_id": "O1", "total": 5}) == []

    def test_running_an_execution_twice_does_nothing(self, make_workflow, integration_rows):
        from automation.engine.runner import run_execution

        make_workflow("order-notification")
        [item] = run("order.created", {"order_id": "O1", "total": 5})
        run_execution(str(item.execution.id))  # simulated redelivery of the Celery task
        assert Notification.objects.count() == 1


class TestRetry:
    def test_temporary_failure_then_retry_succeeds(self, make_workflow, integration_rows):
        make_workflow("welcome-email")
        [item] = run("customer.registered", {"customer_id": "c1", "email": "pat@flaky.example.com", "name": "Pat"})
        assert item.execution.status == "failed" and item.execution.retryable
        retry = retry_execution(str(item.execution.id))
        retry.refresh_from_db()
        assert retry.status == "success" and retry.attempt == 2 and retry.retry_of_id == item.execution.id
        assert OutboxMessage.objects.count() == 1

    def test_second_retry_of_same_execution_is_blocked(self, make_workflow, integration_rows):
        make_workflow("welcome-email")
        [item] = run("customer.registered", {"customer_id": "c1", "email": "pat@flaky.example.com", "name": "Pat"})
        retry_execution(str(item.execution.id))
        with pytest.raises(RetryBlocked) as err:
            retry_execution(str(item.execution.id))
        assert err.value.code == "already_retried"

    def test_only_failed_executions_can_be_retried(self, make_workflow, integration_rows):
        make_workflow("order-notification")
        [item] = run("order.created", {"order_id": "O1", "total": 5})
        with pytest.raises(RetryBlocked) as err:
            retry_execution(str(item.execution.id))
        assert err.value.code == "not_failed"

    def test_attempt_limit(self, make_workflow, integration_rows, settings):
        settings.FLOWPILOT_MAX_ATTEMPTS = 2
        make_workflow("welcome-email")
        [item] = run("customer.registered", {"customer_id": "c1", "email": "x@bounce.example.com", "name": "B"})
        second = retry_execution(str(item.execution.id))
        second.refresh_from_db()
        assert second.status == "failed" and second.attempt == 2
        with pytest.raises(RetryBlocked) as err:
            retry_execution(str(second.id))
        assert err.value.code == "attempts_exhausted"

    def test_retry_blocked_when_workflow_disabled(self, make_workflow, integration_rows):
        wf = make_workflow("welcome-email")
        [item] = run("customer.registered", {"customer_id": "c1", "email": "pat@flaky.example.com", "name": "Pat"})
        Workflow.objects.filter(pk=wf.pk).update(status="disabled")
        with pytest.raises(RetryBlocked) as err:
            retry_execution(str(item.execution.id))
        assert err.value.code == "workflow_disabled"

    def test_partial_failure_retry_does_not_repeat_completed_steps(self, make_workflow, integration_rows):
        """Step 1 (email) succeeds, step 2 (n8n outage) fails. After fixing step 2, the retry must not email again."""
        actions = [
            {"type": "send_email", "config": {"to": "{{ payload.email }}", "subject": "Welcome", "body": "Hi"}},
            {"type": "trigger_n8n", "config": {"path": "simulate-outage"}},
        ]
        wf = make_workflow("welcome-email", actions=actions)
        [item] = run("customer.registered", {"customer_id": "c1", "email": "a@example.com", "name": "A"})
        assert item.execution.status == "failed" and item.execution.error_code == "connection_error"
        assert OutboxMessage.objects.count() == 1 and ActionEffect.objects.count() == 1

        wf.actions[1]["config"]["path"] = "crm-sync"  # the operator fixes the configuration
        wf.save()
        retry = retry_execution(str(item.execution.id))
        retry.refresh_from_db()
        assert retry.status == "success"
        assert OutboxMessage.objects.count() == 1, "the welcome email must not be sent twice"
        assert ActionEffect.objects.count() == 2
        assert any("already completed" in log.message for log in retry.logs.all())


def test_optional_event_fields_do_not_break_templates(make_workflow, integration_rows):
    """Regression: 'currency' is optional on order.created; the shipped template must cope without it."""
    make_workflow("order-notification")
    [item] = run("order.created", {"order_id": "O7", "total": 12.5})
    assert item.execution.status == "success"
    assert Notification.objects.get().body == "Order total: 12.5 EUR"
