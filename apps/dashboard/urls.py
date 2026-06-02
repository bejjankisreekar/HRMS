from django.urls import include, path
from django.views.generic import RedirectView

from .superadmin_views import (
    OrganizationCreateView,
    OrganizationDeleteView,
    OrganizationDetailView,
    OrganizationListView,
    OrganizationUpdateView,
    PlatformUserDeleteView,
    PlatformUserListView,
    PlatformUserUpdateView,
    SuperAdminDashboardView,
)
from apps.orgchart.super_views import (
    SuperAdminGlobalHierarchyView,
    SuperAdminOrgTreeDataAPIView,
    SuperAdminOrgTreeEmployeeAPIView,
    SuperAdminOrgTreeExportView,
    SuperAdminOrgTreeSearchAPIView,
    SuperAdminOrgTreeView,
)
from apps.subscriptions.org_feature_views import OrganizationFeatureControlView, OrganizationFeatureAPIView
from apps.subscriptions.plan_matrix_views import LegacyFeatureControlRedirectView
from apps.subscriptions.mixins import UpgradeRequiredView
from .analytics_views import AttendanceReportLegacyRedirectView
from .department_views import DepartmentManageView
from .topnav_views import (
    GlobalSearchAPIView,
    NotificationListAPIView,
    NotificationReadAllAPIView,
    NotificationReadAPIView,
)
from .views import (
    AttendanceCorrectionsView,
    AttendanceSettingsView,
    AttendanceShiftsView,
    MyAttendanceView,
    TeamAttendanceView,
    WorkCalendarView,
    DashboardRedirectView,
    EmployeeDashboardView,
    OrgAdminDashboardView,
    ProfessionalAdminDashboardView,
    StarterAdminDashboardView,
    SettingsView,
    ModuleSettingsView,
    StaffCreateView,
)
from .staff_views import (
    StaffBulkAPIView,
    StaffDeleteView,
    StaffDetailView,
    StaffExportView,
    StaffListView,
    StaffUpdateView,
)

app_name = "dashboard"

urlpatterns = [
    path("", DashboardRedirectView.as_view(), name="home"),
    path("super/", SuperAdminDashboardView.as_view(), name="super"),
    path(
        "superadmin/",
        RedirectView.as_view(pattern_name="dashboard:super", permanent=False),
        name="superadmin",
    ),
    path("super/organizations/", OrganizationListView.as_view(), name="super_organizations"),
    path("super/organizations/create/", OrganizationCreateView.as_view(), name="super_organization_create"),
    path(
        "super/organizations/<uuid:pk>/",
        OrganizationDetailView.as_view(),
        name="super_organization_detail",
    ),
    path(
        "super/organizations/<uuid:pk>/edit/",
        OrganizationUpdateView.as_view(),
        name="super_organization_edit",
    ),
    path(
        "super/organizations/<uuid:pk>/delete/",
        OrganizationDeleteView.as_view(),
        name="super_organization_delete",
    ),
    path("super/users/", PlatformUserListView.as_view(), name="super_users"),
    path("super/users/<uuid:pk>/edit/", PlatformUserUpdateView.as_view(), name="super_user_edit"),
    path("super/users/<uuid:pk>/delete/", PlatformUserDeleteView.as_view(), name="super_user_delete"),
    path("super/org-tree/global/", SuperAdminGlobalHierarchyView.as_view(), name="super_org_global"),
    path("super/org-tree/", SuperAdminOrgTreeView.as_view(), name="super_org_tree"),
    path("super/org-tree/api/data/", SuperAdminOrgTreeDataAPIView.as_view(), name="super_org_tree_api_data"),
    path(
        "super/org-tree/api/employee/<uuid:pk>/",
        SuperAdminOrgTreeEmployeeAPIView.as_view(),
        name="super_org_tree_api_employee",
    ),
    path("super/org-tree/api/search/", SuperAdminOrgTreeSearchAPIView.as_view(), name="super_org_tree_api_search"),
    path("super/org-tree/export/", SuperAdminOrgTreeExportView.as_view(), name="super_org_tree_export"),
    path("super/plans/", include(("apps.subscriptions.plan_urls", "plans"))),
    path(
        "super/feature-control/",
        LegacyFeatureControlRedirectView.as_view(),
        name="feature_control_redirect",
    ),
    path(
        "super/feature-control/<path:rest>",
        LegacyFeatureControlRedirectView.as_view(),
    ),
    path(
        "super/organizations/<uuid:pk>/features/",
        OrganizationFeatureControlView.as_view(),
        name="super_organization_features",
    ),
    path(
        "super/organizations/<uuid:pk>/features/api/",
        OrganizationFeatureAPIView.as_view(),
        name="super_organization_features_api",
    ),
    path(
        "super/plans/<uuid:pk>/features/",
        LegacyFeatureControlRedirectView.as_view(),
        name="super_plan_features",
    ),
    path("superadmin/financials/", include(("apps.subscriptions.financial_urls", "financials"))),
    path("superadmin/storage/", include(("apps.storage.urls", "storage"))),
    path("admin/", OrgAdminDashboardView.as_view(), name="org_admin"),
    path("admin/starter/", StarterAdminDashboardView.as_view(), name="starter_admin"),
    path("admin/professional/", ProfessionalAdminDashboardView.as_view(), name="professional_admin"),
    path("hr/", RedirectView.as_view(pattern_name="dashboard:attendance_team", permanent=True), name="hr"),
    path("employee/", EmployeeDashboardView.as_view(), name="employee"),
    path("settings/", SettingsView.as_view(), name="settings"),
    path("settings/modules/", ModuleSettingsView.as_view(), name="module_settings"),
    path("api/search/", GlobalSearchAPIView.as_view(), name="global_search"),
    path("api/notifications/", NotificationListAPIView.as_view(), name="notifications_list"),
    path("api/notifications/read-all/", NotificationReadAllAPIView.as_view(), name="notifications_read_all"),
    path("api/notifications/<uuid:pk>/read/", NotificationReadAPIView.as_view(), name="notification_read"),
    path("upgrade/", UpgradeRequiredView.as_view(), name="upgrade"),
    path("staff/", StaffListView.as_view(), name="staff_list"),
    path("staff/create/", StaffCreateView.as_view(), name="staff_create"),
    path("staff/export/", StaffExportView.as_view(), name="staff_export"),
    path("staff/api/bulk/", StaffBulkAPIView.as_view(), name="staff_api_bulk"),
    path("staff/<uuid:pk>/", StaffDetailView.as_view(), name="staff_detail"),
    path("staff/<uuid:pk>/edit/", StaffUpdateView.as_view(), name="staff_edit"),
    path("staff/<uuid:pk>/delete/", StaffDeleteView.as_view(), name="staff_delete"),
    path("departments/", DepartmentManageView.as_view(), name="departments"),
    path("admin/grades/", include(("apps.grades.urls", "grades"))),
    path("attendance/", MyAttendanceView.as_view(), name="attendance"),
    path("attendance/team/", TeamAttendanceView.as_view(), name="attendance_team"),
    path("attendance/settings/", AttendanceSettingsView.as_view(), name="attendance_settings"),
    path("work-calendar/", WorkCalendarView.as_view(), name="work_calendar"),
    path("attendance/corrections/", AttendanceCorrectionsView.as_view(), name="attendance_corrections"),
    path("attendance/report/", AttendanceReportLegacyRedirectView.as_view(), name="attendance_report"),
    path("attendance/shifts/", AttendanceShiftsView.as_view(), name="attendance_shifts"),
    path("org-tree/", include(("apps.orgchart.urls", "orgchart"))),
]
