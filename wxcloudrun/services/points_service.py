"""积分业务逻辑服务"""
from __future__ import annotations

from datetime import date
from typing import Optional

from wxcloudrun.models import PointsRecord, PointsShareSetting, UserInfo, UserPointsAccount
from wxcloudrun.services.user_service import ensure_daily_reset


_POINTS_IDENTITIES = {'OWNER', 'MERCHANT', 'PROPERTY'}


def normalize_points_identity(identity_type: Optional[str]) -> str:
    if identity_type in _POINTS_IDENTITIES:
        return str(identity_type)
    return 'OWNER'


def get_points_account(user: UserInfo, identity_type: Optional[str] = None) -> UserPointsAccount:
    """获取指定身份的积分账户（不存在则创建），并在跨日时重置当日积分。"""
    identity = normalize_points_identity(identity_type or user.active_identity)
    account, _ = UserPointsAccount.objects.get_or_create(
        user=user,
        identity_type=identity,
        defaults={'daily_points_date': date.today()},
    )
    ensure_daily_reset(account)
    return account


def get_points_account_for_update(user: UserInfo, identity_type: str) -> UserPointsAccount:
    """获取指定身份的积分账户（select_for_update），用于事务内并发安全更新。"""
    identity = normalize_points_identity(identity_type)
    account, _ = UserPointsAccount.objects.select_for_update().get_or_create(
        user=user,
        identity_type=identity,
        defaults={'daily_points_date': date.today()},
    )
    ensure_daily_reset(account)
    return account


def change_points_account(
    account: UserPointsAccount,
    delta: int,
    *,
    source_type: str = '',
    source_meta: Optional[dict] = None,
) -> UserPointsAccount:
    """变更积分账户，并写入积分变更记录。"""
    ensure_daily_reset(account)
    account.daily_points += int(delta)
    account.total_points += int(delta)
    account.save()
    PointsRecord.objects.create(
        user=account.user,
        identity_type=account.identity_type,
        change=int(delta),
        daily_points=account.daily_points,
        total_points=account.total_points,
        source_type=str(source_type or ''),
        source_meta=source_meta or {},
    )
    return account


def change_user_points(user: UserInfo, delta: int, identity_type: Optional[str] = None) -> UserPointsAccount:
    """按身份变更用户积分（默认使用 user.active_identity）。

    注意：该方法内部会 select_for_update，务必在 transaction.atomic() 内调用。
    """
    account = get_points_account_for_update(user, identity_type or user.active_identity)
    return change_points_account(account, delta)


def get_points_share_setting():
    """获取积分分成配置"""
    return PointsShareSetting.get_solo()

