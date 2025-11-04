import json
import logging
import os
import uuid
from datetime import date

import requests
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth import authenticate
from django.contrib.auth.models import User

from wxcloudrun.models import (
    Category,
    UserInfo,
    MerchantProfile,
    PropertyProfile,
    PointsThreshold,
    PointsRecord,
    PointsShareSetting,
)
from rest_framework.authtoken.models import Token


logger = logging.getLogger('log')


class WxOpenApiError(Exception):
    pass


WX_OPENAPI_BASE = os.environ.get('WX_OPENAPI_BASE', 'http://api.weixin.qq.com')
WX_ENV_ID = os.environ.get('CLOUD_ID')
# 已移除官方示例计数器接口和 index 页面（本项目为纯 API 后端）


# ---------------------- 通用工具与权限管理 ----------------------

def json_ok(data=None, status=200, message='success'):
    """统一成功响应结构
    - code: 业务状态码，默认等于 HTTP 状态码（200/201/204等）
    - msg: 人类可读提示，默认 'success'
    - data: 成功时返回的数据；若传入 None，返回空对象 {}
    """
    payload = {
        'code': status,
        'msg': message,
        'data': {} if data is None else data,
    }
    return JsonResponse(payload, status=status, json_dumps_params={'ensure_ascii': False})


def json_err(message='错误', code=None, status=400):
    """统一错误响应结构
    - code: 业务状态码，默认等于 HTTP 状态码（400/401/403/404/500等）
    - msg: 错误信息
    - data: 错误时固定为 None
    """
    payload = {
        'code': code or status,
        'msg': message,
        'data': None,
    }
    return JsonResponse(payload, status=status, json_dumps_params={'ensure_ascii': False})


def _get_openid(request):
    """仅从 request.headers 读取微信云托管注入的 OpenID，不做任何回退或兼容逻辑。"""
    return request.headers.get('X-WX-OPENID')


def _parse_auth_header(request):
    """从 Authorization 头中解析出可能的 Token 值。
    支持格式：
      - Authorization: Token <key>
      - Authorization: Bearer <key>
      - Authorization: token <key>
    返回 token_key 或 None。
    """
    auth = request.headers.get('Authorization') or request.META.get('HTTP_AUTHORIZATION')
    if not auth:
        return None
    parts = auth.strip().split()
    if len(parts) == 2 and parts[0].lower() in ('token', 'bearer'):
        return parts[1]
    # 仅有纯token的情况
    if len(parts) == 1:
        return parts[0]
    return None


def _get_admin_from_token(request):
    """校验 Authorization Token 并返回 Django 用户（仅限管理员）。
    仅当 user.is_superuser 为真时视为管理员。验证失败返回 None。
    """
    token_key = _parse_auth_header(request)
    if not token_key:
        return None
    try:
        token = Token.objects.select_related('user').get(key=token_key)
        user = token.user
        if user and user.is_superuser:
            return user
        return None
    except Token.DoesNotExist:
        return None


def openid_required(view_func):
    """仅校验 OpenID 是否存在，存在则放行。不做身份或权限校验。
    适用于小程序通过 wx.cloud.callContainer 自动注入请求头的场景。
    """
    def _wrapped(request, *args, **kwargs):
        # 管理员Token优先直通
        admin = _get_admin_from_token(request)
        if admin:
            return view_func(request, *args, **kwargs)

        openid = _get_openid(request)
        if not openid:
            return json_err('缺少openid', status=401)
        return view_func(request, *args, **kwargs)
    return _wrapped


def admin_token_required(view_func):
    """仅允许持有有效管理员 Token 的请求通过。"""
    def _wrapped(request, *args, **kwargs):
        admin = _get_admin_from_token(request)
        if not admin:
            return json_err('未认证或无权限', status=401)
        return view_func(request, admin=admin, *args, **kwargs)
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


