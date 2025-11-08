"""统计业务逻辑服务"""
from datetime import date, datetime, timedelta
from django.db.models import Sum, Count, Q
from wxcloudrun.models import UserInfo, PointsRecord, AccessLog


def get_overview_statistics():
    """获取统计概览数据"""
    today = date.today()
    
    # 1. 总用户数
    total_users = UserInfo.objects.count()
    
    # 2. 今日新增用户数
    today_new_users = UserInfo.objects.filter(
        created_at__date=today
    ).count()
    
    # 3. 今日交易额（积分变更绝对值总和）
    today_transaction = PointsRecord.objects.filter(
        created_at__date=today
    ).aggregate(
        total=Sum('change')
    )['total'] or 0
    today_transaction_amount = abs(today_transaction)
    
    # 4. 总交易额
    total_transaction = PointsRecord.objects.aggregate(
        total=Sum('change')
    )['total'] or 0
    total_transaction_amount = abs(total_transaction)
    
    # 5. 总访问量
    total_visits = AccessLog.objects.aggregate(
        total=Sum('access_count')
    )['total'] or 0
    
    # 6. 今日访问量
    today_visits = AccessLog.objects.filter(
        access_date=today
    ).aggregate(
        total=Sum('access_count')
    )['total'] or 0
    
    return {
        'total_users': total_users,
        'today_new_users': today_new_users,
        'today_transaction_amount': today_transaction_amount,
        'total_transaction_amount': total_transaction_amount,
        'total_visits': total_visits,
        'today_visits': today_visits,
    }


def get_statistics_by_time(period: str):
    """按时间周期获取统计数据
    period: 'month' 或 'week'
    """
    today = date.today()
    
    if period == 'month':
        # 最近30天
        start_date = today - timedelta(days=29)
        date_list = [(today - timedelta(days=i)) for i in range(29, -1, -1)]
    elif period == 'week':
        # 最近7天
        start_date = today - timedelta(days=6)
        date_list = [(today - timedelta(days=i)) for i in range(6, -1, -1)]
    else:
        raise ValueError(f"不支持的周期: {period}")
    
    # 每日新增用户
    daily_new_users = {}
    for d in date_list:
        count = UserInfo.objects.filter(created_at__date=d).count()
        daily_new_users[d.strftime('%Y-%m-%d')] = count
    
    # 每日交易额
    daily_transaction = {}
    for d in date_list:
        total = PointsRecord.objects.filter(
            created_at__date=d
        ).aggregate(
            total=Sum('change')
        )['total'] or 0
        daily_transaction[d.strftime('%Y-%m-%d')] = abs(total)
    
    # 每日访问量
    daily_visits = {}
    for d in date_list:
        total = AccessLog.objects.filter(
            access_date=d
        ).aggregate(
            total=Sum('access_count')
        )['total'] or 0
        daily_visits[d.strftime('%Y-%m-%d')] = total
    
    return {
        'period': period,
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': today.strftime('%Y-%m-%d'),
        'daily_new_users': daily_new_users,
        'daily_transaction_amount': daily_transaction,
        'daily_visits': daily_visits,
    }

