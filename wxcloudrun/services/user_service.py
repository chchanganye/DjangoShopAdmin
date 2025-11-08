"""用户业务逻辑服务"""
from datetime import date
from wxcloudrun.models import UserInfo


def ensure_daily_reset(user: UserInfo):
    """确保每日积分重置"""
    today = date.today()
    if user.daily_points_date != today:
        user.daily_points = 0
        user.daily_points_date = today
        user.save()

