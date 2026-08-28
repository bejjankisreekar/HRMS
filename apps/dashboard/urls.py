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
from .analytics_views import AttendanceReportLegacyRedirectView, AnalyticsDashboardView, AnalyticsDataView
from .hr_analytics_views import HRAnalyticsView, HRAnalyticsDataView
from .digital_register_views import DigitalRegisterView, DigitalRegisterDataView
from .department_views import DepartmentManageView
from .topnav_views import (
    GlobalSearchAPIView,
    NotificationListAPIView,
    NotificationReadAllAPIView,
    NotificationReadAPIView,
)
from .manager_views import (
    NotificationsPageView,
    TeamAttendanceExportView,
    TeamAttendancePageView,
    TeamDirectoryView,
    TeamLeaveApprovalsView,
    TeamLeaveDecisionView,
    TeamRegularizationDecisionView,
    TeamRegularizationsView,
)
from .views import (
    AttendanceChartDataView,
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
    FinancialYearSettingsView,
    StaffCreateView,
    StaffEmailCheckView,
    StaffQuickCreateView,
)
from .financial_year_views import (
    FinancialYearMasterView,
    FinancialYearEditView,
    FinancialYearToggleActiveView,
    FinancialYearSetDefaultView,
    FinancialYearDeleteView,
    SetFinancialYearView,
)
from .staff_import_views import (
    StaffImportReportView,
    StaffImportTemplateView,
    StaffImportView,
)
from .staff_api import SavedFilterAPI, SavedFilterDeleteAPI, StaffDirectoryAPI
from .staff_views import (
    StaffBulkAPIView,
    StaffAttendanceSheetView,
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
    # ── Team lead (users with direct reports) ────────────────────────────────
    path("notifications/", NotificationsPageView.as_view(), name="notifications"),
    path("team/members/", TeamDirectoryView.as_view(), name="team_members"),
    path("team/attendance/", TeamAttendancePageView.as_view(), name="team_attendance"),
    path("team/attendance/export/", TeamAttendanceExportView.as_view(), name="team_attendance_export"),
    path("team/leave-approvals/", TeamLeaveApprovalsView.as_view(), name="team_leave_approvals"),
    path(
        "team/leave-approvals/<uuid:pk>/<str:decision>/",
        TeamLeaveDecisionView.as_view(),
        name="team_leave_decision",
    ),
    path("team/regularizations/", TeamRegularizationsView.as_view(), name="team_regularizations"),
    path(
        "team/regularizations/<uuid:pk>/<str:decision>/",
        TeamRegularizationDecisionView.as_view(),
        name="team_regularization_decision",
    ),
    path("settings/", SettingsView.as_view(), name="settings"),
    path("settings/modules/", ModuleSettingsView.as_view(), name="module_settings"),
    path("settings/financial-year/", FinancialYearSettingsView.as_view(), name="financial_year_settings"),
    path("settings/financial-years/", FinancialYearMasterView.as_view(), name="financial_year_master"),
    path("settings/financial-years/<uuid:pk>/edit/", FinancialYearEditView.as_view(), name="financial_year_edit"),
    path("settings/financial-years/<uuid:pk>/toggle/", FinancialYearToggleActiveView.as_view(), name="financial_year_toggle"),
    path("settings/financial-years/<uuid:pk>/set-default/", FinancialYearSetDefaultView.as_view(), name="financial_year_set_default"),
    path("settings/financial-years/<uuid:pk>/delete/", FinancialYearDeleteView.as_view(), name="financial_year_delete"),
    path("api/set-fy/", SetFinancialYearView.as_view(), name="set_fy"),
    path("api/search/", GlobalSearchAPIView.as_view(), name="global_search"),
    path("api/notifications/", NotificationListAPIView.as_view(), name="notifications_list"),
    path("api/notifications/read-all/", NotificationReadAllAPIView.as_view(), name="notifications_read_all"),
    path("api/notifications/<uuid:pk>/read/", NotificationReadAPIView.as_view(), name="notification_read"),
    path("upgrade/", UpgradeRequiredView.as_view(), name="upgrade"),
    path("staff/", StaffListView.as_view(), name="staff_list"),
    path("staff/create/", StaffCreateView.as_view(), name="staff_create"),
    path("staff/check-email/", StaffEmailCheckView.as_view(), name="staff_check_email"),
    path("staff/quick-create/<str:kind>/", StaffQuickCreateView.as_view(), name="staff_quick_create"),
    path("staff/export/", StaffExportView.as_view(), name="staff_export"),
    path("staff/import/", StaffImportView.as_view(), name="staff_import"),
    path("staff/import/template/", StaffImportTemplateView.as_view(), name="staff_import_template"),
    path("staff/import/report/", StaffImportReportView.as_view(), name="staff_import_report"),
    path("staff/api/bulk/", StaffBulkAPIView.as_view(), name="staff_api_bulk"),
    path("staff/api/directory/", StaffDirectoryAPI.as_view(), name="staff_api_directory"),
    path("staff/api/saved-filters/", SavedFilterAPI.as_view(), name="staff_saved_filters"),
    path("staff/api/saved-filters/<uuid:pk>/delete/", SavedFilterDeleteAPI.as_view(), name="staff_saved_filter_delete"),
    path("staff/<uuid:pk>/", StaffDetailView.as_view(), name="staff_detail"),
    path("staff/<uuid:pk>/attendance/", StaffAttendanceSheetView.as_view(), name="staff_attendance_sheet"),
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
    path("analytics/", AnalyticsDashboardView.as_view(), name="analytics"),
    path("analytics/data/", AnalyticsDataView.as_view(), name="analytics_data"),
    path("hr-analytics/", HRAnalyticsView.as_view(), name="hr_analytics"),
    path("hr-analytics/data/", HRAnalyticsDataView.as_view(), name="hr_analytics_data"),
    path("attendance/register/", DigitalRegisterView.as_view(), name="digital_register"),
    path("attendance/register/data/", DigitalRegisterDataView.as_view(), name="digital_register_data"),
    path("attendance/shifts/", AttendanceShiftsView.as_view(), name="attendance_shifts"),
    path("attendance/chart-data/", AttendanceChartDataView.as_view(), name="attendance_chart_data"),
    path("org-tree/", include(("apps.orgchart.urls", "orgchart"))),
]
