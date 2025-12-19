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
from wxcloudrun.services.points_service import change_user_points, get_points_share_setting


logger = logging.getLogger('log')


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

    if owner_user.identity_type != 'OWNER':
        return json_err('仅业主可发起积分变更', status=403)

    if not owner_user.owner_property:
        return json_err('业主未关联物业，无法发起积分变更', status=400)

    property_profile = owner_user.owner_property

    try:
        merchant = MerchantProfile.objects.select_related('user').get(merchant_id=merchant_id)
    except MerchantProfile.DoesNotExist:
        return json_err('商户不存在', status=404)

    merchant_user = merchant.user

    share_setting = get_points_share_setting()
    merchant_rate = share_setting.merchant_rate
    merchant_points = (delta * merchant_rate) // 100
    property_points = delta - merchant_points
    if property_points < 0:
        property_points = 0

    owner_user = change_user_points(owner_user, delta)

    if merchant_points > 0:
        change_user_points(merchant_user, merchant_points)

    property_user = property_profile.user
    if property_points > 0:
        change_user_points(property_user, property_points)

    return json_ok({
        'owner': {
            'system_id': owner_user.system_id,
            'daily_points': owner_user.daily_points,
            'total_points': owner_user.total_points,
        },
        'merchant': {
            'merchant_id': merchant.merchant_id,
            'points_added': merchant_points,
        },
        'property': {
            'property_id': property_profile.property_id,
            'points_added': property_points,
        },
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
    if amount_decimal != amount_decimal.to_integral_value():
        return json_err('amount 必须为整数', status=400)
    delta = int(amount_decimal)
    if delta <= 0:
        return json_err('amount 必须为正整数', status=400)

    target_user = UserInfo.objects.select_related('owner_property__user').filter(phone_number=phone_number).order_by('-id').first()
    if not target_user:
        return json_err('用户不存在', status=404)

    share_setting = get_points_share_setting()
    merchant_rate = share_setting.merchant_rate
    merchant_points = (delta * merchant_rate) // 100
    property_points = delta - merchant_points
    if property_points < 0:
        property_points = 0

    property_profile = target_user.owner_property
    property_user = getattr(property_profile, 'user', None) if property_profile else None
    # 如果用户未关联物业，物业分成记为0，剩余全部归商户
    if not property_user:
        merchant_points = delta
        property_points = 0

    with transaction.atomic():
        target_user = change_user_points(target_user, delta)
        if merchant_points > 0:
            merchant_user = change_user_points(merchant_user, merchant_points)
        if property_user and property_points > 0:
            change_user_points(property_user, property_points)

    return json_ok({
        'target_user': {
            'system_id': target_user.system_id,
            'phone_number': target_user.phone_number,
            'daily_points': target_user.daily_points,
            'total_points': target_user.total_points,
            'points_added': delta,
        },
        'merchant': {
            'merchant_id': merchant.merchant_id,
            'points_added': merchant_points,
        },
        'property': {
            'property_id': property_profile.property_id,
            'points_added': property_points,
        } if property_user else None,
        'share_ratio': {
            'merchant_rate': 100 if not property_user else merchant_rate,
            'property_rate': 0 if not property_user else (100 - merchant_rate),
        },
    })

