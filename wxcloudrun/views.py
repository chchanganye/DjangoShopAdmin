import json
import logging
from datetime import date

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from wxcloudrun.models import (
    Category,
    UserInfo,
    MerchantProfile,
    PropertyProfile,
    PointsThreshold,
    PointsRecord,
    ApiPermission,
)


logger = logging.getLogger('log')


def index(request, _):
    """
    获取主页

     `` request `` 请求对象
    """

    return render(request, 'index.html')


# 已移除官方示例计数器接口（与本项目无关）


# ---------------------- 通用工具与权限管理 ----------------------

def json_ok(data=None, status=200, message='success'):
    """统一成功响应结构
    - code: 业务状态码，默认等于 HTTP 状态码（200/201/204等）
    - message: 人类可读提示，默认 'success'
    - data: 成功时返回的数据；若传入 None，返回空对象 {}
    """
    payload = {
        'code': status,
        'message': message,
        'data': {} if data is None else data,
    }
    return JsonResponse(payload, status=status, json_dumps_params={'ensure_ascii': False})


def json_err(message='错误', code=None, status=400):
    """统一错误响应结构
    - code: 业务状态码，默认等于 HTTP 状态码（400/401/403/404/500等）
    - message: 错误信息
    - data: 错误时固定为 None
    """
    payload = {
        'code': code or status,
        'message': message,
        'data': None,
    }
    return JsonResponse(payload, status=status, json_dumps_params={'ensure_ascii': False})


def _get_openid(request):
    """仅从 request.headers 读取微信云托管注入的 OpenID，不做任何回退或兼容逻辑。"""
    return request.headers.get('X-WX-OPENID')


def _get_user_by_openid(openid):
    try:
        return UserInfo.objects.get(openid=openid)
    except UserInfo.DoesNotExist:
        return None


def permission_required(endpoint_name):
    def decorator(view_func):
        def _wrapped(request, *args, **kwargs):
            openid = _get_openid(request)
            if not openid:
                return json_err('缺少openid', status=401)
            user = _get_user_by_openid(openid)
            if not user:
                return json_err('用户不存在，请先注册', status=401)

            # 管理员拥有所有权限
            if user.identity_type == 'ADMIN':
                return view_func(request, user=user, *args, **kwargs)

            method = request.method.upper()
            try:
                perm = ApiPermission.objects.get(endpoint_name=endpoint_name, method=method)
                allowed = perm.allowed_list()
            except ApiPermission.DoesNotExist:
                allowed = ['OWNER', 'PROPERTY', 'MERCHANT', 'ADMIN']

            if user.identity_type not in allowed:
                return json_err('没有权限访问此接口', status=403)
            return view_func(request, user=user, *args, **kwargs)
        return _wrapped
    return decorator


def openid_required(view_func):
    """仅校验 OpenID 是否存在，存在则放行。不做身份或权限校验。
    适用于小程序通过 wx.cloud.callContainer 自动注入请求头的场景。
    """
    def _wrapped(request, *args, **kwargs):
        openid = _get_openid(request)
        if not openid:
            return json_err('缺少openid', status=401)
        return view_func(request, *args, **kwargs)
    return _wrapped


def _ensure_daily_reset(user: UserInfo):
    today = date.today()
    if user.daily_points_date != today:
        user.daily_points = 0
        user.daily_points_date = today
        user.save()


def change_user_points(user: UserInfo, delta: int):
    _ensure_daily_reset(user)
    user.daily_points += int(delta)
    user.total_points += int(delta)
    user.save()
    PointsRecord.objects.create(user=user, change=int(delta))
    return user


# ---------------------- 1. 商品分类管理接口 ----------------------

@openid_required
@require_http_methods(["GET"])
def categories_list(request):
    qs = Category.objects.all().order_by('id')
    items = [{'name': c.name, 'icon_name': c.icon_name} for c in qs]
    return json_ok({'total': qs.count(), 'list': items})


# ---------------------- 2. 用户信息管理接口 ----------------------

@permission_required('users_list')
@require_http_methods(["GET"])
def users_list(request, user):
    qs = UserInfo.objects.select_related('owner_property').all().order_by('id')
    def to_dict(u: UserInfo):
        return {
            'system_id': u.system_id,
            'openid': u.openid,
            'avatar_url': u.avatar_url,
            'phone_number': u.phone_number,
            'identity_type': u.identity_type,
            'daily_points': u.daily_points,
            'total_points': u.total_points,
            'owner_property_id': u.owner_property.property_id if u.owner_property else None,
            'owner_property_name': u.owner_property.property_name if u.owner_property else None,
        }
    return json_ok({'total': qs.count(), 'list': [to_dict(u) for u in qs]})


# ---------------------- 3. 商户信息专用接口 ----------------------

@openid_required
@require_http_methods(["GET"])
def merchants_list(request):
    qs = MerchantProfile.objects.select_related('user', 'category').all().order_by('id')
    items = []
    for m in qs:
        items.append({
            'description': m.description,
            'banner_urls': m.banner_list(),
            'category': m.category.name if m.category else None,
            'contact_phone': m.contact_phone,
            'merchant_name': m.merchant_name,
            'title': m.title,
            'address': m.address,
            'positive_rating_percent': m.positive_rating_percent,
            'merchant_id': m.merchant_id,
        })
    return json_ok({'total': qs.count(), 'list': items})


# ---------------------- 4. 物业信息专用接口 ----------------------

