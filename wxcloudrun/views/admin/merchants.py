"""管理员商户管理视图"""
import json
import logging
from decimal import Decimal
from django.views.decorators.http import require_http_methods

from wxcloudrun.decorators import admin_token_required
from wxcloudrun.utils.responses import json_ok, json_err
from wxcloudrun.exceptions import WxOpenApiError
from wxcloudrun.models import Category, UserInfo, MerchantProfile
from wxcloudrun.services.points_service import get_points_account
from wxcloudrun.services.storage_service import get_temp_file_urls, delete_cloud_files


logger = logging.getLogger('log')

MERCHANT_TYPES = {'NORMAL', 'DISCOUNT_STORE'}


def _normalize_merchant_type(value: str):
    v = (value or '').strip().upper()
    if v in MERCHANT_TYPES:
        return v
    return None


def _parse_pagination(request):
    current_param = request.GET.get('current') or request.GET.get('page')
    size_param = request.GET.get('size') or request.GET.get('page_size') or request.GET.get('limit')

    page = 1
    page_size = 20

    if current_param:
        try:
            page = int(current_param)
        except (TypeError, ValueError):
            raise ValueError('current 必须为数字')
    if size_param:
        try:
            page_size = int(size_param)
        except (TypeError, ValueError):
            raise ValueError('size 必须为数字')
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 1
    if page_size > 100:
        page_size = 100
    return page, page_size


def _admin_merchants_list(request, merchant_type_filter=None):
    try:
        page, page_size = _parse_pagination(request)
    except ValueError as exc:
        return json_err(str(exc), status=400)

    merchant_type = (
        merchant_type_filter
        or _normalize_merchant_type(request.GET.get('merchant_type') or request.GET.get('type') or '')
    )

    qs = MerchantProfile.objects.select_related('user', 'category').all().order_by('-updated_at', '-id')
    if merchant_type:
        qs = qs.filter(merchant_type=merchant_type)
    total = qs.count()
    start = (page - 1) * page_size
    merchants = list(qs[start : start + page_size])

    all_file_ids = []
    for m in merchants:
        if m.banner_url and m.banner_url.startswith('cloud://'):
            all_file_ids.append(m.banner_url)
        if m.contract_file_id and m.contract_file_id.startswith('cloud://'):
            all_file_ids.append(m.contract_file_id)
        if m.business_license_file_id and m.business_license_file_id.startswith('cloud://'):
            all_file_ids.append(m.business_license_file_id)
    temp_urls = get_temp_file_urls(all_file_ids) if all_file_ids else {}
    items = []
    for m in merchants:
        banner_data = None
        if m.banner_url:
            banner_data = {
                'file_id': m.banner_url,
                'url': temp_urls.get(m.banner_url, '') if m.banner_url.startswith('cloud://') else m.banner_url
            }
        contract_data = None
        if m.contract_file_id:
            contract_data = {
                'file_id': m.contract_file_id,
                'url': temp_urls.get(m.contract_file_id, '') if m.contract_file_id.startswith('cloud://') else m.contract_file_id
            }
        business_license_data = None
        if m.business_license_file_id:
            business_license_data = {
                'file_id': m.business_license_file_id,
                'url': temp_urls.get(m.business_license_file_id, '') if m.business_license_file_id.startswith('cloud://') else m.business_license_file_id
            }
        items.append({
            'openid': m.user.openid if m.user else None,
            'merchant_id': m.merchant_id,
            'merchant_name': m.merchant_name,
            'merchant_type': getattr(m, 'merchant_type', 'NORMAL'),
            'title': m.title,
            'description': m.description,
            'banner': banner_data,
            'contract': contract_data,
            'business_license': business_license_data,
            'category_id': m.category.id if m.category else None,
            'category_name': m.category.name if m.category else None,
            'contact_phone': m.contact_phone,
            'address': m.address,
            'latitude': float(m.latitude) if m.latitude is not None else None,
            'longitude': float(m.longitude) if m.longitude is not None else None,
            'positive_rating_percent': m.positive_rating_percent,
            'open_hours': m.open_hours,
            'gallery': m.gallery or [],
            'rating_count': m.rating_count,
            'avg_score': float(m.avg_score) if m.avg_score is not None else 0,
            'daily_points': get_points_account(m.user, 'MERCHANT').daily_points if m.user else 0,
            'total_points': get_points_account(m.user, 'MERCHANT').total_points if m.user else 0,
        })
    return json_ok({'list': items, 'total': total})


