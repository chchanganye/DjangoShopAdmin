"""小程序端积分相关视图"""
import json
import logging
from decimal import Decimal, InvalidOperation
from django.views.decorators.http import require_http_methods
from django.db import transaction

from wxcloudrun.decorators import openid_required
from wxcloudrun.utils.responses import json_ok, json_err
from wxcloudrun.utils.auth import get_openid
from wxcloudrun.models import UserInfo, PropertyProfile, MerchantProfile, PointsThreshold
from wxcloudrun.services.points_service import (
    change_points_account,
    get_points_account_for_update,
    get_points_share_setting,
)
from wxcloudrun.services.order_service import create_settlement_order


logger = logging.getLogger('log')


@openid_required
@require_http_methods(["POST"])
def owner_property_fee_pay(request):
    """业主使用积分抵扣物业费：业主扣积分，物业加积分"""
    openid = get_openid(request)
    if not openid:
        return json_err('缺少openid', status=401)

    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)

    points = body.get('points')
    if points is None:
        return json_err('缺少参数 points', status=400)

    try:
        points_int = int(points)
    except (TypeError, ValueError):
        return json_err('points 必须是整数', status=400)

    if points_int <= 0:
        return json_err('points 必须为正整数', status=400)

    try:
        owner_user = UserInfo.objects.select_related(
            'owner_community__property__user',
            'owner_property__user',
        ).get(openid=openid)
    except UserInfo.DoesNotExist:
        return json_err('用户不存在', status=404)

    if owner_user.active_identity != 'OWNER':
        return json_err('仅业主身份可操作', status=403)

    property_profile = None
    if getattr(owner_user, 'owner_community', None) and owner_user.owner_community:
        property_profile = owner_user.owner_community.property
    elif getattr(owner_user, 'owner_property', None) and owner_user.owner_property:
        property_profile = owner_user.owner_property

    if not property_profile:
        return json_err('请先绑定小区', status=400)

    property_user = getattr(property_profile, 'user', None)
    if not property_user:
        return json_err('未找到对应物业账号', status=404)

    with transaction.atomic():
        lock_pairs = sorted(
            [(owner_user, 'OWNER'), (property_user, 'PROPERTY')],
            key=lambda pair: (pair[0].id, pair[1]),
        )
        locked_accounts = {}
        for lock_user, lock_identity in lock_pairs:
            locked_accounts[(lock_user.id, lock_identity)] = get_points_account_for_update(lock_user, lock_identity)

        owner_account = locked_accounts[(owner_user.id, 'OWNER')]
        property_account = locked_accounts[(property_user.id, 'PROPERTY')]

        if owner_account.total_points < points_int:
            return json_err('积分余额不足', status=400)

        transfer_meta = {
            'action': 'owner_property_fee_pay',
            'points': points_int,
            'owner_system_id': owner_user.system_id,
            'owner_openid': owner_user.openid,
            'property_id': property_profile.property_id,
            'property_name': property_profile.property_name,
            'property_system_id': property_user.system_id,
            'property_openid': property_user.openid,
        }
        owner_account = change_points_account(
            owner_account,
            -points_int,
            source_type='PROPERTY_FEE_PAY',
            source_meta={**transfer_meta, 'direction': 'owner_debit'},
        )
        property_account = change_points_account(
            property_account,
            points_int,
            source_type='PROPERTY_FEE_PAY',
            source_meta={**transfer_meta, 'direction': 'property_credit'},
        )

    return json_ok({
        'points': points_int,
        'owner': {
            'system_id': owner_user.system_id,
            'daily_points': owner_account.daily_points,
            'total_points': owner_account.total_points,
        },
        'property': {
            'property_id': property_profile.property_id,
            'property_name': property_profile.property_name,
            'daily_points': property_account.daily_points,
            'total_points': property_account.total_points,
        },
    })


