from django.urls import path

from . import views

app_name = "documents"

urlpatterns = [
    path("", views.DocumentManagementView.as_view(), name="management"),
    path("templates/create/", views.DocumentTemplateCreateView.as_view(), name="template_create"),
    path("templates/<uuid:pk>/edit/", views.DocumentTemplateEditView.as_view(), name="template_edit"),
    path("templates/<uuid:pk>/delete/", views.DocumentTemplateDeleteView.as_view(), name="template_delete"),
    path("templates/<uuid:pk>/versions/", views.DocumentTemplateVersionsView.as_view(), name="template_versions"),
    path(
        "templates/<uuid:pk>/versions/<uuid:vpk>/restore/",
        views.DocumentTemplateVersionRestoreView.as_view(),
        name="template_version_restore",
    ),
    path("templates/<uuid:pk>/preview/", views.DocumentTemplatePreviewView.as_view(), name="template_preview"),
    path("generate/", views.DocumentGenerateView.as_view(), name="generate"),
    path("generated/<uuid:pk>/", views.GeneratedDocumentDetailView.as_view(), name="generated_detail"),
    path("generated/<uuid:pk>/preview/", views.DocumentPreviewView.as_view(), name="doc_preview"),
    path("generated/<uuid:pk>/download/", views.DocumentDownloadView.as_view(), name="doc_download"),
    path("generated/<uuid:pk>/delete/", views.GeneratedDocumentDeleteView.as_view(), name="doc_delete"),
    path("audit/", views.DocumentAuditView.as_view(), name="audit"),
    path("permissions/", views.DocumentPermissionsView.as_view(), name="permissions"),
    path("api/default-body/", views.DocumentDefaultBodyAPIView.as_view(), name="api_default_body"),
]
