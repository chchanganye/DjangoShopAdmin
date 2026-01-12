"""管理员用户管理视图"""
import json
import logging
from datetime import date
from django.views.decorators.http import require_http_methods
from django.db.models import Q

from wxcloudrun.decorators import admin_token_required
from wxcloudrun.utils.responses import json_ok, json_err
from wxcloudrun.exceptions import WxOpenApiError
from wxcloudrun.models import (
    Category,
    UserInfo,
    MerchantProfile,
    PropertyProfile,
    PointsThreshold,
    PointsRecord,
    UserPointsAccount,
)
from wxcloudrun.services.points_service import get_points_account
from wxcloudrun.services.storage_service import get_temp_file_urls, delete_cloud_files


logger = logging.getLogger('log')


_POINTS_IDENTITIES = ('OWNER', 'MERCHANT', 'PROPERTY')


def _build_points_accounts(accounts):
    """把 UserPointsAccount 列表序列化为 points_accounts（不创建缺失账户）。"""
    today = date.today()
    account_map = {a.identity_type: a for a in accounts}
    points_accounts = {}
    for identity in _POINTS_IDENTITIES:
        account = account_map.get(identity)
        if not account:
            points_accounts[identity] = {'daily_points': 0, 'total_points': 0}
            continue
        points_accounts[identity] = {
            'daily_points': account.daily_points if account.daily_points_date == today else 0,
            'total_points': account.total_points,
        }
    return points_accounts


def _update_points_accounts(user: UserInfo, payload, *, admin=None, source_type: str = 'ADMIN_ADJUST'):
    """按 payload 更新积分账户（支持 dict / list 两种结构）。

    - dict：{"OWNER": {"total_points": 1}, "MERCHANT": {...}}
    - list：[{"identity_type": "OWNER", "total_points": 1}, ...]
    """
    today = date.today()

    if isinstance(payload, dict):
        items = list(payload.items())
    elif isinstance(payload, list):
        items = []
        for item in payload:
            if not isinstance(item, dict):
                raise ValueError('points_accounts 数组元素必须为对象')
            identity = item.get('identity_type')
            if not identity:
                raise ValueError('points_accounts.identity_type 必填')
            items.append((identity, item))
    else:
        raise ValueError('points_accounts 必须为对象或数组')

    for identity, data in items:
        if identity not in _POINTS_IDENTITIES:
            raise ValueError('points_accounts 身份类型仅支持 OWNER/MERCHANT/PROPERTY')
        if data is None:
            continue
        if not isinstance(data, dict):
            raise ValueError(f'points_accounts.{identity} 必须为对象')

        has_daily = 'daily_points' in data
        has_total = 'total_points' in data
        if not has_daily and not has_total:
            continue

        account, _ = UserPointsAccount.objects.get_or_create(
            user=user,
            identity_type=identity,
            defaults={'daily_points_date': today},
        )
        old_daily_points = account.daily_points if account.daily_points_date == today else 0
        old_total_points = account.total_points
        if has_daily:
            try:
                account.daily_points = int(data.get('daily_points') or 0)
            except (TypeError, ValueError):
                raise ValueError(f'points_accounts.{identity}.daily_points 必须为整数')
            account.daily_points_date = today
        if has_total:
            try:
                account.total_points = int(data.get('total_points') or 0)
            except (TypeError, ValueError):
                raise ValueError(f'points_accounts.{identity}.total_points 必须为整数')
        account.save()

        # 写入管理员调整记录（仅在实际变化时记录）
        delta_total = account.total_points - old_total_points if has_total else 0
        delta_daily = account.daily_points - old_daily_points if has_daily else 0
        delta_value = delta_total if has_total else delta_daily
        if delta_value != 0 and admin:
            PointsRecord.objects.create(
                user=user,
                identity_type=identity,
                change=int(delta_value),
                daily_points=account.daily_points if account.daily_points_date == today else 0,
                total_points=account.total_points,
                source_type=source_type,
                source_meta={
                    'operator': {
                        'id': getattr(admin, 'id', None),
                        'username': getattr(admin, 'username', '') or '',
                    },
                    'old_total_points': old_total_points,
                    'new_total_points': account.total_points,
                    'old_daily_points': old_daily_points,
                    'new_daily_points': account.daily_points if account.daily_points_date == today else 0,
                },
            )


