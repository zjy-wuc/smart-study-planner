
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.clock import business_today
from app.repositories.focus import focus_statistics_repository
from app.services.focus import focus_service


def get_focus_statistics(
    db: Session,
    user_id: int,
    days: int = 7,
) -> dict:
    """获取最近 7 天或 30 天的专注统计。"""

    if days not in (7, 30):
        raise ValueError("days 只能是 7 或 30")

    # 统计前先结算已经到期的会话。
    # RUNNING 且尚未到期的会话不提前计入统计。
    focus_service.sync_current(
        db=db,
        user_id=user_id,
    )

    today = business_today()

    start_date = today - timedelta(days=days - 1)

    rows = focus_statistics_repository.list_daily_focus_stats(
        db=db,
        user_id=user_id,
        start_date=start_date,
        end_date=today,
    )

    # 将查询结果建立为日期索引。
    stats_by_date = {
        row["focus_date"]: row
        for row in rows
    }

    daily = []

    # 补齐没有专注记录的日期。
    for offset in range(days):
        current_date = start_date + timedelta(days=offset)

        record = stats_by_date.get(current_date)

        daily.append({
            "date": current_date.isoformat(),
            "focused_seconds": (
                record["focused_seconds"]
                if record else 0
            ),
            "session_count": (
                record["session_count"]
                if record else 0
            ),
            "completed_pomodoros": (
                record["completed_pomodoros"]
                if record else 0
            ),
        })

    period = {
        "focused_seconds": sum(
            day["focused_seconds"]
            for day in daily
        ),
        "session_count": sum(
            day["session_count"]
            for day in daily
        ),
        "completed_pomodoros": sum(
            day["completed_pomodoros"]
            for day in daily
        ),
    }

    # daily 按日期升序排列，最后一项就是今天。
    today_record = daily[-1]

    return {
        "days": days,
        "today": {
            "focused_seconds": today_record["focused_seconds"],
            "session_count": today_record["session_count"],
            "completed_pomodoros": today_record[
                "completed_pomodoros"
            ],
        },
        "period": period,
        "daily": daily,
    }
