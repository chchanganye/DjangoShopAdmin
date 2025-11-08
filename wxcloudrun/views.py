import json
import logging
import os
import uuid
from datetime import date, datetime

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
    IdentityApplication,
    AccessLog,
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


def _ensure_userinfo_exists(openid: str) -> UserInfo:
    """若用户不存在则自动创建一条默认档案，确保前端接口可用。"""
    user, created = UserInfo.objects.get_or_create(
        openid=openid,
        defaults={'identity_type': 'OWNER'},
    )
    if created:
        logger.info(f'自动创建小程序用户: openid={openid}')
    return user


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
        try:
            _ensure_userinfo_exists(openid)
        except Exception as exc:
            logger.error(f'自动创建用户失败: openid={openid}, error={exc}', exc_info=True)
            return json_err('初始化用户失败', status=500)
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


def delete_cloud_files(file_ids):
    if not file_ids:
        return
    wx_openapi_post('tcb/batchdeletefile', {
        'env': WX_ENV_ID,
        'fileid_list': file_ids,
    })


def get_points_share_setting():
    return PointsShareSetting.get_solo()


# ---------------------- 1. 用户登录与身份模块 ----------------------

@openid_required
@require_http_methods(["GET"])
def user_login(request):
    """小程序登录接口：自动创建用户，返回用户身份和是否首次登录，并记录访问日志"""
    openid = _get_openid(request)
    user = UserInfo.objects.get(openid=openid)  # _ensure_userinfo_exists 已在装饰器里确保存在
    
    # 记录访问日志（用于统计访问量）
    today = date.today()
    access_log, created = AccessLog.objects.get_or_create(
        openid=openid,
        access_date=today,
        defaults={
            'access_count': 1,
            'first_access_at': datetime.now(),
            'last_access_at': datetime.now(),
        }
    )
    if not created:
        # 已存在记录，增加访问次数
        access_log.access_count += 1
        access_log.last_access_at = datetime.now()
        access_log.save()
    
    # 判断是否首次登录：identity_type 仍为默认 OWNER 且没有其他扩展字段
    is_first_login = (
        user.identity_type == 'OWNER' 
        and not user.phone_number 
        and not user.owner_property
    )
    
    data = {
        'system_id': user.system_id,
        'openid': user.openid,
        'identity_type': user.identity_type,
        'avatar_url': user.avatar_url,
        'phone_number': user.phone_number,
        'is_first_login': is_first_login,
    }
    
    if user.owner_property:
        data['property'] = {
            'property_id': user.owner_property.property_id,
            'property_name': user.owner_property.property_name,
        }
    else:
        data['property'] = None
    
    return json_ok(data)


@openid_required
@require_http_methods(["GET"])
def properties_public_list(request):
    """获取所有物业列表（供业主选择）"""
    qs = PropertyProfile.objects.select_related('user').all().order_by('property_name')
    items = []
    for p in qs:
        items.append({
            'property_id': p.property_id,
            'property_name': p.property_name,
            'community_name': p.community_name,
        })
    return json_ok({'total': len(items), 'list': items})


@openid_required
@require_http_methods(["PUT"])
def user_update_profile(request):
    """用户更新个人信息（仅业主身份可直接绑定物业，其他身份需走申请流程）"""
    openid = _get_openid(request)
    try:
        user = UserInfo.objects.get(openid=openid)
    except UserInfo.DoesNotExist:
        return json_err('用户不存在', status=404)
    
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)
    
    if 'avatar_url' in body:
        user.avatar_url = body['avatar_url']
    if 'phone_number' in body:
        user.phone_number = body['phone_number']
    
    # 仅当申请业主身份时，可直接设置并关联物业
    if 'identity_type' in body and body['identity_type'] == 'OWNER':
        user.identity_type = 'OWNER'
        if 'owner_property_id' in body:
            property_id = body['owner_property_id']
            if property_id:
                try:
                    user.owner_property = PropertyProfile.objects.get(property_id=property_id)
                except PropertyProfile.DoesNotExist:
                    return json_err('物业不存在', status=404)
            else:
                user.owner_property = None
    
    try:
        user.save()
        return json_ok({
            'system_id': user.system_id,
            'openid': user.openid,
            'identity_type': user.identity_type,
            'avatar_url': user.avatar_url,
            'phone_number': user.phone_number,
            'owner_property_id': user.owner_property.property_id if user.owner_property else None,
        })
    except Exception as exc:
        logger.error(f'更新用户信息失败: {str(exc)}')
        return json_err(f'更新失败: {str(exc)}', status=400)


