"""管理员视图模块统一导出"""
from wxcloudrun.views.admin.auth import admin_login
from wxcloudrun.views.admin.categories import admin_categories, admin_categories_detail
from wxcloudrun.views.admin.merchants import admin_merchants, admin_merchants_detail
from wxcloudrun.views.admin.properties import admin_properties, admin_properties_detail
from wxcloudrun.views.admin.users import admin_users, admin_users_detail
from wxcloudrun.views.admin.storage import admin_storage_upload_credential, admin_storage_delete_files
from wxcloudrun.views.admin.points import admin_share_setting, admin_points_records
from wxcloudrun.views.admin.applications import (
    admin_applications_list,
    admin_application_approve,
    admin_application_reject,
)
from wxcloudrun.views.admin.statistics import admin_statistics_overview, admin_statistics_by_time
from wxcloudrun.views.admin.agreements import admin_contract_image, admin_contract_signature

__all__ = [
    'admin_login',
    'admin_categories',
    'admin_categories_detail',
    'admin_merchants',
    'admin_merchants_detail',
    'admin_properties',
    'admin_properties_detail',
    'admin_users',
    'admin_users_detail',
    'admin_storage_upload_credential',
    'admin_storage_delete_files',
    'admin_share_setting',
    'admin_points_records',
    'admin_applications_list',
    'admin_application_approve',
    'admin_application_reject',
    'admin_statistics_overview',
    'admin_statistics_by_time',
    'admin_contract_image',
    'admin_contract_signature',
]

