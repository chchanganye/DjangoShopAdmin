"""管理员意见反馈视图"""

from django.db.models import Q
from django.views.decorators.http import require_http_methods

from wxcloudrun.decorators import admin_token_required
from wxcloudrun.models import UserFeedback
from wxcloudrun.services.storage_service import get_temp_file_urls
from wxcloudrun.utils.responses import json_ok, json_err


@admin_token_required
@require_http_methods(["GET"])
def admin_feedbacks(request, admin):
    """意见反馈 - GET列表（管理员）"""
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
    openid = (request.GET.get('openid') or '').strip()

    qs = UserFeedback.objects.select_related('user').all().order_by('-created_at', '-id')
    if openid:
        qs = qs.filter(user__openid=openid)
    if keyword:
        qs = qs.filter(
            Q(content__icontains=keyword)
            | Q(user__openid__icontains=keyword)
            | Q(user__system_id__icontains=keyword)
            | Q(user__nickname__icontains=keyword)
        )

    total = qs.count()
    start = (page - 1) * page_size
    feedbacks = list(qs[start : start + page_size])

    cloud_file_ids = []
    for f in feedbacks:
        for fid in (f.images or []):
            if isinstance(fid, str) and fid.startswith('cloud://'):
                cloud_file_ids.append(fid)
    temp_urls = get_temp_file_urls(cloud_file_ids) if cloud_file_ids else {}

    items = []
    for f in feedbacks:
        images = []
        for fid in (f.images or []):
            if not isinstance(fid, str):
                continue
            file_id = fid.strip()
            if not file_id:
                continue
            if file_id.startswith('cloud://'):
                images.append({
                    'file_id': file_id,
                    'url': temp_urls.get(file_id, ''),
                })
            else:
                images.append({
                    'file_id': '',
                    'url': file_id,
                })

        u = f.user
        items.append({
            'id': f.id,
            'content': f.content,
            'images': images,
            'system_id': u.system_id if u else '',
            'openid': u.openid if u else '',
            'nickname': u.nickname if u else '',
            'identity_type': u.active_identity if u else '',
            'created_at': f.created_at.strftime('%Y-%m-%d %H:%M:%S') if f.created_at else None,
            'updated_at': f.updated_at.strftime('%Y-%m-%d %H:%M:%S') if f.updated_at else None,
        })

    return json_ok({'list': items, 'total': total})

