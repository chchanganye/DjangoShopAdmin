"""管理员-推荐商户配置"""
import json
import logging
from django.db import transaction
from django.views.decorators.http import require_http_methods

from wxcloudrun.decorators import admin_token_required
from wxcloudrun.utils.responses import json_ok, json_err
from wxcloudrun.models import MerchantProfile, RecommendedMerchant
from wxcloudrun.services.storage_service import get_temp_file_urls
from wxcloudrun.exceptions import WxOpenApiError


logger = logging.getLogger('log')

MAX_RECOMMENDED_MERCHANTS = 4


def _resolve_banner(file_id: str, temp_urls: dict) -> dict | None:
    if not file_id:
        return None
    return {
        'file_id': file_id,
        'url': temp_urls.get(file_id, '') if file_id.startswith('cloud://') else file_id,
    }


def _build_items(records: list[RecommendedMerchant]) -> list[dict]:
    file_ids: list[str] = []
    for record in records:
        banner_url = getattr(record.merchant, 'banner_url', '') or ''
        if banner_url.startswith('cloud://'):
            file_ids.append(banner_url)

    temp_urls = {}
    if file_ids:
        try:
            temp_urls = get_temp_file_urls(file_ids)
        except WxOpenApiError as exc:
            logger.warning(f'获取推荐商户banner临时URL失败: {exc}')

    items: list[dict] = []
    for record in records:
        merchant = record.merchant
        banner_url = getattr(merchant, 'banner_url', '') or ''
        items.append({
            'merchant_id': merchant.merchant_id,
            'merchant_name': merchant.merchant_name,
            'category_id': merchant.category.id if merchant.category else None,
            'category_name': merchant.category.name if merchant.category else None,
            'banner': _resolve_banner(banner_url, temp_urls),
            'sort_order': record.sort_order,
        })
    return items


@admin_token_required
@require_http_methods(["GET", "PUT"])
def admin_recommended_merchants(request, admin):
    """配置首页推荐商户（最多 4 个，按顺序展示）"""
    if request.method == 'GET':
        records = list(
            RecommendedMerchant.objects.select_related('merchant__category')
            .all()
            .order_by('sort_order', 'id')
        )
        return json_ok({
            'max_count': MAX_RECOMMENDED_MERCHANTS,
            'list': _build_items(records),
        })

    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)

    merchant_ids = body.get('merchant_ids')
    if merchant_ids is None:
        return json_err('缺少参数 merchant_ids', status=400)
    if not isinstance(merchant_ids, list):
        return json_err('merchant_ids 必须为数组', status=400)

    normalized: list[str] = []
    seen: set[str] = set()
    for item in merchant_ids:
        if not isinstance(item, str):
            return json_err('merchant_ids 必须为字符串数组', status=400)
        mid = item.strip()
        if not mid:
            continue
        if mid in seen:
            return json_err('merchant_ids 存在重复值', status=400)
        seen.add(mid)
        normalized.append(mid)

    if len(normalized) > MAX_RECOMMENDED_MERCHANTS:
        return json_err(f'最多只能推荐 {MAX_RECOMMENDED_MERCHANTS} 个商户', status=400)

    if not normalized:
        RecommendedMerchant.objects.all().delete()
        return json_ok({'max_count': MAX_RECOMMENDED_MERCHANTS, 'list': []})

    merchants = list(MerchantProfile.objects.select_related('category').filter(merchant_id__in=normalized))
    merchant_map = {m.merchant_id: m for m in merchants}
    missing = [mid for mid in normalized if mid not in merchant_map]
    if missing:
        return json_err(f'商户不存在: {missing[0]}', status=404)

    with transaction.atomic():
        RecommendedMerchant.objects.exclude(merchant__merchant_id__in=normalized).delete()
        for idx, mid in enumerate(normalized):
            merchant = merchant_map[mid]
            RecommendedMerchant.objects.update_or_create(
                merchant=merchant,
                defaults={'sort_order': idx + 1},
            )

    records = list(
        RecommendedMerchant.objects.select_related('merchant__category')
        .all()
        .order_by('sort_order', 'id')
    )
    return json_ok({'max_count': MAX_RECOMMENDED_MERCHANTS, 'list': _build_items(records)})

