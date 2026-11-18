
from datetime import datetime, date

from sqlalchemy import text
from sqlalchemy.orm import Session


SESSION_COLUMNS = """
    id, user_id, plan_id, task_id,
    session_type, status,
    planned_seconds, focused_seconds,
    running_started_at, started_at, ended_at,
    focus_date, created_at, updated_at
"""


def lock_user(
    db: Session,
    user_id: int,
) -> None:
    """锁定用户行，串行化同一用户的专注操作。"""

    db.execute(
        text("""
            SELECT id
            FROM users
            WHERE id = :user_id
            FOR UPDATE
        """),
        {"user_id": user_id},
    ).scalar_one()


def find_active_session(
    db: Session,
    user_id: int,
) -> dict | None:
    """查询 RUNNING 或 PAUSED 会话并加锁。"""

    row = db.execute(
        text(f"""
            SELECT {SESSION_COLUMNS}
            FROM focus_sessions
            WHERE user_id = :user_id
              AND status IN ('RUNNING', 'PAUSED')
            ORDER BY id DESC
            LIMIT 1
            FOR UPDATE
        """),
        {"user_id": user_id},
    ).mappings().first()

    return dict(row) if row else None


def find_session(
    db: Session,
    session_id: int,
    user_id: int,
    for_update: bool = False,
) -> dict | None:
    lock_sql = "FOR UPDATE" if for_update else ""

    row = db.execute(
        text(f"""
            SELECT {SESSION_COLUMNS}
            FROM focus_sessions
            WHERE id = :session_id
              AND user_id = :user_id
            {lock_sql}
        """),
        {
            "session_id": session_id,
            "user_id": user_id,
        },
    ).mappings().first()

    return dict(row) if row else None


def has_valid_plan(
    db: Session,
    plan_id: int,
    user_id: int,
) -> bool:
    """仅允许关联当前用户的 ACTIVE 有效计划。"""

    result = db.execute(
        text("""
            SELECT id
            FROM study_plans
            WHERE id = :plan_id
              AND user_id = :user_id
              AND status = 'ACTIVE'
              AND deleted_at IS NULL
            FOR UPDATE
        """),
        {
            "plan_id": plan_id,
            "user_id": user_id,
        },
    ).scalar_one_or_none()

    return result is not None


def has_valid_task(
    db: Session,
    task_id: int,
    plan_id: int,
    user_id: int,
) -> bool:
    """校验任务属于指定计划、未删除且尚未完成。"""

    result = db.execute(
        text("""
            SELECT t.id
            FROM daily_tasks AS t
            JOIN study_plans AS p
              ON p.id = t.plan_id
            JOIN plan_steps AS s
              ON s.id = t.step_id
             AND s.plan_id = p.id
            WHERE t.id = :task_id
              AND t.plan_id = :plan_id
              AND p.user_id = :user_id
              AND p.status = 'ACTIVE'
              AND p.deleted_at IS NULL
              AND t.deleted_at IS NULL
              AND s.deleted_at IS NULL
              AND t.status IN ('PENDING', 'IN_PROGRESS')
            FOR UPDATE
        """),
        {
            "task_id": task_id,
            "plan_id": plan_id,
            "user_id": user_id,
        },
    ).scalar_one_or_none()

    return result is not None


def insert_session(
    db: Session,
    user_id: int,
    session_type: str,
    planned_seconds: int | None,
    plan_id: int | None,
    task_id: int | None,
    now: datetime,
    focus_date: date,
) -> int:
    result = db.execute(
        text("""
            INSERT INTO focus_sessions (
                user_id, plan_id, task_id,
                session_type, status,
                planned_seconds, focused_seconds,
                running_started_at, started_at,
                focus_date
            )
            VALUES (
                :user_id, :plan_id, :task_id,
                :session_type, 'RUNNING',
                :planned_seconds, 0,
                :now, :now,
                :focus_date
            )
        """),
        {
            "user_id": user_id,
            "plan_id": plan_id,
            "task_id": task_id,
            "session_type": session_type,
            "planned_seconds": planned_seconds,
            "now": now,
            "focus_date": focus_date,
        },
    )

    return int(
    db.execute(
        text("SELECT LAST_INSERT_ID()")
    ).scalar_one()
)


def save_session(
    db: Session,
    session: dict,
) -> None:
    """持久化一次合法的状态转换。"""

    db.execute(
        text("""
            UPDATE focus_sessions
            SET status = :status,
                focused_seconds = :focused_seconds,
                running_started_at = :running_started_at,
                ended_at = :ended_at,
                updated_at = NOW(6)
            WHERE id = :session_id
              AND user_id = :user_id
        """),
        {
            "session_id": session["id"],
            "user_id": session["user_id"],
            "status": session["status"],
            "focused_seconds": session["focused_seconds"],
            "running_started_at": session[
                "running_started_at"
            ],
            "ended_at": session["ended_at"],
        },
    )


def list_history(
    db: Session,
    user_id: int,
    page: int,
    page_size: int,
) -> dict:
    """历史包含 COMPLETED 和 CANCELLED 会话。"""

    where_sql = """
        user_id = :user_id
        AND status IN ('COMPLETED', 'CANCELLED')
    """

    total = db.execute(
        text(f"""
            SELECT COUNT(*)
            FROM focus_sessions
            WHERE {where_sql}
        """),
        {"user_id": user_id},
    ).scalar_one()

    rows = db.execute(
        text(f"""
            SELECT {SESSION_COLUMNS}
            FROM focus_sessions
            WHERE {where_sql}
            ORDER BY started_at DESC, id DESC
            LIMIT :limit OFFSET :offset
        """),
        {
            "user_id": user_id,
            "limit": page_size,
            "offset": (page - 1) * page_size,
        },
    ).mappings().all()

    return {
        "items": [dict(row) for row in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }
