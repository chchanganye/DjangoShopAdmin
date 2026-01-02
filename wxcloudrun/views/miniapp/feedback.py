"""小程序端意见反馈视图"""

import json
from datetime import datetime

from django.db.models import Q
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_http_methods

from wxcloudrun.decorators import openid_required
from wxcloudrun.models import UserFeedback, UserInfo
from wxcloudrun.services.storage_service import get_temp_file_urls
from wxcloudrun.utils.auth import get_openid
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


def _normalize_images(images):
    if not images:
        return []
    if not isinstance(images, list):
        return None
    result = []
    for v in images:
        if not isinstance(v, str):
            continue
        file_id = v.strip()
        if not file_id:
            continue
        if '127.0.0.1' in file_id or 'localhost' in file_id:
            continue
        result.append(file_id)
    return result


@openid_required
@require_http_methods(["GET", "POST"])
def feedback_handler(request):
    """意见反馈

    - POST：提交反馈（content 必填，images 可选）
    - GET：获取我的反馈记录（游标分页）
    """
    openid = get_openid(request)
    if not openid:
        return json_err('缺少openid', status=401)

    try:
        user = UserInfo.objects.get(openid=openid)
    except UserInfo.DoesNotExist:
        return json_err('用户不存在', status=404)

    if request.method == 'POST':
        try:
            body = json.loads(request.body.decode('utf-8'))
        except Exception:
            return json_err('请求体格式错误', status=400)

        content = (body.get('content') or '').strip()
        if not content:
            return json_err('反馈内容不能为空', status=400)
        if len(content) > 150:
            return json_err('反馈内容最多150字', status=400)

        images = _normalize_images(body.get('images') or body.get('image_file_ids'))
        if images is None:
            return json_err('images 必须为数组', status=400)
        if len(images) > 9:
            return json_err('图片最多9张', status=400)

        feedback = UserFeedback.objects.create(
            user=user,
            content=content,
            images=images,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        return json_ok({
            'id': feedback.id,
            'created_at': feedback.created_at.strftime('%Y-%m-%d %H:%M:%S') if feedback.created_at else None,
        })

    # GET：我的反馈记录
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

    qs = UserFeedback.objects.filter(user=user).all().order_by('-created_at', '-id')
    if cursor_filter:
        cursor_dt, cursor_pk = cursor_filter
        qs = qs.filter(Q(created_at__lt=cursor_dt) | Q(created_at=cursor_dt, id__lt=cursor_pk))

    feedbacks = list(qs[: page_size + 1])
    has_more = len(feedbacks) > page_size
    sliced = feedbacks[:page_size]

    cloud_file_ids = []
    for f in sliced:
        for fid in (f.images or []):
            if isinstance(fid, str) and fid.startswith('cloud://'):
                cloud_file_ids.append(fid)
    temp_urls = get_temp_file_urls(cloud_file_ids) if cloud_file_ids else {}

    items = []
    for f in sliced:
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
        items.append({
            'id': f.id,
            'content': f.content,
            'images': images,
            'created_at': f.created_at.strftime('%Y-%m-%d %H:%M:%S') if f.created_at else None,
        })

    next_cursor = f"{sliced[-1].created_at.isoformat()}#{sliced[-1].id}" if has_more and sliced else None
    return json_ok({'list': items, 'has_more': has_more, 'next_cursor': next_cursor})
