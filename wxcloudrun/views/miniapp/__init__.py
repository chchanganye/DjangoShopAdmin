"""小程序端视图模块统一导出"""
from wxcloudrun.views.miniapp.user import (
    user_login,
    user_profile_handler,
    phone_number_resolve,
    identity_apply,
    properties_public_list,
)
from wxcloudrun.views.miniapp.community import communities_public_list
from wxcloudrun.views.miniapp.category import categories_list
from wxcloudrun.views.miniapp.merchant import (
    merchants_list,
    merchants_recommended,
    merchant_detail,
    merchant_update_banner,
    merchant_business_license,
    merchant_update_location,
    merchant_update_profile,
)
from wxcloudrun.views.miniapp.property import properties_list, owners_by_property, property_update_profile
from wxcloudrun.views.miniapp.points import (
    threshold_query,
    points_change,
    merchant_points_add,
    owner_property_fee_pay,
    discount_store_redeem,
)
from wxcloudrun.views.miniapp.orders import orders_list, order_review_create, merchant_reviews_list
from wxcloudrun.views.miniapp.contract import contract_image
from wxcloudrun.views.miniapp.signature import contract_signature_status, contract_signature_update
from wxcloudrun.views.miniapp.user import user_set_active_identity
from wxcloudrun.views.miniapp.contact import contact_info
from wxcloudrun.views.miniapp.feedback import feedback_handler

__all__ = [
    'user_login',
    'user_profile_handler',
    'phone_number_resolve',
    'identity_apply',
    'properties_public_list',
    'communities_public_list',
    'categories_list',
    'merchants_list',
    'merchants_recommended',
    'merchant_detail',
    'merchant_update_banner',
    'merchant_business_license',
    'merchant_update_location',
    'merchant_update_profile',
    'properties_list',
    'owners_by_property',
    'property_update_profile',
    'threshold_query',
    'points_change',
    'merchant_points_add',
    'owner_property_fee_pay',
    'discount_store_redeem',
    'orders_list',
    'order_review_create',
    'merchant_reviews_list',
    'contract_image',
    'contract_signature_status',
    'contract_signature_update',
    'user_set_active_identity',
    'contact_info',
    'feedback_handler',
]
