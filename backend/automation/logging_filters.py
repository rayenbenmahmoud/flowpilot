import logging

from django.conf import settings


class SecretScrubFilter(logging.Filter):
    """Last line of defence: replace any configured secret value found in a log line."""

    def filter(self, record: logging.LogRecord) -> bool:
        secrets = [
            value
            for value in (
                settings.SECRET_KEY,
                settings.FLOWPILOT_WEBHOOK_SECRET,
                settings.FLOWPILOT_N8N_WEBHOOK_SECRET,
                settings.FLOWPILOT_EXTERNAL_API_KEY,
                settings.EMAIL_HOST_PASSWORD,
            )
            if value and len(value) >= 6
        ]
        if secrets:
            message = record.getMessage()
            scrubbed = message
            for secret in secrets:
                scrubbed = scrubbed.replace(secret, "***")
            if scrubbed != message:
                record.msg, record.args = scrubbed, ()
        return True
