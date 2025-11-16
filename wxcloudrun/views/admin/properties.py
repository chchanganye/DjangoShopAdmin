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
    from datetime import datetime
    from django.db.models import Q
    from django.utils.dateparse import parse_datetime
    limit_param = request.GET.get('limit')
    page_size = 20
    if limit_param:
        try:
            page_size = int(limit_param)
        except (TypeError, ValueError):
            return json_err('limit 必须为数字', status=400)
    if page_size < 1:
        page_size = 1
    if page_size > 100:
        page_size = 100
    cursor_param = (request.GET.get('cursor') or '').strip()
    cursor_filter = None
    if cursor_param:
        parts = cursor_param.split('#', 1)
        if len(parts) == 2:
            ts_str, pk_str = parts
            dt = parse_datetime(ts_str)
            if not dt:
                try:
                    dt = datetime.fromisoformat(ts_str)
                except ValueError:
                    dt = None
            try:
                pk_val = int(pk_str)
            except (TypeError, ValueError):
                pk_val = None
            if dt and pk_val is not None:
                cursor_filter = (dt, pk_val)
        if not cursor_filter:
            return json_err('cursor 无效', status=400)
    qs = PropertyProfile.objects.select_related('user').all().order_by('-updated_at', '-id')
    if cursor_filter:
        cursor_dt, cursor_pk = cursor_filter
        qs = qs.filter(Q(updated_at__lt=cursor_dt) | Q(updated_at=cursor_dt, id__lt=cursor_pk))
    properties = list(qs[: page_size + 1])
    property_ids = [p.id for p in properties[:page_size]]
    thresholds = {th.property.id: th.min_points for th in PointsThreshold.objects.select_related('property').filter(property_id__in=property_ids)}
    has_more = len(properties) > page_size
    sliced = properties[:page_size]
    items = []
    for p in sliced:
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
    next_cursor = f"{sliced[-1].updated_at.isoformat()}#{sliced[-1].id}" if has_more and sliced else None
    return json_ok({'list': items, 'has_more': has_more, 'next_cursor': next_cursor})


@admin_token_required
@require_http_methods(["PUT", "DELETE"])
def admin_properties_detail(request, admin, openid):
    """物业管理 - PUT更新 / DELETE删除（使用 openid）"""
    try:
        user = UserInfo.objects.get(openid=openid)
        if user.active_identity != 'PROPERTY':
            return json_err('该用户不是物业身份', status=400)
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