def wx_openapi_post(path: str, payload: dict):
    if not WX_ENV_ID:
        raise WxOpenApiError('未配置 CLOUD_ID 环境变量')

    url = f"{WX_OPENAPI_BASE.rstrip('/')}/{path.lstrip('/')}"
    headers = {'Content-Type': 'application/json'}
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        resp.raise_for_status()
    except Exception as exc:
        logger.error(f'请求微信开放接口失败: {path}, error={exc}')
        raise WxOpenApiError('调用微信开放接口失败') from exc

    try:
        data = resp.json()
    except ValueError as exc:
        logger.error(f'解析微信开放接口响应失败: {path}, resp={resp.text}')
        raise WxOpenApiError('微信开放接口返回格式错误') from exc

    if data.get('errcode') != 0:
        logger.error(f'微信开放接口返回错误: {path}, payload={payload}, resp={data}')
        raise WxOpenApiError(data.get('errmsg') or '微信开放接口返回错误')
    return data


def get_temp_file_urls(file_ids):
    if not file_ids:
        return {}
    try:
        data = wx_openapi_post('tcb/batchdownloadfile', {
            'env': WX_ENV_ID,
            'file_list': [{'fileid': fid, 'max_age': 7200} for fid in file_ids],
        })
    except WxOpenApiError:
        return {}

    url_map = {}
    for item in data.get('file_list', []):
        if item.get('status') == 0:
            url_map[item['fileid']] = item.get('download_url')
    return url_map


def resolve_icon_url(icon_value, temp_map=None):
    if not icon_value:
        return ''
    if icon_value.startswith('cloud://'):
        return (temp_map or {}).get(icon_value, '')
    if icon_value.startswith('http://') or icon_value.startswith('https://'):
        return icon_value
    return ''


def get_points_share_setting():
    return PointsShareSetting.get_solo()


# ---------------------- 1. 商品分类管理接口 ----------------------

@openid_required
@require_http_methods(["GET"])
def categories_list(request):
    qs = Category.objects.all().order_by('id')
    icon_file_ids = [c.icon_name for c in qs if c.icon_name and c.icon_name.startswith('cloud://')]
    temp_urls = get_temp_file_urls(icon_file_ids)

    items = []
    for c in qs:
        icon_file_id = c.icon_name or ''
        icon_url = resolve_icon_url(icon_file_id, temp_urls)
        items.append({
            'name': c.name,
            'icon_name': icon_file_id,
            'icon_file_id': icon_file_id,
            'icon_url': icon_url,
        })
    return json_ok({'total': qs.count(), 'list': items})


@openid_required
@require_http_methods(["GET"])
def user_profile(request):
    openid = _get_openid(request)
    try:
        user = UserInfo.objects.select_related('owner_property__points_threshold').get(openid=openid)
    except UserInfo.DoesNotExist:
        return json_err('用户不存在', status=404)

    data = {
        'system_id': user.system_id,
        'openid': user.openid,
        'identity_type': user.identity_type,
        'avatar_url': user.avatar_url,
        'phone_number': user.phone_number,
        'daily_points': user.daily_points,
        'total_points': user.total_points,
    }

    if user.owner_property:
        property_profile = user.owner_property
        threshold = getattr(property_profile, 'points_threshold', None)
        data['property'] = {
            'property_id': property_profile.property_id,
            'property_name': property_profile.property_name,
            'community_name': property_profile.community_name,
            'min_points': threshold.min_points if threshold else 0,
        }
    else:
        data['property'] = None

    return json_ok(data)


# ---------------------- 2. 用户信息管理接口 ----------------------

@admin_token_required
@require_http_methods(["GET"])
def users_list(request, admin):
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
    try:
        # 查询所有商户，即使没有关联 user 也返回
        qs = MerchantProfile.objects.select_related('user', 'category').all().order_by('id')
        items = []
        for m in qs:
            items.append({
                'merchant_id': m.merchant_id,
                'merchant_name': m.merchant_name,
                'title': m.title,
                'description': m.description,
                'banner_urls': m.banner_list(),
                'category': m.category.name if m.category else None,
                'category_id': m.category.id if m.category else None,
                'contact_phone': m.contact_phone,
                'address': m.address,
                'positive_rating_percent': m.positive_rating_percent,
            })
        logger.info(f'查询商户列表，共 {len(items)} 条')
        return json_ok({'total': len(items), 'list': items})
    except Exception as exc:
        logger.error(f'查询商户列表失败: {str(exc)}', exc_info=True)
        return json_err(f'查询失败: {str(exc)}', status=500)


