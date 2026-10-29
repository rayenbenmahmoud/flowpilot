import json
import time

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient

from automation.models import IntegrationSetting, Workflow
from automation.templates_catalog import BY_KEY
from automation.webhook_auth import sign

# Engine/API tests use transaction=True so Celery's on_commit dispatch really runs.
pytestmark = pytest.mark.django_db(transaction=True)

WEBHOOK_SECRET = "test-webhook-secret"


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user("tester", password="pw-for-tests-123", is_staff=True)


@pytest.fixture
def api(user):
    from rest_framework.authtoken.models import Token

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=user).key}")
    return client


@pytest.fixture
def anon():
    return APIClient()


@pytest.fixture
def make_workflow(db):
    def _make(template_key: str, status: str = "active", **overrides) -> Workflow:
        t = BY_KEY[template_key]
        data = {
            k: json.loads(json.dumps(t[k]))
            for k in ("name", "description", "trigger_event", "match_mode", "conditions", "actions")
        }
        return Workflow.objects.create(template_key=template_key, status=status, **{**data, **overrides})

    return _make


@pytest.fixture
def send_webhook(anon):
    def _send(
        event: str,
        payload: dict,
        *,
        key: str | None = "evt-1",
        secret: str = WEBHOOK_SECRET,
        timestamp: int | None = None,
        raw: bytes | None = None,
        signature: str | None = None,
        headers: dict | None = None,
    ):
        body = raw if raw is not None else json.dumps(payload).encode()
        ts = str(timestamp if timestamp is not None else int(time.time()))
        extra = {"HTTP_X_FLOWPILOT_TIMESTAMP": ts, "HTTP_X_FLOWPILOT_SIGNATURE": signature or sign(secret, ts, body)}
        if key:
            extra["HTTP_IDEMPOTENCY_KEY"] = key
        for name, value in (headers or {}).items():
            extra[name] = value
        return anon.post(f"/api/v1/webhooks/{event}/", data=body, content_type="application/json", **extra)

    return _send


@pytest.fixture
def integration_rows(db):
    from automation.integrations.registry import ensure_settings_rows

    ensure_settings_rows()
    return IntegrationSetting.objects.all()
