import json
import logging
from datetime import date
import time
import hmac
import hashlib

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from django.conf import settings

from rest_framework.authtoken.models import Token
import requests

from wxcloudrun.models import (
    Counters,
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


def counter(request, _):
    """
    获取当前计数

     `` request `` 请求对象
    """

    rsp = JsonResponse({'code': 0, 'errorMsg': ''}, json_dumps_params={'ensure_ascii': False})
    if request.method == 'GET' or request.method == 'get':
        rsp = get_count()
    elif request.method == 'POST' or request.method == 'post':
        rsp = update_count(request)
    else:
        rsp = JsonResponse({'code': -1, 'errorMsg': '请求方式错误'},
                            json_dumps_params={'ensure_ascii': False})
    logger.info('response result: {}'.format(rsp.content.decode('utf-8')))
    return rsp


# ---------------------- 通用工具与权限管理 ----------------------

def json_ok(data=None, status=200):
    return JsonResponse({'code': 0, 'data': data or {}}, status=status,
                        json_dumps_params={'ensure_ascii': False})


def json_err(message='错误', code=-1, status=400):
    return JsonResponse({'code': code, 'errorMsg': message}, status=status,
                        json_dumps_params={'ensure_ascii': False})


def _get_openid(request):
    # 微信云托管会在header中传递 openid
    # Django会将请求头转为META中的 HTTP_ 前缀
    openid = request.META.get('HTTP_X_WX_OPENID') or request.META.get('X-WX-OPENID')
    return openid


def _get_user_by_openid(openid):
    try:
        return UserInfo.objects.get(openid=openid)
    except UserInfo.DoesNotExist:
        return None


def _parse_auth_token(request):
    """
    从 Authorization 头中提取 DRF Token，支持以下格式：
    - Authorization: Token <key>
    - Authorization: Bearer <key>
    返回 (token_key 或 None)
    """
    header = request.META.get('HTTP_AUTHORIZATION') or request.headers.get('Authorization')
    if not header:
        return None
    parts = header.split()
    if len(parts) == 2 and parts[0].lower() in ('token', 'bearer'):
        return parts[1].strip()
    # 兼容纯 key
    if len(parts) == 1:
        return parts[0].strip()
    return None


def _get_user_by_token(request):
    """通过 Authorization 头中的 Token 获取业务用户(UserInfo)。"""
    token_key = _parse_auth_token(request)
    if not token_key:
        return None, '缺少或格式错误的 Authorization 头'
    try:
        t = Token.objects.get(key=token_key)
    except Token.DoesNotExist:
        return None, '无效的Token'
    # 使用 Django auth.User 的 username 作为 openid 映射
    openid = t.user.username
    user = _get_user_by_openid(openid)
    if not user:
        return None, '关联的用户不存在'
    if not user.wx_session_key:
        return None, '用户登录态无效，请重新登录'
    return user, None


def permission_required(endpoint_name):
    def decorator(view_func):
        def _wrapped(request, *args, **kwargs):
            # 优先通过 Authorization Token 鉴权
            user, err = _get_user_by_token(request)
            if err:
                return json_err(err, status=401)

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

@permission_required('categories_list')
@require_http_methods(["GET"])
def categories_list(request, user):
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

@permission_required('merchants_list')
@require_http_methods(["GET"])
def merchants_list(request, user):
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

@permission_required('properties_list')
@require_http_methods(["GET"])
def properties_list(request, user):
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

@permission_required('owners_by_property')
@require_http_methods(["GET"])
def owners_by_property(request, user, property_id):
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

@permission_required('threshold_query')
@require_http_methods(["GET"])
def threshold_query(request, user, property_id):
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


# ---------------------- 8. 微信登录与会话校验 ----------------------

def _wechat_access_token():
    """获取并缓存微信 access_token（后端内部使用）。"""
    cache = getattr(_wechat_access_token, '_cache', {'token': None, 'expires_at': 0})
    now = time.time()
    if cache['token'] and now < cache['expires_at'] - 300:
        return cache['token']
    if not settings.WX_APP_ID or not settings.WX_APP_SECRET:
        logger.error('缺少 APP_ID/APP_SECRET 环境变量，无法获取微信 access_token')
        return None
    try:
        resp = requests.get(
            'https://api.weixin.qq.com/cgi-bin/token',
            params={'grant_type': 'client_credential', 'appid': settings.WX_APP_ID, 'secret': settings.WX_APP_SECRET},
            timeout=8,
        )
        data = resp.json()
    except Exception as e:
        logger.error(f'调用微信获取access_token失败: {e}')
        return None
    if 'access_token' in data:
        token = data['access_token']
        expires_in = int(data.get('expires_in', 7200))
        cache = {'token': token, 'expires_at': now + expires_in}
        setattr(_wechat_access_token, '_cache', cache)
        return token
    else:
        logger.error(f'微信返回错误: {data}')
        return None


def _wechat_code2session(js_code: str):
    if not settings.WX_APP_ID or not settings.WX_APP_SECRET:
        return None, None, {'errcode': -1, 'errmsg': '缺少APP_ID/APP_SECRET环境变量'}
    try:
        resp = requests.get(
            'https://api.weixin.qq.com/sns/jscode2session',
            params={
                'appid': settings.WX_APP_ID,
                'secret': settings.WX_APP_SECRET,
                'js_code': js_code,
                'grant_type': 'authorization_code'
            },
            timeout=8,
        )
        data = resp.json()
    except Exception as e:
        return None, None, {'errcode': -1, 'errmsg': f'网络错误: {e}'}
    if 'openid' in data and 'session_key' in data:
        return data['openid'], data['session_key'], None
    return None, None, data


@require_http_methods(["POST"])
def auth_code2session(request):
    """
    前端使用 wx.login 获取 code 后调用此接口。
    成功时返回 {token, token_type: 'Token', openid}
    """
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)
    js_code = body.get('code') or body.get('js_code')
    if not js_code:
        return json_err('缺少参数 code', status=400)

    openid, session_key, err = _wechat_code2session(js_code)
    if err:
        # 直接透传微信错误
        return json_err(f"微信接口错误: {err.get('errmsg', '未知错误')}", code=err.get('errcode', -1), status=400)

    # 建立/更新业务用户
    user = _get_user_by_openid(openid)
    if not user:
        # 默认身份设为业主，可根据业务自行调整
        user = UserInfo(openid=openid, identity_type='OWNER')
    user.wx_session_key = session_key
    user.save()

    # 建立/获取 Django auth 用户 + DRF Token
    from django.contrib.auth.models import User as AuthUser
    auth_user, created = AuthUser.objects.get_or_create(username=openid, defaults={'is_active': True})
    if created:
        auth_user.set_unusable_password()
        auth_user.save()
    token, _ = Token.objects.get_or_create(user=auth_user)

    return json_ok({'token': token.key, 'token_type': 'Token', 'openid': openid})


