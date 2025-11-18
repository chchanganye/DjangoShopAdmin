"""小程序端用户相关视图"""
import json
import logging
from datetime import date, datetime
from django.views.decorators.http import require_http_methods
from datetime import datetime
from django.db.models import Q
from django.utils.dateparse import parse_datetime

from wxcloudrun.decorators import openid_required
from wxcloudrun.utils.responses import json_ok, json_err
from wxcloudrun.utils.auth import get_openid
from wxcloudrun.models import UserInfo, PropertyProfile, IdentityApplication, AccessLog, MerchantProfile
from wxcloudrun.services.storage_service import get_temp_file_urls, delete_cloud_files, get_phone_number_by_code
from wxcloudrun.exceptions import WxOpenApiError


logger = logging.getLogger('log')


@openid_required
@require_http_methods(["GET"])
def user_login(request):
    """小程序登录接口：自动创建用户，返回用户身份和是否首次登录，并记录访问日志"""
    openid = get_openid(request)
    user = UserInfo.objects.get(openid=openid)
    
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
        access_log.access_count += 1
        access_log.last_access_at = datetime.now()
        access_log.save()
    
    # 判断是否首次登录
    is_first_login = (
        user.identity_type == 'OWNER' 
        and not user.phone_number 
        and not user.owner_property
    )
    
    # 处理头像：返回 file_id 和临时 URL
    avatar_data = None
    if user.avatar_url:
        if user.avatar_url.startswith('cloud://'):
            temp_urls = get_temp_file_urls([user.avatar_url])
            avatar_data = {
                'file_id': user.avatar_url,
                'url': temp_urls.get(user.avatar_url, '')
            }
        else:
            # 兼容直接URL（如微信头像）
            avatar_data = {
                'file_id': '',
                'url': user.avatar_url
            }
    
    is_merchant = user.assigned_identities.filter(identity_type='MERCHANT').exists()
    is_property = user.assigned_identities.filter(identity_type='PROPERTY').exists()
    data = {
        'system_id': user.system_id,
        'openid': user.openid,
        'nickname': user.nickname,
        'identity_type': user.identity_type,
        'active_identity': user.active_identity,
        'is_merchant': is_merchant,
        'is_property': is_property,
        'avatar': avatar_data,  # 返回 {file_id, url} 或 null
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
@require_http_methods(["PUT"])
def user_update_profile(request):
    """用户更新个人信息
    - 商户和物业身份只能通过申请获得，不能直接设置
    - 商户和物业身份可以切换成业主身份
    - 所有身份只能在第一次绑定物业，之后不能修改（物业身份只能绑定自己的物业）
    """
    openid = get_openid(request)
    try:
        user = UserInfo.objects.select_related(
            'owner_property__points_threshold',
            'property_profile'  # 预加载物业档案（如果是物业身份）
        ).get(openid=openid)
    except UserInfo.DoesNotExist:
        return json_err('用户不存在', status=404)
    
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)
    
    # 更新昵称
    if 'nickname' in body:
        user.nickname = body.get('nickname', '')
    
    # 更新头像（支持云文件ID）
    if 'avatar_file_id' in body:
        new_avatar = body.get('avatar_file_id', '').strip()
        old_avatar = user.avatar_url
        
        # 验证头像格式：必须是云文件ID或空字符串
        if new_avatar:
            # 拒绝本地临时文件路径
            if '127.0.0.1' in new_avatar or 'localhost' in new_avatar or '__tmp__' in new_avatar:
                logger.warning(f"拒绝本地临时文件路径: {new_avatar}")
                return json_err(
                    '不能使用本地临时文件路径。请先调用 /api/storage/upload-credential 获取上传凭证，'
                    '将文件上传到云存储后，再使用返回的 file_id（cloud:// 开头）',
                    status=400
                )
            
            # 验证必须是云文件ID格式（cloud:// 开头）
            if not new_avatar.startswith('cloud://'):
                logger.warning(f"无效的头像文件ID: {new_avatar}")
                return json_err(
                    '头像文件ID格式不正确，必须是云存储文件ID（cloud:// 开头）。'
                    '请先调用 /api/storage/upload-credential 获取上传凭证上传文件',
                    status=400
                )
        
        # 如果新旧头像不同，且旧头像是云文件，则删除旧头像
        if new_avatar != old_avatar:
            if old_avatar and old_avatar.startswith('cloud://'):
                try:
                    delete_cloud_files([old_avatar])
                    logger.info(f"已删除旧用户头像: {old_avatar}")
                except WxOpenApiError as exc:
                    logger.warning(f"删除旧用户头像失败: {old_avatar}, error={exc}")
        
        user.avatar_url = new_avatar
    
    if 'phone_number' in body:
        user.phone_number = body['phone_number']
    
    # 身份类型处理：
    # 1. 商户和物业身份只能通过申请获得，不能直接设置
    # 2. 商户和物业身份可以切换成业主身份
    if 'identity_type' in body:
        requested_identity = body['identity_type']
        
        # 不允许直接设置商户或物业身份（只能通过申请）
        if requested_identity in ['MERCHANT', 'PROPERTY']:
            return json_err('商户和物业身份需要通过申请流程获得，不能直接设置', status=400)
        
        # 允许切换成业主身份（活跃身份）
        if requested_identity == 'OWNER':
            user.active_identity = 'OWNER'
    
    # 物业绑定处理：所有身份只能在第一次绑定物业，之后不能修改
    if 'owner_property_id' in body:
        property_id = body['owner_property_id']
        
        # 检查用户是否已经绑定了物业
        if user.owner_property:
            return json_err('您已绑定物业，不能再次修改', status=400)
        
        if property_id:
            try:
                property_profile = PropertyProfile.objects.get(property_id=property_id)
                
                # 如果用户是物业身份，只能绑定自己的物业
                if user.identity_type == 'PROPERTY':
                    # 检查用户是否有对应的物业档案
                    try:
                        user_property_profile = user.property_profile
                    except PropertyProfile.DoesNotExist:
                        return json_err('物业身份用户未找到对应的物业档案', status=400)
                    
                    # 验证是否绑定的是自己的物业
                    if user_property_profile.property_id != property_id:
                        return json_err('物业身份用户只能绑定自己的物业', status=400)
                
                user.owner_property = property_profile
            except PropertyProfile.DoesNotExist:
                return json_err('物业不存在', status=404)
        else:
            # 不允许传入空值来解除物业绑定
            return json_err('物业绑定后不能解除', status=400)
    elif user.active_identity == 'PROPERTY' and not user.owner_property:
        # 物业身份用户如果还没有绑定物业，自动绑定自己的物业
        try:
            user_property_profile = user.property_profile
            user.owner_property = user_property_profile
        except PropertyProfile.DoesNotExist:
            # 如果物业身份用户还没有物业档案，不强制绑定（可能还在申请中）
            pass
    
    try:
        user.save()
        
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
        
        min_points = 0
        property_data = None
        
        if user.owner_property:
            property_profile = user.owner_property
            threshold = getattr(property_profile, 'points_threshold', None)
            min_points = threshold.min_points if threshold else 0
            property_data = {
                'property_id': property_profile.property_id,
                'property_name': property_profile.property_name,
                'community_name': property_profile.community_name,
                'min_points': min_points,
            }
        
        return json_ok({
            'system_id': user.system_id,
            'openid': user.openid,
            'nickname': user.nickname,
            'identity_type': user.active_identity,
            'avatar': avatar_data,
            'phone_number': user.phone_number,
            'daily_points': user.daily_points,
            'total_points': user.total_points,
            'min_points': min_points,
            'property': property_data,
        })
    except Exception as exc:
        logger.error(f'更新用户信息失败: {str(exc)}')
        return json_err(f'更新失败: {str(exc)}', status=400)