@openid_required
@require_http_methods(["POST"])
def identity_apply(request):
    """用户申请变更身份（商户/物业需审核，业主直接通过user_update_profile）"""
    openid = _get_openid(request)
    try:
        user = UserInfo.objects.get(openid=openid)
    except UserInfo.DoesNotExist:
        return json_err('用户不存在', status=404)
    
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)
    
    requested_identity = body.get('requested_identity')
    if requested_identity not in ['MERCHANT', 'PROPERTY']:
        return json_err('仅支持申请商户或物业身份', status=400)
    
    # 检查是否有待审核的申请
    pending_count = IdentityApplication.objects.filter(user=user, status='PENDING').count()
    if pending_count > 0:
        return json_err('您已有待审核的申请，请勿重复提交', status=400)
    
    application = IdentityApplication(user=user, requested_identity=requested_identity)
    
    if requested_identity == 'MERCHANT':
        application.merchant_name = body.get('merchant_name', '')
        application.merchant_description = body.get('merchant_description', '')
        application.merchant_address = body.get('merchant_address', '')
        application.merchant_phone = body.get('merchant_phone', '')
        
        if not application.merchant_name:
            return json_err('商户名称为必填项', status=400)
    
    elif requested_identity == 'PROPERTY':
        application.property_name = body.get('property_name', '')
        application.property_community = body.get('property_community', '')
        
        if not application.property_name:
            return json_err('物业名称为必填项', status=400)
    
    try:
        application.save()
        return json_ok({
            'application_id': application.id,
            'status': 'PENDING',
            'message': '申请已提交，请等待管理员审核'
        }, status=201)
    except Exception as exc:
        logger.error(f'提交身份申请失败: {str(exc)}')
        return json_err(f'提交失败: {str(exc)}', status=400)


# ---------------------- 2. 商品分类管理接口 ----------------------

