"""管理员通知发布与列表"""

import html
import json
import re
from datetime import datetime

from django.db.models import Q
from django.utils.html import strip_tags
from django.views.decorators.http import require_http_methods

from wxcloudrun.decorators import admin_token_required
from wxcloudrun.models import Notification
from wxcloudrun.services.storage_service import get_temp_file_urls
from wxcloudrun.utils.notification_content import (
    dedupe_file_ids,
    extract_image_file_ids,
    normalize_content,
    render_content,
)
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


def _extract_payload(body):
    title = (body.get('title') or '').strip()
    content = body.get('content') or ''

    if not title:
        return None, None, '标题不能为空'

    content_text = strip_tags(content or '')
    content_text = html.unescape(content_text).strip()
    has_image = bool(re.search(r'<img\\b', content or '', re.IGNORECASE))
    if not content_text and not has_image:
        return None, None, '内容不能为空'

    return title, content, None


@admin_token_required
@require_http_methods(["GET", "POST"])
def admin_notifications(request, admin):
    """通知管理：GET 列表，POST 发布"""
    if request.method == 'POST':
        try:
            body = json.loads(request.body.decode('utf-8'))
        except Exception:
            return json_err('请求体格式错误', status=400)

        title, content, error = _extract_payload(body)
        if error:
            return json_err(error, status=400)

        normalized_content = normalize_content(content)

        notice = Notification.objects.create(
            title=title,
            content=normalized_content,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        file_ids = dedupe_file_ids(extract_image_file_ids(notice.content))
        temp_urls = get_temp_file_urls(file_ids) if file_ids else {}

        return json_ok({
            'id': notice.id,
            'title': notice.title,
            'summary': _build_summary(notice.content),
            'content': render_content(notice.content, temp_urls),
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

    file_ids = []
    for n in notices:
        file_ids.extend(extract_image_file_ids(n.content))
    temp_urls = get_temp_file_urls(dedupe_file_ids(file_ids)) if file_ids else {}

    items = []
    for n in notices:
        items.append({
            'id': n.id,
            'title': n.title,
            'summary': _build_summary(n.content),
            'content': render_content(n.content, temp_urls),
            'created_at': _format_dt(n.created_at),
            'updated_at': _format_dt(n.updated_at),
        })

    return json_ok({'list': items, 'total': total})


@admin_token_required
@require_http_methods(["PUT", "DELETE"])
def admin_notification_detail(request, admin, notification_id):
    """通知编辑/删除（后台控制中心）"""
    try:
        nid = int(notification_id)
    except (TypeError, ValueError):
        return json_err('notification_id 必须为数字', status=400)

    try:
        notice = Notification.objects.get(id=nid)
    except Notification.DoesNotExist:
        return json_err('通知不存在', status=404)

    if request.method == 'DELETE':
        notice.delete()
        return json_ok({'id': nid, 'deleted': True})

    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)

    title, content, error = _extract_payload(body)
    if error:
        return json_err(error, status=400)

    normalized_content = normalize_content(content)
    notice.title = title
    notice.content = normalized_content
    notice.updated_at = datetime.now()
    notice.save(update_fields=['title', 'content', 'updated_at'])

    file_ids = dedupe_file_ids(extract_image_file_ids(notice.content))
    temp_urls = get_temp_file_urls(file_ids) if file_ids else {}

    return json_ok({
        'id': notice.id,
        'title': notice.title,
        'summary': _build_summary(notice.content),
        'content': render_content(notice.content, temp_urls),
        'created_at': _format_dt(notice.created_at),
        'updated_at': _format_dt(notice.updated_at),
    })
