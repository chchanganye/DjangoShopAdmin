"""管理员统计视图"""
import logging
import calendar
from datetime import date
from datetime import timedelta
from django.views.decorators.http import require_http_methods
from django.db.models import Sum

from wxcloudrun.decorators import admin_token_required
from wxcloudrun.utils.responses import json_ok, json_err
from wxcloudrun.models import UserInfo, PointsRecord, AccessLog


logger = logging.getLogger('log')


@admin_token_required
@require_http_methods(["GET"])
def admin_statistics_overview(request, admin):
    """管理员统计概览：总用户数、今日新增、今日交易额、总交易额"""
    today = date.today()
    
    # 1. 总用户数
    total_users = UserInfo.objects.count()
    
    # 2. 今日新增用户数
    today_new_users = UserInfo.objects.filter(
        created_at__date=today
    ).count()
    
    # 3. 今日交易额
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
    
    data = {
        'total_users': total_users,
        'today_new_users': today_new_users,
        'today_transaction_amount': today_transaction_amount,
        'total_transaction_amount': total_transaction_amount,
        'total_visits': total_visits,
        'today_visits': today_visits,
    }
    
    return json_ok(data)


@admin_token_required
@require_http_methods(["GET"])
def admin_statistics_by_time(request, admin):
    """按时间维度统计：支持按年月、按周统计用户数和交易额
    
    Query参数：
    - type: 'month' 或 'week'（必填）
    - year: 年份，如 2025（必填）
    - month: 月份，1-12（type=month或week时必填）
    - week: 周数，1-5（type=week时必填，表示该月第几周）
    """
    stat_type = request.GET.get('type')
    year = request.GET.get('year')
    month = request.GET.get('month')
    week = request.GET.get('week')
    
    if not stat_type or stat_type not in ['month', 'week']:
        return json_err('参数 type 必须为 month 或 week', status=400)
    
    if not year:
        return json_err('参数 year 为必填项', status=400)
    
    try:
        year = int(year)
    except ValueError:
        return json_err('参数 year 必须为整数', status=400)
    
    if stat_type == 'month':
        # 按月统计
        if not month:
            return json_err('参数 month 为必填项', status=400)
        
        try:
            month = int(month)
            if month < 1 or month > 12:
                raise ValueError
        except ValueError:
            return json_err('参数 month 必须为1-12的整数', status=400)
        
        # 计算该月第一天和最后一天
        first_day = date(year, month, 1)
        last_day_num = calendar.monthrange(year, month)[1]
        last_day = date(year, month, last_day_num)
        
        # 统计该月的数据
        users_count = UserInfo.objects.filter(
            created_at__date__gte=first_day,
            created_at__date__lte=last_day
        ).count()
        
        transaction_sum = PointsRecord.objects.filter(
            created_at__date__gte=first_day,
            created_at__date__lte=last_day
        ).aggregate(total=Sum('change'))['total'] or 0
        transaction_amount = abs(transaction_sum)
        
        visits_count = AccessLog.objects.filter(
            access_date__gte=first_day,
            access_date__lte=last_day
        ).aggregate(total=Sum('access_count'))['total'] or 0
        
        data = {
            'type': 'month',
            'year': year,
            'month': month,
            'start_date': str(first_day),
            'end_date': str(last_day),
            'users_count': users_count,
            'transaction_amount': transaction_amount,
            'visits_count': visits_count,
        }
        
        return json_ok(data)


    elif stat_type == 'week':
        # 按周统计（某月的第几周）
        if not month:
            return json_err('参数 month 为必填项', status=400)
        if not week:
            return json_err('参数 week 为必填项', status=400)
        
        try:
            month = int(month)
            week = int(week)
            if month < 1 or month > 12:
                raise ValueError('month')
            if week < 1 or week > 5:
                raise ValueError('week')
        except ValueError as e:
            if str(e) == 'month':
                return json_err('参数 month 必须为1-12的整数', status=400)
            elif str(e) == 'week':
                return json_err('参数 week 必须为1-5的整数', status=400)
            else:
                return json_err('参数格式错误', status=400)
        
        # 计算该月第一天
        first_day_of_month = date(year, month, 1)
        
        # 计算第几周的起始日期（简单算法：每周7天，第1周从1号开始）
        week_start_day = 1 + (week - 1) * 7
        week_end_day = week_start_day + 6
        
        # 获取该月最后一天
        last_day_num = calendar.monthrange(year, month)[1]
        
        # 确保不超出月份范围
        if week_start_day > last_day_num:
            return json_err(f'{year}年{month}月没有第{week}周', status=400)
        
        week_end_day = min(week_end_day, last_day_num)
        
        start_date = date(year, month, week_start_day)
        end_date = date(year, month, week_end_day)
        
        # 统计该周的数据
        users_count = UserInfo.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        ).count()
        
        transaction_sum = PointsRecord.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        ).aggregate(total=Sum('change'))['total'] or 0
        transaction_amount = abs(transaction_sum)
        
        visits_count = AccessLog.objects.filter(
            access_date__gte=start_date,
            access_date__lte=end_date
        ).aggregate(total=Sum('access_count'))['total'] or 0
        
        data = {
            'type': 'week',
            'year': year,
            'month': month,
            'week': week,
            'start_date': str(start_date),
            'end_date': str(end_date),
            'users_count': users_count,
            'transaction_amount': transaction_amount,
            'visits_count': visits_count,
        }
        
        return json_ok(data)


