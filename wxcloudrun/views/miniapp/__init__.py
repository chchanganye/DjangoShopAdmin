"""小程序端视图模块统一导出"""
from wxcloudrun.views.miniapp.user import (
    user_login,
    user_profile_handler,
    phone_number_resolve,
    identity_apply,
    properties_public_list,
)
from wxcloudrun.views.miniapp.category import categories_list
from wxcloudrun.views.miniapp.merchant import (
    merchants_list,
    merchant_detail,
    merchant_update_banner,
)
from wxcloudrun.views.miniapp.property import properties_list, owners_by_property
from wxcloudrun.views.miniapp.points import threshold_query, points_change
from wxcloudrun.views.miniapp.contract import contract_image
from wxcloudrun.views.miniapp.signature import contract_signature_status, contract_signature_update

__all__ = [
    'user_login',
    'user_profile_handler',
    'phone_number_resolve',
    'identity_apply',
    'properties_public_list',
    'categories_list',
    'merchants_list',
    'merchant_detail',
    'merchant_update_banner',
    'properties_list',
    'owners_by_property',
    'threshold_query',
    'points_change',
    'contract_image',
    'contract_signature_status',
    'contract_signature_update',
]