@openid_required
@require_http_methods(["GET"])
def categories_list(request):
    qs = Category.objects.all().order_by('id')
    icon_file_ids = [c.icon_file_id for c in qs if c.icon_file_id and c.icon_file_id.startswith('cloud://')]
    temp_urls = get_temp_file_urls(icon_file_ids)

    items = []
    for c in qs:
        icon_file_id = c.icon_file_id or ''
        icon_url = resolve_icon_url(icon_file_id, temp_urls)
        items.append({
            'name': c.name,
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
        
        # 收集所有横幅图文件ID
        all_file_ids = [m.banner_url for m in qs if m.banner_url and m.banner_url.startswith('cloud://')]
        
        # 批量获取临时URL
        temp_urls = get_temp_file_urls(all_file_ids) if all_file_ids else {}
        
    items = []
    for m in qs:
            # 处理横幅图：返回临时URL（小程序端只需要URL）
            banner_url = ''
            if m.banner_url:
                if m.banner_url.startswith('cloud://'):
                    banner_url = temp_urls.get(m.banner_url, '')
                else:
                    banner_url = m.banner_url
            
        items.append({
                'merchant_id': m.merchant_id,
                'merchant_name': m.merchant_name,
                'title': m.title,
            'description': m.description,
                'banner_url': banner_url,  # 返回临时URL字符串
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

    # 处理横幅图：返回临时URL（小程序端只需要URL）
    banner_url = ''
    if merchant.banner_url:
        if merchant.banner_url.startswith('cloud://'):
            temp_urls = get_temp_file_urls([merchant.banner_url])
            banner_url = temp_urls.get(merchant.banner_url, '')
        else:
            banner_url = merchant.banner_url

    data = {
        'merchant_id': merchant.merchant_id,
        'merchant_name': merchant.merchant_name,
        'title': merchant.title,
        'description': merchant.description,
        'banner_url': banner_url,  # 返回临时URL字符串
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
        icon_file_ids = [c.icon_file_id for c in qs if c.icon_file_id and c.icon_file_id.startswith('cloud://')]
        temp_urls = get_temp_file_urls(icon_file_ids)

        items = []
        for c in qs:
            icon_file_id = c.icon_file_id or ''
            icon_url = resolve_icon_url(icon_file_id, temp_urls)
            items.append({
                'id': c.id,
                'name': c.name,
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
    icon_file_id = body.get('icon_file_id', '')
    
    if not name:
        return json_err('缺少参数 name', status=400)
    
    try:
        category = Category.objects.create(name=name, icon_file_id=icon_file_id)
        temp_urls = get_temp_file_urls([category.icon_file_id]) if category.icon_file_id and category.icon_file_id.startswith('cloud://') else {}
        icon_url = resolve_icon_url(category.icon_file_id, temp_urls)
        return json_ok({
            'id': category.id,
            'name': category.name,
            'icon_file_id': category.icon_file_id,
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
    
    old_icon_file_id = category.icon_file_id or ''

    if 'name' in body:
        category.name = body['name']
    if 'icon_file_id' in body:
        new_icon_file_id = body.get('icon_file_id') or ''
        if new_icon_file_id != old_icon_file_id and old_icon_file_id.startswith('cloud://'):
            try:
                delete_cloud_files([old_icon_file_id])
            except WxOpenApiError as exc:
                logger.error(f'删除旧分类图标失败: {str(exc)}', exc_info=True)
                return json_err(f'删除旧图标失败: {str(exc)}', status=500)
        category.icon_file_id = new_icon_file_id
    
    try:
        category.save()
        temp_urls = get_temp_file_urls([category.icon_file_id]) if category.icon_file_id and category.icon_file_id.startswith('cloud://') else {}
        icon_url = resolve_icon_url(category.icon_file_id, temp_urls)
        return json_ok({
            'id': category.id,
            'name': category.name,
            'icon_file_id': category.icon_file_id,
            'icon_url': icon_url,
        })
    except Exception as e:
        logger.error(f'更新分类失败: {str(e)}')
        return json_err(f'更新失败: {str(e)}', status=400)


# ---------------------- 2. 商户管理 CRUD ----------------------

@admin_token_required
@require_http_methods(["GET"])
def admin_merchants(request, admin):
    """商户管理 - GET列表（只读，通过用户列表创建）"""
    qs = MerchantProfile.objects.select_related('user', 'category').all().order_by('id')
    
    # 收集所有横幅图文件ID
    all_file_ids = [m.banner_url for m in qs if m.banner_url and m.banner_url.startswith('cloud://')]
    
    # 批量获取临时URL
    temp_urls = get_temp_file_urls(all_file_ids) if all_file_ids else {}
    
    items = []
    for m in qs:
        # 处理横幅图：返回 {file_id, url} 或 null
        banner_data = None
        if m.banner_url:
            banner_data = {
                'file_id': m.banner_url,
                'url': temp_urls.get(m.banner_url, '') if m.banner_url.startswith('cloud://') else m.banner_url
            }
        
        items.append({
            'openid': m.user.openid if m.user else None,
            'merchant_id': m.merchant_id,
            'merchant_name': m.merchant_name,
            'title': m.title,
            'description': m.description,
            'banner': banner_data,  # 返回 {file_id, url} 或 null
            'category_id': m.category.id if m.category else None,
            'category_name': m.category.name if m.category else None,
            'contact_phone': m.contact_phone,
            'address': m.address,
            'positive_rating_percent': m.positive_rating_percent,
            'daily_points': m.user.daily_points if m.user else 0,
            'total_points': m.user.total_points if m.user else 0,
        })
    return json_ok({'total': len(items), 'list': items})


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
        # 删除关联的横幅图云文件
        if merchant.banner_url and merchant.banner_url.startswith('cloud://'):
            try:
                delete_cloud_files([merchant.banner_url])
            except WxOpenApiError as exc:
                logger.warning(f"删除商户横幅图失败: {merchant.banner_url}, error={exc}")
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
    if 'banner_file_id' in body:
        # 处理横幅图更新：删除旧图，保存新图
        new_file_id = body['banner_file_id']
        old_file_id = merchant.banner_url
        
        # 如果新旧文件不同，删除旧文件
        if old_file_id and old_file_id.startswith('cloud://') and old_file_id != new_file_id:
            try:
                delete_cloud_files([old_file_id])
            except WxOpenApiError as exc:
                logger.warning(f"删除旧商户横幅图失败: {old_file_id}, error={exc}")
        
        merchant.banner_url = new_file_id if new_file_id else ''
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
        
        # 获取横幅图临时URL
        banner_data = None
        if merchant.banner_url:
            temp_urls = get_temp_file_urls([merchant.banner_url]) if merchant.banner_url.startswith('cloud://') else {}
            banner_data = {
                'file_id': merchant.banner_url,
                'url': temp_urls.get(merchant.banner_url, '') if merchant.banner_url.startswith('cloud://') else merchant.banner_url
            }
        
        return json_ok({
            'openid': merchant.user.openid,
            'merchant_id': merchant.merchant_id,
            'merchant_name': merchant.merchant_name,
            'title': merchant.title,
            'description': merchant.description,
            'banner': banner_data,  # 返回 {file_id, url} 或 null
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
@require_http_methods(["GET"])
def admin_properties(request, admin):
    """物业管理 - GET列表（只读，通过用户列表创建）"""
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
        
        # 收集所有头像文件ID
        avatar_file_ids = [u.avatar_url for u in qs if u.avatar_url and u.avatar_url.startswith('cloud://')]
        
        # 批量获取临时URL
        temp_urls = get_temp_file_urls(avatar_file_ids) if avatar_file_ids else {}
        
        items = []
        for u in qs:
            # 处理头像：返回 file_id 和对应的临时 URL
            avatar_data = None
            if u.avatar_url:
                if u.avatar_url.startswith('cloud://'):
                    avatar_data = {
                        'file_id': u.avatar_url,
                        'url': temp_urls.get(u.avatar_url, '')
                    }
    else:
                    # 兼容旧数据（如果有直接URL的）
                    avatar_data = {
                        'file_id': '',
                        'url': u.avatar_url
                    }
            
            items.append({
                'system_id': u.system_id,
                'openid': u.openid,
                'identity_type': u.identity_type,
                'avatar': avatar_data,  # 返回 {file_id, url} 或 null
                'phone_number': u.phone_number,
                'daily_points': u.daily_points,
                'total_points': u.total_points,
                'owner_property_id': u.owner_property.property_id if u.owner_property else None,
                'owner_property_name': u.owner_property.property_name if u.owner_property else None,
                'created_at': u.created_at.strftime('%Y-%m-%d %H:%M:%S') if u.created_at else None,
                'updated_at': u.updated_at.strftime('%Y-%m-%d %H:%M:%S') if u.updated_at else None,
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
    
    # 处理头像文件ID
    avatar_file_id = body.get('avatar_file_id', '')
    
    try:
        user = UserInfo.objects.create(
            openid=openid,
            identity_type=identity_type,
            avatar_url=avatar_file_id,  # 存储云文件ID
            phone_number=body.get('phone_number', ''),
            owner_property=owner_property,
            daily_points=body.get('daily_points', 0),
            total_points=body.get('total_points', 0),
        )
        
        # 根据身份类型自动创建对应的档案
        if identity_type == 'MERCHANT':
            # 验证商户必填字段
            merchant_name = body.get('merchant_name')
            if not merchant_name:
                return json_err('商户名称为必填项', status=400)
            
            category_id = body.get('category_id')
            if not category_id:
                return json_err('商户分类为必填项', status=400)
            
            contact_phone = body.get('merchant_phone')
            if not contact_phone:
                return json_err('商户电话为必填项', status=400)
            
            address = body.get('merchant_address')
            if not address:
                return json_err('商户地址为必填项', status=400)
            
            banner_file_id = body.get('banner_file_id')
            if not banner_file_id:
                return json_err('商户横幅展示图为必填项', status=400)
            
            # 验证分类是否存在
            try:
                category = Category.objects.get(id=category_id)
            except Category.DoesNotExist:
                return json_err('分类不存在', status=404)
            
            # 创建商户档案
            MerchantProfile.objects.create(
                user=user,
                merchant_name=merchant_name,
                description=body.get('merchant_description', ''),
                address=address,
                contact_phone=contact_phone,
                banner_url=banner_file_id,
                category=category,
            )
        elif identity_type == 'PROPERTY':
            # 创建物业档案
            property_profile = PropertyProfile.objects.create(
                user=user,
                property_name=body.get('property_name', ''),
                community_name=body.get('community_name', ''),
            )
            # 如果提供了积分阈值，创建
            min_points = body.get('min_points')
            if min_points is not None:
                PointsThreshold.objects.create(
                    property=property_profile,
                    min_points=int(min_points)
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
        # 删除用户头像云文件
        if user.avatar_url and user.avatar_url.startswith('cloud://'):
            try:
                delete_cloud_files([user.avatar_url])
            except WxOpenApiError as exc:
                logger.warning(f"删除用户头像失败: {user.avatar_url}, error={exc}")
        user.delete()
        return json_ok({'system_id': system_id, 'deleted': True})
    
    # PUT 更新
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)
    
    if 'avatar_file_id' in body:
        # 处理头像更新：删除旧头像，保存新头像
        old_avatar = user.avatar_url
        new_avatar = body.get('avatar_file_id', '')
        
        # 如果新旧头像不同，且旧头像是云文件，则删除
        if new_avatar != old_avatar and old_avatar and old_avatar.startswith('cloud://'):
            try:
                delete_cloud_files([old_avatar])
            except WxOpenApiError as exc:
                logger.warning(f"删除旧用户头像失败: {old_avatar}, error={exc}")
        
        user.avatar_url = new_avatar
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
        
        # 获取头像临时URL
        avatar_data = None
        if user.avatar_url:
            if user.avatar_url.startswith('cloud://'):
                temp_urls = get_temp_file_urls([user.avatar_url])
                avatar_data = {
                    'file_id': user.avatar_url,
                    'url': temp_urls.get(user.avatar_url, '')
                }
            else:
                avatar_data = {
                    'file_id': '',
                    'url': user.avatar_url
                }
        
        return json_ok({
            'system_id': user.system_id,
            'openid': user.openid,
            'avatar': avatar_data,  # 返回 {file_id, url} 或 null
            'phone_number': user.phone_number,
            'identity_type': user.identity_type,
            'daily_points': user.daily_points,
            'total_points': user.total_points,
            'owner_property_id': user.owner_property.property_id if user.owner_property else None,
            'owner_property_name': user.owner_property.property_name if user.owner_property else None,
            'created_at': user.created_at.strftime('%Y-%m-%d %H:%M:%S') if user.created_at else None,
            'updated_at': user.updated_at.strftime('%Y-%m-%d %H:%M:%S') if user.updated_at else None,
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


# ---------------------- 7. 积分变更记录查询 ----------------------

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


# ---------------------- 8. 身份申请审核管理 ----------------------

@admin_token_required
@require_http_methods(["GET"])
def admin_applications_list(request, admin):
    """获取所有身份申请记录（支持按状态筛选）"""
    status_filter = request.GET.get('status')  # PENDING/APPROVED/REJECTED
    
    qs = IdentityApplication.objects.select_related('user').all().order_by('-created_at')
    
    if status_filter and status_filter in ['PENDING', 'APPROVED', 'REJECTED']:
        qs = qs.filter(status=status_filter)
    
    items = []
    for app in qs:
        items.append({
            'id': app.id,
            'openid': app.user.openid,
            'system_id': app.user.system_id,
            'requested_identity': app.requested_identity,
            'status': app.status,
            'merchant_name': app.merchant_name,
            'merchant_description': app.merchant_description,
            'merchant_address': app.merchant_address,
            'merchant_phone': app.merchant_phone,
            'property_name': app.property_name,
            'property_community': app.property_community,
            'reviewed_by': app.reviewed_by.username if app.reviewed_by else None,
            'reviewed_at': app.reviewed_at.strftime('%Y-%m-%d %H:%M:%S') if app.reviewed_at else None,
            'reject_reason': app.reject_reason,
            'created_at': app.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        })
    
    return json_ok({'total': len(items), 'list': items})


@admin_token_required
@require_http_methods(["POST"])
def admin_application_approve(request, admin):
    """批准身份申请"""
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)
    
    application_id = body.get('application_id')
    if not application_id:
        return json_err('缺少参数 application_id', status=400)
    
    try:
        application = IdentityApplication.objects.select_related('user').get(id=application_id)
    except IdentityApplication.DoesNotExist:
        return json_err('申请不存在', status=404)
    
    if application.status != 'PENDING':
        return json_err(f'该申请状态为 {application.get_status_display()}，无法批准', status=400)
    
    user = application.user
    requested_identity = application.requested_identity
    
    try:
        from django.db import transaction
        
        with transaction.atomic():
            # 更新用户身份
            user.identity_type = requested_identity
            user.save()
            
            # 根据申请类型创建对应档案
            if requested_identity == 'MERCHANT':
                MerchantProfile.objects.create(
                    user=user,
                    merchant_name=application.merchant_name,
                    description=application.merchant_description,
                    address=application.merchant_address,
                    contact_phone=application.merchant_phone,
                )
            elif requested_identity == 'PROPERTY':
                PropertyProfile.objects.create(
                    user=user,
                    property_name=application.property_name,
                    community_name=application.property_community,
                )
            
            # 更新申请状态
            application.status = 'APPROVED'
            application.reviewed_by = admin
            application.reviewed_at = datetime.now()
            application.save()
        
        return json_ok({
            'application_id': application.id,
            'status': 'APPROVED',
            'message': '申请已批准'
        })
    
    except Exception as exc:
        logger.error(f'批准身份申请失败: {str(exc)}', exc_info=True)
        return json_err(f'批准失败: {str(exc)}', status=500)


@admin_token_required
@require_http_methods(["POST"])
def admin_application_reject(request, admin):
    """拒绝身份申请"""
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)
    
    application_id = body.get('application_id')
    reject_reason = body.get('reject_reason', '')
    
    if not application_id:
        return json_err('缺少参数 application_id', status=400)
    
    try:
        application = IdentityApplication.objects.get(id=application_id)
    except IdentityApplication.DoesNotExist:
        return json_err('申请不存在', status=404)
    
    if application.status != 'PENDING':
        return json_err(f'该申请状态为 {application.get_status_display()}，无法拒绝', status=400)
    
    application.status = 'REJECTED'
    application.reviewed_by = admin
    application.reviewed_at = datetime.now()
    application.reject_reason = reject_reason
    application.save()
    
    return json_ok({
        'application_id': application.id,
        'status': 'REJECTED',
        'message': '申请已拒绝'
    })


# ---------------------- 9. 管理员统计接口 ----------------------

@admin_token_required
@require_http_methods(["GET"])
def admin_statistics_overview(request, admin):
    """管理员统计概览：总用户数、今日新增、今日交易额、总交易额"""
    from django.db.models import Sum, Count
    
    today = date.today()
    
    # 1. 总用户数
    total_users = UserInfo.objects.count()
    
    # 2. 今日新增用户数（根据created_at判断）
    today_new_users = UserInfo.objects.filter(
        created_at__date=today
    ).count()
    
    # 3. 今日交易额（根据今日积分变更记录计算绝对值总和）
    today_transaction = PointsRecord.objects.filter(
        created_at__date=today
    ).aggregate(
        total=Sum('change')
    )['total'] or 0
    today_transaction_amount = abs(today_transaction)
    
    # 4. 总交易额（历史所有积分变更绝对值总和）
    total_transaction = PointsRecord.objects.aggregate(
        total=Sum('change')
    )['total'] or 0
    total_transaction_amount = abs(total_transaction)
    
    # 5. 总访问量（所有AccessLog的access_count总和）
    total_visits = AccessLog.objects.aggregate(
        total=Sum('access_count')
    )['total'] or 0
    
    # 6. 日访问量（今日AccessLog的access_count总和）
    today_visits = AccessLog.objects.filter(
        access_date=today
    ).aggregate(
        total=Sum('access_count')
    )['total'] or 0
    
    data = {
        'total_users': total_users,
        'today_new_users': today_new_users,
        'today_transaction_amount': today_transaction_amount,
        'total_transaction_amount': total_transaction_amount,
        'total_visits': total_visits,
        'today_visits': today_visits,
    }
    
    return json_ok(data)


@admin_token_required
@require_http_methods(["GET"])
def admin_statistics_by_time(request, admin):
    """按时间维度统计：支持按年月、按周统计用户数和交易额
    
    Query参数：
    - type: 'month' 或 'week'（必填）
    - year: 年份，如 2025（必填）
    - month: 月份，1-12（type=month或week时必填）
    - week: 周数，1-5（type=week时必填，表示该月第几周）
    """
    from django.db.models import Sum, Count
    import calendar
    
    stat_type = request.GET.get('type')
    year = request.GET.get('year')
    month = request.GET.get('month')
    week = request.GET.get('week')
    
    if not stat_type or stat_type not in ['month', 'week']:
        return json_err('参数 type 必须为 month 或 week', status=400)
    
    if not year:
        return json_err('参数 year 为必填项', status=400)
    
    try:
        year = int(year)
    except ValueError:
        return json_err('参数 year 必须为整数', status=400)
    
    if stat_type == 'month':
        # 按月统计
        if not month:
            return json_err('参数 month 为必填项', status=400)
        
        try:
            month = int(month)
            if month < 1 or month > 12:
                raise ValueError
        except ValueError:
            return json_err('参数 month 必须为1-12的整数', status=400)
        
        # 计算该月第一天和最后一天
        first_day = date(year, month, 1)
        last_day_num = calendar.monthrange(year, month)[1]
        last_day = date(year, month, last_day_num)
        
        # 统计该月的数据
        users_count = UserInfo.objects.filter(
            created_at__date__gte=first_day,
            created_at__date__lte=last_day
        ).count()
        
        transaction_sum = PointsRecord.objects.filter(
            created_at__date__gte=first_day,
            created_at__date__lte=last_day
        ).aggregate(total=Sum('change'))['total'] or 0
        transaction_amount = abs(transaction_sum)
        
        visits_count = AccessLog.objects.filter(
            access_date__gte=first_day,
            access_date__lte=last_day
        ).aggregate(total=Sum('access_count'))['total'] or 0
        
        data = {
            'type': 'month',
            'year': year,
            'month': month,
            'start_date': str(first_day),
            'end_date': str(last_day),
            'users_count': users_count,
            'transaction_amount': transaction_amount,
            'visits_count': visits_count,
        }
        
        return json_ok(data)
    
    elif stat_type == 'week':
        # 按周统计（某月的第几周）
        if not month:
            return json_err('参数 month 为必填项', status=400)
        if not week:
            return json_err('参数 week 为必填项', status=400)
        
        try:
            month = int(month)
            week = int(week)
            if month < 1 or month > 12:
                raise ValueError('month')
            if week < 1 or week > 5:
                raise ValueError('week')
        except ValueError as e:
            if str(e) == 'month':
                return json_err('参数 month 必须为1-12的整数', status=400)
            elif str(e) == 'week':
                return json_err('参数 week 必须为1-5的整数', status=400)
            else:
                return json_err('参数格式错误', status=400)
        
        # 计算该月第一天
        first_day_of_month = date(year, month, 1)
        
        # 计算第几周的起始日期（简单算法：每周7天，第1周从1号开始）
        week_start_day = 1 + (week - 1) * 7
        week_end_day = week_start_day + 6
        
        # 获取该月最后一天
        last_day_num = calendar.monthrange(year, month)[1]
        
        # 确保不超出月份范围
        if week_start_day > last_day_num:
            return json_err(f'{year}年{month}月没有第{week}周', status=400)
        
        week_end_day = min(week_end_day, last_day_num)
        
        start_date = date(year, month, week_start_day)
        end_date = date(year, month, week_end_day)
        
        # 统计该周的数据
        users_count = UserInfo.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        ).count()
        
        transaction_sum = PointsRecord.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        ).aggregate(total=Sum('change'))['total'] or 0
        transaction_amount = abs(transaction_sum)
        
        visits_count = AccessLog.objects.filter(
            access_date__gte=start_date,
            access_date__lte=end_date
        ).aggregate(total=Sum('access_count'))['total'] or 0
        
        data = {
            'type': 'week',
            'year': year,
            'month': month,
            'week': week,
            'start_date': str(start_date),
            'end_date': str(end_date),
            'users_count': users_count,
            'transaction_amount': transaction_amount,
            'visits_count': visits_count,
        }
        
        return json_ok(data)