@admin_token_required
@require_http_methods(["GET"])
def admin_statistics_by_range(request, admin):
    start = request.GET.get('start_date')
    end = request.GET.get('end_date')
    if not start or not end:
        return json_err('缺少参数 start_date 或 end_date', status=400)
    try:
        from datetime import datetime
        sd = datetime.fromisoformat(start).date()
        ed = datetime.fromisoformat(end).date()
    except Exception:
        return json_err('日期格式错误，使用 YYYY-MM-DD', status=400)
    if sd > ed:
        return json_err('start_date 不能大于 end_date', status=400)
    users_count = UserInfo.objects.filter(created_at__date__gte=sd, created_at__date__lte=ed).count()
    transaction_sum = PointsRecord.objects.filter(created_at__date__gte=sd, created_at__date__lte=ed).aggregate(total=Sum('change'))['total'] or 0
    transaction_amount = abs(transaction_sum)
    visits_count = AccessLog.objects.filter(access_date__gte=sd, access_date__lte=ed).aggregate(total=Sum('access_count'))['total'] or 0
    data = {
        'type': 'range',
        'start_date': str(sd),
        'end_date': str(ed),
        'users_count': users_count,
        'transaction_amount': transaction_amount,
        'visits_count': visits_count,
    }
    return json_ok(data)


@admin_token_required
@require_http_methods(["GET"])
def admin_statistics_last_week(request, admin):
    today = date.today()
    # ISO: Monday=0. Last week Monday = today - (weekday+7) days
    last_monday = today - timedelta(days=today.weekday() + 7)
    last_sunday = last_monday + timedelta(days=6)
    users_count = UserInfo.objects.filter(created_at__date__gte=last_monday, created_at__date__lte=last_sunday).count()
    transaction_sum = PointsRecord.objects.filter(created_at__date__gte=last_monday, created_at__date__lte=last_sunday).aggregate(total=Sum('change'))['total'] or 0
    transaction_amount = abs(transaction_sum)
    visits_count = AccessLog.objects.filter(access_date__gte=last_monday, access_date__lte=last_sunday).aggregate(total=Sum('access_count'))['total'] or 0
    data = {
        'type': 'last_week',
        'start_date': str(last_monday),
        'end_date': str(last_sunday),
        'users_count': users_count,
        'transaction_amount': transaction_amount,
        'visits_count': visits_count,
    }
    return json_ok(data)

