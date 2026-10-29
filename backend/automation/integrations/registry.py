"""Lookup, status reporting and connection tests for integrations."""

from typing import Any

from django.conf import settings
from django.utils import timezone

from ..models import IntegrationSetting
from .base import BaseAdapter
from .email import EmailAdapter
from .http import HttpAdapter
from .n8n import N8nAdapter

ADAPTERS: dict[str, type[BaseAdapter]] = {a.key: a for a in (EmailAdapter, N8nAdapter, HttpAdapter)}

STATE_LABELS = {
    "simulated": "Simulated (demo mode)",
    "disabled": "Turned off",
    "not_configured": "Not configured",
    "untested": "Configured, not tested",
    "connected": "Connected (live test passed)",
    "error": "Last live test failed",
}


def get_adapter(key: str) -> BaseAdapter:
    return ADAPTERS[key]()


def ensure_settings_rows() -> None:
    for key in ADAPTERS:
        IntegrationSetting.objects.get_or_create(key=key)


def integration_status(key: str) -> dict[str, Any]:
    adapter = get_adapter(key)
    setting = adapter._setting or IntegrationSetting(key=key)
    missing = adapter.missing_config()
    if not adapter.enabled:
        state = "disabled"
    elif adapter.demo:
        state = "simulated"
    elif missing:
        state = "not_configured"
    elif setting.last_test_ok is None or setting.last_test_mode != "live":
        state = "untested"
    else:
        state = "connected" if setting.last_test_ok else "error"
    return {
        "key": key,
        "label": adapter.label,
        "description": adapter.description,
        "enabled": adapter.enabled,
        "mode": "demo" if adapter.demo else "live",
        "state": state,
        "state_label": STATE_LABELS[state],
        "missing_env": missing,
        "secrets": [
            {"name": name, "is_set": bool(getattr(settings, _SETTING_FOR_ENV.get(name, ""), ""))}
            for name in adapter.secret_envs
        ],
        "settings": {name: adapter.setting_value(name) for name in adapter.editable},
        "settings_schema": [
            {"name": n, "label": s.label, "kind": s.kind, "minimum": s.minimum, "maximum": s.maximum, "help": s.help}
            for n, s in adapter.editable.items()
        ],
        "last_test": {
            "at": setting.last_tested_at,
            "ok": setting.last_test_ok,
            "mode": setting.last_test_mode,
            "message": setting.last_test_message,
        },
    }


_SETTING_FOR_ENV = {
    "EMAIL_HOST_PASSWORD": "EMAIL_HOST_PASSWORD",
    "FLOWPILOT_N8N_WEBHOOK_SECRET": "FLOWPILOT_N8N_WEBHOOK_SECRET",
    "FLOWPILOT_EXTERNAL_API_KEY": "FLOWPILOT_EXTERNAL_API_KEY",
}


def run_connection_test(key: str) -> dict[str, Any]:
    adapter = get_adapter(key)
    result = adapter.test_connection()
    setting, _ = IntegrationSetting.objects.get_or_create(key=key)
    setting.last_tested_at = timezone.now()
    setting.last_test_ok = result["ok"]
    setting.last_test_mode = result["mode"]
    setting.last_test_message = result["message"][:300]
    setting.save()
    return result
