"""管理员协议合同管理视图"""
import json
import logging
from django.views.decorators.http import require_http_methods

from wxcloudrun.decorators import admin_token_required
from wxcloudrun.utils.responses import json_ok, json_err
from wxcloudrun.exceptions import WxOpenApiError
from wxcloudrun.models import ContractSetting
from wxcloudrun.services.storage_service import get_temp_file_urls, resolve_icon_url, delete_cloud_files
from wxcloudrun.models import UserInfo, UserContractSignature


logger = logging.getLogger('log')


@admin_token_required
@require_http_methods(["GET", "PUT"])
def admin_contract_image(request, admin):
    """协议合同图片 - GET查询 / PUT更新（仅存云文件ID）"""
    setting = ContractSetting.get_solo()

    if request.method == 'GET':
        file_id = setting.contract_file_id or ''
        temp_urls = get_temp_file_urls([file_id]) if file_id and file_id.startswith('cloud://') else {}
        return json_ok({
            'file_id': file_id,
            'url': resolve_icon_url(file_id, temp_urls),
        })

    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)

    new_file_id = body.get('contract_file_id') or ''
    old_file_id = setting.contract_file_id or ''

    # 若替换为不同云ID，删除旧云文件
    if new_file_id != old_file_id and old_file_id.startswith('cloud://'):
        try:
            delete_cloud_files([old_file_id])
        except WxOpenApiError as exc:
            logger.warning(f"删除旧协议合同图片失败: {old_file_id}, error={exc}")

    setting.contract_file_id = new_file_id
    setting.save()

    temp_urls = get_temp_file_urls([new_file_id]) if new_file_id and new_file_id.startswith('cloud://') else {}
    return json_ok({
        'file_id': new_file_id,
        'url': resolve_icon_url(new_file_id, temp_urls),
    })


@admin_token_required
@require_http_methods(["GET"])
def admin_contract_signature(request, admin):
    """查询指定用户的合同签名信息（当前合同版本）"""
    openid = request.GET.get('openid')
    if not openid:
        return json_err('缺少参数 openid', status=400)

    try:
        user = UserInfo.objects.get(openid=openid)
    except UserInfo.DoesNotExist:
        return json_err('用户不存在', status=404)

    setting = ContractSetting.get_solo()
    current_contract_id = setting.contract_file_id or ''

    allowed = user.identity_type in ['MERCHANT', 'PROPERTY']
    signed = False
    signed_at = None
    contract_file_id_signed = None
    signature_data = None

    if allowed and current_contract_id:
        record = UserContractSignature.objects.filter(user=user, contract_file_id=current_contract_id).first()
        if record:
            signed = True
            contract_file_id_signed = record.contract_file_id
            signed_at = record.signed_at.strftime('%Y-%m-%d %H:%M:%S') if record.signed_at else None
            fid = record.signature_file_id or ''
            temp_urls = get_temp_file_urls([fid]) if fid and fid.startswith('cloud://') else {}
            signature_data = {
                'file_id': fid,
                'url': resolve_icon_url(fid, temp_urls),
            }

    return json_ok({
        'openid': user.openid,
        'system_id': user.system_id,
        'identity_type': user.identity_type,
        'allowed': allowed,
        'signed': signed,
        'signature': signature_data,
        'signed_at': signed_at,
        'contract_file_id_signed': contract_file_id_signed,
        'current_contract_file_id': current_contract_id,
    })
