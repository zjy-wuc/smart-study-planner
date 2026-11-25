from datetime import date, datetime, timedelta, timezone


# 学习业务统一使用东八区
BUSINESS_TIMEZONE = timezone(timedelta(hours=8))


def business_today() -> date:
    """返回东八区当前业务日期"""
    return datetime.now(BUSINESS_TIMEZONE).date()


def utc_now() -> datetime:
    """返回带有 UTC 时区信息的当前时间"""
    return datetime.now(timezone.utc)


def utc_db_now() -> datetime:
    """返回用于写入 MySQL DATETIME 的 UTC 时间"""
    return utc_now().replace(tzinfo=None)