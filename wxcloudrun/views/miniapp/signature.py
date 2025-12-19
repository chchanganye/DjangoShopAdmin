"""小程序端合同签名视图"""
import json
import logging
from django.views.decorators.http import require_http_methods
from django.core.exceptions import ObjectDoesNotExist

from wxcloudrun.decorators import openid_required
from wxcloudrun.utils.responses import json_ok, json_err
from wxcloudrun.utils.auth import get_openid
from wxcloudrun.models import UserInfo, ContractSetting, UserContractSignature
from wxcloudrun.services.storage_service import get_temp_file_urls, resolve_icon_url


logger = logging.getLogger('log')


def _is_signature_allowed(active_identity: str) -> bool:
    return active_identity in ['MERCHANT', 'PROPERTY']


def _get_current_contract_file_id(user: UserInfo) -> str:
    """获取当前用户需要签署的合同版本（cloud file_id）。
    - 商户：优先取商户专属合同；未配置则回退到全局合同
    - 物业：使用全局合同
    """
    if user.active_identity == 'MERCHANT':
        try:
            merchant = user.merchant_profile
        except ObjectDoesNotExist:
            merchant = None
        if merchant and merchant.contract_file_id:
            return merchant.contract_file_id
    setting = ContractSetting.get_solo()
    return setting.contract_file_id or ''


@openid_required
@require_http_methods(["GET"])
def contract_signature_status(request):
    """获取当前合同的签名状态（仅商户/物业返回详情）"""
    openid = get_openid(request)
    try:
        user = UserInfo.objects.select_related('merchant_profile').get(openid=openid)
    except UserInfo.DoesNotExist:
        return json_err('用户不存在', status=404)

    current_contract_id = _get_current_contract_file_id(user)

    signed = False
    signature_data = None
    signed_at = None
    contract_file_id_signed = None

    if _is_signature_allowed(user.active_identity) and current_contract_id:
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
        'signed': signed,
        'signature': signature_data,
        'signed_at': signed_at,
        'contract_file_id_signed': contract_file_id_signed,
        'current_contract_file_id': current_contract_id,
        'allowed': _is_signature_allowed(user.active_identity),
    })


@openid_required
@require_http_methods(["PUT"])
def contract_signature_update(request):
    """提交/更新手写签名（仅商户/物业），仅保存云文件ID"""
    openid = get_openid(request)
    try:
        user = UserInfo.objects.select_related('merchant_profile').get(openid=openid)
    except UserInfo.DoesNotExist:
        return json_err('用户不存在', status=404)

    if not _is_signature_allowed(user.active_identity):
        return json_err('仅商户和物业身份可以签署协议', status=403)

    current_contract_id = _get_current_contract_file_id(user)
    if not current_contract_id:
        return json_err('当前未配置协议合同图片', status=400)

    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)

    signature_file_id = (body.get('signature_file_id') or '').strip()
    if not signature_file_id or not signature_file_id.startswith('cloud://'):
        return json_err('signature_file_id 必须为云文件ID（cloud:// 开头）', status=400)

    record, _ = UserContractSignature.objects.get_or_create(
        user=user,
        contract_file_id=current_contract_id,
        defaults={'signature_file_id': signature_file_id}
    )
    # 覆盖同一合同版本下的签名
    record.signature_file_id = signature_file_id
    record.save()

    temp_urls = get_temp_file_urls([signature_file_id])
    return json_ok({
        'signed': True,
        'signature': {
            'file_id': signature_file_id,
            'url': resolve_icon_url(signature_file_id, temp_urls),
        },
        'signed_at': record.signed_at.strftime('%Y-%m-%d %H:%M:%S') if record.signed_at else None,
        'contract_file_id_signed': record.contract_file_id,
    })
