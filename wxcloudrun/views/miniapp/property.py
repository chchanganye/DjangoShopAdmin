"""小程序端物业相关视图"""
from django.views.decorators.http import require_http_methods

from wxcloudrun.decorators import openid_required
from wxcloudrun.utils.responses import json_ok, json_err
from wxcloudrun.models import PropertyProfile, UserInfo


@openid_required
@require_http_methods(["GET"])
def properties_list(request):
    """获取物业列表"""
    qs = PropertyProfile.objects.select_related('user').all().order_by('id')
    items = []
    for p in qs:
        items.append({
            'property_name': p.property_name,
            'community_name': p.community_name,
            'property_id': p.property_id,
        })
    return json_ok({'total': qs.count(), 'list': items})


@openid_required
@require_http_methods(["GET"])
def owners_by_property(request, property_id):
    """按物业ID获取业主列表"""
    try:
        prop = PropertyProfile.objects.get(property_id=property_id)
    except PropertyProfile.DoesNotExist:
        return json_err('物业不存在', status=404)
    
    owners = UserInfo.objects.filter(owner_property=prop, identity_type='OWNER').order_by('id')
    items = []
    for o in owners:
        items.append({
            'system_id': o.system_id,
            'openid': o.openid,
            'phone_number': o.phone_number,
            'daily_points': o.daily_points,
            'total_points': o.total_points,
        })
    return json_ok({'total': len(items), 'list': items})

