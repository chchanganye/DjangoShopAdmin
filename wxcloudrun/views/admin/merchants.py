"""管理员商户管理视图"""
import json
import logging
from django.views.decorators.http import require_http_methods

from wxcloudrun.decorators import admin_token_required
from wxcloudrun.utils.responses import json_ok, json_err
from wxcloudrun.exceptions import WxOpenApiError
from wxcloudrun.models import Category, UserInfo, MerchantProfile
from wxcloudrun.services.storage_service import get_temp_file_urls, delete_cloud_files


logger = logging.getLogger('log')


@admin_token_required
@require_http_methods(["GET"])
def admin_merchants(request, admin):
    """商户管理 - GET列表（只读，通过用户列表创建）"""
    qs = MerchantProfile.objects.select_related('user', 'category').all().order_by('id')
    
    # 收集所有横幅图文件ID
    all_file_ids = [m.banner_url for m in qs if m.banner_url and m.banner_url.startswith('cloud://')]
    
    # 批量获取临时URL
    temp_urls = get_temp_file_urls(all_file_ids) if all_file_ids else {}
    
    items = []
    for m in qs:
        # 处理横幅图：返回 {file_id, url} 或 null
        banner_data = None
        if m.banner_url:
            banner_data = {
                'file_id': m.banner_url,
                'url': temp_urls.get(m.banner_url, '') if m.banner_url.startswith('cloud://') else m.banner_url
            }
        
        items.append({
            'openid': m.user.openid if m.user else None,
            'merchant_id': m.merchant_id,
            'merchant_name': m.merchant_name,
            'title': m.title,
            'description': m.description,
            'banner': banner_data,
            'category_id': m.category.id if m.category else None,
            'category_name': m.category.name if m.category else None,
            'contact_phone': m.contact_phone,
            'address': m.address,
            'positive_rating_percent': m.positive_rating_percent,
            'daily_points': m.user.daily_points if m.user else 0,
            'total_points': m.user.total_points if m.user else 0,
        })
    return json_ok({'total': len(items), 'list': items})


@admin_token_required
@require_http_methods(["PUT", "DELETE"])
def admin_merchants_detail(request, admin, openid):
    """商户管理 - PUT更新 / DELETE删除（使用 openid）"""
    try:
        user = UserInfo.objects.get(openid=openid)
        if user.identity_type != 'MERCHANT':
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
    if 'address' in body:
        merchant.address = body.get('address', '')
    if 'positive_rating_percent' in body:
        merchant.positive_rating_percent = body.get('positive_rating_percent', 0)
    
    try:
        merchant.save()
        
        # 获取横幅图临时URL
        banner_data = None
        if merchant.banner_url:
            temp_urls = get_temp_file_urls([merchant.banner_url]) if merchant.banner_url.startswith('cloud://') else {}
            banner_data = {
                'file_id': merchant.banner_url,
                'url': temp_urls.get(merchant.banner_url, '') if merchant.banner_url.startswith('cloud://') else merchant.banner_url
            }
        
        return json_ok({
            'openid': merchant.user.openid,
            'merchant_id': merchant.merchant_id,
            'merchant_name': merchant.merchant_name,
            'title': merchant.title,
            'description': merchant.description,
            'banner': banner_data,
            'category_id': merchant.category.id if merchant.category else None,
            'category_name': merchant.category.name if merchant.category else None,
            'contact_phone': merchant.contact_phone,
            'address': merchant.address,
            'positive_rating_percent': merchant.positive_rating_percent,
            'daily_points': merchant.user.daily_points,
            'total_points': merchant.user.total_points,
        })
    except Exception as e:
        logger.error(f'更新商户失败: {str(e)}')
        return json_err(f'更新失败: {str(e)}', status=400)

