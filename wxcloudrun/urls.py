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

from wxcloudrun import views
from django.conf.urls import url

urlpatterns = (
    # 商品分类
    url(r'^api/categories/?$', views.categories_list),

    # 用户个人信息
    url(r'^api/user/profile/?$', views.user_profile),

    # 用户信息
    url(r'^api/users/?$', views.users_list),

    # 商户信息
    url(r'^api/merchants/?$', views.merchants_list),
    url(r'^api/merchants/(?P<merchant_id>[^/]+)/?$', views.merchant_detail),

    # 物业信息
    url(r'^api/properties/?$', views.properties_list),

    # 业主信息（按物业ID）
    url(r'^api/owners/by_property/(?P<property_id>[^/]+)/?$', views.owners_by_property),

    # 积分阈值查询（小程序端，使用 openid）
    url(r'^api/thresholds/(?P<openid>[^/]+)/?$', views.threshold_query),

    # 积分变更示例
    url(r'^api/points/change/?$', views.points_change),

    # 管理员认证相关
    url(r'^api/admin/login/?$', views.admin_login),        # POST

    # 管理员-分类管理 CRUD
    url(r'^api/admin/categories/?$', views.admin_categories),                  # GET/POST
    url(r'^api/admin/categories/(?P<category_id>\d+)/?$', views.admin_categories_detail),   # PUT/DELETE

    # 管理员-商户管理 CRUD（使用 openid）
    url(r'^api/admin/merchants/?$', views.admin_merchants),                    # GET/POST
    url(r'^api/admin/merchants/(?P<openid>[^/]+)/?$', views.admin_merchants_detail),   # PUT/DELETE

    # 管理员-物业管理 CRUD（使用 openid，包含积分阈值）
    url(r'^api/admin/properties/?$', views.admin_properties),                  # GET/POST
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
)
