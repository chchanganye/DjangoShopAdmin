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