@require_http_methods(["GET"])
def auth_check_session(request):
    """校验服务器保存的 session_key 是否有效。"""
    user, err = _get_user_by_token(request)
    if err:
        return json_err(err, status=401)
    access_token = _wechat_access_token()
    if not access_token:
        return json_err('获取access_token失败', status=500)
    # 计算签名: signature = hmac_sha256(session_key, "")
    signature = hmac.new(key=user.wx_session_key.encode('utf-8'), msg=b'', digestmod=hashlib.sha256).hexdigest()
    try:
        resp = requests.get(
            'https://api.weixin.qq.com/wxa/checksession',
            params={
                'access_token': access_token,
                'signature': signature,
                'openid': user.openid,
                'sig_method': 'hmac_sha256'
            },
            timeout=8,
        )
        data = resp.json()
    except Exception as e:
        return json_err(f'网络错误: {e}', status=400)
    if int(data.get('errcode', -1)) == 0:
        return json_ok({'valid': True, 'errmsg': data.get('errmsg', 'ok')})
    return json_err(data.get('errmsg', 'invalid'), code=data.get('errcode', 87009), status=400)


@require_http_methods(["GET"])
def admin_wechat_access_token(request):
    """仅管理员查看当前 access_token（便于排查）。"""
    user, err = _get_user_by_token(request)
    if err:
        return json_err(err, status=401)
    if user.identity_type != 'ADMIN':
        return json_err('没有权限访问此接口', status=403)
    token = _wechat_access_token()
    if not token:
        return json_err('获取access_token失败', status=500)
    return json_ok({'access_token': token})



def get_count():
    """
    获取当前计数
    """

    try:
        data = Counters.objects.get(id=1)
    except Counters.DoesNotExist:
        return JsonResponse({'code': 0, 'data': 0},
                    json_dumps_params={'ensure_ascii': False})
    return JsonResponse({'code': 0, 'data': data.count},
                        json_dumps_params={'ensure_ascii': False})


def update_count(request):
    """
    更新计数，自增或者清零

    `` request `` 请求对象
    """

    logger.info('update_count req: {}'.format(request.body))

    body_unicode = request.body.decode('utf-8')
    body = json.loads(body_unicode)

    if 'action' not in body:
        return JsonResponse({'code': -1, 'errorMsg': '缺少action参数'},
                            json_dumps_params={'ensure_ascii': False})

    if body['action'] == 'inc':
        try:
            data = Counters.objects.get(id=1)
        except Counters.DoesNotExist:
            data = Counters()
        data.id = 1
        data.count += 1
        data.save()
        return JsonResponse({'code': 0, "data": data.count},
                    json_dumps_params={'ensure_ascii': False})
    elif body['action'] == 'clear':
        try:
            data = Counters.objects.get(id=1)
            data.delete()
        except Counters.DoesNotExist:
            logger.info('record not exist')
        return JsonResponse({'code': 0, 'data': 0},
                    json_dumps_params={'ensure_ascii': False})
    else:
        return JsonResponse({'code': -1, 'errorMsg': 'action参数错误'},
                    json_dumps_params={'ensure_ascii': False})
