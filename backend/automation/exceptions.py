from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    """Every error leaves the API as {"error": {"code", "message", "details"?}}."""
    response = exception_handler(exc, context)
    if response is None:
        return None
    data = response.data
    code = getattr(exc, "default_code", "error")
    details = getattr(exc, "details", None)
    if isinstance(data, dict) and "detail" in data and len(data) == 1:
        message = str(data["detail"])
        code = getattr(data["detail"], "code", code)
    elif isinstance(data, dict):
        message, details = "The request contains invalid data.", data
        code = "validation_error"
    elif isinstance(data, list):
        message, details, code = "The request contains invalid data.", {"non_field_errors": data}, "validation_error"
    else:
        message = str(data)
    body: dict = {"code": str(code), "message": message}
    if details:
        body["details"] = details
    return Response({"error": body}, status=response.status_code, headers=dict(response.items()))


class ApiError(APIException):
    """Raise anywhere for a clean, coded error response."""

    def __init__(self, status: int, code: str, message: str, details: dict | None = None):
        self.status_code = status
        self.details = details
        super().__init__(detail=message, code=code)
