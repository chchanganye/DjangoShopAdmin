"""小程序端通知/消息视图"""

import html
import re
from datetime import datetime

from django.db.models import Q
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_http_methods

from wxcloudrun.decorators import openid_required
from wxcloudrun.models import Notification, NotificationRead, UserInfo
from wxcloudrun.services.storage_service import get_temp_file_urls
from wxcloudrun.utils.auth import get_openid
from wxcloudrun.utils.notification_content import dedupe_file_ids, extract_image_file_ids, render_content
from wxcloudrun.utils.responses import json_ok, json_err


def _parse_cursor(cursor_param: str):
    cursor_param = (cursor_param or '').strip()
    if not cursor_param:
        return None
    parts = cursor_param.split('#', 1)
    if len(parts) != 2:
        return None
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
    if not dt or pk_val is None:
        return None
    return dt, pk_val


def _strip_html(raw: str) -> str:
    if not raw:
        return ''
    text = re.sub(r'<[^>]+>', '', raw)
    text = html.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _build_summary(raw: str, limit: int = 80) -> str:
    text = _strip_html(raw)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _format_dt(value):
    return value.strftime('%Y-%m-%d %H:%M:%S') if value else None


@openid_required
@require_http_methods(["GET"])
def notifications_list(request):
    """通知列表（游标分页，返回已读状态与未读数）"""
    openid = get_openid(request)
    if not openid:
        return json_err('缺少openid', status=401)

    try:
        user = UserInfo.objects.get(openid=openid)
    except UserInfo.DoesNotExist:
        return json_err('用户不存在', status=404)

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

    cursor_param = request.GET.get('cursor') or ''
    cursor_filter = _parse_cursor(cursor_param)
    if cursor_param and not cursor_filter:
        return json_err('cursor 无效', status=400)

    qs = Notification.objects.all().order_by('-created_at', '-id')
    if cursor_filter:
        cursor_dt, cursor_pk = cursor_filter
        qs = qs.filter(Q(created_at__lt=cursor_dt) | Q(created_at=cursor_dt, id__lt=cursor_pk))

    notifications = list(qs[: page_size + 1])
    has_more = len(notifications) > page_size
    sliced = notifications[:page_size]

    ids = [n.id for n in sliced]
    read_ids = set(
        NotificationRead.objects.filter(user=user, notification_id__in=ids).values_list(
            'notification_id',
            flat=True,
        )
    )

    items = []
    for n in sliced:
        items.append({
            'id': n.id,
            'title': n.title,
            'summary': _build_summary(n.content),
            'created_at': _format_dt(n.created_at),
            'is_read': n.id in read_ids,
        })

    next_cursor = (
        f"{sliced[-1].created_at.isoformat()}#{sliced[-1].id}" if has_more and sliced else None
    )
    unread_count = Notification.objects.exclude(reads__user=user).count()

    return json_ok({
        'list': items,
        'has_more': has_more,
        'next_cursor': next_cursor,
        'unread_count': unread_count,
    })


@openid_required
@require_http_methods(["GET"])
def notifications_unread_count(request):
    """未读通知数量"""
    openid = get_openid(request)
    if not openid:
        return json_err('缺少openid', status=401)

    try:
        user = UserInfo.objects.get(openid=openid)
    except UserInfo.DoesNotExist:
        return json_err('用户不存在', status=404)

    unread_count = Notification.objects.exclude(reads__user=user).count()
    return json_ok({'unread_count': unread_count})


@openid_required
@require_http_methods(["GET"])
def notification_detail(request, notification_id):
    """通知详情（访问即标记为已读）"""
    openid = get_openid(request)
    if not openid:
        return json_err('缺少openid', status=401)

    try:
        user = UserInfo.objects.get(openid=openid)
    except UserInfo.DoesNotExist:
        return json_err('用户不存在', status=404)

    try:
        notice = Notification.objects.get(id=notification_id)
    except Notification.DoesNotExist:
        return json_err('通知不存在', status=404)

    read_record, created = NotificationRead.objects.get_or_create(
        notification=notice,
        user=user,
        defaults={'read_at': datetime.now()},
    )
    if not created and not read_record.read_at:
        read_record.read_at = datetime.now()
        read_record.save()

    file_ids = dedupe_file_ids(extract_image_file_ids(notice.content))
    temp_urls = get_temp_file_urls(file_ids) if file_ids else {}
    content_html = render_content(notice.content, temp_urls)

    return json_ok({
        'id': notice.id,
        'title': notice.title,
        'content_html': content_html,
        'created_at': _format_dt(notice.created_at),
        'read_at': _format_dt(read_record.read_at),
    })
