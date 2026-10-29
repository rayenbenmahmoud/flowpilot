"""Event dispatch, execution and retry.

Reliability rules implemented here:
  * Duplicate events: one Execution per (workflow, idempotency key), enforced by a database
    unique constraint, so concurrent duplicates cannot both win.
  * Exactly-once local effects: every completed action step is written to ``ActionEffect`` in the
    same transaction as its output rows; a retry skips steps already recorded.
  * Safe retries: only failed, latest, non-exhausted executions of active workflows can be retried,
    and the retry itself is protected by a unique idempotency key.
  * Failures are recorded, never raised: a failed run produces an error notification through the
    ``workflow.failed`` event.
"""

import logging
import uuid
from dataclasses import dataclass

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from ..events import summarize_input
from ..models import ActionEffect, Execution, ExecutionLog, Workflow
from .actions import ACTIONS, ActionContext, ActionError
from .conditions import evaluate
from .redaction import redact
from .templating import TemplateError

logger = logging.getLogger(__name__)
FAILURE_EVENT = "workflow.failed"


class RetryBlocked(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


@dataclass
class DispatchItem:
    execution: Execution
    duplicate: bool


def log(execution: Execution, message: str, level: str = "info", step: str = "") -> None:
    ExecutionLog.objects.create(execution=execution, level=level, step=step, message=message[:2000])


def create_execution(
    workflow: Workflow,
    event_type: str,
    payload: dict,
    *,
    source: str,
    idempotency_key: str = "",
    retry_of: Execution | None = None,
) -> Execution:
    clean = redact(payload)
    execution = Execution(
        id=uuid.uuid4(),
        workflow=workflow,
        workflow_name=workflow.name,
        workflow_version=workflow.version,
        event_type=event_type,
        status=Execution.Status.PENDING,
        source=source,
        idempotency_key=idempotency_key,
        attempt=retry_of.attempt + 1 if retry_of else 1,
        retry_of=retry_of,
        payload=clean,
        input_summary=summarize_input(event_type, clean),
    )
    execution.root_id = retry_of.root_id if retry_of else execution.id
    execution.save()
    return execution


def enqueue(execution: Execution) -> None:
    from ..tasks import run_execution_task

    execution_id = str(execution.id)
    transaction.on_commit(lambda: run_execution_task.delay(execution_id))


def dispatch_event(event_type: str, payload: dict, *, source: str, idempotency_key: str = "") -> list[DispatchItem]:
    """Create (and queue) one execution per active workflow listening to ``event_type``."""
    items: list[DispatchItem] = []
    for workflow in Workflow.objects.filter(status=Workflow.Status.ACTIVE, trigger_event=event_type):
        if idempotency_key:
            existing = Execution.objects.filter(workflow=workflow, idempotency_key=idempotency_key).first()
            if existing:
                items.append(DispatchItem(existing, True))
                continue
        try:
            with transaction.atomic():
                execution = create_execution(
                    workflow, event_type, payload, source=source, idempotency_key=idempotency_key
                )
        except IntegrityError:  # lost a race with an identical concurrent event
            items.append(DispatchItem(Execution.objects.get(workflow=workflow, idempotency_key=idempotency_key), True))
            continue
        enqueue(execution)
        items.append(DispatchItem(execution, False))
    return items


def run_execution(execution_id: str) -> Execution:
    with transaction.atomic():
        execution = Execution.objects.select_for_update().select_related("workflow").get(pk=execution_id)
        if execution.status != Execution.Status.PENDING:  # redelivered task or double click: do nothing
            return execution
        execution.status = Execution.Status.RUNNING
        execution.started_at = timezone.now()
        execution.save(update_fields=["status", "started_at"])

    workflow = execution.workflow
    context = {"payload": execution.payload, "execution": {"id": str(execution.id), "attempt": execution.attempt}}
    log(execution, f"Started attempt {execution.attempt} of '{workflow.name}' (v{workflow.version}).", step="start")
    try:
        matched, reasons = evaluate(workflow.conditions, workflow.match_mode, context)
        for reason in reasons:
            log(execution, f"Condition: {reason}", step="conditions")
        if not matched:
            execution.status = Execution.Status.SKIPPED
            execution.result = {"reason": "conditions_not_met"}
            log(execution, "Skipped: the event did not match this workflow's conditions.", step="conditions")
        else:
            execution.result = {"steps": _run_actions(execution, workflow, context)}
            execution.status = Execution.Status.SUCCESS
            log(execution, "All actions completed.", step="finish")
    except (ActionError, TemplateError) as exc:
        _mark_failed(
            execution,
            getattr(exc, "code", "invalid_template"),
            getattr(exc, "message", str(exc)),
            bool(getattr(exc, "retryable", False)),
        )
    except Exception:
        logger.exception("Unexpected error while running execution %s", execution.id)
        _mark_failed(
            execution,
            "internal_error",
            "An unexpected error occurred. The details were written to the server log.",
            False,
        )

    execution.finished_at = timezone.now()
    execution.duration_ms = int((execution.finished_at - execution.started_at).total_seconds() * 1000)
    execution.save()

    if execution.status == Execution.Status.FAILED and execution.event_type != FAILURE_EVENT:
        _emit_failure_event(execution)
    return execution


def _run_actions(execution: Execution, workflow: Workflow, context: dict) -> list[dict]:
    steps = []
    for index, action in enumerate(workflow.actions):
        spec, label = ACTIONS[action["type"]], f"step {index + 1}: {ACTIONS[action['type']].label}"
        key = f"{execution.root_id}:{index}:{action['type']}"
        done = ActionEffect.objects.filter(dedupe_key=key).first()
        if done:
            log(
                execution,
                f"{label} was already completed in an earlier attempt; not repeated.",
                step=f"step-{index + 1}",
            )
            steps.append({"type": action["type"], "status": "already_done", **{"result": done.result}})
            continue
        try:
            with transaction.atomic():
                result = spec.handler(ActionContext(execution, index, key, context), action["config"])
                ActionEffect.objects.create(
                    dedupe_key=key,
                    execution=execution,
                    step_index=index,
                    action_type=action["type"],
                    result=redact(result),
                )
        except (ActionError, TemplateError) as exc:
            log(
                execution,
                f"{label} failed: {getattr(exc, 'message', str(exc))}",
                level="error",
                step=f"step-{index + 1}",
            )
            raise
        log(execution, f"{label} completed ({result.get('mode', 'ok')}).", step=f"step-{index + 1}")
        steps.append({"type": action["type"], "status": "done", "result": redact(result)})
    return steps


def _mark_failed(execution: Execution, code: str, message: str, retryable: bool) -> None:
    execution.status = Execution.Status.FAILED
    execution.error_code, execution.error_message, execution.retryable = code, message, retryable
    log(execution, f"Failed: {message}", level="error", step="finish")


def _emit_failure_event(execution: Execution) -> None:
    payload = {
        "execution_id": str(execution.id),
        "workflow_id": str(execution.workflow_id),
        "workflow_name": execution.workflow_name,
        "failed_event": execution.event_type,
        "attempt": execution.attempt,
        "error_code": execution.error_code,
        "error_message": execution.error_message,
        "retryable": execution.retryable,
    }
    dispatch_event(FAILURE_EVENT, payload, source=Execution.Source.SYSTEM, idempotency_key=f"failed:{execution.id}")


def retry_block_reason(execution: Execution) -> tuple[str, str] | None:
    if execution.status != Execution.Status.FAILED:
        return "not_failed", "Only failed executions can be retried."
    if execution.workflow.status == Workflow.Status.ARCHIVED:
        return "workflow_archived", "This workflow is archived. Restore and enable it before retrying."
    if execution.workflow.status != Workflow.Status.ACTIVE:
        return "workflow_disabled", "This workflow is disabled. Enable it before retrying."
    if execution.attempt >= settings.FLOWPILOT_MAX_ATTEMPTS:
        return "attempts_exhausted", f"The limit of {settings.FLOWPILOT_MAX_ATTEMPTS} attempts has been reached."
    if execution.retries.exists():
        return "already_retried", "This execution has already been retried. Check the newer attempt."
    return None


def retry_execution(execution_id: str) -> Execution:
    with transaction.atomic():
        execution = Execution.objects.select_for_update().select_related("workflow").get(pk=execution_id)
        if blocked := retry_block_reason(execution):
            raise RetryBlocked(*blocked)
        key = f"{execution.idempotency_key or execution.root_id}:retry:{execution.attempt + 1}"
        try:
            with transaction.atomic():
                retry = create_execution(
                    execution.workflow,
                    execution.event_type,
                    execution.payload,
                    source=Execution.Source.RETRY,
                    idempotency_key=key,
                    retry_of=execution,
                )
        except IntegrityError:
            raise RetryBlocked("already_retried", "This execution has already been retried.") from None
        log(retry, f"Retry of attempt {execution.attempt} ({execution.id}).", step="retry")
    enqueue(retry)
    return retry
