"""管理员视图模块统一导出"""
from wxcloudrun.views.admin.auth import admin_login
from wxcloudrun.views.admin.categories import admin_categories, admin_categories_detail
from wxcloudrun.views.admin.merchants import admin_merchants, admin_merchants_detail, admin_discount_stores
from wxcloudrun.views.admin.properties import admin_properties, admin_properties_detail
from wxcloudrun.views.admin.communities import admin_communities, admin_communities_detail
from wxcloudrun.views.admin.users import admin_users, admin_users_detail
from wxcloudrun.views.admin.storage import admin_storage_upload_credential, admin_storage_delete_files
from wxcloudrun.views.admin.points import admin_share_setting, admin_points_records, admin_discount_redeem_records
from wxcloudrun.views.admin.applications import (
    admin_applications_list,
    admin_application_approve,
    admin_application_reject,
)
from wxcloudrun.views.admin.statistics import admin_statistics_overview, admin_statistics_by_time, admin_statistics_by_range, admin_statistics_last_week
from wxcloudrun.views.admin.agreements import admin_contract_image, admin_contract_signature
from wxcloudrun.views.admin.identities import admin_identity_assign, admin_identity_revoke, admin_identity_active_set
from wxcloudrun.views.admin.contact import admin_contact_info
from wxcloudrun.views.admin.feedbacks import admin_feedbacks
from wxcloudrun.views.admin.recommended_merchants import admin_recommended_merchants
from wxcloudrun.views.admin.orders import admin_orders, admin_reviews, admin_review_delete
from wxcloudrun.views.admin.notifications import admin_notifications

__all__ = [
    'admin_login',
    'admin_categories',
    'admin_categories_detail',
    'admin_merchants',
    'admin_merchants_detail',
    'admin_discount_stores',
    'admin_properties',
    'admin_properties_detail',
    'admin_communities',
    'admin_communities_detail',
    'admin_users',
    'admin_users_detail',
    'admin_storage_upload_credential',
    'admin_storage_delete_files',
    'admin_share_setting',
    'admin_points_records',
    'admin_discount_redeem_records',
    'admin_applications_list',
    'admin_application_approve',
    'admin_application_reject',
    'admin_statistics_overview',
    'admin_statistics_by_time',
    'admin_statistics_by_range',
    'admin_statistics_last_week',
    'admin_contract_image',
    'admin_contract_signature',
    'admin_identity_assign',
    'admin_identity_revoke',
    'admin_identity_active_set',
    'admin_contact_info',
    'admin_feedbacks',
    'admin_recommended_merchants',
    'admin_orders',
    'admin_reviews',
    'admin_review_delete',
    'admin_notifications',
]
