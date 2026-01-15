"""管理员通知发布与列表"""

import html
import json
from datetime import datetime

from django.db.models import Q
from django.utils.html import strip_tags
from django.views.decorators.http import require_http_methods

from wxcloudrun.decorators import admin_token_required
from wxcloudrun.models import Notification
from wxcloudrun.utils.responses import json_ok, json_err


def _build_summary(raw: str, limit: int = 80) -> str:
    text = strip_tags(raw or '')
    text = html.unescape(text)
    text = ' '.join(text.split())
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _format_dt(value):
    return value.strftime('%Y-%m-%d %H:%M:%S') if value else None


@admin_token_required
@require_http_methods(["GET", "POST"])
def admin_notifications(request, admin):
    """通知管理：GET 列表，POST 发布"""
    if request.method == 'POST':
        try:
            body = json.loads(request.body.decode('utf-8'))
        except Exception:
            return json_err('请求体格式错误', status=400)

        title = (body.get('title') or '').strip()
        content = body.get('content') or ''

        if not title:
            return json_err('标题不能为空', status=400)

        content_text = strip_tags(content or '')
        content_text = html.unescape(content_text).strip()
        if not content_text:
            return json_err('内容不能为空', status=400)

        notice = Notification.objects.create(
            title=title,
            content=content,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        return json_ok({
            'id': notice.id,
            'title': notice.title,
            'summary': _build_summary(notice.content),
            'content': notice.content,
            'created_at': _format_dt(notice.created_at),
            'updated_at': _format_dt(notice.updated_at),
        }, status=201)

    current_param = request.GET.get('current') or request.GET.get('page')
    size_param = request.GET.get('size') or request.GET.get('page_size') or request.GET.get('limit')

    page = 1
    page_size = 20
    if current_param:
        try:
            page = int(current_param)
        except (TypeError, ValueError):
            return json_err('current 必须为数字', status=400)
    if size_param:
        try:
            page_size = int(size_param)
        except (TypeError, ValueError):
            return json_err('size 必须为数字', status=400)
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 1
    if page_size > 100:
        page_size = 100

    keyword = (request.GET.get('keyword') or request.GET.get('q') or '').strip()

    qs = Notification.objects.all().order_by('-created_at', '-id')
    if keyword:
        qs = qs.filter(Q(title__icontains=keyword) | Q(content__icontains=keyword))

    total = qs.count()
    start = (page - 1) * page_size
    notices = list(qs[start : start + page_size])

    items = []
    for n in notices:
        items.append({
            'id': n.id,
            'title': n.title,
            'summary': _build_summary(n.content),
            'content': n.content,
            'created_at': _format_dt(n.created_at),
            'updated_at': _format_dt(n.updated_at),
        })

    return json_ok({'list': items, 'total': total})