@openid_required
@require_http_methods(["POST"])
def identity_apply(request):
    """用户申请变更身份（商户/物业需审核，业主直接通过user_update_profile）"""
    openid = get_openid(request)
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
    
    # 商户和物业申请时都可以提交所在物业ID
    if 'owner_property_id' in body:
        application.owner_property_id = body.get('owner_property_id', '')
    
    if requested_identity == 'MERCHANT':
        application.merchant_name = body.get('merchant_name', '')
        application.merchant_description = body.get('merchant_description', '')
        application.merchant_address = body.get('merchant_address', '')
        application.merchant_phone = body.get('merchant_phone', '')
        
        if not application.merchant_name:
            return json_err('商户名称为必填项', status=400)
        
        # 商户申请时，必须选择所在物业（从存在的物业列表中选择）
        if not application.owner_property_id:
            return json_err('商户申请时必须选择所在物业', status=400)
        
        # 验证物业是否存在
        try:
            PropertyProfile.objects.get(property_id=application.owner_property_id)
        except PropertyProfile.DoesNotExist:
            return json_err('所选物业不存在', status=404)
    
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


def user_profile_handler(request):
    """处理用户信息的 GET 和 PUT 请求"""
    if request.method == 'GET':
        return user_profile(request)
    elif request.method == 'PUT':
        return user_update_profile(request)
    else:
        return json_err('不支持的请求方法', status=405)


