import json

import pytest
import requests
import responses
from django.core import mail

from automation.integrations.base import AdapterError, http_call
from automation.integrations.email import EmailAdapter
from automation.integrations.n8n import N8nAdapter
from automation.models import Execution

pytestmark = pytest.mark.django_db(transaction=True)
URL = "https://n8n.test/webhook/flowpilot-order"


@pytest.fixture
def live(settings, integration_rows):
    settings.FLOWPILOT_DEMO_MODE = False
    settings.FLOWPILOT_N8N_BASE_URL = "https://n8n.test"
    settings.FLOWPILOT_N8N_WEBHOOK_SECRET = "n8n-secret-value-123"
    settings.FLOWPILOT_EXTERNAL_API_BASE_URL = "https://api.partner.test"
    settings.FLOWPILOT_EXTERNAL_API_KEY = "partner-key-value-456"
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    return settings


class TestHttpCall:
    @responses.activate
    def test_retries_5xx_up_to_the_limit_then_fails(self):
        responses.add(responses.POST, URL, status=503)
        sleeps = []
        with pytest.raises(AdapterError) as err:
            http_call("POST", URL, headers={}, json_body={}, timeout=2, max_attempts=3, sleep=sleeps.append)
        assert len(responses.calls) == 3 and err.value.code == "http_503" and err.value.retryable
        assert sleeps == [0.5, 1.0]  # bounded exponential backoff, no sleep after the last attempt

    @responses.activate
    def test_recovers_after_a_transient_error(self):
        responses.add(responses.POST, URL, status=502)
        responses.add(responses.POST, URL, status=200, json={"ok": True})
        assert (
            http_call(
                "POST", URL, headers={}, json_body={}, timeout=2, max_attempts=2, sleep=lambda s: None
            ).status_code
            == 200
        )

    @responses.activate
    def test_4xx_is_not_retried(self):
        responses.add(responses.POST, URL, status=400)
        with pytest.raises(AdapterError) as err:
            http_call("POST", URL, headers={}, json_body={}, timeout=2, max_attempts=3, sleep=lambda s: None)
        assert len(responses.calls) == 1 and not err.value.retryable

    @responses.activate
    def test_timeout_is_reported_clearly(self):
        responses.add(responses.POST, URL, body=requests.Timeout())
        with pytest.raises(AdapterError) as err:
            http_call("POST", URL, headers={}, json_body={}, timeout=2, max_attempts=1, sleep=lambda s: None)
        assert err.value.code == "timeout" and "2 seconds" in err.value.message

    @responses.activate
    def test_redirects_are_not_followed(self):
        responses.add(responses.POST, URL, status=302, headers={"Location": "http://169.254.169.254/"})
        with pytest.raises(AdapterError) as err:
            http_call("POST", URL, headers={}, json_body={}, timeout=2, max_attempts=1)
        assert err.value.code == "unexpected_redirect" and len(responses.calls) == 1


class TestN8nLive:
    @responses.activate
    def test_sends_secret_header_and_idempotency_key(self, live):
        responses.add(responses.POST, URL, status=200)
        result = N8nAdapter().trigger(
            path="flowpilot-order", body={"order_id": "O1"}, idempotency_key="root:0:trigger_n8n"
        )
        sent = responses.calls[0].request
        assert result["mode"] == "live" and sent.headers["X-FlowPilot-Secret"] == "n8n-secret-value-123"
        assert sent.headers["Idempotency-Key"] == "root:0:trigger_n8n" and json.loads(sent.body) == {"order_id": "O1"}

    def test_not_configured_message_names_the_variables(self, live):
        live.FLOWPILOT_N8N_BASE_URL = ""
        live.FLOWPILOT_N8N_WEBHOOK_SECRET = ""
        with pytest.raises(AdapterError) as err:
            N8nAdapter().trigger(path="x", body={})
        assert err.value.code == "not_configured" and "FLOWPILOT_N8N_BASE_URL" in err.value.message

    def test_path_cannot_escape_the_webhook_prefix(self, live):
        for bad in ("../admin", "a b", "x?y=1", "http://evil.test"):
            with pytest.raises(AdapterError) as err:
                N8nAdapter().trigger(path=bad, body={})
            assert err.value.code == "invalid_path"

    @responses.activate
    def test_failure_message_never_contains_the_secret(self, live):
        responses.add(responses.POST, URL, status=500)
        with pytest.raises(AdapterError) as err:
            N8nAdapter().trigger(path="flowpilot-order", body={})
        assert "n8n-secret-value-123" not in err.value.message

    @responses.activate
    def test_workflow_run_with_live_n8n_outage_fails_cleanly_and_is_retryable(self, live, make_workflow):
        from automation.engine.runner import dispatch_event

        responses.add(responses.POST, URL, body=requests.ConnectionError())
        make_workflow("order-n8n-handoff")
        [item] = dispatch_event("order.created", {"order_id": "O1", "total": 1}, source="webhook", idempotency_key="e")
        item.execution.refresh_from_db()
        assert item.execution.status == "failed" and item.execution.retryable
        assert len(responses.calls) == live.FLOWPILOT_ADAPTER_MAX_ATTEMPTS  # bounded, not infinite


