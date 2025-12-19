"""管理员用户管理视图"""
import json
import logging
from django.views.decorators.http import require_http_methods

from wxcloudrun.decorators import admin_token_required
from wxcloudrun.utils.responses import json_ok, json_err
from wxcloudrun.exceptions import WxOpenApiError
from wxcloudrun.models import (
    Category,
    UserInfo,
    MerchantProfile,
    PropertyProfile,
    PointsThreshold,
)
from wxcloudrun.services.storage_service import get_temp_file_urls, delete_cloud_files


logger = logging.getLogger('log')


@admin_token_required
@require_http_methods(["GET", "POST"])
def admin_users(request, admin):
    """用户管理 - GET列表 / POST创建"""
    if request.method == 'GET':
        from datetime import datetime
        from django.db.models import Q
        from django.utils.dateparse import parse_datetime
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
        qs = UserInfo.objects.select_related('owner_property').all().order_by('-updated_at', '-id')
        if cursor_filter:
            cursor_dt, cursor_pk = cursor_filter
            qs = qs.filter(Q(updated_at__lt=cursor_dt) | Q(updated_at=cursor_dt, id__lt=cursor_pk))
        users = list(qs[: page_size + 1])
        avatar_file_ids = [u.avatar_url for u in users if u.avatar_url and u.avatar_url.startswith('cloud://')]
        temp_urls = get_temp_file_urls(avatar_file_ids) if avatar_file_ids else {}
        has_more = len(users) > page_size
        sliced = users[:page_size]
        items = []
        for u in sliced:
            avatar_data = None
            if u.avatar_url:
                if u.avatar_url.startswith('cloud://'):
                    avatar_data = {
                        'file_id': u.avatar_url,
                        'url': temp_urls.get(u.avatar_url, '')
                    }
                else:
                    avatar_data = {
                        'file_id': '',
                        'url': u.avatar_url
                    }
            is_merchant = MerchantProfile.objects.filter(user=u).exists()
            is_property = PropertyProfile.objects.filter(user=u).exists()
            items.append({
                'system_id': u.system_id,
                'openid': u.openid,
                'nickname': u.nickname,
                'identity_type': u.active_identity,
                'active_identity': u.active_identity,
                'is_merchant': is_merchant,
                'is_property': is_property,
                'avatar': avatar_data,
                'phone_number': u.phone_number,
                'daily_points': u.daily_points,
                'total_points': u.total_points,
                'owner_property_id': u.owner_property.property_id if u.owner_property else None,
                'owner_property_name': u.owner_property.property_name if u.owner_property else None,
                'created_at': u.created_at.strftime('%Y-%m-%d %H:%M:%S') if u.created_at else None,
                'updated_at': u.updated_at.strftime('%Y-%m-%d %H:%M:%S') if u.updated_at else None,
            })
        next_cursor = f"{sliced[-1].updated_at.isoformat()}#{sliced[-1].id}" if has_more and sliced else None
        return json_ok({'list': items, 'has_more': has_more, 'next_cursor': next_cursor})

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
            avatar_url=avatar_file_id,
            phone_number=body.get('phone_number', ''),
            owner_property=owner_property,
            daily_points=body.get('daily_points', 0),
            total_points=body.get('total_points', 0),
        )
        from wxcloudrun.models import UserAssignedIdentity
        try:
            UserAssignedIdentity.objects.get_or_create(user=user, identity_type='OWNER')
            UserAssignedIdentity.objects.get_or_create(user=user, identity_type=identity_type)
        except Exception:
            pass
        try:
            user.active_identity = identity_type
            user.save()
        except Exception:
            pass
        
        # 根据身份类型自动创建对应的档案
        if identity_type == 'MERCHANT':
            # 验证商户必填字段
            merchant_name = body.get('merchant_name')
            if not merchant_name:
                return json_err('商户名称为必填项', status=400)
            
            category_id = body.get('category_id')
            if not category_id:
                return json_err('商户分类为必填项', status=400)
            
            contact_phone = body.get('merchant_phone') or ''
            
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
            user.owner_property = property_profile
            user.save()
        elif identity_type == 'MERCHANT':
            if owner_property_id:
                try:
                    user.owner_property = PropertyProfile.objects.get(property_id=owner_property_id)
                    user.save()
                except PropertyProfile.DoesNotExist:
                    return json_err('物业不存在', status=404)
        
        return json_ok({
            'system_id': user.system_id,
            'openid': user.openid,
            'nickname': user.nickname,
            'avatar_url': user.avatar_url,
            'phone_number': user.phone_number,
            'identity_type': user.active_identity,
            'active_identity': user.active_identity,
            'is_merchant': MerchantProfile.objects.filter(user=user).exists(),
            'is_property': PropertyProfile.objects.filter(user=user).exists(),
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
    
    old_identity = user.identity_type
    new_identity = None
    
    if 'nickname' in body:
        user.nickname = body.get('nickname', '')
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
        user.active_identity = identity_type
        new_identity = identity_type
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
    
    # 处理身份变更的关联档案同步
    try:
        if new_identity and new_identity != old_identity:
            if new_identity == 'ADMIN':
                user.owner_property = None
            
            # OWNER/ADMIN：不删除商户与物业档案，仅切换活跃身份
            if new_identity in ['OWNER', 'ADMIN']:
                pass
            elif new_identity == 'MERCHANT':
                # 切换为商户：如无商户档案则按入参创建
                need_create = not hasattr(user, 'merchant_profile')
                if need_create:
                    merchant_name = body.get('merchant_name')
                    category_id = body.get('category_id')
                    contact_phone = body.get('merchant_phone') or ''
                    address = body.get('merchant_address')
                    banner_file_id = body.get('banner_file_id')
                    if not merchant_name:
                        return json_err('商户名称为必填项', status=400)
                    if not category_id:
                        return json_err('商户分类为必填项', status=400)
                    if not address:
                        return json_err('商户地址为必填项', status=400)
                    if not banner_file_id:
                        return json_err('商户横幅展示图为必填项', status=400)
                    try:
                        category = Category.objects.get(id=category_id)
                    except Category.DoesNotExist:
                        return json_err('分类不存在', status=404)
                    MerchantProfile.objects.create(
                        user=user,
                        merchant_name=merchant_name,
                        description=body.get('merchant_description', ''),
                        address=address,
                        contact_phone=contact_phone,
                        banner_url=banner_file_id,
                        category=category,
                    )
                owner_property_id = body.get('owner_property_id')
                if owner_property_id:
                    try:
                        user.owner_property = PropertyProfile.objects.get(property_id=owner_property_id)
                    except PropertyProfile.DoesNotExist:
                        return json_err('物业不存在', status=404)
                # 保留可能存在的物业档案
                pass
            elif new_identity == 'PROPERTY':
                # 切换为物业：如无物业档案则按入参创建
                need_create = not hasattr(user, 'property_profile')
                if need_create:
                    property_name = body.get('property_name')
                    community_name = body.get('community_name', '')
                    if not property_name:
                        return json_err('物业名称为必填项', status=400)
                    property_profile = PropertyProfile.objects.create(
                        user=user,
                        property_name=property_name,
                        community_name=community_name,
                    )
                    min_points = body.get('min_points')
                    if min_points is not None:
                        try:
                            PointsThreshold.objects.create(
                                property=property_profile,
                                min_points=int(min_points)
                            )
                        except Exception:
                            return json_err('min_points 必须为整数', status=400)
                user.owner_property = user.property_profile if hasattr(user, 'property_profile') else None
                # 保留可能存在的商户档案
                pass
        
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
            'nickname': user.nickname,
            'avatar': avatar_data,
            'phone_number': user.phone_number,
            'identity_type': user.active_identity,
            'active_identity': user.active_identity,
            'is_merchant': MerchantProfile.objects.filter(user=user).exists(),
            'is_property': PropertyProfile.objects.filter(user=user).exists(),
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

