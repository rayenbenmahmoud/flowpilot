from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("workflows", views.WorkflowViewSet, basename="workflow")
router.register("executions", views.ExecutionViewSet, basename="execution")
router.register("notifications", views.NotificationViewSet, basename="notification")
router.register("outbox", views.OutboxViewSet, basename="outbox")
router.register("assignments", views.AssignmentViewSet, basename="assignment")

urlpatterns = [
    path("config/", views.ConfigView.as_view()),
    path("health/", views.HealthView.as_view()),
    path("auth/login/", views.LoginView.as_view()),
    path("auth/logout/", views.LogoutView.as_view()),
    path("auth/me/", views.MeView.as_view()),
    path("meta/", views.MetaView.as_view()),
    path("dashboard/", views.DashboardView.as_view()),
    path("integrations/", views.IntegrationListView.as_view()),
    path("integrations/<str:key>/", views.IntegrationDetailView.as_view()),
    path("integrations/<str:key>/test/", views.IntegrationTestView.as_view()),
    path("demo/scenarios/", views.DemoScenarioListView.as_view()),
    path("demo/scenarios/<str:key>/run/", views.DemoScenarioRunView.as_view()),
    path("demo/reset/", views.DemoResetView.as_view()),
    path("webhooks/<str:event_type>/", views.WebhookView.as_view()),
    path("", include(router.urls)),
]