class TestEmailLive:
    def test_sends_through_the_configured_backend(self, live):
        result = EmailAdapter().send(to="a@example.com", subject="Hi\r\nBcc: x@evil.test", body="Hello")
        assert result["mode"] == "live" and len(mail.outbox) == 1
        assert "\n" not in mail.outbox[0].subject and mail.outbox[0].to == ["a@example.com"]

    def test_invalid_recipient(self, live):
        with pytest.raises(AdapterError) as err:
            EmailAdapter().send(to="not-an-email", subject="s", body="b")
        assert err.value.code == "invalid_recipient"


class TestIntegrationsApi:
    def test_demo_mode_status_is_clearly_simulated(self, api, integration_rows):
        data = api.get("/api/v1/integrations/").json()
        assert {i["key"] for i in data} == {"email", "n8n", "http"}
        assert all(i["state"] == "simulated" and i["mode"] == "demo" for i in data)

    def test_secret_values_never_leave_the_server(self, api, live):
        body = api.get("/api/v1/integrations/").content.decode()
        for secret in ("n8n-secret-value-123", "partner-key-value-456", "test-webhook-secret"):
            assert secret not in body
        n8n = next(i for i in json.loads(body) if i["key"] == "n8n")
        assert n8n["secrets"] == [{"name": "FLOWPILOT_N8N_WEBHOOK_SECRET", "is_set": True}]

    def test_live_is_not_claimed_until_a_live_test_passes(self, api, live):
        n8n = lambda: next(i for i in api.get("/api/v1/integrations/").json() if i["key"] == "n8n")  # noqa: E731
        assert n8n()["state"] == "untested"
        with responses.RequestsMock() as rsps:
            rsps.add(responses.GET, "https://n8n.test/healthz", status=200)
            assert api.post("/api/v1/integrations/n8n/test/").json()["result"]["ok"] is True
        assert n8n()["state"] == "connected"
        with responses.RequestsMock() as rsps:
            rsps.add(responses.GET, "https://n8n.test/healthz", status=503)
            assert api.post("/api/v1/integrations/n8n/test/").json()["result"]["ok"] is False
        assert n8n()["state"] == "error"

    def test_live_unconfigured_reports_missing_env(self, api, live):
        live.FLOWPILOT_EXTERNAL_API_KEY = ""
        http = next(i for i in api.get("/api/v1/integrations/").json() if i["key"] == "http")
        assert http["state"] == "not_configured" and http["missing_env"] == ["FLOWPILOT_EXTERNAL_API_KEY"]

    def test_demo_test_button_never_reports_connected(self, api, integration_rows):
        r = api.post("/api/v1/integrations/n8n/test/").json()
        assert r["result"]["mode"] == "demo" and "Simulated" in r["result"]["message"]
        assert r["integration"]["state"] == "simulated"

    def test_update_validates_and_rejects_secrets_or_urls(self, api, integration_rows):
        ok = api.patch("/api/v1/integrations/n8n/", {"settings": {"timeout_seconds": 8}}, format="json")
        assert ok.status_code == 200 and ok.json()["settings"]["timeout_seconds"] == 8
        assert (
            api.patch("/api/v1/integrations/n8n/", {"settings": {"timeout_seconds": 999}}, format="json").status_code
            == 400
        )
        sneaky = api.patch(
            "/api/v1/integrations/n8n/",
            {"settings": {"base_url": "http://169.254.169.254", "api_key": "x"}},
            format="json",
        )
        assert sneaky.status_code == 400 and set(sneaky.json()["error"]["details"]) == {"base_url", "api_key"}
        assert api.get("/api/v1/integrations/nope/").status_code == 404

    def test_disabled_integration_fails_workflows_with_a_fix_hint(self, api, make_workflow, integration_rows):
        from automation.engine.runner import dispatch_event

        api.patch("/api/v1/integrations/email/", {"enabled": False}, format="json")
        make_workflow("welcome-email")
        [item] = dispatch_event(
            "customer.registered",
            {"customer_id": "c", "email": "a@example.com", "name": "A"},
            source="webhook",
            idempotency_key="z",
        )
        item.execution.refresh_from_db()
        assert (
            item.execution.error_code == "integration_disabled" and "Integrations page" in item.execution.error_message
        )
        assert Execution.objects.filter(status="failed").count() == 1
