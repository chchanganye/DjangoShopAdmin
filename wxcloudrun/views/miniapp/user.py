"""小程序端用户相关视图"""
import json
import logging
from datetime import date, datetime
from django.views.decorators.http import require_http_methods

from wxcloudrun.decorators import openid_required
from wxcloudrun.utils.responses import json_ok, json_err
from wxcloudrun.utils.auth import get_openid
from wxcloudrun.models import UserInfo, PropertyProfile, IdentityApplication, AccessLog
from wxcloudrun.services.storage_service import get_temp_file_urls, delete_cloud_files
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
    
    data = {
        'system_id': user.system_id,
        'openid': user.openid,
        'nickname': user.nickname,
        'identity_type': user.identity_type,
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
    """用户更新个人信息（仅业主身份可直接绑定物业，其他身份需走申请流程）"""
    openid = get_openid(request)
    try:
        user = UserInfo.objects.get(openid=openid)
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
        new_avatar = body.get('avatar_file_id', '')
        old_avatar = user.avatar_url
        
        # 如果新旧头像不同，且旧头像是云文件，则删除旧头像
        if new_avatar != old_avatar and old_avatar and old_avatar.startswith('cloud://'):
            try:
                delete_cloud_files([old_avatar])
            except WxOpenApiError as exc:
                logger.warning(f"删除旧用户头像失败: {old_avatar}, error={exc}")
        
        user.avatar_url = new_avatar
    
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
        
        return json_ok({
            'system_id': user.system_id,
            'openid': user.openid,
            'nickname': user.nickname,
            'identity_type': user.identity_type,
            'avatar': avatar_data,  # 返回 {file_id, url} 或 null
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


@openid_required
@require_http_methods(["GET"])
def user_profile(request):
    """获取用户详细信息"""
    openid = get_openid(request)
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

