"""小程序端商户相关视图"""
import json
import logging
from datetime import datetime

from django.db.models import Q
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_http_methods

from wxcloudrun.decorators import openid_required
from wxcloudrun.utils.responses import json_ok, json_err
from wxcloudrun.utils.auth import get_openid
from wxcloudrun.models import MerchantProfile, UserInfo
from wxcloudrun.services.storage_service import get_temp_file_urls, delete_cloud_files
from wxcloudrun.exceptions import WxOpenApiError


logger = logging.getLogger('log')

MAX_PAGE_SIZE = 10
DEFAULT_PAGE_SIZE = 10


def _collect_temp_urls(file_ids):
    cloud_ids = [fid for fid in file_ids if isinstance(fid, str) and fid.startswith('cloud://')]
    if not cloud_ids:
        return {}
    return get_temp_file_urls(cloud_ids)


def _resolve_file_id(file_id, temp_urls):
    if not file_id or not isinstance(file_id, str):
        return ''
    if file_id.startswith('cloud://'):
        return temp_urls.get(file_id, '')
    return file_id


def _resolve_gallery(gallery, temp_urls):
    resolved = []
    for fid in gallery or []:
        if not isinstance(fid, str):
            continue
        resolved.append(_resolve_file_id(fid, temp_urls))
    return resolved


def _parse_cursor(cursor: str):
    if not cursor:
        return None
    parts = cursor.split('#', 1)
    if len(parts) != 2:
        return None
    ts_str, pk_str = parts
    dt = parse_datetime(ts_str)
    if not dt:
        try:
            dt = datetime.fromisoformat(ts_str)
        except ValueError:
            return None
    try:
        pk_val = int(pk_str)
    except (TypeError, ValueError):
        return None
    return dt, pk_val


def _build_cursor(obj: MerchantProfile):
    return f"{obj.updated_at.isoformat()}#{obj.id}"


@openid_required
@require_http_methods(["GET"])
def merchants_list(request):
    """获取商户列表"""
    qs = MerchantProfile.objects.select_related('user', 'category').all().order_by('-updated_at', '-id')
    category_param = request.GET.get('categoryId') or request.GET.get('category_id')
    category_value = None
    if category_param:
        try:
            category_value = int(category_param)
        except (TypeError, ValueError):
            return json_err('categoryId 必须为数字', status=400)
        qs = qs.filter(category_id=category_value)

    limit_param = request.GET.get('limit')
    page_size = DEFAULT_PAGE_SIZE
    if limit_param:
        try:
            page_size = int(limit_param)
        except (TypeError, ValueError):
            return json_err('limit 必须为数字', status=400)
    if page_size < 1:
        page_size = 1
    if page_size > MAX_PAGE_SIZE:
        page_size = MAX_PAGE_SIZE

    cursor_param = request.GET.get('cursor', '').strip()
    cursor_filter = _parse_cursor(cursor_param) if cursor_param else None
    if cursor_param and not cursor_filter:
        return json_err('cursor 无效', status=400)
    if cursor_filter:
        cursor_dt, cursor_pk = cursor_filter
        qs = qs.filter(
            Q(updated_at__lt=cursor_dt)
            | Q(updated_at=cursor_dt, id__lt=cursor_pk)
        )

    merchants = list(qs[: page_size + 1])
    try:
        all_file_ids = [m.banner_url for m in merchants if m.banner_url and m.banner_url.startswith('cloud://')]
        temp_urls = _collect_temp_urls(all_file_ids)

        has_more = len(merchants) > page_size
        sliced = merchants[:page_size]
        items = []
        for m in sliced:
            banner_url = _resolve_file_id(m.banner_url, temp_urls)
            items.append({
                'merchant_id': m.merchant_id,
                'merchant_name': m.merchant_name,
                'title': m.title,
                'description': m.description,
                'banner_url': banner_url,
                'category': m.category.name if m.category else None,
                'category_id': m.category.id if m.category else None,
                'contact_phone': m.contact_phone,
                'address': m.address,
                'positive_rating_percent': m.positive_rating_percent,
                'open_hours': m.open_hours,
                'gallery': m.gallery or [],
                'rating_count': m.rating_count,
                'avg_score': float(m.avg_score),
            })
        logger.info(f'查询商户列表，共 {len(items)} 条 category={category_value} cursor={cursor_param}')
        next_cursor = _build_cursor(sliced[-1]) if has_more and sliced else None
        return json_ok({
            'list': items,
            'has_more': has_more,
            'next_cursor': next_cursor,
        })
    except WxOpenApiError as e:
        logger.error(f"获取商户横幅图临时URL失败: {e}")
        has_more = len(merchants) > page_size
        sliced = merchants[:page_size]
        items = []
        for m in sliced:
            items.append({
                'merchant_id': m.merchant_id,
                'merchant_name': m.merchant_name,
                'title': m.title,
                'description': m.description,
                'banner_url': '',
                'category': m.category.name if m.category else None,
                'category_id': m.category.id if m.category else None,
                'contact_phone': m.contact_phone,
                'address': m.address,
                'positive_rating_percent': m.positive_rating_percent,
                'open_hours': m.open_hours,
                'gallery': m.gallery or [],
                'rating_count': m.rating_count,
                'avg_score': float(m.avg_score),
            })
        next_cursor = _build_cursor(sliced[-1]) if has_more and sliced else None
        return json_ok({
            'list': items,
            'has_more': has_more,
            'next_cursor': next_cursor,
        })
    except Exception as exc:
        logger.error(f'查询商户列表失败: {str(exc)}', exc_info=True)
        return json_err(f'查询失败: {str(exc)}', status=500)


