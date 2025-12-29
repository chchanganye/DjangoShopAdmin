"""管理员协议合同管理视图"""
import json
import logging
from datetime import datetime
from django.views.decorators.http import require_http_methods
from django.db.models import Q
from django.utils.dateparse import parse_datetime
from django.core.exceptions import ObjectDoesNotExist

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
    """查询所有商户/物业用户当前合同签名列表（游标分页）"""
    setting = ContractSetting.get_solo()
    default_contract_id = setting.contract_file_id or ''
    
    limit_param = request.GET.get('limit')
    page_size = 20
    if limit_param:
        try:
            page_size = int(limit_param)
        except (TypeError, ValueError):
            return json_err('limit 必须为数字', status=400)
    if page_size < 1:
        page_size = 1
    if page_size > 100:
        page_size = 100

    cursor_param = (request.GET.get('cursor') or '').strip()
    cursor_filter = None
    if cursor_param:
        parts = cursor_param.split('#', 1)
        if len(parts) == 2:
            ts_str, pk_str = parts
            dt = parse_datetime(ts_str)
            if not dt:
                try:
                    dt = datetime.fromisoformat(ts_str)
                except ValueError:
                    dt = None
            try:
                pk_val = int(pk_str)
            except (TypeError, ValueError):
                pk_val = None
            if dt and pk_val is not None:
                cursor_filter = (dt, pk_val)
        if not cursor_filter:
            return json_err('cursor 无效', status=400)

    users_qs = UserInfo.objects.select_related('merchant_profile', 'property_profile').filter(
        Q(merchant_profile__isnull=False) | Q(property_profile__isnull=False)
    ).order_by('-updated_at', '-id')
    if cursor_filter:
        cursor_dt, cursor_pk = cursor_filter
        users_qs = users_qs.filter(Q(updated_at__lt=cursor_dt) | Q(updated_at=cursor_dt, id__lt=cursor_pk))
    users = list(users_qs[: page_size + 1])

    user_ids = [u.id for u in users]
    user_current_contract_map = {}
    contract_ids = set()
    for u in users:
        current_contract_id = default_contract_id
        try:
            merchant = u.merchant_profile
        except ObjectDoesNotExist:
            merchant = None
        if merchant and merchant.contract_file_id:
            current_contract_id = merchant.contract_file_id
        user_current_contract_map[u.id] = current_contract_id
        if current_contract_id:
            contract_ids.add(current_contract_id)

    signatures = []
    signature_map = {}
    if user_ids and contract_ids:
        records = UserContractSignature.objects.select_related('user').filter(
            user_id__in=user_ids,
            contract_file_id__in=list(contract_ids),
        )
        signatures = list(records)
        signature_map = {(r.user_id, r.contract_file_id): r for r in signatures}

    # 收集所有需要生成临时URL的文件ID
    file_ids = []
    for cid in contract_ids:
        if cid and cid.startswith('cloud://'):
            file_ids.append(cid)
    for r in signatures:
        fid = r.signature_file_id or ''
        if fid and fid.startswith('cloud://'):
            file_ids.append(fid)
    temp_urls = get_temp_file_urls(file_ids) if file_ids else {}

    has_more = len(users) > page_size
    sliced = users[:page_size]
    items = []
    for u in sliced:
        current_contract_id = user_current_contract_map.get(u.id) or ''
        record = signature_map.get((u.id, current_contract_id))
        signed = bool(record)
        signed_at = record.signed_at.strftime('%Y-%m-%d %H:%M:%S') if record and record.signed_at else None
        fid = record.signature_file_id if record else ''
        sig = None
        if fid:
            sig = {
                'file_id': fid,
                'url': resolve_icon_url(fid, temp_urls),
            }
        contract_current = None
        if current_contract_id:
            contract_current = {
                'file_id': current_contract_id,
                'url': resolve_icon_url(current_contract_id, temp_urls),
            }
        contract_signed = None
        if record and record.contract_file_id:
            contract_signed = {
                'file_id': record.contract_file_id,
                'url': resolve_icon_url(record.contract_file_id, temp_urls),
            }
        items.append({
            'openid': u.openid,
            'system_id': u.system_id,
            'identity_type': u.identity_type,
            'signed': signed,
            'signature': sig,
            'signed_at': signed_at,
            'contract_file_id_signed': record.contract_file_id if record else None,
            'current_contract_file_id': current_contract_id,
            'contract_signed': contract_signed,
            'contract_current': contract_current,
        })
    next_cursor = f"{sliced[-1].updated_at.isoformat()}#{sliced[-1].id}" if has_more and sliced else None
    return json_ok({'list': items, 'has_more': has_more, 'next_cursor': next_cursor})
