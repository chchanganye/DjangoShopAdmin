"""小程序端分类相关视图"""
from django.views.decorators.http import require_http_methods

from wxcloudrun.decorators import openid_required
from wxcloudrun.utils.responses import json_ok
from wxcloudrun.models import Category
from wxcloudrun.services.storage_service import get_temp_file_urls, resolve_icon_url


@openid_required
@require_http_methods(["GET"])
def categories_list(request):
    """获取分类列表"""
    qs = Category.objects.all().order_by('id')
    icon_file_ids = [c.icon_file_id for c in qs if c.icon_file_id and c.icon_file_id.startswith('cloud://')]
    temp_urls = get_temp_file_urls(icon_file_ids)

    items = []
    for c in qs:
        icon_file_id = c.icon_file_id or ''
        icon_url = resolve_icon_url(icon_file_id, temp_urls)
        items.append({
            'name': c.name,
            'icon_file_id': icon_file_id,
            'icon_url': icon_url,
        })
    return json_ok({'total': qs.count(), 'list': items})