@openid_required
@require_http_methods(["POST"])
def phone_number_resolve(request):
    openid = get_openid(request)
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)
    code = (body.get('code') or '').strip()
    if not code:
        return json_err('缺少参数 code', status=400)
    info = get_phone_number_by_code(code)
    return json_ok({
        'openid': openid,
        'phone_number': info.get('phoneNumber', ''),
        'pure_phone_number': info.get('purePhoneNumber', ''),
        'country_code': info.get('countryCode', ''),
    })


@openid_required
@require_http_methods(["PUT"])
def user_set_active_identity(request):
    openid = get_openid(request)
    try:
        user = UserInfo.objects.get(openid=openid)
    except UserInfo.DoesNotExist:
        return json_err('用户不存在', status=404)
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)
    identity_type = (body.get('identity_type') or '').strip()
    if identity_type not in ['OWNER', 'MERCHANT', 'PROPERTY']:
        return json_err('无效的身份类型', status=400)
    # 必须是已赋予身份
    if not user.assigned_identities.filter(identity_type=identity_type).exists():
        return json_err('该身份未赋予，无法切换', status=400)
    # 不允许同时拥有 MERCHANT 与 PROPERTY（assign 已防止，这里仅切换）
    user.active_identity = identity_type
    user.save()
    return json_ok({'active_identity': user.active_identity, 'available_identities': [ai.identity_type for ai in user.assigned_identities.all()]})


