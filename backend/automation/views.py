import json
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate
from django.db import connection
from django.db.models import Count, Max, OuterRef, Q, Subquery
from django.db.models.functions import TruncDate
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import demo
from .engine.actions import ACTIONS
from .engine.conditions import OPERATORS
from .engine.runner import RetryBlocked, create_execution, dispatch_event, enqueue, retry_execution
from .events import EVENT_CATALOG, RESERVED_EVENTS, validate_event_payload
from .exceptions import ApiError
from .filters import ExecutionFilter, WorkflowFilter
from .integrations.registry import ADAPTERS, integration_status, run_connection_test
from .models import (
    Execution,
    IntegrationSetting,
    Notification,
    OutboxMessage,
    TicketAssignment,
    Workflow,
)
from .serializers import (
    ExecutionDetailSerializer,
    ExecutionListSerializer,
    FromTemplateSerializer,
    IntegrationUpdateSerializer,
    LoginSerializer,
    NotificationSerializer,
    OutboxMessageSerializer,
    RunWorkflowSerializer,
    TicketAssignmentSerializer,
    WebhookResultSerializer,
    WorkflowSerializer,
)
from .templates_catalog import BY_KEY as TEMPLATE_BY_KEY
from .templates_catalog import TEMPLATES
from .throttles import LoginThrottle, WebhookThrottle
from .webhook_auth import verify_signature

VERSION = "1.0.0"


