"""管理员积分管理视图"""
import json
import logging
from django.views.decorators.http import require_http_methods
from django.db.models import Q

from wxcloudrun.decorators import admin_token_required
from wxcloudrun.utils.responses import json_ok, json_err
from wxcloudrun.models import UserInfo, PointsRecord
from wxcloudrun.services.points_service import get_points_share_setting


logger = logging.getLogger('log')


@admin_token_required
@require_http_methods(["GET", "PUT"])
def admin_share_setting(request, admin):
    """积分发放规则配置 - GET查询 / PUT更新

    规则说明：
    - 商户积分：消费金额 1:1（小数抹掉）
    - 业主奖励：按配置比例(%)发放（取整）
    """
    setting = get_points_share_setting()

    if request.method == 'GET':
        return json_ok({
            'merchant_rate': 100,
            'owner_rate': setting.merchant_rate,
        })

    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)

    owner_rate = body.get('owner_rate')
    # 兼容旧字段：merchant_rate 过去用于“商户分成”，现在作为业主奖励比例
    if owner_rate is None:
        owner_rate = body.get('merchant_rate')
    if owner_rate is None:
        return json_err('缺少参数 owner_rate', status=400)

    try:
        owner_rate = int(owner_rate)
    except ValueError:
        return json_err('owner_rate 必须是整数', status=400)

    if owner_rate < 0 or owner_rate > 100:
        return json_err('owner_rate 必须在 0-100 之间', status=400)

    setting.merchant_rate = owner_rate
    setting.save()

    return json_ok({
        'merchant_rate': 100,
        'owner_rate': setting.merchant_rate,
    })


@admin_token_required
@require_http_methods(["GET"])
def admin_points_records(request, admin):
    def build_source_text(record: PointsRecord) -> str:
        source_type = getattr(record, 'source_type', '') or ''
        meta = getattr(record, 'source_meta', None) or {}

        if source_type == 'PROPERTY_FEE_PAY':
            property_name = meta.get('property_name') or ''
            property_id = meta.get('property_id') or ''
            points = meta.get('points')
            direction = meta.get('direction') or ''
            if direction == 'owner_debit':
                return f'物业费抵扣：向{property_name}({property_id})抵扣 {points} 积分'
            if direction == 'property_credit':
                owner_system_id = meta.get('owner_system_id') or ''
                return f'物业费抵扣：业主{owner_system_id}抵扣转入 {points} 积分'
            return f'物业费抵扣：{property_name}({property_id}) {points} 积分'

        if source_type == 'MERCHANT_SETTLEMENT':
            merchant_name = meta.get('merchant_name') or ''
            merchant_id = meta.get('merchant_id') or ''
            phone_number = meta.get('target_phone_number') or ''
            amount = meta.get('amount') or meta.get('amount_int')
            owner_rate = meta.get('owner_rate')
            parts = [f'商户结算：{merchant_name}({merchant_id})']
            if phone_number:
                parts.append(f'业主手机号 {phone_number}')
            if amount is not None:
                parts.append(f'金额 {amount}')
            if owner_rate is not None:
                parts.append(f'业主奖励 {owner_rate}%')
            return '，'.join(parts)

        if source_type == 'OWNER_SETTLEMENT':
            merchant_name = meta.get('merchant_name') or ''
            merchant_id = meta.get('merchant_id') or ''
            if merchant_name or merchant_id:
                return f'业主结算：来自{merchant_name}({merchant_id})'
            return '业主结算'

        if source_type == 'ADMIN_ADJUST':
            operator = meta.get('operator') or {}
            username = operator.get('username') or ''
            old_total = meta.get('old_total_points')
            new_total = meta.get('new_total_points')
            if old_total is not None and new_total is not None:
                return f'管理员调整：{username}，累计积分 {old_total} → {new_total}'
            return f'管理员调整：{username}'

        return source_type or '-'

    current_param = request.GET.get('current') or request.GET.get('page')
    size_param = request.GET.get('size') or request.GET.get('page_size') or request.GET.get('limit')
    openid = (request.GET.get('openid') or '').strip()
    system_id = (request.GET.get('system_id') or '').strip()
    keyword = (request.GET.get('keyword') or '').strip()
    identity_type = (request.GET.get('identity_type') or '').strip().upper()
    source_type = (request.GET.get('source_type') or '').strip()

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

    qs = PointsRecord.objects.select_related('user').all().order_by('-created_at', '-id')
    if openid:
        qs = qs.filter(user__openid=openid)
    if system_id:
        qs = qs.filter(user__system_id=system_id)
    if keyword:
        qs = qs.filter(
            Q(user__openid__icontains=keyword)
            | Q(user__system_id__icontains=keyword)
            | Q(user__phone_number__icontains=keyword)
            | Q(user__nickname__icontains=keyword)
        )
    if identity_type in {'OWNER', 'MERCHANT', 'PROPERTY'}:
        qs = qs.filter(identity_type=identity_type)
    if source_type:
        qs = qs.filter(source_type=source_type)

    total = qs.count()
    start = (page - 1) * page_size
    records = list(qs[start : start + page_size])
    items = []
    for record in records:
        user = record.user
        items.append({
            'id': record.id,
            'openid': user.openid,
            'system_id': user.system_id,
            'nickname': user.nickname,
            'identity_type': getattr(record, 'identity_type', None),
            'delta': record.change,
            'change': record.change,
            'daily_points': getattr(record, 'daily_points', 0),
            'total_points': getattr(record, 'total_points', 0),
            'source_type': getattr(record, 'source_type', '') or '',
            'source_meta': getattr(record, 'source_meta', {}) or {},
            'source_text': build_source_text(record),
            'created_at': record.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        })
    return json_ok({'list': items, 'total': total})
