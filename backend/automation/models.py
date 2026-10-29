import uuid

from django.db import models
from django.db.models import Q


class Workflow(models.Model):
    """A rule: when ``trigger_event`` arrives and ``conditions`` match, run ``actions`` in order."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        DISABLED = "disabled", "Disabled"
        ARCHIVED = "archived", "Archived"

    class MatchMode(models.TextChoices):
        ALL = "all", "All conditions must match"
        ANY = "any", "Any condition may match"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    template_key = models.CharField(max_length=64, blank=True)
    trigger_event = models.CharField(max_length=80)
    match_mode = models.CharField(max_length=3, choices=MatchMode, default=MatchMode.ALL)
    conditions = models.JSONField(default=list, blank=True)
    actions = models.JSONField(default=list)
    status = models.CharField(max_length=10, choices=Status, default=Status.DISABLED)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["status", "trigger_event"])]

    def __str__(self) -> str:
        return self.name


class Execution(models.Model):
    """One run of one workflow for one event. Retries create a *new* row (attempt + 1)."""

    class Status(models.TextChoices):
        PENDING = "pending", "Queued"
        RUNNING = "running", "Running"
        SUCCESS = "success", "Succeeded"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    class Source(models.TextChoices):
        WEBHOOK = "webhook", "Webhook"
        MANUAL = "manual", "Manual run"
        DEMO = "demo", "Guided demo"
        RETRY = "retry", "Retry"
        SYSTEM = "system", "System event"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name="executions")
    workflow_name = models.CharField(max_length=120)  # snapshot, survives renames
    workflow_version = models.PositiveIntegerField(default=1)
    event_type = models.CharField(max_length=80)
    status = models.CharField(max_length=10, choices=Status, default=Status.PENDING)
    source = models.CharField(max_length=10, choices=Source, default=Source.WEBHOOK)
    idempotency_key = models.CharField(max_length=200, blank=True)
    attempt = models.PositiveSmallIntegerField(default=1)
    root_id = models.UUIDField(db_index=True)  # first attempt of this chain
    retry_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="retries")
    payload = models.JSONField(default=dict)  # secrets redacted before storage
    input_summary = models.CharField(max_length=300, blank=True)
    result = models.JSONField(default=dict, blank=True)
    error_code = models.CharField(max_length=60, blank=True)
    error_message = models.TextField(blank=True)
    retryable = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # Duplicate prevention: one execution per (workflow, idempotency key).
            models.UniqueConstraint(
                fields=["workflow", "idempotency_key"],
                condition=~Q(idempotency_key=""),
                name="uniq_execution_idempotency",
            )
        ]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["workflow", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.workflow_name} #{self.attempt} [{self.status}]"


class ExecutionLog(models.Model):
    class Level(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"

    execution = models.ForeignKey(Execution, on_delete=models.CASCADE, related_name="logs")
    level = models.CharField(max_length=8, choices=Level, default=Level.INFO)
    step = models.CharField(max_length=60, blank=True)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return f"{self.execution_id} {self.level}: {self.message[:60]}"


class ActionEffect(models.Model):
    """Ledger of completed action steps. A retry skips any step already recorded here, so a
    partially failed run never repeats an email or ticket that was already produced."""

    dedupe_key = models.CharField(max_length=255, unique=True)  # "<root_id>:<step>:<type>"
    execution = models.ForeignKey(Execution, on_delete=models.CASCADE, related_name="effects")
    step_index = models.PositiveSmallIntegerField()
    action_type = models.CharField(max_length=40)
    result = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.dedupe_key


class Notification(models.Model):
    class Kind(models.TextChoices):
        NOTIFICATION = "notification", "Notification"
        ALERT = "alert", "Alert"

    class Severity(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"

    kind = models.CharField(max_length=14, choices=Kind, default=Kind.NOTIFICATION)
    severity = models.CharField(max_length=8, choices=Severity, default=Severity.INFO)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    execution = models.ForeignKey(
        Execution, null=True, blank=True, on_delete=models.SET_NULL, related_name="notifications"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return self.title


class OutboxMessage(models.Model):
    """Every email the email adapter handled. In demo mode this *is* the mailbox."""

    to_address = models.EmailField()
    subject = models.CharField(max_length=200)
    body = models.TextField()
    mode = models.CharField(max_length=4, default="demo")  # demo | live
    status = models.CharField(max_length=10, default="sent")
    provider_message_id = models.CharField(max_length=120, blank=True)
    execution = models.ForeignKey(Execution, null=True, blank=True, on_delete=models.SET_NULL, related_name="messages")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.to_address}: {self.subject}"


class TicketAssignment(models.Model):
    ticket_id = models.CharField(max_length=80)
    subject = models.CharField(max_length=300, blank=True)
    priority = models.CharField(max_length=20, blank=True)
    category = models.CharField(max_length=60, blank=True)
    assignee = models.CharField(max_length=120)
    team = models.CharField(max_length=120, blank=True)
    matched_rule = models.CharField(max_length=200)
    execution = models.ForeignKey(
        Execution, null=True, blank=True, on_delete=models.SET_NULL, related_name="assignments"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.ticket_id} -> {self.assignee}"


class IntegrationSetting(models.Model):
    """Non-secret, user-editable integration settings plus the last connection test.
    Secrets are never stored here; they live in environment variables."""

    key = models.CharField(max_length=20, unique=True)
    enabled = models.BooleanField(default=True)
    settings = models.JSONField(default=dict, blank=True)
    last_tested_at = models.DateTimeField(null=True, blank=True)
    last_test_ok = models.BooleanField(null=True)
    last_test_mode = models.CharField(max_length=4, blank=True)
    last_test_message = models.CharField(max_length=300, blank=True)

    def __str__(self) -> str:
        return self.key
