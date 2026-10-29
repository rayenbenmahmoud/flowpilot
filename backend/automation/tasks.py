from celery import shared_task

from .engine.runner import run_execution


@shared_task(name="automation.run_execution")
def run_execution_task(execution_id: str) -> str:
    """Runs one execution. Safe to deliver twice: the runner only starts PENDING executions."""
    return run_execution(execution_id).status
