"""小程序端分类相关视图"""
from django.views.decorators.http import require_http_methods

from wxcloudrun.decorators import openid_required
from wxcloudrun.utils.responses import json_ok
from wxcloudrun.models import Category
from datetime import datetime
from django.db.models import Q
from django.utils.dateparse import parse_datetime
from wxcloudrun.services.storage_service import get_temp_file_urls, resolve_icon_url


@openid_required
@require_http_methods(["GET"])
def categories_list(request):
    """获取分类列表"""
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
    qs = Category.objects.all().order_by('-updated_at', '-id')
    if cursor_filter:
        cursor_dt, cursor_pk = cursor_filter
        qs = qs.filter(Q(updated_at__lt=cursor_dt) | Q(updated_at=cursor_dt, id__lt=cursor_pk))
    categories = list(qs[: page_size + 1])
    icon_file_ids = [c.icon_file_id for c in categories if c.icon_file_id and c.icon_file_id.startswith('cloud://')]
    temp_urls = get_temp_file_urls(icon_file_ids)
    has_more = len(categories) > page_size
    sliced = categories[:page_size]
    items = []
    for c in sliced:
        icon_file_id = c.icon_file_id or ''
        icon_url = resolve_icon_url(icon_file_id, temp_urls)
        items.append({
            'name': c.name,
            'icon_file_id': icon_file_id,
            'icon_url': icon_url,
        })
    next_cursor = f"{sliced[-1].updated_at.isoformat()}#{sliced[-1].id}" if has_more and sliced else None
    return json_ok({'list': items, 'has_more': has_more, 'next_cursor': next_cursor})

