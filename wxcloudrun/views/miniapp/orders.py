"""小程序端订单与评价接口"""
import json
import logging

from django.views.decorators.http import require_http_methods

from wxcloudrun.decorators import openid_required
from wxcloudrun.utils.auth import get_openid
from wxcloudrun.utils.responses import json_ok, json_err
from wxcloudrun.models import MerchantProfile, MerchantReview, SettlementOrder, UserInfo
from wxcloudrun.services.order_service import can_review_order, create_order_review
from wxcloudrun.services.storage_service import get_temp_file_urls


logger = logging.getLogger('log')


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


def _normalize_order_status_filter(status: str):
    s = (status or '').strip()
    if not s:
        return None
    mapping = {
        'comment': 'PENDING_REVIEW',
        'unpaid': 'PENDING_REVIEW',
        'pending_review': 'PENDING_REVIEW',
        'pending': 'PENDING_REVIEW',
        'PENDING_REVIEW': 'PENDING_REVIEW',
        'paid': 'REVIEWED',
        'reviewed': 'REVIEWED',
        'completed': 'REVIEWED',
        'REVIEWED': 'REVIEWED',
    }
    return mapping.get(s, None)


@openid_required
@require_http_methods(["GET"])
def orders_list(request):
    """我的订单列表

    - 业主：返回自己的结算订单（可评价/已评价）
    - 商户：返回自己商户的结算订单（仅查看）
    """
    openid = get_openid(request)
    if not openid:
        return json_err('缺少openid', status=401)

    try:
        user = UserInfo.objects.get(openid=openid)
    except UserInfo.DoesNotExist:
        return json_err('用户不存在', status=404)

    try:
        page, page_size = _parse_pagination(request)
    except ValueError as exc:
        return json_err(str(exc), status=400)

    status_param = request.GET.get('status') or ''
    normalized_status = _normalize_order_status_filter(status_param)

    qs = (
        SettlementOrder.objects.select_related('merchant', 'merchant__user', 'owner')
        .select_related('review')
        .all()
        .order_by('-created_at', '-id')
    )
    if user.active_identity == 'MERCHANT':
        qs = qs.filter(merchant__user=user)
    else:
        qs = qs.filter(owner=user)
    if normalized_status:
        qs = qs.filter(status=normalized_status)

    total = qs.count()
    start = (page - 1) * page_size
    orders = list(qs[start : start + page_size])

    items = []
    for o in orders:
        merchant = o.merchant
        owner = o.owner
        review = getattr(o, 'review', None)
        items.append({
            'order_id': o.order_id,
            'status': o.status,
            'amount': str(o.amount),
            'amount_int': o.amount_int,
            'merchant_points': o.merchant_points,
            'owner_points': o.owner_points,
            'owner_rate': o.owner_rate,
            'created_at': o.created_at.strftime('%Y-%m-%d %H:%M:%S') if o.created_at else None,
            'reviewed_at': o.reviewed_at.strftime('%Y-%m-%d %H:%M:%S') if o.reviewed_at else None,
            'merchant': {
                'merchant_id': merchant.merchant_id,
                'merchant_name': merchant.merchant_name,
                'contact_phone': merchant.contact_phone,
                'address': merchant.address,
                'positive_rating_percent': merchant.positive_rating_percent,
                'rating_count': merchant.rating_count,
                'avg_score': float(merchant.avg_score),
            } if merchant else None,
            'owner': {
                'openid': owner.openid,
                'system_id': owner.system_id,
                'nickname': owner.nickname,
                'phone_number': owner.phone_number,
            } if owner else None,
            'review': {
                'review_id': review.id,
                'rating': review.rating,
                'content': review.content,
                'created_at': review.created_at.strftime('%Y-%m-%d %H:%M:%S') if review.created_at else None,
            } if review else None,
            'can_review': can_review_order(order=o, owner=user),
        })
    return json_ok({'list': items, 'total': total})


@openid_required
@require_http_methods(["POST"])
def order_review_create(request, order_id):
    """提交评价（仅允许业主对自己的已结算订单评价）"""
    openid = get_openid(request)
    if not openid:
        return json_err('缺少openid', status=401)

    try:
        user = UserInfo.objects.get(openid=openid)
    except UserInfo.DoesNotExist:
        return json_err('用户不存在', status=404)

    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return json_err('请求体格式错误', status=400)

    rating = body.get('rating')
    content = body.get('content', '')

    try:
        review = create_order_review(order_id=order_id, owner=user, rating=rating, content=content)
    except SettlementOrder.DoesNotExist:
        return json_err('订单不存在', status=404)
    except PermissionError as exc:
        return json_err(str(exc), status=403)
    except ValueError as exc:
        return json_err(str(exc), status=400)
    except Exception as exc:
        logger.error(f'创建评价失败: order_id={order_id}, openid={openid}, error={exc}', exc_info=True)
        return json_err('提交评价失败', status=500)

    return json_ok({
        'review_id': review.id,
        'order_id': review.order.order_id,
        'merchant_id': review.merchant.merchant_id,
        'rating': review.rating,
        'content': review.content,
        'created_at': review.created_at.strftime('%Y-%m-%d %H:%M:%S') if review.created_at else None,
    })


@openid_required
@require_http_methods(["GET"])
def merchant_reviews_list(request, merchant_id):
    """获取商户评价列表（用于商户详情页展示）"""
    try:
        merchant = MerchantProfile.objects.select_related('user').get(merchant_id=merchant_id)
    except MerchantProfile.DoesNotExist:
        return json_err('商户不存在', status=404)

    try:
        page, page_size = _parse_pagination(request)
    except ValueError as exc:
        return json_err(str(exc), status=400)

    qs = (
        MerchantReview.objects.select_related('owner', 'order')
        .filter(merchant=merchant)
        .order_by('-created_at', '-id')
    )
    total = qs.count()
    start = (page - 1) * page_size
    reviews = list(qs[start : start + page_size])

    avatar_file_ids = [
        r.owner.avatar_url for r in reviews
        if r.owner and r.owner.avatar_url and r.owner.avatar_url.startswith('cloud://')
    ]
    temp_urls = get_temp_file_urls(avatar_file_ids) if avatar_file_ids else {}

    items = []
    for r in reviews:
        avatar_data = None
        if r.owner and r.owner.avatar_url:
            if r.owner.avatar_url.startswith('cloud://'):
                avatar_data = {
                    'file_id': r.owner.avatar_url,
                    'url': temp_urls.get(r.owner.avatar_url, ''),
                }
            else:
                avatar_data = {
                    'file_id': '',
                    'url': r.owner.avatar_url,
                }
        items.append({
            'review_id': r.id,
            'order_id': r.order.order_id if r.order else None,
            'rating': r.rating,
            'content': r.content,
            'owner': {
                'system_id': r.owner.system_id,
                'nickname': r.owner.nickname,
                'avatar': avatar_data,
            } if r.owner else None,
            'created_at': r.created_at.strftime('%Y-%m-%d %H:%M:%S') if r.created_at else None,
        })

    return json_ok({
        'summary': {
            'merchant_id': merchant.merchant_id,
            'rating_count': merchant.rating_count,
            'avg_score': float(merchant.avg_score),
            'positive_rating_percent': merchant.positive_rating_percent,
        },
        'list': items,
        'total': total,
    })