@openid_required
@require_http_methods(["GET"])
def threshold_query(request, openid):
    """查询物业积分阈值（小程序端，使用 openid）"""
    try:
        user = UserInfo.objects.get(openid=openid)
        if user.identity_type != 'PROPERTY':
            return json_err('该用户不是物业身份', status=400)
    except UserInfo.DoesNotExist:
        return json_err('用户不存在', status=404)
    
    try:
        prop = PropertyProfile.objects.get(user=user)
    except PropertyProfile.DoesNotExist:
        return json_err('物业不存在', status=404)
    
    try:
        th = PointsThreshold.objects.get(property=prop)
        data = {'openid': openid, 'min_points': th.min_points}
    except PointsThreshold.DoesNotExist:
        data = {'openid': openid, 'min_points': 0}
    return json_ok(data)


@openid_required
@require_http_methods(["POST"])
def points_change(request):
    """业主发起积分变更（仅允许增加积分）"""
    openid = get_openid(request)

    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)

    delta = body.get('delta')
    merchant_id = body.get('merchant_id')

    if delta is None or merchant_id is None:
        return json_err('缺少参数 delta 或 merchant_id', status=400)

    try:
        delta = int(delta)
    except ValueError:
        return json_err('delta 必须是整数', status=400)

    if delta <= 0:
        return json_err('delta 必须为正整数', status=400)

    try:
        owner_user = UserInfo.objects.select_related('owner_property').get(openid=openid)
    except UserInfo.DoesNotExist:
        return json_err('用户不存在', status=404)

    if owner_user.active_identity != 'OWNER':
        return json_err('仅业主可发起积分变更', status=403)

    try:
        merchant = MerchantProfile.objects.select_related('user').get(merchant_id=merchant_id)
    except MerchantProfile.DoesNotExist:
        return json_err('商户不存在', status=404)

    merchant_user = merchant.user

    # 当前规则：业主积分全额增加；商户积分按消费金额 1:1 增加；不再给物业发放积分
    merchant_points = delta
    property_profile = owner_user.owner_property
    property_points = 0

    with transaction.atomic():
        lock_pairs = sorted(
            [(owner_user, 'OWNER'), (merchant_user, 'MERCHANT')],
            key=lambda pair: (pair[0].id, pair[1]),
        )
        locked_accounts = {}
        for lock_user, lock_identity in lock_pairs:
            locked_accounts[(lock_user.id, lock_identity)] = get_points_account_for_update(lock_user, lock_identity)

        owner_account = locked_accounts[(owner_user.id, 'OWNER')]
        merchant_account = locked_accounts[(merchant_user.id, 'MERCHANT')]

        owner_account = change_points_account(
            owner_account,
            delta,
            source_type='OWNER_SETTLEMENT',
            source_meta={
                'action': 'points_change',
                'merchant_id': merchant.merchant_id,
                'merchant_name': merchant.merchant_name,
            },
        )
        if merchant_points > 0:
            merchant_account = change_points_account(
                merchant_account,
                merchant_points,
                source_type='OWNER_SETTLEMENT',
                source_meta={
                    'action': 'points_change',
                    'merchant_id': merchant.merchant_id,
                    'merchant_name': merchant.merchant_name,
                },
            )

    return json_ok({
        'owner': {
            'system_id': owner_user.system_id,
            'daily_points': owner_account.daily_points,
            'total_points': owner_account.total_points,
        },
        'merchant': {
            'merchant_id': merchant.merchant_id,
            'points_added': merchant_points,
        },
        'property': {
            'property_id': property_profile.property_id,
            'points_added': property_points,
        } if property_profile else None,
    })


