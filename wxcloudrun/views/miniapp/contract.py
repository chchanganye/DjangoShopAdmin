"""小程序端协议合同视图"""
from django.views.decorators.http import require_http_methods

from wxcloudrun.decorators import openid_required
from wxcloudrun.utils.responses import json_ok, json_err
from wxcloudrun.utils.auth import get_openid
from wxcloudrun.models import ContractSetting, UserInfo
from wxcloudrun.services.storage_service import get_temp_file_urls, resolve_icon_url
from django.core.exceptions import ObjectDoesNotExist


@openid_required
@require_http_methods(["GET"])
def contract_image(request):
    """获取协议合同图片（仅GET）"""
    openid = get_openid(request)
    try:
        user = UserInfo.objects.select_related('merchant_profile').get(openid=openid)
    except UserInfo.DoesNotExist:
        return json_err('用户不存在', status=404)

    file_id = ''
    if user.active_identity == 'MERCHANT':
        try:
            merchant = user.merchant_profile
        except ObjectDoesNotExist:
            merchant = None
        if merchant and merchant.contract_file_id:
            file_id = merchant.contract_file_id

    if not file_id:
        setting = ContractSetting.get_solo()
        file_id = setting.contract_file_id or ''
    temp_urls = get_temp_file_urls([file_id]) if file_id and file_id.startswith('cloud://') else {}
    url = resolve_icon_url(file_id, temp_urls)
    return json_ok({
        'file_id': file_id,
        'url': url,
    })
