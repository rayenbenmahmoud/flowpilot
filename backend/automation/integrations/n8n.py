import re
from typing import Any

from django.conf import settings

from .base import AdapterError, BaseAdapter, SettingSpec, http_call

_PATH = re.compile(r"^[A-Za-z0-9_\-/]{1,100}$")


class N8nAdapter(BaseAdapter):
    """Hands an event to an n8n workflow through its production webhook URL.

    The base URL and shared secret come from the environment, never from the UI or from
    workflow configuration, so a workflow author cannot point FlowPilot at arbitrary hosts."""

    key = "n8n"
    label = "n8n webhooks"
    description = "Triggers n8n workflows (CRM sync, Slack posts, spreadsheets) with the event data."
    secret_envs = ("FLOWPILOT_N8N_WEBHOOK_SECRET",)
    editable = {"timeout_seconds": SettingSpec("Timeout (seconds)", "int", 1, 30, 5)}

    def missing_config(self) -> list[str]:
        return [
            name
            for name, value in (
                ("FLOWPILOT_N8N_BASE_URL", settings.FLOWPILOT_N8N_BASE_URL),
                ("FLOWPILOT_N8N_WEBHOOK_SECRET", settings.FLOWPILOT_N8N_WEBHOOK_SECRET),
            )
            if not value
        ]

    def trigger(self, *, path: str, body: Any, idempotency_key: str = "") -> dict[str, Any]:
        self.ensure_ready()
        if not _PATH.match(path):
            raise AdapterError(
                "invalid_path", "The n8n webhook path may only contain letters, numbers, '-', '_' and '/'."
            )
        if self.demo:
            if path == "simulate-outage":
                raise AdapterError(
                    "connection_error",
                    "Simulated outage: n8n is not reachable. A retry may succeed once it is back.",
                    True,
                )
            return {"mode": "demo", "status_code": 200, "path": path, "accepted": True}
        url = f"{settings.FLOWPILOT_N8N_BASE_URL.rstrip('/')}/webhook/{path.strip('/')}"
        response = http_call(
            "POST",
            url,
            headers={"X-FlowPilot-Secret": settings.FLOWPILOT_N8N_WEBHOOK_SECRET, "Idempotency-Key": idempotency_key},
            json_body=body,
            timeout=self.timeout(),
            max_attempts=settings.FLOWPILOT_ADAPTER_MAX_ATTEMPTS,
        )
        return {"mode": "live", "status_code": response.status_code, "path": path, "accepted": True}

    def test_connection(self) -> dict[str, Any]:
        if self.demo:
            return self.simulated_test()
        if missing := self.missing_config():
            return {"ok": False, "mode": "live", "message": f"Not configured. Set {', '.join(missing)}."}
        try:
            http_call(
                "GET",
                f"{settings.FLOWPILOT_N8N_BASE_URL.rstrip('/')}/healthz",
                headers={},
                json_body=None,
                timeout=self.timeout(),
                max_attempts=1,
            )
        except AdapterError as exc:
            return {"ok": False, "mode": "live", "message": exc.message}
        return {"ok": True, "mode": "live", "message": "n8n answered its health check."}
