"""管理员用户身份管理视图"""
import json
from django.views.decorators.http import require_http_methods

from wxcloudrun.decorators import admin_token_required
from wxcloudrun.utils.responses import json_ok, json_err
from wxcloudrun.models import UserInfo, UserAssignedIdentity


def _conflict_exists(user: UserInfo, target: str) -> bool:
    if target == 'MERCHANT':
        return user.assigned_identities.filter(identity_type='PROPERTY').exists()
    if target == 'PROPERTY':
        return user.assigned_identities.filter(identity_type='MERCHANT').exists()
    return False


@admin_token_required
@require_http_methods(["POST"])
def admin_identity_assign(request, admin, system_id):
    try:
        user = UserInfo.objects.get(system_id=system_id)
    except UserInfo.DoesNotExist:
        return json_err('用户不存在', status=404)

    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)

    identity_type = (body.get('identity_type') or '').strip()
    if identity_type not in ['OWNER', 'MERCHANT', 'PROPERTY', 'ADMIN']:
        return json_err('无效的身份类型', status=400)

    # 冲突校验：不允许 MERCHANT 与 PROPERTY 同时存在
    if identity_type in ['MERCHANT', 'PROPERTY'] and _conflict_exists(user, identity_type):
        return json_err('商户与物业身份不可同时存在，请先撤销现有身份', status=400)

    UserAssignedIdentity.objects.get_or_create(user=user, identity_type=identity_type)
    return json_ok({'system_id': user.system_id, 'assigned': identity_type})


@admin_token_required
@require_http_methods(["POST"])
def admin_identity_revoke(request, admin, system_id):
    try:
        user = UserInfo.objects.get(system_id=system_id)
    except UserInfo.DoesNotExist:
        return json_err('用户不存在', status=404)

    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)

    identity_type = (body.get('identity_type') or '').strip()
    if identity_type not in ['OWNER', 'MERCHANT', 'PROPERTY', 'ADMIN']:
        return json_err('无效的身份类型', status=400)

    UserAssignedIdentity.objects.filter(user=user, identity_type=identity_type).delete()
    if user.active_identity == identity_type:
        user.active_identity = 'OWNER'
        user.save()
    return json_ok({'system_id': user.system_id, 'revoked': identity_type})


@admin_token_required
@require_http_methods(["PUT"])
def admin_identity_active_set(request, admin, system_id):
    try:
        user = UserInfo.objects.get(system_id=system_id)
    except UserInfo.DoesNotExist:
        return json_err('用户不存在', status=404)

    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)

    identity_type = (body.get('identity_type') or '').strip()
    if identity_type not in ['OWNER', 'MERCHANT', 'PROPERTY', 'ADMIN']:
        return json_err('无效的身份类型', status=400)

    # 必须是已赋予身份
    if not user.assigned_identities.filter(identity_type=identity_type).exists():
        return json_err('该身份未赋予，无法切换', status=400)

    # 冲突安全：仍不允许激活 MERCHANT 与 PROPERTY 同时存在（理论上 assign 已防止）
    if identity_type in ['MERCHANT', 'PROPERTY'] and _conflict_exists(user, identity_type):
        return json_err('商户与物业身份不可同时存在', status=400)

    user.active_identity = identity_type
    user.save()
    return json_ok({'system_id': user.system_id, 'active_identity': user.active_identity})