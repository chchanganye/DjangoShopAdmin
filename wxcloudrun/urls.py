"""wxcloudrun URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from wxcloudrun.views import (
    # 小程序端视图
    user_login,
    user_profile_handler,
    phone_number_resolve,
    user_set_active_identity,
    identity_apply,
    properties_public_list,
    communities_public_list,
    categories_list,
    merchants_list,
    merchants_recommended,
    merchant_detail,
    merchant_update_banner,
    merchant_business_license,
    merchant_update_location,
    merchant_update_profile,
    properties_list,
    owners_by_property,
    property_update_profile,
    threshold_query,
    points_change,
    merchant_points_add,
    owner_property_fee_pay,
    discount_store_redeem,
    orders_list,
    order_review_create,
    merchant_reviews_list,
    contract_image,
    contract_signature_status,
    contract_signature_update,
    contact_info,
    feedback_handler,
)
from wxcloudrun import views  # 管理员视图
from django.urls import re_path as url

urlpatterns = (
    # ========== 小程序端接口 ==========
    
    # 用户登录与身份管理
    url(r'^api/user/login/?$', user_login),                          # GET 登录/获取用户信息
    url(r'^api/user/profile/?$', user_profile_handler),              # GET 获取/PUT 更新用户详细信息
    url(r'^api/user/phone/resolve/?$', phone_number_resolve),        # POST 通过code换取手机号
    url(r'^api/user/identity/active/?$', user_set_active_identity),  # PUT 切换活跃身份
    url(r'^api/user/identity/apply/?$', identity_apply),             # POST 申请商户/物业身份
    url(r'^api/properties/public/?$', properties_public_list),       # GET 获取物业列表（供业主选择）
    url(r'^api/communities/public/?$', communities_public_list),     # GET 获取小区列表（供业主选择）
    
    # 商品分类
    url(r'^api/categories/?$', categories_list),

    # 商户信息
    url(r'^api/merchants/?$', merchants_list),
    url(r'^api/merchants/recommended/?$', merchants_recommended),
    url(r'^api/merchants/(?P<merchant_id>[^/]+)/reviews/?$', merchant_reviews_list),
    url(r'^api/merchants/(?P<merchant_id>[^/]+)/?$', merchant_detail),
    url(r'^api/merchant/banner/?$', merchant_update_banner),                  # PUT 商户更新横幅
    url(r'^api/merchant/license/?$', merchant_business_license),              # GET/PUT 商户营业执照
    url(r'^api/merchant/location/?$', merchant_update_location),              # PUT 商户更新定位
    url(r'^api/merchant/profile/?$', merchant_update_profile),                # PUT 商户编辑资料

    # 物业信息
    url(r'^api/properties/?$', properties_list),
    url(r'^api/property/profile/?$', property_update_profile),                # PUT 物业编辑资料

    # 业主信息（按物业ID）
    url(r'^api/owners/by_property/(?P<property_id>[^/]+)/?$', owners_by_property),

    # 积分阈值查询（小程序端，使用 openid）
    url(r'^api/thresholds/(?P<openid>[^/]+)/?$', threshold_query),

    # 积分变更
    url(r'^api/points/change/?$', points_change),
    # 商户为用户增加积分（手机号+金额）
    url(r'^api/points/merchant/add/?$', merchant_points_add),
    # 业主使用积分抵扣物业费（积分转给物业）
    url(r'^api/points/property/pay/?$', owner_property_fee_pay),
    # 折扣店积分兑换：扣除业主积分，转入折扣店积分
    url(r'^api/points/discount/redeem/?$', discount_store_redeem),

    # 订单与评价
    url(r'^api/orders/?$', orders_list),
    url(r'^api/orders/(?P<order_id>[^/]+)/review/?$', order_review_create),
    # 协议合同图片
    url(r'^api/contract/image/?$', contract_image),
    # 合同签名（状态与提交）
    url(r'^api/contract/signature/status/?$', contract_signature_status),
    url(r'^api/contract/signature/?$', contract_signature_update),
    # 联系我们
    url(r'^api/contact/?$', contact_info),
    # 意见反馈（提交/记录）
    url(r'^api/feedback/?$', feedback_handler),

    # ========== 管理员端接口 ==========
    
    # 管理员认证相关
    url(r'^api/admin/login/?$', views.admin_login),        # POST

    # 管理员-分类管理 CRUD
    url(r'^api/admin/categories/?$', views.admin_categories),                  # GET/POST
    url(r'^api/admin/categories/(?P<category_id>\d+)/?$', views.admin_categories_detail),   # PUT/DELETE

    # 管理员-商户管理 CRUD（使用 openid）
    url(r'^api/admin/merchants/?$', views.admin_merchants),                    # GET（只读，通过用户列表创建）
    url(r'^api/admin/merchants/(?P<openid>[^/]+)/?$', views.admin_merchants_detail),   # PUT/DELETE
    # 管理员-折扣店列表
    url(r'^api/admin/discount-stores/?$', views.admin_discount_stores),        # GET

    # 管理员-推荐商户配置（最多4个）
    url(r'^api/admin/recommended-merchants/?$', views.admin_recommended_merchants),   # GET/PUT

    # 管理员-物业管理 CRUD（使用 openid，包含积分阈值）
    url(r'^api/admin/properties/?$', views.admin_properties),                  # GET（只读，通过用户列表创建）
    url(r'^api/admin/properties/(?P<openid>[^/]+)/?$', views.admin_properties_detail), # PUT/DELETE

    # 管理员-小区管理 CRUD（使用 community_id）
    url(r'^api/admin/communities/?$', views.admin_communities),               # GET/POST
    url(r'^api/admin/communities/(?P<community_id>[^/]+)/?$', views.admin_communities_detail),  # PUT/DELETE

    # 管理员-用户管理 CRUD
    url(r'^api/admin/users/?$', views.admin_users),                            # GET/POST
    url(r'^api/admin/users/(?P<system_id>[^/]+)/?$', views.admin_users_detail),  # PUT/DELETE
    # 管理员-身份管理
    url(r'^api/admin/users/(?P<system_id>[^/]+)/identities/assign/?$', views.admin_identity_assign),   # POST
    url(r'^api/admin/users/(?P<system_id>[^/]+)/identities/revoke/?$', views.admin_identity_revoke),   # POST
    url(r'^api/admin/users/(?P<system_id>[^/]+)/identity/active/?$', views.admin_identity_active_set), # PUT

    # 管理员-对象存储辅助接口
    url(r'^api/admin/storage/upload-credential/?$', views.admin_storage_upload_credential),  # POST
    url(r'^api/admin/storage/delete/?$', views.admin_storage_delete_files),                  # POST

    # 管理员-积分分成配置
    url(r'^api/admin/share-setting/?$', views.admin_share_setting),            # GET/PUT

    # 管理员-积分变更记录查询
    url(r'^api/admin/points-records/?$', views.admin_points_records),          # GET
    # 管理员-折扣店积分兑换记录
    url(r'^api/admin/discount-redeem-records/?$', views.admin_discount_redeem_records),  # GET

    # 管理员-订单与评价记录
    url(r'^api/admin/orders/?$', views.admin_orders),                          # GET
    url(r'^api/admin/reviews/?$', views.admin_reviews),                        # GET
    
    # 管理员-身份申请审核管理
    url(r'^api/admin/applications/?$', views.admin_applications_list),         # GET 获取申请列表
    url(r'^api/admin/applications/approve/?$', views.admin_application_approve),   # POST 批准申请
    url(r'^api/admin/applications/reject/?$', views.admin_application_reject),     # POST 拒绝申请
    
    # 管理员-统计接口
    url(r'^api/admin/statistics/overview/?$', views.admin_statistics_overview),     # GET 统计概览
    url(r'^api/admin/statistics/by-time/?$', views.admin_statistics_by_time),       # GET 按时间维度统计
    url(r'^api/admin/statistics/by-range/?$', views.admin_statistics_by_range),     # GET 按日期范围统计
    url(r'^api/admin/statistics/last-week/?$', views.admin_statistics_last_week),   # GET 上周统计（服务器时间）
    # 管理员-协议合同图片配置
    url(r'^api/admin/contract/image/?$', views.admin_contract_image),               # GET/PUT
    # 管理员-查询用户合同签名
    url(r'^api/admin/contract/signature/?$', views.admin_contract_signature),       # GET
    # 管理员-联系我们配置
    url(r'^api/admin/contact/?$', views.admin_contact_info),                        # GET/PUT
    # 管理员-意见反馈
    url(r'^api/admin/feedbacks/?$', views.admin_feedbacks),                         # GET
)
