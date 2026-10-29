import uuid
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage, get_connection
from django.core.validators import validate_email

from .base import AdapterError, BaseAdapter, SettingSpec


class EmailAdapter(BaseAdapter):
    key = "email"
    label = "Email (SMTP)"
    description = "Sends transactional email such as welcome messages."
    secret_envs = ("EMAIL_HOST_PASSWORD",)
    editable = {
        "from_address": SettingSpec(
            "From address", "email", default="FlowPilot <no-reply@example.com>", help="Sender shown to recipients."
        ),
        "timeout_seconds": SettingSpec("Timeout (seconds)", "int", 1, 30, 10),
    }

    def missing_config(self) -> list[str]:
        if settings.EMAIL_BACKEND.endswith("smtp.EmailBackend") and not settings.EMAIL_HOST:
            return ["EMAIL_HOST"]
        return []

    def send(self, *, to: str, subject: str, body: str, attempt: int = 1, idempotency_key: str = "") -> dict[str, Any]:
        self.ensure_ready()
        try:
            validate_email(to)
        except ValidationError:
            raise AdapterError("invalid_recipient", f"'{to}' is not a valid email address.") from None
        subject = " ".join(subject.splitlines())[:200]  # no header injection through newlines
        if self.demo:
            return self._simulate(to, attempt)
        message = EmailMessage(subject, body, from_email=self.setting_value("from_address"), to=[to])
        message.extra_headers["X-FlowPilot-Idempotency-Key"] = idempotency_key
        try:
            message.connection = get_connection(timeout=self.timeout())
            message.send(fail_silently=False)
        except Exception:  # noqa: BLE001 - provider errors vary widely; never leak their text
            raise AdapterError("smtp_error", "The mail server could not deliver the message.", True) from None
        return {"mode": "live", "message_id": f"smtp-{uuid.uuid4().hex[:12]}"}

    def _simulate(self, to: str, attempt: int) -> dict[str, Any]:
        domain = to.rsplit("@", 1)[-1].lower()
        if domain == "bounce.example.com":
            raise AdapterError(
                "recipient_rejected", "Simulated bounce: the mailbox does not exist (permanent failure).", False
            )
        if domain == "flaky.example.com" and attempt == 1:
            raise AdapterError(
                "smtp_timeout", "Simulated SMTP timeout (temporary failure). A retry should succeed.", True
            )
        return {"mode": "demo", "message_id": f"demo-{uuid.uuid4().hex[:12]}"}

    def test_connection(self) -> dict[str, Any]:
        if self.demo:
            return self.simulated_test()
        if missing := self.missing_config():
            return {"ok": False, "mode": "live", "message": f"Not configured. Set {', '.join(missing)}."}
        try:
            connection = get_connection(timeout=self.timeout())
            connection.open()
            connection.close()
        except Exception:  # noqa: BLE001
            return {"ok": False, "mode": "live", "message": "Could not open a connection to the mail server."}
        return {"ok": True, "mode": "live", "message": "Connected to the mail server."}
