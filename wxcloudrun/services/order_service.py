"""订单与评价业务逻辑服务"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

from django.db import transaction
from django.db.models import Avg, Count, Q

from wxcloudrun.models import MerchantProfile, MerchantReview, SettlementOrder, UserInfo


def create_settlement_order(
    *,
    merchant: MerchantProfile,
    owner: UserInfo,
    amount: Decimal,
    amount_int: int,
    merchant_points: int,
    owner_points: int,
    owner_rate: int,
) -> SettlementOrder:
    """创建商户结算订单记录。"""
    return SettlementOrder.objects.create(
        merchant=merchant,
        owner=owner,
        amount=amount,
        amount_int=int(amount_int),
        merchant_points=int(merchant_points),
        owner_points=int(owner_points),
        owner_rate=int(owner_rate),
        status='PENDING_REVIEW',
    )


def _quantize_one_decimal(value: Any) -> Decimal:
    try:
        dec = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception:
        return Decimal('0.0')
    return dec.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)


def refresh_merchant_rating(merchant: MerchantProfile) -> MerchantProfile:
    """重新计算并更新商户评分汇总字段（平均分、好评率、评分次数）。"""
    agg = MerchantReview.objects.filter(merchant=merchant).aggregate(
        rating_count=Count('id'),
        avg_score=Avg('rating'),
        positive_count=Count('id', filter=Q(rating__gte=4)),
    )
    rating_count = int(agg.get('rating_count') or 0)
    avg_score = _quantize_one_decimal(agg.get('avg_score') or 0)
    positive_count = int(agg.get('positive_count') or 0)
    positive_percent = int(round((positive_count / rating_count) * 100)) if rating_count else 0

    merchant.rating_count = rating_count
    merchant.avg_score = avg_score
    merchant.positive_rating_percent = positive_percent
    merchant.save(update_fields=['rating_count', 'avg_score', 'positive_rating_percent', 'updated_at'])
    return merchant


def create_order_review(
    *,
    order_id: str,
    owner: UserInfo,
    rating: int,
    content: str,
) -> MerchantReview:
    """创建订单评价（仅允许业主对已结算订单评价）。"""
    if owner.active_identity != 'OWNER':
        raise PermissionError('仅业主身份可评价')

    try:
        rating_int = int(rating)
    except (TypeError, ValueError):
        raise ValueError('rating 必须为整数')
    if rating_int < 1 or rating_int > 5:
        raise ValueError('rating 必须在 1-5 之间')

    content_text = (content or '').strip()
    if len(content_text) > 500:
        raise ValueError('content 最长 500 字')

    with transaction.atomic():
        order = (
            SettlementOrder.objects.select_for_update()
            .select_related('merchant', 'owner')
            .get(order_id=order_id)
        )
        if order.owner_id != owner.id:
            raise PermissionError('无权限评价该订单')
        if order.status != 'PENDING_REVIEW':
            raise ValueError('该订单不可评价或已评价')

        review, created = MerchantReview.objects.get_or_create(
            order=order,
            defaults={
                'merchant': order.merchant,
                'owner': owner,
                'rating': rating_int,
                'content': content_text,
                'created_at': datetime.now(),
            },
        )
        if not created:
            raise ValueError('该订单已评价')

        order.status = 'REVIEWED'
        order.reviewed_at = datetime.now()
        order.save(update_fields=['status', 'reviewed_at', 'updated_at'])

        merchant = MerchantProfile.objects.select_for_update().get(id=order.merchant_id)
        refresh_merchant_rating(merchant)

        return review


def can_review_order(*, order: SettlementOrder, owner: UserInfo) -> bool:
    """判断用户是否可评价该订单（用于接口返回）。"""
    if owner.active_identity != 'OWNER':
        return False
    return order.owner_id == owner.id and order.status == 'PENDING_REVIEW'

