"""小程序端视图模块统一导出"""
from wxcloudrun.views.miniapp.user import (
    user_login,
    user_profile_handler,
    identity_apply,
    properties_public_list,
)
from wxcloudrun.views.miniapp.category import categories_list
from wxcloudrun.views.miniapp.merchant import merchants_list, merchant_detail
from wxcloudrun.views.miniapp.property import properties_list, owners_by_property
from wxcloudrun.views.miniapp.points import threshold_query, points_change

__all__ = [
    'user_login',
    'user_profile_handler',
    'identity_apply',
    'properties_public_list',
    'categories_list',
    'merchants_list',
    'merchant_detail',
    'properties_list',
    'owners_by_property',
    'threshold_query',
    'points_change',
]

