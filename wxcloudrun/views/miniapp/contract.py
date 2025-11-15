"""小程序端协议合同视图"""
from django.views.decorators.http import require_http_methods

from wxcloudrun.decorators import openid_required
from wxcloudrun.utils.responses import json_ok
from wxcloudrun.models import ContractSetting
from wxcloudrun.services.storage_service import get_temp_file_urls, resolve_icon_url


@openid_required
@require_http_methods(["GET"])
def contract_image(request):
    """获取协议合同图片（仅GET）"""
    setting = ContractSetting.get_solo()
    file_id = setting.contract_file_id or ''
    temp_urls = get_temp_file_urls([file_id]) if file_id and file_id.startswith('cloud://') else {}
    url = resolve_icon_url(file_id, temp_urls)
    return json_ok({
        'file_id': file_id,
        'url': url,
    })