@openid_required
@require_http_methods(["GET"])
def merchant_detail(request, merchant_id):
    try:
        merchant = MerchantProfile.objects.select_related('user', 'category').get(merchant_id=merchant_id)
    except MerchantProfile.DoesNotExist:
        return json_err('商户不存在', status=404)

    data = {
        'merchant_id': merchant.merchant_id,
        'merchant_name': merchant.merchant_name,
        'title': merchant.title,
        'description': merchant.description,
        'banner_urls': merchant.banner_list(),
        'category_id': merchant.category.id if merchant.category else None,
        'category_name': merchant.category.name if merchant.category else None,
        'contact_phone': merchant.contact_phone,
        'address': merchant.address,
        'positive_rating_percent': merchant.positive_rating_percent,
    }
    return json_ok(data)


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


# ---------------------- 7. 积分统计逻辑（示例接口：变更积分） ----------------------

@openid_required
@require_http_methods(["POST"])
def points_change(request):
    """业主发起积分变更（仅允许增加积分）"""
    openid = _get_openid(request)

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
        'share_ratio': {
            'merchant_rate': merchant_rate,
            'property_rate': 100 - merchant_rate,
        }
    })


# ---------------------- 8. 管理员账号登录（Token 认证） ----------------------


@require_http_methods(["POST"])
def admin_login(request):
    """管理员登录，返回Token。
    请求体示例：{"username":"admin","password":"123456"}
    """
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)
    username = body.get('username')
    password = body.get('password')
    if not username or not password:
        return json_err('缺少参数 username 或 password', status=400)
    user = authenticate(username=username, password=password)
    if not user:
        return json_err('用户名或密码错误', status=401)
    # 仅允许超级用户获取管理员Token
    if not user.is_superuser:
        return json_err('仅允许超级用户登录', status=403)
    token, _ = Token.objects.get_or_create(user=user)
    return json_ok({'token': token.key, 'username': username})


# ==================== 管理员 CRUD 接口 ====================

# ---------------------- 1. 分类管理 CRUD ----------------------

@admin_token_required
@require_http_methods(["GET", "POST"])
def admin_categories(request, admin):
    """分类管理 - GET列表 / POST创建"""
    if request.method == 'GET':
        qs = Category.objects.all().order_by('id')
        icon_file_ids = [c.icon_name for c in qs if c.icon_name and c.icon_name.startswith('cloud://')]
        temp_urls = get_temp_file_urls(icon_file_ids)

        items = []
        for c in qs:
            icon_file_id = c.icon_name or ''
            icon_url = resolve_icon_url(icon_file_id, temp_urls)
            items.append({
                'id': c.id,
                'name': c.name,
                'icon_name': icon_file_id,
                'icon_file_id': icon_file_id,
                'icon_url': icon_url,
            })
        return json_ok({'total': len(items), 'list': items})
    
    # POST 创建
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)
    
    name = body.get('name')
    icon_name = body.get('icon_file_id') or body.get('icon_name', '')
    
    if not name:
        return json_err('缺少参数 name', status=400)
    
    try:
        category = Category.objects.create(name=name, icon_name=icon_name)
        temp_urls = get_temp_file_urls([category.icon_name]) if category.icon_name and category.icon_name.startswith('cloud://') else {}
        icon_url = resolve_icon_url(category.icon_name, temp_urls)
        return json_ok({
            'id': category.id,
            'name': category.name,
            'icon_name': category.icon_name,
            'icon_file_id': category.icon_name,
            'icon_url': icon_url,
        }, status=201)
    except Exception as e:
        logger.error(f'创建分类失败: {str(e)}')
        return json_err(f'创建失败: {str(e)}', status=400)


