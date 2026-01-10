"""用户业务逻辑服务"""
from datetime import date
from wxcloudrun.models import UserPointsAccount


def ensure_daily_reset(account: UserPointsAccount):
    """确保每日积分重置（按身份积分账户）"""
    today = date.today()
    if account.daily_points_date != today:
        account.daily_points = 0
        account.daily_points_date = today
        account.save()

