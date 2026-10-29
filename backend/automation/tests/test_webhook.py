import json
import time

import pytest

from automation.models import Execution, OutboxMessage
from automation.throttles import WebhookThrottle

pytestmark = pytest.mark.django_db(transaction=True)
GOOD = {"customer_id": "c1", "email": "amira@example.com", "name": "Amira"}


@pytest.fixture(autouse=True)
def _workflow(make_workflow, integration_rows):
    return make_workflow("welcome-email")


def error_code(response):
    return response.json()["error"]["code"]


def test_valid_signed_webhook_runs_the_workflow(send_webhook):
    r = send_webhook("customer.registered", GOOD)
    assert r.status_code == 202
    body = r.json()
    assert body["duplicate"] is False and body["executions"][0]["status"] == "success"
    assert OutboxMessage.objects.count() == 1


def test_bad_signature_is_rejected_and_nothing_runs(send_webhook):
    r = send_webhook("customer.registered", GOOD, signature="sha256=" + "0" * 64)
    assert r.status_code == 401 and error_code(r) == "invalid_signature"
    assert Execution.objects.count() == 0


def test_wrong_secret_is_rejected(send_webhook):
    assert send_webhook("customer.registered", GOOD, secret="not-the-secret").status_code == 401


def test_body_tampering_after_signing_is_rejected(send_webhook):
    ts = str(int(time.time()))
    from automation.webhook_auth import sign

    signature = sign("test-webhook-secret", ts, json.dumps(GOOD).encode())
    tampered = json.dumps({**GOOD, "email": "attacker@example.com"}).encode()
    r = send_webhook("customer.registered", GOOD, raw=tampered, timestamp=int(ts), signature=signature)
    assert r.status_code == 401


def test_missing_signature_headers(anon):
    r = anon.post("/api/v1/webhooks/customer.registered/", data=json.dumps(GOOD), content_type="application/json")
    assert r.status_code == 401 and error_code(r) == "missing_signature"


def test_stale_timestamp_is_rejected_as_replay(send_webhook):
    r = send_webhook("customer.registered", GOOD, timestamp=int(time.time()) - 3600)
    assert r.status_code == 401 and error_code(r) == "stale_timestamp"


def test_no_secret_configured_refuses_everything(send_webhook, settings):
    settings.FLOWPILOT_WEBHOOK_SECRET = ""
    r = send_webhook("customer.registered", GOOD)
    assert r.status_code == 503 and error_code(r) == "webhook_not_configured"


def test_invalid_json(send_webhook):
    assert error_code(send_webhook("customer.registered", {}, raw=b"{not json")) == "invalid_json"


def test_payload_schema_errors_are_listed(send_webhook):
    r = send_webhook("customer.registered", {"customer_id": "c1", "email": "nope"})
    assert r.status_code == 400 and error_code(r) == "invalid_payload"
    details = r.json()["error"]["details"]["payload"]
    assert any("email" in d for d in details) and any("name" in d for d in details)


def test_non_object_body(send_webhook):
    assert error_code(send_webhook("customer.registered", {}, raw=b"[1,2]")) == "invalid_payload"


def test_unknown_event_404(send_webhook):
    assert send_webhook("made.up", GOOD).status_code == 404


def test_reserved_system_event_cannot_be_sent(send_webhook):
    assert error_code(send_webhook("workflow.failed", {"execution_id": "x", "workflow_name": "y"})) == "reserved_event"


def test_idempotency_key_is_required(send_webhook):
    assert error_code(send_webhook("customer.registered", GOOD, key=None)) == "missing_idempotency_key"


def test_event_id_in_body_counts_as_idempotency_key(send_webhook):
    r = send_webhook("customer.registered", {**GOOD, "event_id": "evt-body"}, key=None)
    assert r.status_code == 202 and r.json()["idempotency_key"] == "evt-body"


def test_duplicate_delivery_is_recognised(send_webhook):
    first = send_webhook("customer.registered", GOOD, key="dup-1")
    second = send_webhook("customer.registered", GOOD, key="dup-1")
    assert first.status_code == 202 and second.status_code == 200
    assert second.json()["duplicate"] is True
    assert second.json()["executions"][0]["id"] == first.json()["executions"][0]["id"]
    assert Execution.objects.count() == 1 and OutboxMessage.objects.count() == 1


def test_oversized_body_rejected(send_webhook, settings):
    settings.FLOWPILOT_WEBHOOK_MAX_BYTES = 100
    r = send_webhook("customer.registered", {**GOOD, "name": "x" * 400})
    assert r.status_code == 413


def test_no_listening_workflow_is_a_clear_202(send_webhook):
    r = send_webhook("order.created", {"order_id": "O1", "total": 3})
    assert r.status_code == 202 and r.json()["executions"] == [] and "No active workflow" in r.json()["message"]


def test_rate_limit(send_webhook, monkeypatch):
    monkeypatch.setitem(WebhookThrottle.THROTTLE_RATES, "webhook", "3/min")
    codes = [send_webhook("customer.registered", GOOD, key=f"k{i}").status_code for i in range(5)]
    assert codes[:3] == [202, 202, 202] and codes[3:] == [429, 429]


def test_secret_never_appears_in_responses(send_webhook):
    r = send_webhook("customer.registered", GOOD, signature="sha256=bad")
    assert "test-webhook-secret" not in r.content.decode()


def test_secret_looking_payload_fields_are_redacted_before_storage(send_webhook):
    send_webhook("customer.registered", {**GOOD, "api_key": "super-secret-value"})
    stored = Execution.objects.get().payload
    assert stored["api_key"] == "[REDACTED]" and "super-secret-value" not in json.dumps(stored)
