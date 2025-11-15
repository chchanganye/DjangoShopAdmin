"""管理员分类管理视图"""
import json
import logging
from django.views.decorators.http import require_http_methods

from wxcloudrun.decorators import admin_token_required
from wxcloudrun.utils.responses import json_ok, json_err
from wxcloudrun.exceptions import WxOpenApiError
from wxcloudrun.models import Category
from wxcloudrun.services.storage_service import (
    get_temp_file_urls,
    resolve_icon_url,
    delete_cloud_files,
)


logger = logging.getLogger('log')


@admin_token_required
@require_http_methods(["GET", "POST"])
def admin_categories(request, admin):
    """分类管理 - GET列表 / POST创建"""
    if request.method == 'GET':
        from datetime import datetime
        from django.db.models import Q
        from django.utils.dateparse import parse_datetime
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
                'id': c.id,
                'name': c.name,
                'icon_file_id': icon_file_id,
                'icon_url': icon_url,
            })
        next_cursor = f"{sliced[-1].updated_at.isoformat()}#{sliced[-1].id}" if has_more and sliced else None
        return json_ok({'list': items, 'has_more': has_more, 'next_cursor': next_cursor})
    
    # POST 创建
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)
    
    name = body.get('name')
    icon_file_id = body.get('icon_file_id', '')
    
    if not name:
        return json_err('缺少参数 name', status=400)
    
    try:
        category = Category.objects.create(name=name, icon_file_id=icon_file_id)
        temp_urls = get_temp_file_urls([category.icon_file_id]) if category.icon_file_id and category.icon_file_id.startswith('cloud://') else {}
        icon_url = resolve_icon_url(category.icon_file_id, temp_urls)
        return json_ok({
            'id': category.id,
            'name': category.name,
            'icon_file_id': category.icon_file_id,
            'icon_url': icon_url,
        }, status=201)
    except Exception as e:
        logger.error(f'创建分类失败: {str(e)}')
        return json_err(f'创建失败: {str(e)}', status=400)


@admin_token_required
@require_http_methods(["PUT", "DELETE"])
def admin_categories_detail(request, admin, category_id):
    """分类管理 - PUT更新 / DELETE删除"""
    try:
        category = Category.objects.get(id=category_id)
    except Category.DoesNotExist:
        return json_err('分类不存在', status=404)

    if request.method == 'DELETE':
        category.delete()
        return json_ok({'id': category_id, 'deleted': True})

    # PUT 更新
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)
    
    old_icon_file_id = category.icon_file_id or ''

    if 'name' in body:
        category.name = body['name']
    if 'icon_file_id' in body:
        new_icon_file_id = body.get('icon_file_id') or ''
        if new_icon_file_id != old_icon_file_id and old_icon_file_id.startswith('cloud://'):
            try:
                delete_cloud_files([old_icon_file_id])
            except WxOpenApiError as exc:
                logger.error(f'删除旧分类图标失败: {str(exc)}', exc_info=True)
                return json_err(f'删除旧图标失败: {str(exc)}', status=500)
        category.icon_file_id = new_icon_file_id
    
    try:
        category.save()
        temp_urls = get_temp_file_urls([category.icon_file_id]) if category.icon_file_id and category.icon_file_id.startswith('cloud://') else {}
        icon_url = resolve_icon_url(category.icon_file_id, temp_urls)
        return json_ok({
            'id': category.id,
            'name': category.name,
            'icon_file_id': category.icon_file_id,
            'icon_url': icon_url,
        })
    except Exception as e:
        logger.error(f'更新分类失败: {str(e)}')
        return json_err(f'更新失败: {str(e)}', status=400)