@admin_token_required
@require_http_methods(["PUT", "DELETE"])
def admin_categories_detail(request, admin, category_id):
    """分类管理 - PUT更新 / DELETE删除"""
    try:
        category = Category.objects.get(id=category_id)
    except Category.DoesNotExist:
        return json_err('分类不存在', status=404)
    
    if request.method == 'DELETE':
        category.delete()
        return json_ok({'id': category_id, 'deleted': True})
    
    # PUT 更新
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)
    
    if 'name' in body:
        category.name = body['name']
    if 'icon_name' in body or 'icon_file_id' in body:
        category.icon_name = body.get('icon_file_id') or body.get('icon_name', '')
    
    try:
        category.save()
        temp_urls = get_temp_file_urls([category.icon_name]) if category.icon_name and category.icon_name.startswith('cloud://') else {}
        icon_url = resolve_icon_url(category.icon_name, temp_urls)
        return json_ok({
            'id': category.id,
            'name': category.name,
            'icon_name': category.icon_name,
            'icon_file_id': category.icon_name,
            'icon_url': icon_url,
        })
    except Exception as e:
        logger.error(f'更新分类失败: {str(e)}')
        return json_err(f'更新失败: {str(e)}', status=400)


# ---------------------- 2. 商户管理 CRUD ----------------------

@admin_token_required
@require_http_methods(["GET", "POST"])
def admin_merchants(request, admin):
    """商户管理 - GET列表 / POST创建"""
    if request.method == 'GET':
        qs = MerchantProfile.objects.select_related('user', 'category').all().order_by('id')
        items = []
        for m in qs:
            items.append({
                'openid': m.user.openid if m.user else None,
                'merchant_id': m.merchant_id,
                'merchant_name': m.merchant_name,
                'title': m.title,
                'description': m.description,
                'banner_urls': m.banner_list(),
                'category_id': m.category.id if m.category else None,
                'category_name': m.category.name if m.category else None,
                'contact_phone': m.contact_phone,
                'address': m.address,
                'positive_rating_percent': m.positive_rating_percent,
                'daily_points': m.user.daily_points if m.user else 0,
                'total_points': m.user.total_points if m.user else 0,
            })
        return json_ok({'total': len(items), 'list': items})
    
    # POST 创建
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)
    
    openid = body.get('openid')
    merchant_name = body.get('merchant_name')
    
    if not openid or not merchant_name:
        return json_err('缺少参数 openid 或 merchant_name', status=400)
    
    try:
        user = UserInfo.objects.get(openid=openid)
        if user.identity_type != 'MERCHANT':
            return json_err('该用户身份类型不是商户', status=400)
    except UserInfo.DoesNotExist:
        return json_err('用户不存在', status=404)
    
    # 检查是否已有商户档案
    if hasattr(user, 'merchant_profile'):
        return json_err('该用户已有商户档案', status=400)
    
    category_id = body.get('category_id')
    category = None
    if category_id:
        try:
            category = Category.objects.get(id=category_id)
        except Category.DoesNotExist:
            return json_err('分类不存在', status=404)
    
    banner_urls = body.get('banner_urls', [])
    banner_urls_str = ','.join(banner_urls) if isinstance(banner_urls, list) else str(banner_urls) if banner_urls else ''
    
    try:
        merchant = MerchantProfile.objects.create(
            user=user,
            merchant_name=merchant_name,
            title=body.get('title', ''),
            description=body.get('description', ''),
            banner_urls=banner_urls_str,
            category=category,
            contact_phone=body.get('contact_phone', ''),
            address=body.get('address', ''),
            positive_rating_percent=body.get('positive_rating_percent', 0),
        )
        return json_ok({
            'openid': merchant.user.openid,
            'merchant_id': merchant.merchant_id,
            'merchant_name': merchant.merchant_name,
            'title': merchant.title,
            'description': merchant.description,
            'banner_urls': merchant.banner_list(),
            'category_id': merchant.category.id if merchant.category else None,
            'category_name': merchant.category.name if merchant.category else None,
            'contact_phone': merchant.contact_phone,
            'address': merchant.address,
            'positive_rating_percent': merchant.positive_rating_percent,
            'daily_points': merchant.user.daily_points,
            'total_points': merchant.user.total_points,
        }, status=201)
    except Exception as e:
        logger.error(f'创建商户失败: {str(e)}')
        return json_err(f'创建失败: {str(e)}', status=400)