@admin_token_required
@require_http_methods(["GET", "POST"])
def admin_users(request, admin):
    """用户管理 - GET列表 / POST创建"""
    if request.method == 'GET':
        current_param = request.GET.get('current') or request.GET.get('page')
        size_param = request.GET.get('size') or request.GET.get('page_size') or request.GET.get('limit')
        keyword = (request.GET.get('keyword') or request.GET.get('q') or '').strip()

        page = 1
        page_size = 20

        if current_param:
            try:
                page = int(current_param)
            except (TypeError, ValueError):
                return json_err('current 必须为数字', status=400)
        if size_param:
            try:
                page_size = int(size_param)
            except (TypeError, ValueError):
                return json_err('size 必须为数字', status=400)
        if page < 1:
            page = 1
        if page_size < 1:
            page_size = 1
        if page_size > 100:
            page_size = 100

        qs = (
            UserInfo.objects.select_related('owner_property')
            .prefetch_related('points_accounts')
            .all()
            .order_by('-updated_at', '-id')
        )
        if keyword:
            qs = qs.filter(
                Q(phone_number__icontains=keyword)
                | Q(nickname__icontains=keyword)
            )
        total = qs.count()
        start = (page - 1) * page_size
        users = list(qs[start : start + page_size])
        avatar_file_ids = [u.avatar_url for u in users if u.avatar_url and u.avatar_url.startswith('cloud://')]
        temp_urls = get_temp_file_urls(avatar_file_ids) if avatar_file_ids else {}
        user_ids = [u.id for u in users]
        merchant_user_ids = set(
            MerchantProfile.objects.filter(user_id__in=user_ids).values_list('user_id', flat=True)
        )
        property_user_ids = set(
            PropertyProfile.objects.filter(user_id__in=user_ids).values_list('user_id', flat=True)
        )

        items = []
        for u in users:
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

            is_merchant = u.id in merchant_user_ids
            is_property = u.id in property_user_ids
            points_accounts = _build_points_accounts(list(u.points_accounts.all()))
            points_identity = u.active_identity if u.active_identity in _POINTS_IDENTITIES else 'OWNER'
            active_points = points_accounts.get(points_identity) or {'daily_points': 0, 'total_points': 0}
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
                'daily_points': active_points['daily_points'],
                'total_points': active_points['total_points'],
                'points_accounts': points_accounts,
                'owner_property_id': u.owner_property.property_id if u.owner_property else None,
                'owner_property_name': u.owner_property.property_name if u.owner_property else None,
                'created_at': u.created_at.strftime('%Y-%m-%d %H:%M:%S') if u.created_at else None,
                'updated_at': u.updated_at.strftime('%Y-%m-%d %H:%M:%S') if u.updated_at else None,
            })
        return json_ok({'list': items, 'total': total})

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
        points_account = get_points_account(user, identity_type)
        if 'daily_points' in body:
            points_account.daily_points = int(body.get('daily_points') or 0)
            points_account.daily_points_date = date.today()
        if 'total_points' in body:
            points_account.total_points = int(body.get('total_points') or 0)
        if 'daily_points' in body or 'total_points' in body:
            points_account.save()
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

            merchant_type = (body.get('merchant_type') or 'NORMAL').strip().upper()
            if merchant_type not in ['NORMAL', 'DISCOUNT_STORE']:
                return json_err('merchant_type 仅支持 NORMAL/DISCOUNT_STORE', status=400)
            
            # 验证分类是否存在
            try:
                category = Category.objects.get(id=category_id)
            except Category.DoesNotExist:
                return json_err('分类不存在', status=404)
            
            # 创建商户档案
            MerchantProfile.objects.create(
                user=user,
                merchant_name=merchant_name,
                merchant_type=merchant_type,
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
        
        points_accounts = _build_points_accounts(
            list(UserPointsAccount.objects.filter(user=user, identity_type__in=_POINTS_IDENTITIES))
        )
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
            'daily_points': points_account.daily_points,
            'total_points': points_account.total_points,
            'points_accounts': points_accounts,
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

    points_account = None
    if 'points_accounts' in body:
        try:
            _update_points_accounts(user, body.get('points_accounts'), admin=admin, source_type='ADMIN_ADJUST')
        except ValueError as exc:
            return json_err(str(exc), status=400)
    if 'daily_points' in body or 'total_points' in body:
        points_account = get_points_account(user, user.active_identity)
        old_daily_points = points_account.daily_points
        old_total_points = points_account.total_points
        if 'daily_points' in body:
            points_account.daily_points = int(body['daily_points'])
            points_account.daily_points_date = date.today()
        if 'total_points' in body:
            points_account.total_points = int(body['total_points'])
        points_account.save()

        delta_total = points_account.total_points - old_total_points if 'total_points' in body else 0
        delta_daily = points_account.daily_points - old_daily_points if 'daily_points' in body else 0
        delta_value = delta_total if 'total_points' in body else delta_daily
        if delta_value != 0:
            PointsRecord.objects.create(
                user=user,
                identity_type=points_account.identity_type,
                change=int(delta_value),
                daily_points=points_account.daily_points,
                total_points=points_account.total_points,
                source_type='ADMIN_ADJUST',
                source_meta={
                    'operator': {
                        'id': getattr(admin, 'id', None),
                        'username': getattr(admin, 'username', '') or '',
                    },
                    'old_total_points': old_total_points,
                    'new_total_points': points_account.total_points,
                    'old_daily_points': old_daily_points,
                    'new_daily_points': points_account.daily_points,
                },
            )
    
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
                    merchant_type = (body.get('merchant_type') or 'NORMAL').strip().upper()
                    if merchant_type not in ['NORMAL', 'DISCOUNT_STORE']:
                        return json_err('merchant_type 仅支持 NORMAL/DISCOUNT_STORE', status=400)
                    try:
                        category = Category.objects.get(id=category_id)
                    except Category.DoesNotExist:
                        return json_err('分类不存在', status=404)
                    MerchantProfile.objects.create(
                        user=user,
                        merchant_name=merchant_name,
                        merchant_type=merchant_type,
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

        if points_account is None:
            points_account = get_points_account(user, user.active_identity)
        points_accounts = _build_points_accounts(
            list(UserPointsAccount.objects.filter(user=user, identity_type__in=_POINTS_IDENTITIES))
        )
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
            'daily_points': points_account.daily_points,
            'total_points': points_account.total_points,
            'points_accounts': points_accounts,
            'owner_property_id': user.owner_property.property_id if user.owner_property else None,
            'owner_property_name': user.owner_property.property_name if user.owner_property else None,
            'created_at': user.created_at.strftime('%Y-%m-%d %H:%M:%S') if user.created_at else None,
            'updated_at': user.updated_at.strftime('%Y-%m-%d %H:%M:%S') if user.updated_at else None,
        })
    except Exception as e:
        logger.error(f'更新用户失败: {str(e)}')
        return json_err(f'更新失败: {str(e)}', status=400)

