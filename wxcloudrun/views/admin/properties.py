"""管理员物业管理视图"""
import json
import logging
from django.views.decorators.http import require_http_methods

from wxcloudrun.decorators import admin_token_required
from wxcloudrun.utils.responses import json_ok, json_err
from wxcloudrun.models import UserInfo, PropertyProfile, PointsThreshold


logger = logging.getLogger('log')


@admin_token_required
@require_http_methods(["GET"])
def admin_properties(request, admin):
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

    qs = PropertyProfile.objects.select_related('user').all().order_by('-updated_at', '-id')
    total = qs.count()
    start = (page - 1) * page_size
    properties = list(qs[start : start + page_size])
    property_ids = [p.id for p in properties]
    thresholds = {th.property.id: th.min_points for th in PointsThreshold.objects.select_related('property').filter(property_id__in=property_ids)}
    items = []
    for p in properties:
        min_points = thresholds.get(p.id, 0)
        items.append({
            'openid': p.user.openid if p.user else None,
            'property_id': p.property_id,
            'property_name': p.property_name,
            'community_name': p.community_name,
            'daily_points': p.user.daily_points if p.user else 0,
            'total_points': p.user.total_points if p.user else 0,
            'min_points': min_points,
        })
    return json_ok({'list': items, 'total': total})


@admin_token_required
@require_http_methods(["PUT", "DELETE"])
def admin_properties_detail(request, admin, openid):
    """物业管理 - PUT更新 / DELETE删除（使用 openid）"""
    try:
        user = UserInfo.objects.get(openid=openid)
    except UserInfo.DoesNotExist:
        return json_err('用户不存在', status=404)
    
    try:
        property_profile = PropertyProfile.objects.get(user=user)
    except PropertyProfile.DoesNotExist:
        return json_err('物业不存在', status=404)
    
    if request.method == 'DELETE':
        property_profile.delete()
        return json_ok({'openid': openid, 'deleted': True})
    
    # PUT 更新
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)
    
    if 'property_name' in body:
        property_profile.property_name = body['property_name']
    if 'community_name' in body:
        property_profile.community_name = body.get('community_name', '')
    
    # 更新积分阈值
    if 'min_points' in body:
        min_points = body.get('min_points')
        if min_points is not None:
            PointsThreshold.objects.update_or_create(
                property=property_profile,
                defaults={'min_points': int(min_points)}
            )
        elif min_points is None and hasattr(property_profile, 'points_threshold'):
            # 如果传入 null，删除积分阈值
            property_profile.points_threshold.delete()
    
    property_profile.save()
    
    # 获取积分阈值
    min_points_value = 0
    try:
        if hasattr(property_profile, 'points_threshold'):
            min_points_value = property_profile.points_threshold.min_points
    except Exception:
        pass
    
    return json_ok({
        'openid': property_profile.user.openid,
        'property_id': property_profile.property_id,
        'property_name': property_profile.property_name,
        'community_name': property_profile.community_name,
        'daily_points': property_profile.user.daily_points,
        'total_points': property_profile.user.total_points,
        'min_points': min_points_value,
    })

