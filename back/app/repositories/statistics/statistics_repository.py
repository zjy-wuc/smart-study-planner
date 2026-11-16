from datetime import date, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session


def _to_date(value: date | datetime | str) -> date:
    """统一数据库返回的日期类型。"""

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    return date.fromisoformat(value)


def get_checkin_counts(
    db: Session,
    user_id: int,
    start_7: datetime,
    start_30: datetime,
    end_exclusive: datetime,
) -> dict:
    """一次查询累计、近 7 天和近 30 天打卡次数。"""

    sql = text("""
        SELECT
            COUNT(*) AS total_count,

            COALESCE(
                SUM(
                    CASE
                        WHEN sr.recorded_at >= :start_7
                         AND sr.recorded_at < :end_exclusive
                        THEN 1
                        ELSE 0
                    END
                ),
                0
            ) AS last_7_days_count,

            COALESCE(
                SUM(
                    CASE
                        WHEN sr.recorded_at >= :start_30
                         AND sr.recorded_at < :end_exclusive
                        THEN 1
                        ELSE 0
                    END
                ),
                0
            ) AS last_30_days_count

        FROM study_records AS sr

        JOIN daily_tasks AS dt
            ON dt.id = sr.task_id

        JOIN study_plans AS sp
            ON sp.id = dt.plan_id

        WHERE sr.user_id = :user_id
          AND sp.user_id = :user_id
          AND sp.deleted_at IS NULL
    """)

    row = db.execute(
        sql,
        {
            "user_id": user_id,
            "start_7": start_7,
            "start_30": start_30,
            "end_exclusive": end_exclusive,
        },
    ).mappings().one()

    return {
        "total_count": int(row["total_count"]),
        "last_7_days_count": int(row["last_7_days_count"]),
        "last_30_days_count": int(row["last_30_days_count"]),
    }


def get_plan_status_counts(
    db: Session,
    user_id: int,
) -> dict:
    """一次查询执行中和已结束的计划数量。"""

    sql = text("""
        SELECT
            COALESCE(
                SUM(CASE WHEN status = 'ACTIVE' THEN 1 ELSE 0 END),
                0
            ) AS active_count,

            COALESCE(
                SUM(CASE WHEN status = 'ENDED' THEN 1 ELSE 0 END),
                0
            ) AS ended_count

        FROM study_plans

        WHERE user_id = :user_id
          AND deleted_at IS NULL
    """)

    row = db.execute(
        sql,
        {"user_id": user_id},
    ).mappings().one()

    return {
        "active_count": int(row["active_count"]),
        "ended_count": int(row["ended_count"]),
    }


def get_daily_checkin_counts(
    db: Session,
    user_id: int,
    start_at: datetime,
    end_exclusive: datetime,
) -> list[dict]:
    """查询指定时间范围内每日真实打卡次数。"""

    sql = text("""
        SELECT
            DATE(sr.recorded_at) AS checkin_date,
            COUNT(*) AS checkin_count

        FROM study_records AS sr

        JOIN daily_tasks AS dt
            ON dt.id = sr.task_id

        JOIN study_plans AS sp
            ON sp.id = dt.plan_id

        WHERE sr.user_id = :user_id
          AND sp.user_id = :user_id
          AND sp.deleted_at IS NULL
          AND sr.recorded_at >= :start_at
          AND sr.recorded_at < :end_exclusive

        GROUP BY DATE(sr.recorded_at)
        ORDER BY checkin_date ASC
    """)

    rows = db.execute(
        sql,
        {
            "user_id": user_id,
            "start_at": start_at,
            "end_exclusive": end_exclusive,
        },
    ).mappings().all()

    return [
        {
            "date": _to_date(row["checkin_date"]),
            "checkin_count": int(row["checkin_count"]),
        }
        for row in rows
    ]


def get_checkin_dates(
    db: Session,
    user_id: int,
    end_exclusive: datetime,
) -> list[date]:
    """查询历史打卡日期，日期去重，供连续天数计算。"""

    sql = text("""
        SELECT DISTINCT
            DATE(sr.recorded_at) AS checkin_date

        FROM study_records AS sr

        JOIN daily_tasks AS dt
            ON dt.id = sr.task_id

        JOIN study_plans AS sp
            ON sp.id = dt.plan_id

        WHERE sr.user_id = :user_id
          AND sp.user_id = :user_id
          AND sp.deleted_at IS NULL
          AND sr.recorded_at < :end_exclusive

        ORDER BY checkin_date DESC
    """)

    rows = db.execute(
        sql,
        {
            "user_id": user_id,
            "end_exclusive": end_exclusive,
        },
    ).mappings().all()

    return [
        _to_date(row["checkin_date"])
        for row in rows
    ]