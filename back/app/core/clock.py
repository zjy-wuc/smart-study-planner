
from datetime import date, datetime, timedelta, timezone


# 业务日期统一按东八区计算，避免服务器使用 UTC 时「今日任务」错位
BUSINESS_TIMEZONE = timezone(timedelta(hours=8))


def business_today() -> date:
    """返回东八区（Asia/Shanghai）的当前日期"""

    return datetime.now(BUSINESS_TIMEZONE).date()
