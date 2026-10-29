import uuid

import django_filters as df
from django.db.models import Q

from .models import Execution, Workflow


class WorkflowFilter(df.FilterSet):
    status = df.ChoiceFilter(choices=Workflow.Status.choices)
    trigger_event = df.CharFilter()
    q = df.CharFilter(method="search", label="Search name or description")

    class Meta:
        model = Workflow
        fields = ["status", "trigger_event", "q"]

    def search(self, queryset, name, value):
        return queryset.filter(Q(name__icontains=value) | Q(description__icontains=value))


class ExecutionFilter(df.FilterSet):
    workflow = df.UUIDFilter(field_name="workflow_id")
    status = df.MultipleChoiceFilter(choices=Execution.Status.choices)
    event_type = df.CharFilter()
    source = df.ChoiceFilter(choices=Execution.Source.choices)
    date_from = df.DateFilter(field_name="created_at", lookup_expr="date__gte", label="Created on or after (UTC date)")
    date_to = df.DateFilter(field_name="created_at", lookup_expr="date__lte", label="Created on or before (UTC date)")
    q = df.CharFilter(method="search", label="Search workflow, input, error, key or execution ID")

    class Meta:
        model = Execution
        fields = ["workflow", "status", "event_type", "source", "date_from", "date_to", "q"]

    def search(self, queryset, name, value):
        query = (
            Q(workflow_name__icontains=value)
            | Q(input_summary__icontains=value)
            | Q(error_message__icontains=value)
            | Q(idempotency_key__icontains=value)
        )
        try:
            query |= Q(id=uuid.UUID(value.strip())) | Q(root_id=uuid.UUID(value.strip()))
        except ValueError:
            pass
        return queryset.filter(query)
