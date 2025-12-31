"""管理员小区管理视图"""

import json
import logging

from django.views.decorators.http import require_http_methods

from wxcloudrun.decorators import admin_token_required
from wxcloudrun.models import Community, PropertyProfile
from wxcloudrun.utils.responses import json_ok, json_err


logger = logging.getLogger('log')


@admin_token_required
@require_http_methods(["GET", "POST"])
def admin_communities(request, admin):
    """小区管理 - GET列表 / POST创建"""
    if request.method == 'GET':
        current_param = request.GET.get('current') or request.GET.get('page')
        size_param = request.GET.get('size') or request.GET.get('page_size') or request.GET.get('limit')

        page = 1
        page_size = 20

        if current_param:
            try:
                page = int(current_param)
            except (TypeError, ValueError):
                return json_err('current 必须为数字', status=400)
        if size_param:
            try:
                page_size = int(size_param)
            except (TypeError, ValueError):
                return json_err('size 必须为数字', status=400)
        if page < 1:
            page = 1
        if page_size < 1:
            page_size = 1
        if page_size > 100:
            page_size = 100

        qs = Community.objects.select_related('property').all().order_by('-updated_at', '-id')
        total = qs.count()
        start = (page - 1) * page_size
        communities = list(qs[start : start + page_size])

        items = []
        for c in communities:
            items.append({
                'community_id': c.community_id,
                'community_name': c.community_name,
                'property_id': c.property.property_id if c.property else None,
                'property_name': c.property.property_name if c.property else None,
                'updated_at': c.updated_at.strftime('%Y-%m-%d %H:%M:%S') if c.updated_at else None,
            })
        return json_ok({'list': items, 'total': total})

    # POST 创建
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)

    property_id = (body.get('property_id') or '').strip()
    community_name = (body.get('community_name') or '').strip()
    if not property_id:
        return json_err('缺少参数 property_id', status=400)
    if not community_name:
        return json_err('缺少参数 community_name', status=400)

    try:
        prop = PropertyProfile.objects.get(property_id=property_id)
    except PropertyProfile.DoesNotExist:
        return json_err('物业不存在', status=404)

    community = Community(property=prop, community_name=community_name)
    community.save()
    return json_ok({
        'community_id': community.community_id,
        'community_name': community.community_name,
        'property_id': prop.property_id,
        'property_name': prop.property_name,
        'updated_at': community.updated_at.strftime('%Y-%m-%d %H:%M:%S') if community.updated_at else None,
    }, status=201)


@admin_token_required
@require_http_methods(["PUT", "DELETE"])
def admin_communities_detail(request, admin, community_id):
    """小区管理 - PUT更新 / DELETE删除（使用 community_id）"""
    try:
        community = Community.objects.select_related('property').get(community_id=community_id)
    except Community.DoesNotExist:
        return json_err('小区不存在', status=404)

    if request.method == 'DELETE':
        community.delete()
        return json_ok({'community_id': community_id, 'deleted': True})

    # PUT 更新
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)

    if 'community_name' in body:
        community.community_name = (body.get('community_name') or '').strip()
    if 'property_id' in body:
        property_id = (body.get('property_id') or '').strip()
        if property_id:
            try:
                prop = PropertyProfile.objects.get(property_id=property_id)
            except PropertyProfile.DoesNotExist:
                return json_err('物业不存在', status=404)
            community.property = prop

    community.save()
    return json_ok({
        'community_id': community.community_id,
        'community_name': community.community_name,
        'property_id': community.property.property_id if community.property else None,
        'property_name': community.property.property_name if community.property else None,
        'updated_at': community.updated_at.strftime('%Y-%m-%d %H:%M:%S') if community.updated_at else None,
    })

