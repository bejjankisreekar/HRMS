from django.urls import path

from .views import RuleBuilderView, RuleLogsView, RuleManagementView, RuleTestView

app_name = "ruleengine"

urlpatterns = [
    path("", RuleManagementView.as_view(), name="management"),
    path("builder/", RuleBuilderView.as_view(), name="builder_create"),
    path("builder/<uuid:pk>/", RuleBuilderView.as_view(), name="builder_edit"),
    path("test/", RuleTestView.as_view(), name="test"),
    path("logs/", RuleLogsView.as_view(), name="logs"),
]
