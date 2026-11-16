from datetime import date, datetime, time, timedelta
from typing import Literal

from sqlalchemy.orm import Session

from app.core.clock import business_today
from app.repositories.statistics import statistics_repository
from app.schemas.statistics import (
    CheckinStatistics,
    PlanStatistics,
    DailyCheckinTrend,
    StatisticsOverview,
)
from app.services.statistics.streak_rules import (
    calculate_current_streak,
)


def get_statistics_overview(
    db: Session,
    user_id: int,
    days: Literal[7, 30] = 7,
    today: date | None = None,
) -> StatisticsOverview:
    """
    获取当前用户的学习数据统计概览。

    days 只影响每日趋势图显示的天数；
    累计、最近 7 天、最近 30 天三个指标始终返回。
    """

    if days not in (7, 30):
        raise ValueError("days 只支持 7 或 30")

    if today is None:
        today = business_today()

    # 统一按北京时间自然日构造查询窗口。
    # 前提：recorded_at 按北京时间写入 MySQL DATETIME。
    end_exclusive = datetime.combine(
        today + timedelta(days=1),
        time.min,
    )

    start_7 = datetime.combine(
        today - timedelta(days=6),
        time.min,
    )

    start_30 = datetime.combine(
        today - timedelta(days=29),
        time.min,
    )

    # 1. 统一查询三个打卡次数指标，总，7，30
    checkin_counts = statistics_repository.get_checkin_counts(
        db=db,
        user_id=user_id,
        start_7=start_7,
        start_30=start_30,
        end_exclusive=end_exclusive,
    )

    # 2. 查询计划状态数量
    plan_counts = statistics_repository.get_plan_status_counts(
        db=db,
        user_id=user_id,
    )

    # 3. 查询去重日期，计算当前连续打卡天数
    checkin_dates = statistics_repository.get_checkin_dates(
        db=db,
        user_id=user_id,
        end_exclusive=end_exclusive,
    )

    current_streak = calculate_current_streak(
        checkin_dates=checkin_dates,
        today=today,
    )

    # 4. 查询 7 天或 30 天趋势
    trend_start_date = today - timedelta(days=days - 1)

    trend_start_at = datetime.combine(
        trend_start_date,
        time.min,
    )

    trend_rows = statistics_repository.get_daily_checkin_counts(
        db=db,
        user_id=user_id,
        start_at=trend_start_at,
        end_exclusive=end_exclusive,
    )

    # 5. 转换为日期 -> 打卡次数的映射
    trend_map = {
        row["date"]: row["checkin_count"]
        for row in trend_rows
    }

    # 6. 补齐没有打卡的日期，保证图表日期连续
    daily_trend = []

    for offset in range(days):
        current_date = trend_start_date + timedelta(days=offset)
#组装
        daily_trend.append(
            DailyCheckinTrend(
                date=current_date,
                checkin_count=trend_map.get(current_date, 0),#如果不存在，就返回默认值0
            )
        )

    # 7. 按照统一 Schema 返回
    return StatisticsOverview(
        as_of_date=today,

        checkins=CheckinStatistics(
            total_count=checkin_counts["total_count"],
            last_7_days_count=checkin_counts["last_7_days_count"],
            last_30_days_count=checkin_counts["last_30_days_count"],
            current_streak_days=current_streak,
        ),

        plans=PlanStatistics(
            active_count=plan_counts["active_count"],
            ended_count=plan_counts["ended_count"],
        ),

        trend_days=days,
        daily_trend=daily_trend,
    )