@admin_token_required
@require_http_methods(["PUT", "DELETE"])
def admin_merchants_detail(request, admin, openid):
    """商户管理 - PUT更新 / DELETE删除（使用 openid）"""
    try:
        user = UserInfo.objects.get(openid=openid)
        if user.identity_type != 'MERCHANT':
            return json_err('该用户不是商户身份', status=400)
    except UserInfo.DoesNotExist:
        return json_err('用户不存在', status=404)
    
    try:
        merchant = MerchantProfile.objects.select_related('category', 'user').get(user=user)
    except MerchantProfile.DoesNotExist:
        return json_err('商户不存在', status=404)
    
    if request.method == 'DELETE':
        merchant.delete()
        return json_ok({'openid': openid, 'deleted': True})
    
    # PUT 更新
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)
    
    if 'merchant_name' in body:
        merchant.merchant_name = body['merchant_name']
    if 'title' in body:
        merchant.title = body.get('title', '')
    if 'description' in body:
        merchant.description = body.get('description', '')
    if 'banner_urls' in body:
        banner_urls = body['banner_urls']
        merchant.banner_urls = ','.join(banner_urls) if isinstance(banner_urls, list) else str(banner_urls) if banner_urls else ''
    if 'category_id' in body:
        category_id = body.get('category_id')
        if category_id:
            try:
                merchant.category = Category.objects.get(id=category_id)
            except Category.DoesNotExist:
                return json_err('分类不存在', status=404)
        else:
            merchant.category = None
    if 'contact_phone' in body:
        merchant.contact_phone = body.get('contact_phone', '')
    if 'address' in body:
        merchant.address = body.get('address', '')
    if 'positive_rating_percent' in body:
        merchant.positive_rating_percent = body.get('positive_rating_percent', 0)
    
    try:
        merchant.save()
        return json_ok({
            'openid': merchant.user.openid,
            'merchant_id': merchant.merchant_id,
            'merchant_name': merchant.merchant_name,
            'title': merchant.title,
            'description': merchant.description,
            'banner_urls': merchant.banner_list(),
            'category_id': merchant.category.id if merchant.category else None,
            'category_name': merchant.category.name if merchant.category else None,
            'contact_phone': merchant.contact_phone,
            'address': merchant.address,
            'positive_rating_percent': merchant.positive_rating_percent,
            'daily_points': merchant.user.daily_points,
            'total_points': merchant.user.total_points,
        })
    except Exception as e:
        logger.error(f'更新商户失败: {str(e)}')
        return json_err(f'更新失败: {str(e)}', status=400)


# ---------------------- 3. 物业管理 CRUD ----------------------

@admin_token_required
@require_http_methods(["GET", "POST"])
def admin_properties(request, admin):
    """物业管理 - GET列表 / POST创建"""
    if request.method == 'GET':
        qs = PropertyProfile.objects.select_related('user').all().order_by('id')
        # 批量查询所有积分阈值，减少数据库查询
        property_ids = [p.id for p in qs]
        thresholds = {th.property.id: th.min_points for th in PointsThreshold.objects.select_related('property').filter(property_id__in=property_ids)}
        
        items = []
        for p in qs:
            min_points = thresholds.get(p.id, 0)
            items.append({
                'openid': p.user.openid if p.user else None,
                'property_id': p.property_id,
                'property_name': p.property_name,
                'community_name': p.community_name,
                'daily_points': p.user.daily_points if p.user else 0,
                'total_points': p.user.total_points if p.user else 0,
                'min_points': min_points,  # 积分阈值
            })
        return json_ok({'total': len(items), 'list': items})
    
    # POST 创建
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)
    
    openid = body.get('openid')
    property_name = body.get('property_name')
    
    if not openid or not property_name:
        return json_err('缺少参数 openid 或 property_name', status=400)
    
    try:
        user = UserInfo.objects.get(openid=openid)
        if user.identity_type != 'PROPERTY':
            return json_err('该用户身份类型不是物业', status=400)
    except UserInfo.DoesNotExist:
        return json_err('用户不存在', status=404)
    
    # 检查是否已有物业档案
    if hasattr(user, 'property_profile'):
        return json_err('该用户已有物业档案', status=400)
    
    try:
        property_profile = PropertyProfile.objects.create(
            user=user,
            property_name=property_name,
            community_name=body.get('community_name', ''),
        )
        
        # 如果提供了积分阈值，创建或更新
        min_points = body.get('min_points')
        if min_points is not None:
            PointsThreshold.objects.update_or_create(
                property=property_profile,
                defaults={'min_points': int(min_points)}
            )
        
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
        }, status=201)
    except Exception as e:
        logger.error(f'创建物业失败: {str(e)}')
        return json_err(f'创建失败: {str(e)}', status=400)