@openid_required
@require_http_methods(["POST"])
def merchant_points_add(request):
    """商户给用户增加积分（通过手机号和金额）"""
    openid = get_openid(request)
    try:
        merchant_user = UserInfo.objects.select_related('merchant_profile').get(openid=openid)
    except UserInfo.DoesNotExist:
        return json_err('用户不存在', status=404)

    if merchant_user.active_identity != 'MERCHANT':
        return json_err('仅商户身份可操作', status=403)

    try:
        merchant = merchant_user.merchant_profile
    except MerchantProfile.DoesNotExist:
        return json_err('商户档案不存在', status=400)

    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)

    phone_number = (body.get('user_phone_number') or body.get('phone_number') or '').strip()
    amount = body.get('amount')
    if not phone_number or amount is None:
        return json_err('缺少参数 user_phone_number 或 amount', status=400)

    try:
        amount_decimal = Decimal(str(amount))
    except InvalidOperation:
        return json_err('amount 必须为数字', status=400)

    if amount_decimal <= 0:
        return json_err('amount 必须大于 0', status=400)
    # 小数点直接抹掉（仅支持正数）
    delta = int(amount_decimal)
    if delta <= 0:
        return json_err('amount 必须不小于 1', status=400)

    target_user = UserInfo.objects.select_related('owner_property__user').filter(phone_number=phone_number).order_by('-id').first()
    if not target_user:
        return json_err('找不到该手机号用户', status=404)

    share_setting = get_points_share_setting()
    owner_rate = share_setting.merchant_rate
    owner_points = (delta * owner_rate) // 100
    merchant_points = delta

    with transaction.atomic():
        lock_pairs = sorted(
            [(merchant_user, 'MERCHANT'), (target_user, 'OWNER')],
            key=lambda pair: (pair[0].id, pair[1]),
        )
        locked_accounts = {}
        for lock_user, lock_identity in lock_pairs:
            locked_accounts[(lock_user.id, lock_identity)] = get_points_account_for_update(lock_user, lock_identity)

        merchant_account = locked_accounts[(merchant_user.id, 'MERCHANT')]
        owner_account = locked_accounts[(target_user.id, 'OWNER')]

        settlement_meta = {
            'action': 'merchant_points_add',
            'merchant_id': merchant.merchant_id,
            'merchant_name': merchant.merchant_name,
            'target_system_id': target_user.system_id,
            'target_openid': target_user.openid,
            'target_phone_number': target_user.phone_number,
            'amount': str(amount_decimal),
            'amount_int': delta,
            'merchant_rate': 100,
            'owner_rate': owner_rate,
        }

        if merchant_points > 0:
            merchant_account = change_points_account(
                merchant_account,
                merchant_points,
                source_type='MERCHANT_SETTLEMENT',
                source_meta={**settlement_meta, 'direction': 'merchant_credit'},
            )
        if owner_points > 0:
            owner_account = change_points_account(
                owner_account,
                owner_points,
                source_type='MERCHANT_SETTLEMENT',
                source_meta={**settlement_meta, 'direction': 'owner_credit'},
            )

        order = create_settlement_order(
            merchant=merchant,
            owner=target_user,
            amount=amount_decimal,
            amount_int=delta,
            merchant_points=merchant_points,
            owner_points=owner_points,
            owner_rate=owner_rate,
        )

    return json_ok({
        'target_user': {
            'system_id': target_user.system_id,
            'phone_number': target_user.phone_number,
            'daily_points': owner_account.daily_points,
            'total_points': owner_account.total_points,
            'points_added': owner_points,
        },
        'merchant': {
            'merchant_id': merchant.merchant_id,
            'points_added': merchant_points,
            'daily_points': merchant_account.daily_points,
            'total_points': merchant_account.total_points,
        },
        'share_ratio': {
            'merchant_rate': 100,
            'owner_rate': owner_rate,
        },
        'order': {
            'order_id': order.order_id,
            'status': order.status,
            'amount': str(order.amount),
            'amount_int': order.amount_int,
            'owner_points': order.owner_points,
            'merchant_points': order.merchant_points,
            'owner_rate': order.owner_rate,
            'created_at': order.created_at.strftime('%Y-%m-%d %H:%M:%S') if order.created_at else None,
        },
    })

