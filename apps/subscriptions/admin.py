from django.contrib import admin

from .models import (
    AddOnCatalog,
    Coupon,
    FeatureCategory,
    FeatureControlAuditLog,
    FeatureDefinition,
    FeatureModule,
    FeatureRolePermission,
    FieldDefinition,
    FinancialAuditLog,
    Invoice,
    NavigationItem,
    OrganizationAddOn,
    OrganizationFeatureOverride,
    OrganizationLimit,
    PageDefinition,
    Payment,
    Plan,
    PlanFeature,
    PlanMenuItem,
    Subscription,
    UsageRecord,
)


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "monthly_price_inr", "yearly_price_inr", "employee_limit", "is_active")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(AddOnCatalog)
class AddOnCatalogAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "monthly_price_inr", "is_active")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(PlanFeature)
class PlanFeatureAdmin(admin.ModelAdmin):
    list_display = ("plan", "feature", "is_enabled")
    list_filter = ("plan", "is_enabled")


@admin.register(PlanMenuItem)
class PlanMenuItemAdmin(admin.ModelAdmin):
    list_display = ("plan", "label", "audience", "sort_order", "is_enabled")
    list_filter = ("plan", "audience", "is_enabled")
    ordering = ("plan", "audience", "sort_order")


@admin.register(FeatureDefinition)
class FeatureDefinitionAdmin(admin.ModelAdmin):
    list_display = ("name", "key", "category", "is_active")
    prepopulated_fields = {"key": ("name",)}


@admin.register(FeatureCategory)
class FeatureCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "key", "sort_order", "is_active")


@admin.register(FeatureModule)
class FeatureModuleAdmin(admin.ModelAdmin):
    list_display = ("name", "key", "is_globally_enabled", "is_active", "sort_order")


@admin.register(PageDefinition)
class PageDefinitionAdmin(admin.ModelAdmin):
    list_display = ("name", "key", "url_name", "is_globally_enabled")


@admin.register(NavigationItem)
class NavigationItemAdmin(admin.ModelAdmin):
    """The live source of left-nav order. Edit ``sort_order`` inline and save."""

    list_display = ("sort_order", "label", "audience", "plan", "feature_key", "url_name", "is_visible")
    list_display_links = ("label",)
    list_editable = ("sort_order", "is_visible")
    list_filter = ("audience", "plan", "is_visible")
    search_fields = ("label", "feature_key", "url_name")
    ordering = ("audience", "sort_order", "label")
    list_per_page = 100

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Nav is cached per org — without this the new order only appears once the
        # cache expires.
        from apps.subscriptions.services.feature_control import invalidate_org_entitlements_for_all

        invalidate_org_entitlements_for_all()


@admin.register(OrganizationFeatureOverride)
class OrganizationFeatureOverrideAdmin(admin.ModelAdmin):
    list_display = ("organization", "feature", "is_enabled", "updated_at")


@admin.register(OrganizationLimit)
class OrganizationLimitAdmin(admin.ModelAdmin):
    list_display = ("organization", "employee_limit", "storage_limit_mb", "branch_limit")


@admin.register(FeatureControlAuditLog)
class FeatureControlAuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "summary", "feature_key", "organization", "actor", "created_at")
    list_filter = ("action",)


@admin.register(FeatureRolePermission)
class FeatureRolePermissionAdmin(admin.ModelAdmin):
    list_display = ("feature", "role", "is_allowed")


@admin.register(FieldDefinition)
class FieldDefinitionAdmin(admin.ModelAdmin):
    list_display = ("name", "key", "form_context", "is_globally_visible")


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ("code", "percent_off", "amount_off_inr", "is_active", "redemption_count")


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("organization", "plan", "status", "billing_interval", "current_period_end")
    list_filter = ("status", "billing_interval")


@admin.register(OrganizationAddOn)
class OrganizationAddOnAdmin(admin.ModelAdmin):
    list_display = ("organization", "addon", "is_active", "activated_at")


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "organization", "amount_inr", "status", "paid_at")
    list_filter = ("status",)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("organization", "amount_inr", "status", "method", "paid_at")
    list_filter = ("status", "method")


@admin.register(FinancialAuditLog)
class FinancialAuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "summary", "organization", "actor", "created_at")
    list_filter = ("action",)


admin.site.register(UsageRecord)
