"""小程序端积分相关视图"""
import json
import logging
from django.views.decorators.http import require_http_methods

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

