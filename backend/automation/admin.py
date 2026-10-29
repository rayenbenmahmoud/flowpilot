from django.contrib import admin

from .models import Execution, IntegrationSetting, Notification, OutboxMessage, TicketAssignment, Workflow

admin.site.register([Workflow, Execution, Notification, OutboxMessage, TicketAssignment, IntegrationSetting])
