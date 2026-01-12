"""管理员订单与评价视图"""
import logging

from django.db.models import Q
from django.views.decorators.http import require_http_methods

from wxcloudrun.decorators import admin_token_required
from wxcloudrun.models import MerchantReview, SettlementOrder
from wxcloudrun.utils.responses import json_ok, json_err


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


def _normalize_order_status(value: str):
    v = (value or '').strip().upper()
    if v in {'PENDING_REVIEW', 'REVIEWED'}:
        return v
    mapping = {
        'PENDING': 'PENDING_REVIEW',
        'COMMENT': 'PENDING_REVIEW',
        'PAID': 'REVIEWED',
        'COMPLETED': 'REVIEWED',
    }
    return mapping.get(v)


@admin_token_required
@require_http_methods(["GET"])
def admin_orders(request, admin):
    """订单记录列表（后台控制中心）"""
    try:
        page, page_size = _parse_pagination(request)
    except ValueError as exc:
        return json_err(str(exc), status=400)

    keyword = (request.GET.get('keyword') or request.GET.get('q') or '').strip()
    merchant_id = (request.GET.get('merchant_id') or '').strip()
    owner_openid = (request.GET.get('openid') or request.GET.get('owner_openid') or '').strip()
    status = _normalize_order_status(request.GET.get('status') or '')

    qs = (
        SettlementOrder.objects.select_related('merchant', 'merchant__user', 'owner')
        .select_related('review')
        .all()
        .order_by('-created_at', '-id')
    )
    if merchant_id:
        qs = qs.filter(merchant__merchant_id=merchant_id)
    if owner_openid:
        qs = qs.filter(owner__openid=owner_openid)
    if status:
        qs = qs.filter(status=status)
    if keyword:
        qs = qs.filter(
            Q(order_id__icontains=keyword)
            | Q(owner__openid__icontains=keyword)
            | Q(owner__system_id__icontains=keyword)
            | Q(owner__phone_number__icontains=keyword)
            | Q(owner__nickname__icontains=keyword)
            | Q(merchant__merchant_id__icontains=keyword)
            | Q(merchant__merchant_name__icontains=keyword)
        )

    total = qs.count()
    start = (page - 1) * page_size
    orders = list(qs[start : start + page_size])

    items = []
    for order in orders:
        merchant = order.merchant
        owner = order.owner
        review = getattr(order, 'review', None)
        items.append({
            'order_id': order.order_id,
            'status': order.status,
            'amount': str(order.amount),
            'amount_int': order.amount_int,
            'merchant_points': order.merchant_points,
            'owner_points': order.owner_points,
            'owner_rate': order.owner_rate,
            'merchant': {
                'merchant_id': merchant.merchant_id,
                'merchant_name': merchant.merchant_name,
                'openid': merchant.user.openid if getattr(merchant, 'user', None) else None,
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
            'reviewed_at': order.reviewed_at.strftime('%Y-%m-%d %H:%M:%S') if order.reviewed_at else None,
            'created_at': order.created_at.strftime('%Y-%m-%d %H:%M:%S') if order.created_at else None,
            'updated_at': order.updated_at.strftime('%Y-%m-%d %H:%M:%S') if order.updated_at else None,
        })
    return json_ok({'list': items, 'total': total})


@admin_token_required
@require_http_methods(["GET"])
def admin_reviews(request, admin):
    """评价记录列表（后台控制中心）"""
    try:
        page, page_size = _parse_pagination(request)
    except ValueError as exc:
        return json_err(str(exc), status=400)

    keyword = (request.GET.get('keyword') or request.GET.get('q') or '').strip()
    merchant_id = (request.GET.get('merchant_id') or '').strip()
    owner_openid = (request.GET.get('openid') or request.GET.get('owner_openid') or '').strip()
    rating_param = (request.GET.get('rating') or '').strip()
    rating = None
    if rating_param:
        try:
            rating = int(rating_param)
        except (TypeError, ValueError):
            return json_err('rating 必须为数字', status=400)
        if rating < 1 or rating > 5:
            return json_err('rating 必须在 1-5 之间', status=400)

    qs = (
        MerchantReview.objects.select_related('merchant', 'merchant__user', 'owner', 'order')
        .all()
        .order_by('-created_at', '-id')
    )
    if merchant_id:
        qs = qs.filter(merchant__merchant_id=merchant_id)
    if owner_openid:
        qs = qs.filter(owner__openid=owner_openid)
    if rating is not None:
        qs = qs.filter(rating=rating)
    if keyword:
        qs = qs.filter(
            Q(order__order_id__icontains=keyword)
            | Q(owner__openid__icontains=keyword)
            | Q(owner__system_id__icontains=keyword)
            | Q(owner__phone_number__icontains=keyword)
            | Q(owner__nickname__icontains=keyword)
            | Q(merchant__merchant_id__icontains=keyword)
            | Q(merchant__merchant_name__icontains=keyword)
            | Q(content__icontains=keyword)
        )

    total = qs.count()
    start = (page - 1) * page_size
    reviews = list(qs[start : start + page_size])

    items = []
    for review in reviews:
        merchant = review.merchant
        owner = review.owner
        items.append({
            'review_id': review.id,
            'order_id': review.order.order_id if review.order else None,
            'rating': review.rating,
            'content': review.content,
            'merchant': {
                'merchant_id': merchant.merchant_id,
                'merchant_name': merchant.merchant_name,
                'openid': merchant.user.openid if getattr(merchant, 'user', None) else None,
            } if merchant else None,
            'owner': {
                'openid': owner.openid,
                'system_id': owner.system_id,
                'nickname': owner.nickname,
                'phone_number': owner.phone_number,
            } if owner else None,
            'created_at': review.created_at.strftime('%Y-%m-%d %H:%M:%S') if review.created_at else None,
        })
    return json_ok({'list': items, 'total': total})

