from datetime import date, timedelta
from collections.abc import Iterable


def calculate_current_streak(
    checkin_dates: Iterable[date],
    today: date,
) -> int:
    """
    计算当前连续打卡天数。


    """

    # 去重：同一天打卡多次，只算一天
    date_set = set(checkin_dates)

    yesterday = today - timedelta(days=1)

    if today in date_set:#今天打了卡
        cursor = today
    elif yesterday in date_set:#昨天打了卡
        cursor = yesterday
    else:
        return 0

    streak = 0

    while cursor in date_set:
        streak += 1
        cursor -= timedelta(days=1)

    return streak