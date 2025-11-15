"""管理员积分管理视图"""
import json
import logging
from django.views.decorators.http import require_http_methods

from wxcloudrun.decorators import admin_token_required
from wxcloudrun.utils.responses import json_ok, json_err
from wxcloudrun.models import UserInfo, PointsRecord
from wxcloudrun.services.points_service import get_points_share_setting


logger = logging.getLogger('log')


@admin_token_required
@require_http_methods(["GET", "PUT"])
def admin_share_setting(request, admin):
    """积分分成配置 - GET查询 / PUT更新"""
    setting = get_points_share_setting()

    if request.method == 'GET':
        return json_ok({
            'merchant_rate': setting.merchant_rate,
            'property_rate': 100 - setting.merchant_rate,
        })

    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)

    merchant_rate = body.get('merchant_rate')
    if merchant_rate is None:
        return json_err('缺少参数 merchant_rate', status=400)

    try:
        merchant_rate = int(merchant_rate)
    except ValueError:
        return json_err('merchant_rate 必须是整数', status=400)

    if merchant_rate < 0 or merchant_rate > 100:
        return json_err('merchant_rate 必须在 0-100 之间', status=400)

    setting.merchant_rate = merchant_rate
    setting.save()

    return json_ok({
        'merchant_rate': setting.merchant_rate,
        'property_rate': 100 - setting.merchant_rate,
    })


@admin_token_required
@require_http_methods(["GET"])
def admin_points_records(request, admin):
    openid = request.GET.get('openid')
    if not openid:
        return json_err('缺少参数 openid', status=400)
    try:
        user = UserInfo.objects.get(openid=openid)
    except UserInfo.DoesNotExist:
        return json_err('用户不存在', status=404)
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
    qs = PointsRecord.objects.filter(user=user).order_by('-created_at', '-id')
    if cursor_filter:
        cursor_dt, cursor_pk = cursor_filter
        qs = qs.filter(Q(created_at__lt=cursor_dt) | Q(created_at=cursor_dt, id__lt=cursor_pk))
    records = list(qs[: page_size + 1])
    has_more = len(records) > page_size
    sliced = records[:page_size]
    items = []
    for record in sliced:
        items.append({
            'id': record.id,
            'openid': user.openid,
            'system_id': user.system_id,
            'change': record.change,
            'created_at': record.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        })
    next_cursor = f"{sliced[-1].created_at.isoformat()}#{sliced[-1].id}" if has_more and sliced else None
    return json_ok({'list': items, 'has_more': has_more, 'next_cursor': next_cursor})