@openid_required
@require_http_methods(["GET"])
def user_profile(request):
    """获取用户详细信息（包含积分信息）
    - 所有身份都返回积分信息和所在物业信息
    """
    openid = get_openid(request)
    try:
        user = UserInfo.objects.select_related('owner_property__points_threshold').get(openid=openid)
    except UserInfo.DoesNotExist:
        return json_err('用户不存在', status=404)

    # 处理头像：返回 file_id 和临时 URL
    avatar_data = None
    if user.avatar_url:
        if user.avatar_url.startswith('cloud://'):
            temp_urls = get_temp_file_urls([user.avatar_url])
            avatar_data = {
                'file_id': user.avatar_url,
                'url': temp_urls.get(user.avatar_url, '')
            }
        else:
            # 兼容直接URL（如微信头像）
            avatar_data = {
                'file_id': '',
                'url': user.avatar_url
            }

    # 获取积分阈值（只要用户关联了物业，无论身份类型，都返回所在物业的积分阈值）
    # 商户和物业身份也可能关联物业（因为可以在业主身份之间切换）
    min_points = 0
    property_data = None
    
    if user.owner_property:
        property_profile = user.owner_property
        threshold = getattr(property_profile, 'points_threshold', None)
        min_points = threshold.min_points if threshold else 0
        
        property_data = {
            'property_id': property_profile.property_id,
            'property_name': property_profile.property_name,
            'community_name': property_profile.community_name,
            'min_points': min_points,  # 积分阈值
        }
    elif user.identity_type == 'PROPERTY':
        try:
            property_profile = user.property_profile
            threshold = getattr(property_profile, 'points_threshold', None)
            min_points = threshold.min_points if threshold else 0
            property_data = {
                'property_id': property_profile.property_id,
                'property_name': property_profile.property_name,
                'community_name': property_profile.community_name,
                'min_points': min_points,
            }
        except PropertyProfile.DoesNotExist:
            pass

    data = {
        'system_id': user.system_id,
        'openid': user.openid,
        'nickname': user.nickname,
        'identity_type': user.active_identity,
        'avatar': avatar_data,  # 返回 {file_id, url} 或 null
        'phone_number': user.phone_number,
        'daily_points': user.daily_points,      # 当日积分
        'total_points': user.total_points,      # 累计积分
        'min_points': min_points,               # 积分阈值（用户关联了物业时返回所在物业的积分阈值，否则为0）
        'property': property_data,              # 物业信息（用户关联了物业时有值，否则为null）
    }

    # 商户身份返回商户档案信息
    if user.active_identity == 'MERCHANT':
        try:
            merchant = user.merchant_profile
            banner_data = None
            if merchant.banner_url:
                if merchant.banner_url.startswith('cloud://'):
                    temp_urls2 = get_temp_file_urls([merchant.banner_url])
                    banner_data = {
                        'file_id': merchant.banner_url,
                        'url': temp_urls2.get(merchant.banner_url, '')
                    }
                else:
                    banner_data = {
                        'file_id': merchant.banner_url,
                        'url': merchant.banner_url
                    }
            data['merchant'] = {
                'merchant_id': merchant.merchant_id,
                'merchant_name': merchant.merchant_name,
                'title': merchant.title,
                'description': merchant.description,
                'banner': banner_data,
                'category_id': merchant.category.id if merchant.category else None,
                'category_name': merchant.category.name if merchant.category else None,
                'contact_phone': merchant.contact_phone,
                'address': merchant.address,
                'positive_rating_percent': merchant.positive_rating_percent,
                'open_hours': merchant.open_hours,
                'gallery': merchant.gallery or [],
                'rating_count': merchant.rating_count,
                'avg_score': float(merchant.avg_score) if merchant.avg_score is not None else 0,
            }
        except MerchantProfile.DoesNotExist:
            data['merchant'] = None

    return json_ok(data)


@openid_required
@require_http_methods(["GET"])
def properties_public_list(request):
    """获取所有物业列表（供业主和商户选择）
    - 只有通过审核的物业身份用户，其对应的物业档案才会出现在列表中
    """
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
    qs = PropertyProfile.objects.select_related('user').all().order_by('-updated_at', '-id')
    if cursor_filter:
        cursor_dt, cursor_pk = cursor_filter
        qs = qs.filter(Q(updated_at__lt=cursor_dt) | Q(updated_at=cursor_dt, id__lt=cursor_pk))
    properties = list(qs[: page_size + 1])
    has_more = len(properties) > page_size
    sliced = properties[:page_size]
    items = []
    for p in sliced:
        items.append({
            'property_id': p.property_id,
            'property_name': p.property_name,
            'community_name': p.community_name,
        })
    next_cursor = f"{sliced[-1].updated_at.isoformat()}#{sliced[-1].id}" if has_more and sliced else None
    return json_ok({'list': items, 'has_more': has_more, 'next_cursor': next_cursor})
