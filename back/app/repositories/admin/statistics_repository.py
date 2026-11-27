from datetime import date, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session


def get_user_counts(db: Session) -> dict:

    row = db.execute(
        text("""
            SELECT
                COUNT(*) AS total_users,
                COUNT(CASE WHEN is_active = 1 THEN 1 END)
                    AS enabled_users,
                COUNT(CASE WHEN is_active = 0 THEN 1 END)
                    AS disabled_users
            FROM users
        """)
    ).mappings().one()

    return dict(row)


def get_daily_new_users(
    db: Session,
    start_at: datetime,
    end_exclusive: datetime,
) -> list[dict]:

    rows = db.execute(
        text("""
            SELECT
                DATE(created_at) AS date,
                COUNT(*) AS new_user_count
            FROM users
            WHERE created_at >= :start_at
              AND created_at < :end_exclusive
            GROUP BY DATE(created_at)
            ORDER BY date ASC
        """),
        {
            "start_at": start_at,
            "end_exclusive": end_exclusive,
        },
    ).mappings().all()

    return [dict(row) for row in rows]


def count_checkins(db: Session) -> int:

    count = db.execute(
        text("""
            SELECT COUNT(*)
            FROM study_records AS sr

            JOIN daily_tasks AS dt
                ON dt.id = sr.task_id

            JOIN study_plans AS sp
                ON sp.id = dt.plan_id
               AND sp.user_id = sr.user_id

            WHERE sp.deleted_at IS NULL
        """)
    ).scalar_one()

    return int(count)


def get_daily_learning_activity(
    db: Session,
    start_at: datetime,
    end_exclusive: datetime,
) -> list[dict]:

    rows = db.execute(
        text("""
            SELECT
                DATE(sr.recorded_at) AS date,
                COUNT(*) AS checkin_count,
                COUNT(DISTINCT sr.user_id)
                    AS active_user_count

            FROM study_records AS sr

            JOIN daily_tasks AS dt
                ON dt.id = sr.task_id

            JOIN study_plans AS sp
                ON sp.id = dt.plan_id
               AND sp.user_id = sr.user_id

            WHERE sp.deleted_at IS NULL
              AND sr.recorded_at >= :start_at
              AND sr.recorded_at < :end_exclusive

            GROUP BY DATE(sr.recorded_at)
            ORDER BY date ASC
        """),
        {
            "start_at": start_at,
            "end_exclusive": end_exclusive,
        },
    ).mappings().all()

    return [dict(row) for row in rows]


def get_plan_status_counts(
    db: Session,
) -> dict:

    rows = db.execute(
        text("""
            SELECT
                status,
                COUNT(*) AS count
            FROM study_plans
            WHERE deleted_at IS NULL
            GROUP BY status
        """)
    ).mappings().all()

    return {
        row["status"]: int(row["count"])
        for row in rows
    }


def count_notes(db: Session) -> int:

    count = db.execute(
        text("""
            SELECT COUNT(*)
            FROM knowledge_notes
            WHERE deleted_at IS NULL
        """)
    ).scalar_one()

    return int(count)


def count_ai_requests(
    db: Session,
    request_date: date,
) -> int:

    count = db.execute(
        text("""
            SELECT COUNT(*)
            FROM ai_requests
            WHERE request_date = :request_date
        """),
        {"request_date": request_date},
    ).scalar_one()

    return int(count)


def get_daily_ai_counts(
    db: Session,
    start_date: date,
    end_exclusive: date,
) -> list[dict]:

    rows = db.execute(
        text("""
            SELECT
                request_date AS date,
                COUNT(*) AS request_count
            FROM ai_requests
            WHERE request_date >= :start_date
              AND request_date < :end_exclusive
            GROUP BY request_date
            ORDER BY request_date ASC
        """),
        {
            "start_date": start_date,
            "end_exclusive": end_exclusive,
        },
    ).mappings().all()

    return [dict(row) for row in rows]


def get_ai_state(
    db: Session,
    request_date: date,
) -> dict:

    # 使用同一个数据库 UTC 时间判断租约状态。
    now = db.execute(
        text("SELECT UTC_TIMESTAMP(6)")
    ).scalar_one()

    rows = db.execute(
        text("""
            SELECT
                CASE
                    WHEN status = 'RUNNING'
                     AND leased_until <= :now
                    THEN 'RUNNING_EXPIRED'

                    ELSE status
                END AS status_group,

                COUNT(*) AS count

            FROM ai_requests
            WHERE request_date = :request_date

            GROUP BY status_group
        """),
        {
            "request_date": request_date,
            "now": now,
        },
    ).mappings().all()

    # 有效并发不限制日期：
    # 昨天开始、今天仍在运行的请求也占用并发。
    active_count = db.execute(
        text("""
            SELECT COUNT(*)
            FROM ai_requests
            WHERE status = 'RUNNING'
              AND leased_until > :now
        """),
        {"now": now},
    ).scalar_one()

    return {
        "status_counts": {
            row["status_group"]: int(row["count"])
            for row in rows
        },
        "active_count": int(active_count),
    }


def get_ai_operation_counts(
    db: Session,
    request_date: date,
) -> dict:

    rows = db.execute(
        text("""
            SELECT
                operation,
                COUNT(*) AS count
            FROM ai_requests
            WHERE request_date = :request_date
            GROUP BY operation
        """),
        {
            "request_date": request_date,
        },
    ).mappings().all()

    return {
        row["operation"]: int(row["count"])
        for row in rows
    }