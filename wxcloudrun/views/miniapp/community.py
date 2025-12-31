"""小程序端小区相关视图"""

from datetime import datetime

from django.db.models import Q
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_http_methods

from wxcloudrun.decorators import openid_required
from wxcloudrun.models import Community
from wxcloudrun.utils.responses import json_ok, json_err


@openid_required
@require_http_methods(["GET"])
def communities_public_list(request):
    """获取小区列表（供业主选择）

    - 支持游标分页
    - 支持 keyword 关键字搜索（匹配小区名称/物业名称）
    """
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

    keyword = (request.GET.get('keyword') or request.GET.get('q') or '').strip()

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

    qs = Community.objects.select_related('property').all().order_by('-updated_at', '-id')
    if keyword:
        qs = qs.filter(
            Q(community_name__icontains=keyword)
            | Q(property__property_name__icontains=keyword)
        )
    if cursor_filter:
        cursor_dt, cursor_pk = cursor_filter
        qs = qs.filter(Q(updated_at__lt=cursor_dt) | Q(updated_at=cursor_dt, id__lt=cursor_pk))

    communities = list(qs[: page_size + 1])
    has_more = len(communities) > page_size
    sliced = communities[:page_size]

    items = []
    for c in sliced:
        items.append({
            'community_id': c.community_id,
            'community_name': c.community_name,
            'property_id': c.property.property_id if c.property else None,
            'property_name': c.property.property_name if c.property else None,
        })

    next_cursor = f"{sliced[-1].updated_at.isoformat()}#{sliced[-1].id}" if has_more and sliced else None
    return json_ok({'list': items, 'has_more': has_more, 'next_cursor': next_cursor})