@openid_required
@require_http_methods(["GET"])
def properties_list(request):
    qs = PropertyProfile.objects.select_related('user').all().order_by('id')
    items = []
    for p in qs:
        items.append({
            'property_name': p.property_name,
            'community_name': p.community_name,
            'openid': p.user.openid,
            'property_id': p.property_id,
        })
    return json_ok({'total': qs.count(), 'list': items})


# ---------------------- 5. 业主信息查询接口（按物业ID） ----------------------

@openid_required
@require_http_methods(["GET"])
def owners_by_property(request, property_id):
    try:
        prop = PropertyProfile.objects.get(property_id=property_id)
    except PropertyProfile.DoesNotExist:
        return json_err('物业不存在', status=404)

    qs = UserInfo.objects.filter(identity_type='OWNER', owner_property=prop).order_by('id')
    def to_dict(u: UserInfo):
        return {
            'owner_id': u.system_id,
            'property_name': prop.property_name,
            'openid': u.openid,
            'avatar_url': u.avatar_url,
            'phone_number': u.phone_number,
            'identity_type': u.identity_type,
            'daily_points': u.daily_points,
            'total_points': u.total_points,
        }
    return json_ok({'total': qs.count(), 'list': [to_dict(u) for u in qs]})


# ---------------------- 6. 积分阈值管理系统 ----------------------

@openid_required
@require_http_methods(["GET"])
def threshold_query(request, property_id):
    try:
        prop = PropertyProfile.objects.get(property_id=property_id)
    except PropertyProfile.DoesNotExist:
        return json_err('物业不存在', status=404)
    try:
        th = PointsThreshold.objects.get(property=prop)
        data = {'property_id': prop.property_id, 'min_points': th.min_points}
    except PointsThreshold.DoesNotExist:
        data = {'property_id': prop.property_id, 'min_points': 0}
    return json_ok(data)


# 管理员配置接口（阈值CRUD）
@permission_required('admin_threshold_create')
@require_http_methods(["POST"])
def admin_threshold_create(request, user):
    # 仅管理员能访问（装饰器已允许管理员直通），其他身份需在权限表中放行
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)
    property_id = body.get('property_id')
    min_points = body.get('min_points')
    if property_id is None or min_points is None:
        return json_err('缺少参数 property_id 或 min_points', status=400)
    try:
        prop = PropertyProfile.objects.get(property_id=property_id)
    except PropertyProfile.DoesNotExist:
        return json_err('物业不存在', status=404)
    th, _ = PointsThreshold.objects.update_or_create(property=prop, defaults={'min_points': int(min_points)})
    return json_ok({'property_id': prop.property_id, 'min_points': th.min_points}, status=201)


@permission_required('admin_threshold_update')
@require_http_methods(["PUT", "DELETE"])
def admin_threshold_update(request, user, property_id):
    try:
        prop = PropertyProfile.objects.get(property_id=property_id)
    except PropertyProfile.DoesNotExist:
        return json_err('物业不存在', status=404)

    if request.method.upper() == 'DELETE':
        PointsThreshold.objects.filter(property=prop).delete()
        return json_ok({'property_id': prop.property_id, 'deleted': True})

    # PUT
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)
    min_points = body.get('min_points')
    if min_points is None:
        return json_err('缺少参数 min_points', status=400)
    th, _ = PointsThreshold.objects.update_or_create(property=prop, defaults={'min_points': int(min_points)})
    return json_ok({'property_id': prop.property_id, 'min_points': th.min_points})


# 删除接口已合并到 admin_threshold_update（DELETE 方法）


# ---------------------- 7. 积分统计逻辑（示例接口：变更积分） ----------------------

@permission_required('points_change')
@require_http_methods(["POST"])
def points_change(request, user):
    # 对当前请求用户的积分进行变更（正负皆可），用于演示每日清零+历史累计
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)
    delta = body.get('delta')
    if delta is None:
        return json_err('缺少参数 delta', status=400)
    updated_user = change_user_points(user, int(delta))
    return json_ok({
        'system_id': updated_user.system_id,
        'daily_points': updated_user.daily_points,
        'total_points': updated_user.total_points,
    })


# ---------------------- 接口权限配置（管理员可管理） ----------------------

@permission_required('admin_api_permissions')
@require_http_methods(["GET", "POST"])
def admin_api_permissions(request, user):
    if request.method.upper() == 'GET':
        qs = ApiPermission.objects.all().order_by('endpoint_name', 'method')
        data = [{
            'endpoint_name': p.endpoint_name,
            'method': p.method,
            'allowed_identities': p.allowed_list(),
        } for p in qs]
        return json_ok({'total': qs.count(), 'list': data})
    else:
        try:
            body = json.loads(request.body.decode('utf-8'))
        except Exception:
            return json_err('请求体格式错误', status=400)
        endpoint_name = body.get('endpoint_name')
        method = body.get('method', 'GET').upper()
        allowed = body.get('allowed_identities')
        if not endpoint_name or not allowed:
            return json_err('缺少参数 endpoint_name 或 allowed_identities', status=400)
        if isinstance(allowed, list):
            allowed_str = ','.join(allowed)
        else:
            allowed_str = str(allowed)
        obj, _ = ApiPermission.objects.update_or_create(
            endpoint_name=endpoint_name, method=method,
            defaults={'allowed_identities': allowed_str}
        )
        return json_ok({
            'endpoint_name': obj.endpoint_name,
            'method': obj.method,
            'allowed_identities': obj.allowed_list(),
        }, status=201)



# 注：若需要保留演示页面，可在 templates/index.html 中展示静态内容或自定义引导，无需后端计数接口。
