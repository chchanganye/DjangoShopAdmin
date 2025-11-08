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
    """查询积分变更记录（按 openid）"""
    openid = request.GET.get('openid')
    
    if not openid:
        return json_err('缺少参数 openid', status=400)
    
    try:
        user = UserInfo.objects.get(openid=openid)
    except UserInfo.DoesNotExist:
        return json_err('用户不存在', status=404)
    
    qs = PointsRecord.objects.filter(user=user).order_by('-created_at')
    items = []
    for record in qs:
        items.append({
            'id': record.id,
            'openid': user.openid,
            'system_id': user.system_id,
            'change': record.change,
            'created_at': record.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        })
    
    return json_ok({'total': len(items), 'list': items})

