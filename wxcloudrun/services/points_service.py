"""积分业务逻辑服务"""
from wxcloudrun.models import PointsRecord, PointsShareSetting
from wxcloudrun.services.user_service import ensure_daily_reset


def change_user_points(user, delta: int):
    """变更用户积分"""
    ensure_daily_reset(user)
    user.daily_points += int(delta)
    user.total_points += int(delta)
    user.save()
    PointsRecord.objects.create(user=user, change=int(delta))
    return user


def get_points_share_setting():
    """获取积分分成配置"""
    return PointsShareSetting.get_solo()

