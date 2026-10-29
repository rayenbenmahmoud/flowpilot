"""Shared adapter plumbing: error type, bounded HTTP calls, demo/live mode, status reporting."""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import requests
from django.conf import settings

from ..models import IntegrationSetting


class AdapterError(Exception):
    """A failure with a stable machine code and a message safe to show to users."""

    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


@dataclass(frozen=True)
class SettingSpec:
    label: str
    kind: str  # "int" | "email"
    minimum: int = 0
    maximum: int = 0
    default: Any = None
    help: str = ""


def http_call(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    json_body: Any,
    timeout: int,
    max_attempts: int,
    sleep: Callable[[float], None] = time.sleep,
) -> requests.Response:
    """One external HTTP call with a hard timeout and a *bounded* number of attempts.

    Network errors, timeouts and 5xx responses are retried with exponential backoff up to
    ``max_attempts``. 4xx responses are never retried (the request itself is wrong).
    Redirects are not followed. Header values are never included in error messages.
    """
    last: AdapterError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.request(
                method, url, headers=headers, json=json_body, timeout=timeout, allow_redirects=False
            )
        except requests.Timeout:
            last = AdapterError("timeout", f"The service did not answer within {timeout} seconds.", True)
        except requests.ConnectionError:
            last = AdapterError(
                "connection_error", "Could not connect to the service. Is it running and reachable?", True
            )
        except requests.RequestException:
            raise AdapterError("request_error", "The request could not be sent.", False) from None
        else:
            status = response.status_code
            if status < 300:
                return response
            if 300 <= status < 400:
                raise AdapterError(
                    "unexpected_redirect",
                    f"The service answered with a redirect (HTTP {status}); redirects are not followed.",
                )
            if status < 500:
                raise AdapterError(
                    f"http_{status}", f"The service rejected the request (HTTP {status}).", status in {408, 429}
                )
            last = AdapterError(f"http_{status}", f"The service failed with HTTP {status}.", True)
        if attempt < max_attempts:
            sleep(min(0.5 * 2 ** (attempt - 1), 4))
    raise last or AdapterError("request_error", "No request attempt was made.")


class BaseAdapter:
    key = ""
    label = ""
    description = ""
    secret_envs: tuple[str, ...] = ()  # env var *names* shown in the UI, never their values
    editable: dict[str, SettingSpec] = {}

    def __init__(self) -> None:
        self._setting = IntegrationSetting.objects.filter(key=self.key).first()

    # -- mode & configuration -------------------------------------------------
    @property
    def demo(self) -> bool:
        return bool(settings.FLOWPILOT_DEMO_MODE)

    @property
    def enabled(self) -> bool:
        return self._setting.enabled if self._setting else True

    def setting_value(self, name: str) -> Any:
        stored = (self._setting.settings if self._setting else {}).get(name)
        return stored if stored not in (None, "") else self.editable[name].default

    def timeout(self) -> int:
        spec = self.editable.get("timeout_seconds")
        value = int(self.setting_value("timeout_seconds")) if spec else settings.FLOWPILOT_ADAPTER_TIMEOUT
        return max(1, min(value, 30))

    def missing_config(self) -> list[str]:
        """Names of required environment variables that are not set (live mode only)."""
        return []

    def ensure_ready(self) -> None:
        if not self.enabled:
            raise AdapterError(
                "integration_disabled",
                f"The {self.label} integration is turned off. Turn it on from the Integrations page.",
            )
        if not self.demo and (missing := self.missing_config()):
            raise AdapterError(
                "not_configured",
                f"{self.label} is not configured. Set {', '.join(missing)} in the server environment.",
            )

    def test_connection(self) -> dict[str, Any]:  # pragma: no cover - overridden
        raise NotImplementedError

    def simulated_test(self) -> dict[str, Any]:
        return {
            "ok": True,
            "mode": "demo",
            "message": "Simulated check. Demo mode is on, so no real connection was made.",
        }