@admin_token_required
@require_http_methods(["GET"])
def admin_merchants(request, admin):
    return _admin_merchants_list(request, merchant_type_filter=None)


@admin_token_required
@require_http_methods(["GET"])
def admin_discount_stores(request, admin):
    """折扣店列表（后台控制中心）"""
    return _admin_merchants_list(request, merchant_type_filter='DISCOUNT_STORE')


@admin_token_required
@require_http_methods(["PUT", "DELETE"])
def admin_merchants_detail(request, admin, openid):
    """商户管理 - PUT更新 / DELETE删除（使用 openid）"""
    try:
        user = UserInfo.objects.get(openid=openid)
        if user.active_identity != 'MERCHANT':
            return json_err('该用户不是商户身份', status=400)
    except UserInfo.DoesNotExist:
        return json_err('用户不存在', status=404)
    
    try:
        merchant = MerchantProfile.objects.select_related('category', 'user').get(user=user)
    except MerchantProfile.DoesNotExist:
        return json_err('商户不存在', status=404)
    
    if request.method == 'DELETE':
        # 删除关联的横幅图云文件
        if merchant.banner_url and merchant.banner_url.startswith('cloud://'):
            try:
                delete_cloud_files([merchant.banner_url])
            except WxOpenApiError as exc:
                logger.warning(f"删除商户横幅图失败: {merchant.banner_url}, error={exc}")
        if merchant.contract_file_id and merchant.contract_file_id.startswith('cloud://'):
            try:
                delete_cloud_files([merchant.contract_file_id])
            except WxOpenApiError as exc:
                logger.warning(f"删除商户合同文件失败: {merchant.contract_file_id}, error={exc}")
        if merchant.business_license_file_id and merchant.business_license_file_id.startswith('cloud://'):
            try:
                delete_cloud_files([merchant.business_license_file_id])
            except WxOpenApiError as exc:
                logger.warning(f"删除商户营业执照文件失败: {merchant.business_license_file_id}, error={exc}")
        merchant.delete()
        return json_ok({'openid': openid, 'deleted': True})
    
    # PUT 更新
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)
    
    if 'merchant_name' in body:
        merchant.merchant_name = body['merchant_name']
    if 'title' in body:
        merchant.title = body.get('title', '')
    if 'description' in body:
        merchant.description = body.get('description', '')
    if 'banner_file_id' in body:
        # 处理横幅图更新：删除旧图，保存新图
        new_file_id = body['banner_file_id']
        old_file_id = merchant.banner_url
        
        # 如果新旧文件不同，删除旧文件
        if old_file_id and old_file_id.startswith('cloud://') and old_file_id != new_file_id:
            try:
                delete_cloud_files([old_file_id])
            except WxOpenApiError as exc:
                logger.warning(f"删除旧商户横幅图失败: {old_file_id}, error={exc}")
        
        merchant.banner_url = new_file_id if new_file_id else ''
    if 'category_id' in body:
        category_id = body.get('category_id')
        if category_id:
            try:
                merchant.category = Category.objects.get(id=category_id)
            except Category.DoesNotExist:
                return json_err('分类不存在', status=404)
        else:
            merchant.category = None
    if 'contact_phone' in body:
        merchant.contact_phone = body.get('contact_phone', '')
    if 'contract_file_id' in body:
        new_file_id = body.get('contract_file_id') or ''
        old_file_id = merchant.contract_file_id or ''
        if old_file_id and old_file_id.startswith('cloud://') and old_file_id != new_file_id:
            try:
                delete_cloud_files([old_file_id])
            except WxOpenApiError as exc:
                logger.warning(f"删除旧商户合同文件失败: {old_file_id}, error={exc}")
        merchant.contract_file_id = new_file_id
    if 'address' in body:
        merchant.address = body.get('address', '')
    if 'latitude' in body:
        latitude_value = body.get('latitude')
        if latitude_value in (None, ''):
            merchant.latitude = None
        else:
            try:
                latitude = Decimal(str(latitude_value))
            except Exception:
                return json_err('latitude 必须为数值', status=400)
            if latitude < Decimal('-90') or latitude > Decimal('90'):
                return json_err('latitude 超出范围（-90~90）', status=400)
            merchant.latitude = latitude
    if 'longitude' in body:
        longitude_value = body.get('longitude')
        if longitude_value in (None, ''):
            merchant.longitude = None
        else:
            try:
                longitude = Decimal(str(longitude_value))
            except Exception:
                return json_err('longitude 必须为数值', status=400)
            if longitude < Decimal('-180') or longitude > Decimal('180'):
                return json_err('longitude 超出范围（-180~180）', status=400)
            merchant.longitude = longitude
    if 'positive_rating_percent' in body:
        merchant.positive_rating_percent = body.get('positive_rating_percent', 0)
    if 'open_hours' in body:
        merchant.open_hours = body.get('open_hours', '').strip()
    if 'gallery' in body:
        gallery = body.get('gallery') or []
        if not isinstance(gallery, list):
            return json_err('gallery 必须为数组', status=400)
        merchant.gallery = [str(item) for item in gallery]
    if 'rating_count' in body:
        try:
            merchant.rating_count = max(0, int(body.get('rating_count', 0)))
        except (TypeError, ValueError):
            return json_err('rating_count 必须为整数', status=400)
    if 'avg_score' in body:
        try:
            merchant.avg_score = Decimal(str(body.get('avg_score', 0)))
        except Exception:
            return json_err('avg_score 必须为数值', status=400)
    
    try:
        merchant.save()
        
        # 获取横幅图临时URL
        banner_data = None
        file_ids = []
        if merchant.banner_url and merchant.banner_url.startswith('cloud://'):
            file_ids.append(merchant.banner_url)
        if merchant.contract_file_id and merchant.contract_file_id.startswith('cloud://'):
            file_ids.append(merchant.contract_file_id)
        if merchant.business_license_file_id and merchant.business_license_file_id.startswith('cloud://'):
            file_ids.append(merchant.business_license_file_id)
        temp_urls = get_temp_file_urls(file_ids) if file_ids else {}
        if merchant.banner_url:
            banner_data = {
                'file_id': merchant.banner_url,
                'url': temp_urls.get(merchant.banner_url, '') if merchant.banner_url.startswith('cloud://') else merchant.banner_url
            }
        contract_data = None
        if merchant.contract_file_id:
            contract_data = {
                'file_id': merchant.contract_file_id,
                'url': temp_urls.get(merchant.contract_file_id, '') if merchant.contract_file_id.startswith('cloud://') else merchant.contract_file_id
            }
        business_license_data = None
        if merchant.business_license_file_id:
            business_license_data = {
                'file_id': merchant.business_license_file_id,
                'url': temp_urls.get(merchant.business_license_file_id, '') if merchant.business_license_file_id.startswith('cloud://') else merchant.business_license_file_id
            }
        
        return json_ok({
            'openid': merchant.user.openid,
            'merchant_id': merchant.merchant_id,
            'merchant_name': merchant.merchant_name,
            'title': merchant.title,
            'description': merchant.description,
            'banner': banner_data,
            'contract': contract_data,
            'business_license': business_license_data,
            'category_id': merchant.category.id if merchant.category else None,
            'category_name': merchant.category.name if merchant.category else None,
            'contact_phone': merchant.contact_phone,
            'address': merchant.address,
            'latitude': float(merchant.latitude) if merchant.latitude is not None else None,
            'longitude': float(merchant.longitude) if merchant.longitude is not None else None,
            'positive_rating_percent': merchant.positive_rating_percent,
            'open_hours': merchant.open_hours,
            'gallery': merchant.gallery or [],
            'rating_count': merchant.rating_count,
            'avg_score': float(merchant.avg_score),
            'daily_points': get_points_account(merchant.user, 'MERCHANT').daily_points,
            'total_points': get_points_account(merchant.user, 'MERCHANT').total_points,
        })
    except Exception as e:
        logger.error(f'更新商户失败: {str(e)}')
        return json_err(f'更新失败: {str(e)}', status=400)
