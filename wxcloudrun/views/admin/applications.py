"""管理员申请审核管理视图"""
import json
import logging
from datetime import datetime
from django.views.decorators.http import require_http_methods
from django.db import transaction

from wxcloudrun.decorators import admin_token_required
from wxcloudrun.utils.responses import json_ok, json_err
from wxcloudrun.models import UserInfo, MerchantProfile, PropertyProfile, IdentityApplication


logger = logging.getLogger('log')


@admin_token_required
@require_http_methods(["GET"])
def admin_applications_list(request, admin):
    status_filter = request.GET.get('status')
    current_param = request.GET.get('current') or request.GET.get('page')
    size_param = request.GET.get('size') or request.GET.get('page_size') or request.GET.get('limit')

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

    qs = IdentityApplication.objects.select_related('user').all().order_by('-created_at', '-id')
    if status_filter and status_filter in ['PENDING', 'APPROVED', 'REJECTED']:
        qs = qs.filter(status=status_filter)
    total = qs.count()
    start = (page - 1) * page_size
    apps = list(qs[start : start + page_size])
    items = []
    for app in apps:
        items.append({
            'id': app.id,
            'openid': app.user.openid,
            'system_id': app.user.system_id,
            'requested_identity': app.requested_identity,
            'status': app.status,
            'owner_property_id': app.owner_property_id,
            'merchant_name': app.merchant_name,
            'merchant_description': app.merchant_description,
            'merchant_address': app.merchant_address,
            'merchant_phone': app.merchant_phone,
            'merchant_type': getattr(app, 'merchant_type', 'NORMAL'),
            'property_name': app.property_name,
            'property_community': app.property_community,
            'reviewed_by': app.reviewed_by.username if app.reviewed_by else None,
            'reviewed_at': app.reviewed_at.strftime('%Y-%m-%d %H:%M:%S') if app.reviewed_at else None,
            'reject_reason': app.reject_reason,
            'created_at': app.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        })
    return json_ok({'list': items, 'total': total})


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
        with transaction.atomic():
            # 赋予身份（不允许同时拥有商户与物业）
            from wxcloudrun.models import UserAssignedIdentity
            if requested_identity in ['MERCHANT', 'PROPERTY']:
                conflict = (requested_identity == 'MERCHANT' and user.assigned_identities.filter(identity_type='PROPERTY').exists()) or \
                           (requested_identity == 'PROPERTY' and user.assigned_identities.filter(identity_type='MERCHANT').exists())
                if conflict:
                    return json_err('商户与物业身份不可同时存在，请先撤销现有身份', status=400)
            UserAssignedIdentity.objects.get_or_create(user=user, identity_type=requested_identity)
            UserAssignedIdentity.objects.get_or_create(user=user, identity_type='OWNER')
            user.active_identity = requested_identity
            user.save()
            
            # 根据申请类型创建对应档案
            if requested_identity == 'MERCHANT':
                MerchantProfile.objects.create(
                    user=user,
                    merchant_name=application.merchant_name,
                    merchant_type=getattr(application, 'merchant_type', 'NORMAL') or 'NORMAL',
                    description=application.merchant_description,
                    address=application.merchant_address,
                    contact_phone=application.merchant_phone,
                )
                
                # 商户申请通过时，自动绑定所在物业（如果申请时填写了物业ID）
                if application.owner_property_id:
                    try:
                        property_profile = PropertyProfile.objects.get(property_id=application.owner_property_id)
                        user.owner_property = property_profile
                        user.save()
                    except PropertyProfile.DoesNotExist:
                        logger.warning(f"商户申请的物业不存在: {application.owner_property_id}")
                
            elif requested_identity == 'PROPERTY':
                # 创建物业档案
                property_profile = PropertyProfile.objects.create(
                    user=user,
                    property_name=application.property_name,
                    community_name=application.property_community,
                )
                
                # 物业申请通过时，自动绑定自己的物业
                user.owner_property = property_profile
                user.save()
            
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
