from django.contrib import admin
from .models import (
    Category,
    UserInfo,
    PropertyProfile,
    MerchantProfile,
    PointsThreshold,
    PointsRecord,
    ApiPermission,
    IdentityApplication,
    AccessLog,
)


# 已移除 Counters 模型的后台管理注册


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "icon_file_id", "created_at", "updated_at")
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(UserInfo)
class UserInfoAdmin(admin.ModelAdmin):
    list_display = (
        "system_id",
        "openid",
        "identity_type",
        "daily_points",
        "total_points",
        "owner_property",
        "created_at",
    )
    search_fields = ("system_id", "openid", "phone_number")
    list_filter = ("identity_type",)


@admin.register(PropertyProfile)
class PropertyProfileAdmin(admin.ModelAdmin):
    list_display = ("property_id", "property_name", "community_name", "user", "created_at")
    search_fields = ("property_id", "property_name")


@admin.register(MerchantProfile)
class MerchantProfileAdmin(admin.ModelAdmin):
    list_display = (
        "merchant_id",
        "merchant_name",
        "category",
        "positive_rating_percent",
        "contact_phone",
        "open_hours",
        "avg_score",
        "created_at",
    )
    search_fields = ("merchant_id", "merchant_name")
    list_filter = ("category",)


@admin.register(PointsThreshold)
class PointsThresholdAdmin(admin.ModelAdmin):
    list_display = ("property", "min_points", "updated_at")
    search_fields = ("property__property_id", "property__property_name")


@admin.register(PointsRecord)
class PointsRecordAdmin(admin.ModelAdmin):
    list_display = ("user", "change", "created_at")
    search_fields = ("user__system_id", "user__openid")
    list_filter = ("created_at",)

@admin.register(ApiPermission)
class ApiPermissionAdmin(admin.ModelAdmin):
    list_display = ("endpoint_name", "method", "allowed_identities", "updated_at")
    search_fields = ("endpoint_name", "method")
    list_filter = ("method",)


@admin.register(IdentityApplication)
class IdentityApplicationAdmin(admin.ModelAdmin):
    list_display = ("user", "requested_identity", "status", "reviewed_by", "created_at", "reviewed_at")
    search_fields = ("user__openid", "user__system_id", "merchant_name", "property_name")
    list_filter = ("status", "requested_identity", "created_at")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(AccessLog)
class AccessLogAdmin(admin.ModelAdmin):
    list_display = ("openid", "access_date", "access_count", "first_access_at", "last_access_at")
    search_fields = ("openid",)
    list_filter = ("access_date",)
    ordering = ("-access_date", "-access_count")
    readonly_fields = ("first_access_at", "last_access_at")


# 自定义 Admin 站点文案
admin.site.site_header = "后台管理"
admin.site.site_title = "后台管理"
admin.site.index_title = "站点管理"
