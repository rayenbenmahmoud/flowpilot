import pytest

from automation.engine.conditions import evaluate
from automation.engine.redaction import redact
from automation.engine.templating import TemplateError, render
from automation.engine.validation import validate_workflow
from automation.events import validate_event_payload

CTX = {
    "payload": {
        "total": 120,
        "quantity": 4,
        "reorder_level": 10,
        "name": "Amira",
        "tags": ["vip", "eu"],
        "customer": {"country": "TN"},
    }
}
pytestmark = pytest.mark.django_db(transaction=False)


class TestTemplating:
    def test_inline_placeholders(self):
        assert render("Hi {{ payload.name }}!", CTX) == "Hi Amira!"

    def test_lone_placeholder_keeps_type(self):
        assert render("{{ payload.total }}", CTX) == 120

    def test_nested_and_list_paths(self):
        assert render("{{ payload.customer.country }}/{{ payload.tags[1] }}", CTX) == "TN/eu"

    def test_missing_value_is_a_clear_error(self):
        with pytest.raises(TemplateError, match="payload.nope"):
            render("{{ payload.nope }}", CTX)

    def test_lenient_mode_returns_blank(self):
        assert render("x{{ payload.nope }}", CTX, strict=False) == "x"

    def test_no_code_execution(self):
        with pytest.raises(TemplateError):
            render("{{ payload.__class__ }}", CTX)
        with pytest.raises(TemplateError):
            render("{{ 7*7 }}", CTX)


class TestConditions:
    @pytest.mark.parametrize(
        "cond,expected",
        [
            ({"field": "total", "operator": "gte", "value": 100}, True),
            ({"field": "total", "operator": "lt", "value": 100}, False),
            ({"field": "quantity", "operator": "lte", "value": "{{ payload.reorder_level }}"}, True),
            ({"field": "name", "operator": "eq", "value": "amira"}, True),
            ({"field": "tags", "operator": "contains", "value": "vip"}, True),
            ({"field": "customer.country", "operator": "in", "value": ["TN", "FR"]}, True),
            ({"field": "customer.country", "operator": "not_in", "value": ["TN"]}, False),
            ({"field": "missing", "operator": "exists"}, False),
            ({"field": "missing", "operator": "not_exists"}, True),
            ({"field": "missing", "operator": "eq", "value": 1}, False),
            ({"field": "name", "operator": "gt", "value": 5}, False),  # non-numeric compare is False, not a crash
        ],
    )
    def test_operators(self, cond, expected):
        assert evaluate([cond], "all", CTX)[0] is expected

    def test_all_vs_any(self):
        rules = [
            {"field": "total", "operator": "gt", "value": 500},
            {"field": "name", "operator": "eq", "value": "Amira"},
        ]
        assert evaluate(rules, "all", CTX)[0] is False
        assert evaluate(rules, "any", CTX)[0] is True

    def test_no_conditions_always_matches(self):
        assert evaluate([], "all", CTX) == (True, [])

    def test_reasons_are_human_readable(self):
        _, reasons = evaluate([{"field": "total", "operator": "gt", "value": 500}], "all", CTX)
        assert "total is greater than 500" in reasons[0] and "120" in reasons[0]


class TestRedaction:
    def test_masks_secret_like_keys_recursively(self):
        out = redact({"email": "a@b.c", "api_key": "x", "nested": {"Password": "p", "ok": 1}, "list": [{"token": "t"}]})
        assert out == {
            "email": "a@b.c",
            "api_key": "[REDACTED]",
            "nested": {"Password": "[REDACTED]", "ok": 1},
            "list": [{"token": "[REDACTED]"}],
        }


class TestValidation:
    def test_unknown_event_and_empty_actions(self):
        problems = validate_workflow("nope", "all", [], [])
        assert "trigger_event" in problems and "actions" in problems

    def test_action_required_fields_and_bad_placeholder(self):
        problems = validate_workflow(
            "customer.registered",
            "all",
            [],
            [{"type": "send_email", "config": {"to": "{{ payload.email }}", "subject": "{{ 1+1 }}"}}],
        )
        text = " ".join(problems["actions"])
        assert "'body' is required" in text and "not a valid placeholder" in text

    def test_bad_condition_operator(self):
        assert "conditions" in validate_workflow(
            "order.created",
            "all",
            [{"field": "total", "operator": "sorta"}],
            [{"type": "notify_internal", "config": {"title": "x"}}],
        )


class TestEventPayloads:
    def test_valid(self):
        assert validate_event_payload("order.created", {"order_id": "A1", "total": 10}) == []

    def test_problems_are_listed(self):
        problems = validate_event_payload("support.request.created", {"ticket_id": "T", "priority": "meh"})
        assert any("subject" in p for p in problems) and any("priority" in p for p in problems)

    def test_rejects_bool_as_number_and_negative(self):
        assert validate_event_payload("order.created", {"order_id": "A", "total": True})
        assert validate_event_payload("inventory.updated", {"sku": "s", "quantity": -1, "reorder_level": 1})


class TestDefaultFilter:
    def test_default_used_only_when_missing(self):
        assert render("{{ payload.currency | default:EUR }}", CTX) == "EUR"
        assert render("{{ payload.name | default:nobody }}", CTX) == "Amira"
        assert render("Total {{ payload.total }} {{ payload.currency | default:EUR }}", CTX) == "Total 120 EUR"

    def test_unknown_filter_is_rejected(self):
        with pytest.raises(TemplateError, match="Unknown filter"):
            render("{{ payload.name | upper }}", CTX)
        problems = validate_workflow(
            "order.created",
            "all",
            [],
            [{"type": "notify_internal", "config": {"title": "{{ payload.order_id | upper }}"}}],
        )
        assert "Unknown filter" in " ".join(problems["actions"])


class TestLogScrubbing:
    def test_configured_secrets_are_masked_in_log_lines(self, settings):
        import logging

        from automation.logging_filters import SecretScrubFilter

        settings.FLOWPILOT_N8N_WEBHOOK_SECRET = "n8n-super-secret-value"
        record = logging.LogRecord(
            "t", logging.INFO, __file__, 1, "call failed for token %s", ("n8n-super-secret-value",), None
        )
        assert SecretScrubFilter().filter(record) is True
        assert "n8n-super-secret-value" not in record.getMessage() and "***" in record.getMessage()
