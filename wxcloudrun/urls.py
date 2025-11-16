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
    identity_apply,
    properties_public_list,
    categories_list,
    merchants_list,
    merchant_detail,
    merchant_update_banner,
    properties_list,
    owners_by_property,
    threshold_query,
    points_change,
    contract_image,
    contract_signature_status,
    contract_signature_update,
)
from wxcloudrun import views  # 管理员视图
from django.conf.urls import url

urlpatterns = (
    # ========== 小程序端接口 ==========
    
    # 用户登录与身份管理
    url(r'^api/user/login/?$', user_login),                          # GET 登录/获取用户信息
    url(r'^api/user/profile/?$', user_profile_handler),              # GET 获取/PUT 更新用户详细信息
    url(r'^api/user/phone/resolve/?$', phone_number_resolve),        # POST 通过code换取手机号
    url(r'^api/user/identity/apply/?$', identity_apply),             # POST 申请商户/物业身份
    url(r'^api/properties/public/?$', properties_public_list),       # GET 获取物业列表（供业主选择）
    
    # 商品分类
    url(r'^api/categories/?$', categories_list),

    # 商户信息
    url(r'^api/merchants/?$', merchants_list),
    url(r'^api/merchants/(?P<merchant_id>[^/]+)/?$', merchant_detail),
    url(r'^api/merchant/banner/?$', merchant_update_banner),                  # PUT 商户更新横幅

    # 物业信息
    url(r'^api/properties/?$', properties_list),

    # 业主信息（按物业ID）
    url(r'^api/owners/by_property/(?P<property_id>[^/]+)/?$', owners_by_property),

    # 积分阈值查询（小程序端，使用 openid）
    url(r'^api/thresholds/(?P<openid>[^/]+)/?$', threshold_query),

    # 积分变更
    url(r'^api/points/change/?$', points_change),
    # 协议合同图片
    url(r'^api/contract/image/?$', contract_image),
    # 合同签名（状态与提交）
    url(r'^api/contract/signature/status/?$', contract_signature_status),
    url(r'^api/contract/signature/?$', contract_signature_update),

    # ========== 管理员端接口 ==========
    
    # 管理员认证相关
    url(r'^api/admin/login/?$', views.admin_login),        # POST

    # 管理员-分类管理 CRUD
    url(r'^api/admin/categories/?$', views.admin_categories),                  # GET/POST
    url(r'^api/admin/categories/(?P<category_id>\d+)/?$', views.admin_categories_detail),   # PUT/DELETE

    # 管理员-商户管理 CRUD（使用 openid）
    url(r'^api/admin/merchants/?$', views.admin_merchants),                    # GET（只读，通过用户列表创建）
    url(r'^api/admin/merchants/(?P<openid>[^/]+)/?$', views.admin_merchants_detail),   # PUT/DELETE

    # 管理员-物业管理 CRUD（使用 openid，包含积分阈值）
    url(r'^api/admin/properties/?$', views.admin_properties),                  # GET（只读，通过用户列表创建）
    url(r'^api/admin/properties/(?P<openid>[^/]+)/?$', views.admin_properties_detail), # PUT/DELETE

    # 管理员-用户管理 CRUD
    url(r'^api/admin/users/?$', views.admin_users),                            # GET/POST
    url(r'^api/admin/users/(?P<system_id>[^/]+)/?$', views.admin_users_detail),  # PUT/DELETE

    # 管理员-对象存储辅助接口
    url(r'^api/admin/storage/upload-credential/?$', views.admin_storage_upload_credential),  # POST
    url(r'^api/admin/storage/delete/?$', views.admin_storage_delete_files),                  # POST

    # 管理员-积分分成配置
    url(r'^api/admin/share-setting/?$', views.admin_share_setting),            # GET/PUT

    # 管理员-积分变更记录查询
    url(r'^api/admin/points-records/?$', views.admin_points_records),          # GET
    
    # 管理员-身份申请审核管理
    url(r'^api/admin/applications/?$', views.admin_applications_list),         # GET 获取申请列表
    url(r'^api/admin/applications/approve/?$', views.admin_application_approve),   # POST 批准申请
    url(r'^api/admin/applications/reject/?$', views.admin_application_reject),     # POST 拒绝申请
    
    # 管理员-统计接口
    url(r'^api/admin/statistics/overview/?$', views.admin_statistics_overview),     # GET 统计概览
    url(r'^api/admin/statistics/by-time/?$', views.admin_statistics_by_time),       # GET 按时间维度统计
    # 管理员-协议合同图片配置
    url(r'^api/admin/contract/image/?$', views.admin_contract_image),               # GET/PUT
    # 管理员-查询用户合同签名
    url(r'^api/admin/contract/signature/?$', views.admin_contract_signature),       # GET
)
