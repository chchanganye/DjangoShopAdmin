"""视图模块统一导出"""
# 小程序端视图
from wxcloudrun.views.miniapp import (
    user_login,
    user_profile_handler,
    identity_apply,
    properties_public_list,
    categories_list,
    merchants_list,
    merchant_detail,
    properties_list,
    owners_by_property,
    threshold_query,
    points_change,
)

# 管理员视图
from wxcloudrun.views.admin import (
    admin_login,
    admin_categories,
    admin_categories_detail,
    admin_merchants,
    admin_merchants_detail,
    admin_properties,
    admin_properties_detail,
    admin_users,
    admin_users_detail,
    admin_storage_upload_credential,
    admin_storage_delete_files,
    admin_share_setting,
    admin_points_records,
    admin_applications_list,
    admin_application_approve,
    admin_application_reject,
    admin_statistics_overview,
    admin_statistics_by_time,
)

