from rest_framework import serializers

from .engine.runner import retry_block_reason
from .engine.validation import validate_workflow
from .models import (
    Execution,
    ExecutionLog,
    Notification,
    OutboxMessage,
    TicketAssignment,
    Workflow,
)


class WorkflowSerializer(serializers.ModelSerializer):
    status = serializers.ChoiceField(choices=["active", "disabled"], required=False)
    runs_total = serializers.IntegerField(read_only=True)
    runs_success = serializers.IntegerField(read_only=True)
    runs_failed = serializers.IntegerField(read_only=True)
    last_run_at = serializers.DateTimeField(read_only=True)
    last_status = serializers.CharField(read_only=True)

    class Meta:
        model = Workflow
        fields = [
            "id",
            "name",
            "description",
            "template_key",
            "trigger_event",
            "match_mode",
            "conditions",
            "actions",
            "status",
            "version",
            "created_at",
            "updated_at",
            "archived_at",
            "runs_total",
            "runs_success",
            "runs_failed",
            "last_run_at",
            "last_status",
        ]
        read_only_fields = ["id", "template_key", "version", "created_at", "updated_at", "archived_at"]

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Give the workflow a name.")
        return value

    def validate(self, attrs):
        instance = self.instance
        if instance and instance.status == Workflow.Status.ARCHIVED:
            raise serializers.ValidationError({"status": ["Archived workflows cannot be edited. Restore it first."]})
        pick = lambda f, d: attrs.get(f, getattr(instance, f) if instance else d)  # noqa: E731
        problems = validate_workflow(
            pick("trigger_event", ""), pick("match_mode", "all"), pick("conditions", []), pick("actions", [])
        )
        if problems:
            raise serializers.ValidationError(problems)
        if instance:
            attrs.pop("status", None)  # status changes go through enable/disable/archive
        return attrs

    def update(self, instance, validated_data):
        if any(
            f in validated_data and validated_data[f] != getattr(instance, f)
            for f in ("trigger_event", "match_mode", "conditions", "actions")
        ):
            instance.version += 1
        return super().update(instance, validated_data)


class FromTemplateSerializer(serializers.Serializer):
    template_key = serializers.CharField()
    name = serializers.CharField(required=False, max_length=120)


class RunWorkflowSerializer(serializers.Serializer):
    payload = serializers.DictField()


class ExecutionLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExecutionLog
        fields = ["id", "level", "step", "message", "created_at"]


class ExecutionListSerializer(serializers.ModelSerializer):
    workflow = serializers.UUIDField(source="workflow_id", read_only=True)

    class Meta:
        model = Execution
        fields = [
            "id",
            "workflow",
            "workflow_name",
            "event_type",
            "status",
            "source",
            "attempt",
            "input_summary",
            "error_code",
            "error_message",
            "retryable",
            "created_at",
            "started_at",
            "finished_at",
            "duration_ms",
        ]


class ExecutionDetailSerializer(ExecutionListSerializer):
    logs = ExecutionLogSerializer(many=True, read_only=True)
    retry_of = serializers.UUIDField(source="retry_of_id", read_only=True)
    retried_by = serializers.SerializerMethodField()
    can_retry = serializers.SerializerMethodField()
    retry_blocked_reason = serializers.SerializerMethodField()

    class Meta(ExecutionListSerializer.Meta):
        fields = ExecutionListSerializer.Meta.fields + [
            "root_id",
            "workflow_version",
            "idempotency_key",
            "payload",
            "result",
            "logs",
            "retry_of",
            "retried_by",
            "can_retry",
            "retry_blocked_reason",
        ]

    def get_retried_by(self, obj) -> str | None:
        child = obj.retries.order_by("created_at").first()
        return str(child.id) if child else None

    def get_can_retry(self, obj) -> bool:
        return retry_block_reason(obj) is None

    def get_retry_blocked_reason(self, obj) -> str | None:
        blocked = retry_block_reason(obj)
        return blocked[1] if blocked and obj.status == Execution.Status.FAILED else None


class NotificationSerializer(serializers.ModelSerializer):
    execution = serializers.UUIDField(source="execution_id", read_only=True)

    class Meta:
        model = Notification
        fields = ["id", "kind", "severity", "title", "body", "execution", "created_at"]


class OutboxMessageSerializer(serializers.ModelSerializer):
    execution = serializers.UUIDField(source="execution_id", read_only=True)

    class Meta:
        model = OutboxMessage
        fields = [
            "id",
            "to_address",
            "subject",
            "body",
            "mode",
            "status",
            "provider_message_id",
            "execution",
            "created_at",
        ]


class TicketAssignmentSerializer(serializers.ModelSerializer):
    execution = serializers.UUIDField(source="execution_id", read_only=True)

    class Meta:
        model = TicketAssignment
        fields = [
            "id",
            "ticket_id",
            "subject",
            "priority",
            "category",
            "assignee",
            "team",
            "matched_rule",
            "execution",
            "created_at",
        ]


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class IntegrationUpdateSerializer(serializers.Serializer):
    enabled = serializers.BooleanField(required=False)
    settings = serializers.DictField(required=False)


class WebhookResultSerializer(serializers.Serializer):
    event = serializers.CharField()
    idempotency_key = serializers.CharField()
    duplicate = serializers.BooleanField()
    message = serializers.CharField(required=False)
    executions = serializers.ListField(child=serializers.DictField())
