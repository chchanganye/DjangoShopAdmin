"""小程序端商户相关视图"""
import logging
from django.views.decorators.http import require_http_methods

from wxcloudrun.decorators import openid_required
from wxcloudrun.utils.responses import json_ok, json_err
from wxcloudrun.models import MerchantProfile
from wxcloudrun.services.storage_service import get_temp_file_urls
from wxcloudrun.exceptions import WxOpenApiError


logger = logging.getLogger('log')


@openid_required
@require_http_methods(["GET"])
def merchants_list(request):
    """获取商户列表"""
    try:
        qs = MerchantProfile.objects.select_related('user', 'category').all().order_by('id')
        
        # 收集所有横幅图文件ID
        all_file_ids = [m.banner_url for m in qs if m.banner_url and m.banner_url.startswith('cloud://')]
        
        # 批量获取临时URL
        temp_urls = get_temp_file_urls(all_file_ids) if all_file_ids else {}
        
        items = []
        for m in qs:
            # 处理横幅图：返回临时URL（小程序端只需要URL）
            banner_url = ''
            if m.banner_url:
                if m.banner_url.startswith('cloud://'):
                    banner_url = temp_urls.get(m.banner_url, '')
                else:
                    banner_url = m.banner_url
            
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
            })
        logger.info(f'查询商户列表，共 {len(items)} 条')
        return json_ok({'total': len(items), 'list': items})
    except WxOpenApiError as e:
        logger.error(f"获取商户横幅图临时URL失败: {e}")
        qs = MerchantProfile.objects.select_related('user', 'category').all().order_by('id')
        items = []
        for m in qs:
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
            })
        return json_ok({'total': len(items), 'list': items})
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

    # 处理横幅图：返回临时URL（小程序端只需要URL）
    banner_url = ''
    if merchant.banner_url:
        if merchant.banner_url.startswith('cloud://'):
            temp_urls = get_temp_file_urls([merchant.banner_url])
            banner_url = temp_urls.get(merchant.banner_url, '')
        else:
            banner_url = merchant.banner_url

    data = {
        'merchant_id': merchant.merchant_id,
        'merchant_name': merchant.merchant_name,
        'title': merchant.title,
        'description': merchant.description,
        'banner_url': banner_url,
        'category_id': merchant.category.id if merchant.category else None,
        'category_name': merchant.category.name if merchant.category else None,
        'contact_phone': merchant.contact_phone,
        'address': merchant.address,
        'positive_rating_percent': merchant.positive_rating_percent,
    }
    return json_ok(data)

