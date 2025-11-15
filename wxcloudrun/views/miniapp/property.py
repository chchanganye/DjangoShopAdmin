"""小程序端物业相关视图"""
from django.views.decorators.http import require_http_methods

from datetime import datetime
from django.db.models import Q
from django.utils.dateparse import parse_datetime
from wxcloudrun.decorators import openid_required
from wxcloudrun.utils.responses import json_ok, json_err
from wxcloudrun.models import PropertyProfile, UserInfo


@openid_required
@require_http_methods(["GET"])
def properties_list(request):
    """获取物业列表"""
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
    has_more = len(properties) > page_size
    sliced = properties[:page_size]
    items = []
    for p in sliced:
        items.append({
            'property_name': p.property_name,
            'community_name': p.community_name,
            'property_id': p.property_id,
        })
    next_cursor = f"{sliced[-1].updated_at.isoformat()}#{sliced[-1].id}" if has_more and sliced else None
    return json_ok({'list': items, 'has_more': has_more, 'next_cursor': next_cursor})


@openid_required
@require_http_methods(["GET"])
def owners_by_property(request, property_id):
    """按物业ID获取业主列表"""
    try:
        prop = PropertyProfile.objects.get(property_id=property_id)
    except PropertyProfile.DoesNotExist:
        return json_err('物业不存在', status=404)
    
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
    owners_qs = UserInfo.objects.filter(owner_property=prop, identity_type='OWNER').order_by('-updated_at', '-id')
    if cursor_filter:
        cursor_dt, cursor_pk = cursor_filter
        owners_qs = owners_qs.filter(Q(updated_at__lt=cursor_dt) | Q(updated_at=cursor_dt, id__lt=cursor_pk))
    owners = list(owners_qs[: page_size + 1])
    has_more = len(owners) > page_size
    sliced = owners[:page_size]
    items = []
    for o in sliced:
        items.append({
            'system_id': o.system_id,
            'openid': o.openid,
            'phone_number': o.phone_number,
            'daily_points': o.daily_points,
            'total_points': o.total_points,
        })
    next_cursor = f"{sliced[-1].updated_at.isoformat()}#{sliced[-1].id}" if has_more and sliced else None
    return json_ok({'list': items, 'has_more': has_more, 'next_cursor': next_cursor})

