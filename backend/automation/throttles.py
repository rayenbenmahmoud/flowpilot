from rest_framework.throttling import SimpleRateThrottle


class WebhookThrottle(SimpleRateThrottle):
    """Per-client-IP rate limit for the public webhook endpoint (FLOWPILOT_WEBHOOK_RATE)."""

    scope = "webhook"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class LoginThrottle(SimpleRateThrottle):
    scope = "login"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}