# ------------------------------------------------------------------ public / session
class ConfigView(APIView):
    """Public, non-sensitive runtime info so the UI can show the demo-mode banner before login."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(responses=OpenApiTypes.OBJECT, auth=[])
    def get(self, request):
        return Response({"app": "FlowPilot", "version": VERSION, "demo_mode": settings.FLOWPILOT_DEMO_MODE})


class HealthView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(responses=OpenApiTypes.OBJECT, auth=[])
    def get(self, request):
        try:
            connection.ensure_connection()
            db = "ok"
        except Exception:  # noqa: BLE001
            db = "unavailable"
        body = {
            "status": "ok" if db == "ok" else "degraded",
            "database": db,
            "task_mode": "inline" if settings.CELERY_TASK_ALWAYS_EAGER else "celery",
        }
        return Response(body, status=200 if db == "ok" else 503)


class LoginView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [LoginThrottle]

    @extend_schema(request=LoginSerializer, responses=OpenApiTypes.OBJECT, auth=[])
    def post(self, request):
        data = LoginSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = authenticate(username=data.validated_data["username"], password=data.validated_data["password"])
        if user is None:
            raise ApiError(401, "invalid_credentials", "The username or password is incorrect.")
        Token.objects.filter(user=user).delete()  # one active session per user
        token = Token.objects.create(user=user)
        return Response({"token": token.key, "username": user.get_username()})


class LogoutView(APIView):
    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(status=204)


class MeView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response({"username": request.user.get_username(), "demo_mode": settings.FLOWPILOT_DEMO_MODE})


class MetaView(APIView):
    """Everything the workflow editor needs: events, operators, action types and templates."""

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(
            {
                "events": [
                    {
                        "key": k,
                        "label": v["label"],
                        "description": v["description"],
                        "reserved": k in RESERVED_EVENTS,
                        "fields": [{"name": n, **r} for n, r in v["fields"].items()],
                        "sample": v["sample"],
                    }
                    for k, v in EVENT_CATALOG.items()
                ],
                "operators": [{"key": k, "label": v} for k, v in OPERATORS.items()],
                "actions": [
                    {
                        "type": s.type,
                        "label": s.label,
                        "description": s.description,
                        "required": list(s.required),
                        "example": s.example,
                    }
                    for s in ACTIONS.values()
                ],
                "templates": [{k: t[k] for k in ("key", "name", "description", "trigger_event")} for t in TEMPLATES],
            }
        )


# ------------------------------------------------------------------ dashboard
class DashboardView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        wf = Workflow.objects.aggregate(
            total=Count("id", filter=~Q(status="archived")),
            active=Count("id", filter=Q(status="active")),
            disabled=Count("id", filter=Q(status="disabled")),
            archived=Count("id", filter=Q(status="archived")),
        )
        ex = Execution.objects.aggregate(
            total=Count("id"),
            success=Count("id", filter=Q(status="success")),
            failed=Count("id", filter=Q(status="failed")),
            skipped=Count("id", filter=Q(status="skipped")),
            in_progress=Count("id", filter=Q(status__in=["pending", "running"])),
        )
        now = timezone.now()
        last_day = Execution.objects.filter(created_at__gte=now - timedelta(hours=24)).aggregate(
            success=Count("id", filter=Q(status="success")), failed=Count("id", filter=Q(status="failed"))
        )
        finished = ex["success"] + ex["failed"]
        first_day = (now - timedelta(days=6)).date()
        rows = {
            r["day"]: r
            for r in Execution.objects.filter(created_at__date__gte=first_day)
            .annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(
                success=Count("id", filter=Q(status="success")),
                failed=Count("id", filter=Q(status="failed")),
                other=Count("id", filter=~Q(status__in=["success", "failed"])),
            )
        }
        daily = []
        for offset in range(7):
            day = first_day + timedelta(days=offset)
            row = rows.get(day, {})
            daily.append(
                {
                    "date": day.isoformat(),
                    "success": row.get("success", 0),
                    "failed": row.get("failed", 0),
                    "other": row.get("other", 0),
                }
            )
        recent = Execution.objects.order_by("-created_at")[:8]
        return Response(
            {
                "workflows": wf,
                "executions": ex,
                "last_24h": last_day,
                "success_rate": round(ex["success"] / finished * 100, 1) if finished else None,
                "needs_attention": Execution.objects.filter(status="failed", retries__isnull=True).count(),
                "daily": daily,
                "recent": ExecutionListSerializer(recent, many=True).data,
            }
        )


# ------------------------------------------------------------------ workflows
class WorkflowViewSet(viewsets.ModelViewSet):
    serializer_class = WorkflowSerializer
    filterset_class = WorkflowFilter
    http_method_names = ["get", "post", "put", "patch", "head", "options"]  # no DELETE: archive instead

    def get_queryset(self):
        latest = Execution.objects.filter(workflow=OuterRef("pk")).order_by("-created_at")
        return Workflow.objects.annotate(
            runs_total=Count("executions"),
            runs_success=Count("executions", filter=Q(executions__status="success")),
            runs_failed=Count("executions", filter=Q(executions__status="failed")),
            last_run_at=Max("executions__created_at"),
            last_status=Subquery(latest.values("status")[:1]),
        ).order_by("name")

    def _fresh(self, workflow):  # re-read with annotations for the response
        return self.get_queryset().get(pk=workflow.pk)

    def perform_create(self, serializer):
        serializer.save(status=serializer.validated_data.get("status", Workflow.Status.DISABLED))
        serializer.instance = self._fresh(serializer.instance)

    def perform_update(self, serializer):
        serializer.save()
        serializer.instance = self._fresh(serializer.instance)

    def _set_status(self, workflow, new_status, allowed_from):
        if workflow.status != new_status:
            if workflow.status not in allowed_from:
                raise ApiError(409, "invalid_transition", f"A {workflow.status} workflow cannot become {new_status}.")
            workflow.status = new_status
            workflow.archived_at = timezone.now() if new_status == Workflow.Status.ARCHIVED else None
            workflow.save(update_fields=["status", "archived_at", "updated_at"])
        return Response(self.get_serializer(self._fresh(workflow)).data)

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def enable(self, request, pk=None):
        return self._set_status(self.get_object(), Workflow.Status.ACTIVE, {Workflow.Status.DISABLED})

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def disable(self, request, pk=None):
        return self._set_status(self.get_object(), Workflow.Status.DISABLED, {Workflow.Status.ACTIVE})

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        return self._set_status(
            self.get_object(), Workflow.Status.ARCHIVED, {Workflow.Status.ACTIVE, Workflow.Status.DISABLED}
        )

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        """Bring an archived workflow back as *disabled* (re-enable it deliberately)."""
        return self._set_status(self.get_object(), Workflow.Status.DISABLED, {Workflow.Status.ARCHIVED})

    @extend_schema(
        request=RunWorkflowSerializer,
        responses=ExecutionListSerializer,
        parameters=[OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=False)],
    )
    @action(detail=True, methods=["post"])
    def run(self, request, pk=None):
        """Run this workflow once with a test payload (active workflows only)."""
        workflow = self.get_object()
        if workflow.status != Workflow.Status.ACTIVE:
            raise ApiError(409, "workflow_not_active", "Enable the workflow before running it.")
        body = RunWorkflowSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        payload = body.validated_data["payload"]
        if workflow.trigger_event in EVENT_CATALOG and (
            problems := validate_event_payload(workflow.trigger_event, payload)
        ):
            raise ApiError(
                400, "invalid_payload", "The test payload does not match the trigger event.", {"payload": problems}
            )
        key = request.headers.get("Idempotency-Key", "").strip()[:200] or f"manual:{uuid.uuid4()}"
        existing = Execution.objects.filter(workflow=workflow, idempotency_key=key).first()
        if existing:
            return Response(ExecutionListSerializer(existing).data, status=200)
        execution = create_execution(
            workflow, workflow.trigger_event, payload, source=Execution.Source.MANUAL, idempotency_key=key
        )
        enqueue(execution)
        execution.refresh_from_db()
        return Response(ExecutionListSerializer(execution).data, status=202)

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def templates(self, request):
        return Response(TEMPLATES)

    @extend_schema(request=FromTemplateSerializer, responses=WorkflowSerializer)
    @action(detail=False, methods=["post"], url_path="from-template")
    def from_template(self, request):
        body = FromTemplateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        template = TEMPLATE_BY_KEY.get(body.validated_data["template_key"])
        if not template:
            raise ApiError(404, "unknown_template", "No template with that key.")
        workflow = Workflow.objects.create(
            name=body.validated_data.get("name") or template["name"],
            description=template["description"],
            template_key=template["key"],
            trigger_event=template["trigger_event"],
            match_mode=template["match_mode"],
            conditions=json.loads(json.dumps(template["conditions"])),
            actions=json.loads(json.dumps(template["actions"])),
            status=Workflow.Status.DISABLED,
        )
        return Response(self.get_serializer(self._fresh(workflow)).data, status=201)


# ------------------------------------------------------------------ executions & outputs
class ExecutionViewSet(viewsets.ReadOnlyModelViewSet):
    filterset_class = ExecutionFilter
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    ordering_fields = ["created_at", "duration_ms", "status", "workflow_name"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = Execution.objects.select_related("workflow")
        return qs.prefetch_related("logs", "retries") if self.action == "retrieve" else qs

    def get_serializer_class(self):
        return ExecutionDetailSerializer if self.action == "retrieve" else ExecutionListSerializer

    @extend_schema(request=None, responses={202: ExecutionListSerializer})
    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        """Create attempt N+1 of a failed execution. Completed steps are not repeated."""
        self.get_object()  # 404 + permission check
        try:
            retry = retry_execution(pk)
        except RetryBlocked as exc:
            raise ApiError(409, exc.code, exc.message) from None
        retry.refresh_from_db()
        return Response(ExecutionListSerializer(retry).data, status=202)


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    filterset_fields = ["kind", "severity"]


class OutboxViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = OutboxMessage.objects.all()
    serializer_class = OutboxMessageSerializer
    filterset_fields = ["mode", "status"]


class AssignmentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = TicketAssignment.objects.all()
    serializer_class = TicketAssignmentSerializer
    filterset_fields = ["team", "priority"]


# ------------------------------------------------------------------ integrations
def _adapter_or_404(key: str):
    if key not in ADAPTERS:
        raise ApiError(404, "unknown_integration", "No integration with that key.")
    return ADAPTERS[key]


class IntegrationListView(APIView):
    @extend_schema(operation_id="integrations_list", responses=OpenApiTypes.OBJECT)
    def get(self, request):
        for key in ADAPTERS:
            IntegrationSetting.objects.get_or_create(key=key)
        return Response([integration_status(key) for key in ADAPTERS])


class IntegrationDetailView(APIView):
    @extend_schema(operation_id="integrations_retrieve", responses=OpenApiTypes.OBJECT)
    def get(self, request, key):
        _adapter_or_404(key)
        return Response(integration_status(key))

    @extend_schema(request=IntegrationUpdateSerializer, responses=OpenApiTypes.OBJECT)
    def patch(self, request, key):
        adapter_cls = _adapter_or_404(key)
        body = IntegrationUpdateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        setting, _ = IntegrationSetting.objects.get_or_create(key=key)
        errors: dict[str, str] = {}
        incoming = body.validated_data.get("settings", {})
        clean = dict(setting.settings)
        for name, value in incoming.items():
            spec = adapter_cls.editable.get(name)
            if spec is None:
                errors[name] = (
                    "This setting cannot be changed here. Secrets and URLs are set through environment variables."
                )
            elif spec.kind == "int":
                if isinstance(value, bool) or not isinstance(value, int) or not spec.minimum <= value <= spec.maximum:
                    errors[name] = f"Enter a whole number from {spec.minimum} to {spec.maximum}."
                else:
                    clean[name] = value
            elif spec.kind == "email":
                from email.utils import parseaddr

                from django.core.exceptions import ValidationError
                from django.core.validators import validate_email

                try:
                    validate_email(parseaddr(str(value))[1])
                    clean[name] = str(value)[:200].replace("\n", " ")
                except ValidationError:
                    errors[name] = "Enter a valid email address."
        if errors:
            raise ApiError(400, "validation_error", "Some settings are invalid.", errors)
        setting.settings = clean
        if "enabled" in body.validated_data:
            setting.enabled = body.validated_data["enabled"]
        setting.save()
        return Response(integration_status(key))


class IntegrationTestView(APIView):
    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request, key):
        _adapter_or_404(key)
        result = run_connection_test(key)
        return Response({"result": result, "integration": integration_status(key)})


# ------------------------------------------------------------------ demo
class DemoGuardMixin:
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not settings.FLOWPILOT_DEMO_MODE:
            raise ApiError(403, "demo_disabled", "Demo tools are only available while FLOWPILOT_DEMO_MODE is on.")


class DemoScenarioListView(DemoGuardMixin, APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(demo.scenario_catalog())


class DemoScenarioRunView(DemoGuardMixin, APIView):
    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request, key):
        if key not in demo.BY_KEY:
            raise ApiError(404, "unknown_scenario", "No demo scenario with that key.")
        return Response(demo.run_scenario(key), status=202)


class DemoResetView(DemoGuardMixin, APIView):
    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        return Response(demo.reset_demo())


# ------------------------------------------------------------------ webhook
class WebhookView(APIView):
    """Receive an event from an external system (n8n, a shop backend, ...).

    Order of checks: rate limit -> size -> signature -> event type -> JSON -> payload schema ->
    idempotency key. Nothing is executed unless every check passes."""

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [WebhookThrottle]

    @extend_schema(
        request=OpenApiTypes.OBJECT,
        responses={200: WebhookResultSerializer, 202: WebhookResultSerializer},
        auth=[],
        parameters=[
            OpenApiParameter("X-FlowPilot-Timestamp", str, OpenApiParameter.HEADER, required=True),
            OpenApiParameter(
                "X-FlowPilot-Signature",
                str,
                OpenApiParameter.HEADER,
                required=True,
                description="sha256=<hex HMAC of '<timestamp>.<raw body>'>",
            ),
            OpenApiParameter(
                "Idempotency-Key",
                str,
                OpenApiParameter.HEADER,
                required=False,
                description="Or send event_id in the body.",
            ),
        ],
    )
    def post(self, request, event_type):
        limit = settings.FLOWPILOT_WEBHOOK_MAX_BYTES
        try:
            declared = int(request.META.get("CONTENT_LENGTH") or 0)
        except ValueError:
            declared = 0
        if declared > limit:
            raise ApiError(413, "payload_too_large", f"The request body may be at most {limit} bytes.")
        body = request.body
        if len(body) > limit:
            raise ApiError(413, "payload_too_large", f"The request body may be at most {limit} bytes.")
        verify_signature(
            secret=settings.FLOWPILOT_WEBHOOK_SECRET,
            timestamp=request.headers.get("X-FlowPilot-Timestamp"),
            signature=request.headers.get("X-FlowPilot-Signature"),
            body=body,
            tolerance=settings.FLOWPILOT_WEBHOOK_TOLERANCE_SECONDS,
        )
        if event_type in RESERVED_EVENTS:
            raise ApiError(400, "reserved_event", f"'{event_type}' is generated by FlowPilot and cannot be sent.")
        if event_type not in EVENT_CATALOG:
            raise ApiError(
                404,
                "unknown_event",
                f"Unknown event '{event_type}'. Known events: {', '.join(k for k in EVENT_CATALOG if k not in RESERVED_EVENTS)}.",
            )
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise ApiError(400, "invalid_json", "The request body must be valid UTF-8 JSON.") from None
        if problems := validate_event_payload(event_type, payload):
            raise ApiError(400, "invalid_payload", "The event data is not valid.", {"payload": problems})
        key = (request.headers.get("Idempotency-Key") or str(payload.get("event_id") or "")).strip()
        if not key:
            raise ApiError(
                400,
                "missing_idempotency_key",
                "Send an Idempotency-Key header or an event_id field so duplicate deliveries can be recognised.",
            )
        if len(key) > 200:
            raise ApiError(400, "invalid_idempotency_key", "The idempotency key may be at most 200 characters.")
        items = dispatch_event(event_type, payload, source=Execution.Source.WEBHOOK, idempotency_key=key)
        rows = []
        for item in items:
            item.execution.refresh_from_db()
            rows.append(
                {
                    "id": str(item.execution.id),
                    "workflow_id": str(item.execution.workflow_id),
                    "workflow": item.execution.workflow_name,
                    "status": item.execution.status,
                    "duplicate": item.duplicate,
                }
            )
        all_duplicates = bool(items) and all(i.duplicate for i in items)
        result = {"event": event_type, "idempotency_key": key, "duplicate": all_duplicates, "executions": rows}
        if not items:
            result["message"] = "No active workflow listens to this event."
        return Response(result, status=200 if all_duplicates else 202)