@openid_required
@require_http_methods(["GET"])
def merchant_detail(request, merchant_id):
    """获取商户详情"""
    try:
        merchant = MerchantProfile.objects.select_related('user', 'category').get(merchant_id=merchant_id)
    except MerchantProfile.DoesNotExist:
        return json_err('商户不存在', status=404)

    gallery_source = merchant.gallery or []
    file_ids = []
    if merchant.banner_url:
        file_ids.append(merchant.banner_url)
    file_ids.extend([fid for fid in gallery_source if isinstance(fid, str)])

    temp_urls = {}
    try:
        temp_urls = _collect_temp_urls(file_ids)
    except WxOpenApiError as exc:
        logger.warning(f'获取商户媒体临时URL失败: merchant={merchant_id}, error={exc}')

    banner_url = _resolve_file_id(merchant.banner_url, temp_urls)
    gallery_urls = _resolve_gallery(gallery_source, temp_urls)

    data = {
        'merchant_id': merchant.merchant_id,
        'merchant_name': merchant.merchant_name,
        'title': merchant.title,
        'description': merchant.description,
        'banner_url': banner_url,
        'gallery': gallery_urls,
        'category_id': merchant.category.id if merchant.category else None,
        'category_name': merchant.category.name if merchant.category else None,
        'contact_phone': merchant.contact_phone,
        'address': merchant.address,
        'positive_rating_percent': merchant.positive_rating_percent,
        'open_hours': merchant.open_hours,
        'rating_count': merchant.rating_count,
        'avg_score': float(merchant.avg_score),
    }
    return json_ok(data)


@openid_required
@require_http_methods(["PUT"])
def merchant_update_banner(request):
    """商户用户更新自己的横幅图片
    - 只有商户身份的用户可以调用
    - 自动删除旧横幅
    """
    openid = get_openid(request)
    
    try:
        user = UserInfo.objects.get(openid=openid)
    except UserInfo.DoesNotExist:
        return json_err('用户不存在', status=404)
    
    # 验证用户身份
    if user.identity_type != 'MERCHANT':
        return json_err('只有商户用户可以上传横幅', status=403)
    
    # 获取商户档案
    try:
        merchant = MerchantProfile.objects.get(user=user)
    except MerchantProfile.DoesNotExist:
        return json_err('商户档案不存在', status=404)
    
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)
    
    if 'banner_file_id' not in body:
        return json_err('缺少参数 banner_file_id', status=400)
    
    new_banner = body.get('banner_file_id', '').strip()
    old_banner = merchant.banner_url
    
    # 验证横幅格式：必须是云文件ID或空字符串
    if new_banner:
        # 拒绝本地临时文件路径
        if '127.0.0.1' in new_banner or 'localhost' in new_banner or '__tmp__' in new_banner:
            logger.warning(f"拒绝本地临时文件路径: {new_banner}")
            return json_err(
                '不能使用本地临时文件路径。请先调用 /api/storage/upload-credential 获取上传凭证（file_type=banner），'
                '将文件上传到云存储后，再使用返回的 file_id（cloud:// 开头）',
                status=400
            )
        
        # 验证必须是云文件ID格式（cloud:// 开头）
        if not new_banner.startswith('cloud://'):
            logger.warning(f"无效的横幅文件ID: {new_banner}")
            return json_err(
                '横幅文件ID格式不正确，必须是云存储文件ID（cloud:// 开头）。'
                '请先调用 /api/storage/upload-credential 获取上传凭证上传文件',
                status=400
            )
    
    # 如果新旧横幅不同，删除旧横幅
    if new_banner != old_banner:
        if old_banner and old_banner.startswith('cloud://'):
            try:
                delete_cloud_files([old_banner])
                logger.info(f"已删除旧商户横幅: {old_banner}")
            except WxOpenApiError as exc:
                logger.warning(f"删除旧商户横幅失败: {old_banner}, error={exc}")
    
    merchant.banner_url = new_banner
    
    try:
        merchant.save()
        
        # 返回更新后的横幅信息
        banner_data = None
        if merchant.banner_url:
            if merchant.banner_url.startswith('cloud://'):
                temp_urls = get_temp_file_urls([merchant.banner_url])
                banner_data = {
                    'file_id': merchant.banner_url,
                    'url': temp_urls.get(merchant.banner_url, '')
                }
            else:
                banner_data = {
                    'file_id': merchant.banner_url,
                    'url': merchant.banner_url
                }
        
        return json_ok({
            'merchant_id': merchant.merchant_id,
            'banner': banner_data,
            'message': '横幅更新成功'
        })
    except Exception as exc:
        logger.error(f'更新商户横幅失败: {str(exc)}', exc_info=True)
        return json_err(f'更新失败: {str(exc)}', status=400)