@admin_token_required
@require_http_methods(["PUT", "DELETE"])
def admin_properties_detail(request, admin, openid):
    """物业管理 - PUT更新 / DELETE删除（使用 openid）"""
    try:
        user = UserInfo.objects.get(openid=openid)
        if user.identity_type != 'PROPERTY':
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
    
    try:
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
    except Exception as e:
        logger.error(f'更新物业失败: {str(e)}')
        return json_err(f'更新失败: {str(e)}', status=400)


# ---------------------- 4. 用户管理 CRUD（扩展） ----------------------

@admin_token_required
@require_http_methods(["GET", "POST"])
def admin_users(request, admin):
    """用户管理 - GET列表 / POST创建"""
    if request.method == 'GET':
        qs = UserInfo.objects.select_related('owner_property').all().order_by('id')
        items = []
        for u in qs:
            items.append({
                'system_id': u.system_id,
                'openid': u.openid,
                'identity_type': u.identity_type,
                'avatar_url': u.avatar_url,
                'phone_number': u.phone_number,
                'daily_points': u.daily_points,
                'total_points': u.total_points,
                'owner_property_id': u.owner_property.property_id if u.owner_property else None,
                'owner_property_name': u.owner_property.property_name if u.owner_property else None,
            })
        return json_ok({'total': len(items), 'list': items})

    # POST 创建
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)
    
    openid = body.get('openid')
    identity_type = body.get('identity_type')
    
    if not openid or not identity_type:
        return json_err('缺少参数 openid 或 identity_type', status=400)
    
    if identity_type not in ['OWNER', 'PROPERTY', 'MERCHANT', 'ADMIN']:
        return json_err('无效的身份类型', status=400)
    
    # 检查 openid 是否已存在
    if UserInfo.objects.filter(openid=openid).exists():
        return json_err('该 OpenID 已存在', status=400)
    
    owner_property_id = body.get('owner_property_id')
    owner_property = None
    if owner_property_id and identity_type == 'OWNER':
        try:
            owner_property = PropertyProfile.objects.get(property_id=owner_property_id)
        except PropertyProfile.DoesNotExist:
            return json_err('物业不存在', status=404)
    
    try:
        user = UserInfo.objects.create(
            openid=openid,
            identity_type=identity_type,
            avatar_url=body.get('avatar_url', ''),
            phone_number=body.get('phone_number', ''),
            owner_property=owner_property,
            daily_points=body.get('daily_points', 0),
            total_points=body.get('total_points', 0),
        )
        return json_ok({
            'system_id': user.system_id,
            'openid': user.openid,
            'avatar_url': user.avatar_url,
            'phone_number': user.phone_number,
            'identity_type': user.identity_type,
            'daily_points': user.daily_points,
            'total_points': user.total_points,
            'owner_property_id': user.owner_property.property_id if user.owner_property else None,
            'owner_property_name': user.owner_property.property_name if user.owner_property else None,
        }, status=201)
    except Exception as e:
        logger.error(f'创建用户失败: {str(e)}')
        return json_err(f'创建失败: {str(e)}', status=400)


