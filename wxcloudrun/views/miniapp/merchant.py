"""小程序端商户相关视图"""
import json
import logging
from django.views.decorators.http import require_http_methods

from wxcloudrun.decorators import openid_required
from wxcloudrun.utils.responses import json_ok, json_err
from wxcloudrun.utils.auth import get_openid
from wxcloudrun.models import MerchantProfile, UserInfo
from wxcloudrun.services.storage_service import get_temp_file_urls, delete_cloud_files
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

