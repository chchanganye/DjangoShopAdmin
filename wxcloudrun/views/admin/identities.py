"""管理员用户身份管理视图"""
import json
from django.views.decorators.http import require_http_methods

from wxcloudrun.decorators import admin_token_required
from wxcloudrun.utils.responses import json_ok, json_err
from wxcloudrun.models import UserInfo, UserAssignedIdentity, Category, MerchantProfile, PropertyProfile, PointsThreshold


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
    result = {
        'system_id': user.system_id,
        'assigned': identity_type,
        'active_identity': user.active_identity,
        'is_merchant': MerchantProfile.objects.filter(user=user).exists(),
        'is_property': PropertyProfile.objects.filter(user=user).exists(),
    }
    
    if identity_type == 'MERCHANT':
        need_create = not hasattr(user, 'merchant_profile')
        merchant_name = (body.get('merchant_name') or '').strip()
        category_id = body.get('category_id')
        contact_phone = (body.get('merchant_phone') or '').strip()
        address = (body.get('merchant_address') or '').strip()
        banner_file_id = (body.get('banner_file_id') or '').strip()
        if need_create:
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
        else:
            mp = user.merchant_profile
            if merchant_name:
                mp.merchant_name = merchant_name
            if 'merchant_description' in body:
                mp.description = body.get('merchant_description', '')
            if address:
                mp.address = address
            if 'merchant_phone' in body:
                mp.contact_phone = contact_phone
            if banner_file_id:
                mp.banner_url = banner_file_id
            if category_id:
                try:
                    mp.category = Category.objects.get(id=category_id)
                except Category.DoesNotExist:
                    return json_err('分类不存在', status=404)
            mp.save()
        owner_property_id = body.get('owner_property_id')
        if owner_property_id:
            try:
                user.owner_property = PropertyProfile.objects.get(property_id=owner_property_id)
            except PropertyProfile.DoesNotExist:
                return json_err('物业不存在', status=404)
        user.active_identity = 'MERCHANT'
        user.save()
        result['active_identity'] = user.active_identity
        result['is_merchant'] = MerchantProfile.objects.filter(user=user).exists()
        result['is_property'] = PropertyProfile.objects.filter(user=user).exists()
        m = user.merchant_profile
        result['merchant'] = {
            'merchant_id': m.merchant_id,
            'merchant_name': m.merchant_name,
            'title': m.title,
            'description': m.description,
            'banner_file_id': m.banner_url,
            'category_id': m.category.id if m.category else None,
            'category_name': m.category.name if m.category else None,
            'contact_phone': m.contact_phone,
            'address': m.address,
        }
    elif identity_type == 'PROPERTY':
        need_create = not hasattr(user, 'property_profile')
        property_name = (body.get('property_name') or '').strip()
        community_name = (body.get('community_name') or '').strip()
        if need_create:
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
                    PointsThreshold.objects.create(property=property_profile, min_points=int(min_points))
                except Exception:
                    return json_err('min_points 必须为整数', status=400)
        else:
            pp = user.property_profile
            if property_name:
                pp.property_name = property_name
            if 'community_name' in body:
                pp.community_name = community_name
            pp.save()
            if 'min_points' in body:
                min_points = body.get('min_points')
                if min_points is None:
                    if hasattr(pp, 'points_threshold'):
                        pp.points_threshold.delete()
                else:
                    PointsThreshold.objects.update_or_create(property=pp, defaults={'min_points': int(min_points)})
        user.owner_property = user.property_profile
        user.active_identity = 'PROPERTY'
        user.save()
        result['active_identity'] = user.active_identity
        result['is_merchant'] = MerchantProfile.objects.filter(user=user).exists()
        result['is_property'] = PropertyProfile.objects.filter(user=user).exists()
        p = user.property_profile
        result['property'] = {
            'property_id': p.property_id,
            'property_name': p.property_name,
            'community_name': p.community_name,
            'min_points': p.points_threshold.min_points if hasattr(p, 'points_threshold') else 0,
        }
    return json_ok(result)


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
    return json_ok({
        'system_id': user.system_id,
        'revoked': identity_type,
        'active_identity': user.active_identity,
        'is_merchant': MerchantProfile.objects.filter(user=user).exists(),
        'is_property': PropertyProfile.objects.filter(user=user).exists(),
    })


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
    return json_ok({
        'system_id': user.system_id,
        'active_identity': user.active_identity,
        'is_merchant': MerchantProfile.objects.filter(user=user).exists(),
        'is_property': PropertyProfile.objects.filter(user=user).exists(),
    })
