import re
from typing import Any

from django.conf import settings

from .base import AdapterError, BaseAdapter, SettingSpec, http_call

_PATH = re.compile(r"^[A-Za-z0-9_\-/.]{1,200}$")


class HttpAdapter(BaseAdapter):
    """Generic JSON-over-HTTPS client for a partner or internal API (CRM, ERP, ...)."""

    key = "http"
    label = "External REST API"
    description = "Calls a partner API with a JSON body and a bearer token."
    secret_envs = ("FLOWPILOT_EXTERNAL_API_KEY",)
    editable = {"timeout_seconds": SettingSpec("Timeout (seconds)", "int", 1, 30, 5)}

    def missing_config(self) -> list[str]:
        return [
            name
            for name, value in (
                ("FLOWPILOT_EXTERNAL_API_BASE_URL", settings.FLOWPILOT_EXTERNAL_API_BASE_URL),
                ("FLOWPILOT_EXTERNAL_API_KEY", settings.FLOWPILOT_EXTERNAL_API_KEY),
            )
            if not value
        ]

    def call(self, *, path: str, body: Any, idempotency_key: str = "") -> dict[str, Any]:
        self.ensure_ready()
        if not _PATH.match(path) or ".." in path:
            raise AdapterError("invalid_path", "The API path contains characters that are not allowed.")
        if self.demo:
            return {"mode": "demo", "status_code": 201, "path": path, "accepted": True}
        url = f"{settings.FLOWPILOT_EXTERNAL_API_BASE_URL.rstrip('/')}/{path.lstrip('/')}"
        response = http_call(
            "POST",
            url,
            headers={
                "Authorization": f"Bearer {settings.FLOWPILOT_EXTERNAL_API_KEY}",
                "Idempotency-Key": idempotency_key,
            },
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
                settings.FLOWPILOT_EXTERNAL_API_BASE_URL,
                headers={"Authorization": f"Bearer {settings.FLOWPILOT_EXTERNAL_API_KEY}"},
                json_body=None,
                timeout=self.timeout(),
                max_attempts=1,
            )
        except AdapterError as exc:
            return {"ok": False, "mode": "live", "message": exc.message}
        return {"ok": True, "mode": "live", "message": "The API answered the test request."}
