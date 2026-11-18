
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session


def list_daily_focus_stats(
    db: Session,
    user_id: int,
    start_date: date,
    end_date: date,
) -> list[dict]:
    """按专注开始日期统计已完成的有效专注。"""

    rows = db.execute(
        text("""
            SELECT
                focus_date,

                COALESCE(
                    SUM(focused_seconds),
                    0
                ) AS focused_seconds,

                COUNT(*) AS session_count,

                COALESCE(
                    SUM(
                        CASE
                            WHEN session_type = 'POMODORO'
                             AND focused_seconds >= planned_seconds
                            THEN 1
                            ELSE 0
                        END
                    ),
                    0
                ) AS completed_pomodoros

            FROM focus_sessions

            WHERE user_id = :user_id
              AND status = 'COMPLETED'
              AND focused_seconds > 0
              AND focus_date BETWEEN :start_date AND :end_date

            GROUP BY focus_date
            ORDER BY focus_date ASC
        """),
        {
            "user_id": user_id,
            "start_date": start_date,
            "end_date": end_date,
        },
    ).mappings().all()

    return [
        {
            "focus_date": row["focus_date"],
            "focused_seconds": int(row["focused_seconds"]),
            "session_count": int(row["session_count"]),
            "completed_pomodoros": int(
                row["completed_pomodoros"]
            ),
        }
        for row in rows
    ]
