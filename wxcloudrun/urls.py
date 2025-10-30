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
    # 计数器接口
    url(r'^^api/count(/)?$', views.counter),

    # 获取主页
    url(r'(/)?$', views.index),

    # 商品分类
    url(r'^api/categories/?$', views.categories_list),

    # 用户信息
    url(r'^api/users/?$', views.users_list),

    # 商户信息
    url(r'^api/merchants/?$', views.merchants_list),

    # 物业信息
    url(r'^api/properties/?$', views.properties_list),

    # 业主信息（按物业ID）
    url(r'^api/owners/by_property/(?P<property_id>[^/]+)/?$', views.owners_by_property),

    # 积分阈值查询
    url(r'^api/thresholds/(?P<property_id>[^/]+)/?$', views.threshold_query),

    # 管理员-积分阈值CRUD
    url(r'^api/admin/thresholds/?$', views.admin_threshold_create),            # POST
    url(r'^api/admin/thresholds/(?P<property_id>[^/]+)/?$', views.admin_threshold_update),  # PUT/DELETE

    # 积分变更示例
    url(r'^api/points/change/?$', views.points_change),

    # 管理员-接口权限管理
    url(r'^api/admin/permissions/?$', views.admin_api_permissions),  # GET/POST
)