@admin_token_required
@require_http_methods(["PUT", "DELETE"])
def admin_users_detail(request, admin, system_id):
    """用户管理 - PUT更新 / DELETE删除"""
    try:
        user = UserInfo.objects.select_related('owner_property').get(system_id=system_id)
    except UserInfo.DoesNotExist:
        return json_err('用户不存在', status=404)
    
    if request.method == 'DELETE':
        user.delete()
        return json_ok({'system_id': system_id, 'deleted': True})
    
    # PUT 更新
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)
    
    if 'avatar_url' in body:
        user.avatar_url = body.get('avatar_url', '')
    if 'phone_number' in body:
        user.phone_number = body.get('phone_number', '')
    if 'identity_type' in body:
        identity_type = body['identity_type']
        if identity_type not in ['OWNER', 'PROPERTY', 'MERCHANT', 'ADMIN']:
            return json_err('无效的身份类型', status=400)
        user.identity_type = identity_type
    if 'owner_property_id' in body:
        owner_property_id = body.get('owner_property_id')
        if owner_property_id:
            try:
                user.owner_property = PropertyProfile.objects.get(property_id=owner_property_id)
            except PropertyProfile.DoesNotExist:
                return json_err('物业不存在', status=404)
        else:
            user.owner_property = None
    if 'daily_points' in body:
        user.daily_points = int(body['daily_points'])
    if 'total_points' in body:
        user.total_points = int(body['total_points'])
    
    try:
        user.save()
        return json_ok({
            'system_id': user.system_id,
            'openid': user.openid,
            'avatar_url': user.avatar_url,
            'phone_number': user.phone_number,
            'identity_type': user.identity_type,
            'daily_points': user.daily_points,
            'total_points': user.total_points,
            'owner_property_id': user.owner_property.property_id if user.owner_property else None,
            'owner_property_name': user.owner_property.property_name if user.owner_property else None,
        })
    except Exception as e:
        logger.error(f'更新用户失败: {str(e)}')
        return json_err(f'更新失败: {str(e)}', status=400)


# ---------------------- 5. 存储辅助接口 ----------------------

def _generate_storage_path(filename: str, directory: str = 'category-icons') -> str:
    directory = directory.strip().strip('/') or 'category-icons'
    ext = ''
    if filename:
        ext = os.path.splitext(filename)[1].lower()
    return f"{directory}/{uuid.uuid4().hex}{ext}"


@admin_token_required
@require_http_methods(["POST"])
def admin_storage_upload_credential(request, admin):
    if not WX_ENV_ID:
        return json_err('未配置存储环境变量 CLOUD_ID', status=500)

    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)

    filename = body.get('filename', '') or ''
    directory = body.get('directory', 'category-icons')
    custom_path = body.get('path')

    if custom_path:
        storage_path = custom_path.lstrip('/')
    else:
        storage_path = _generate_storage_path(filename, directory)

    try:
        data = wx_openapi_post('tcb/uploadfile', {
            'env': WX_ENV_ID,
            'path': storage_path,
        })
    except WxOpenApiError as exc:
        return json_err(str(exc) or '获取上传凭证失败', status=500)

    return json_ok({
        'file_id': data.get('file_id'),
        'upload_url': data.get('url'),
        'authorization': data.get('authorization'),
        'token': data.get('token'),
        'cos_file_id': data.get('cos_file_id'),
        'path': storage_path,
        'expires_in': data.get('expired_time'),
    })


@admin_token_required
@require_http_methods(["POST"])
def admin_storage_delete_files(request, admin):
    if not WX_ENV_ID:
        return json_err('未配置存储环境变量 CLOUD_ID', status=500)

    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)

    file_ids = body.get('file_ids')
    if not file_ids or not isinstance(file_ids, list):
        return json_err('缺少参数 file_ids', status=400)

    try:
        data = wx_openapi_post('tcb/batchdeletefile', {
            'env': WX_ENV_ID,
            'fileid_list': file_ids,
        })
    except WxOpenApiError as exc:
        return json_err(str(exc) or '删除文件失败', status=500)

    return json_ok({
        'deleted': file_ids,
        'result': data.get('delete_list', []),
    })


# ---------------------- 6. 积分分成配置 ----------------------

@admin_token_required
@require_http_methods(["GET", "PUT"])
def admin_share_setting(request, admin):
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


# ---------------------- 6. 积分变更记录查询 ----------------------

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

