
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session
##当多个用户同时调用 AI 时，利用 MySQL 统一管理请求数量、并发额度和请求状态，避免超过系统设置的限制。

def lock_admission(db: Session) -> None:
    """
    统一串行化 AI 请求准入。

    所有进程必须先获得这把数据库行锁，
    才能检查共享额度并插入新请求。
    """
    row = db.execute(
        text("""
            SELECT id
            FROM ai_guard_mutex
            WHERE id = 1
            FOR UPDATE
        """)
    ).scalar_one_or_none()
#是在确保数据库中确实存在这条锁记录
    if row is None:
        raise RuntimeError("AI admission mutex is missing")

#检查用户和全局请求数量
def daily_counts(
    db: Session,
    request_date: date,
    user_id: int,
) -> tuple[int, int]:
    global_count = db.execute(
        text("""
            SELECT COUNT(*)
            FROM ai_requests
            WHERE request_date = :request_date
        """),
        {"request_date": request_date},
    ).scalar_one()

    user_count = db.execute(
        text("""
            SELECT COUNT(*)
            FROM ai_requests
            WHERE request_date = :request_date
              AND user_id = :user_id
        """),
        {
            "request_date": request_date,
            "user_id": user_id,
        },
    ).scalar_one()

    return int(global_count), int(user_count)


def active_counts(
    db: Session,
    user_id: int,
) -> tuple[int, int]:
    global_count = db.execute(
        text("""
            SELECT COUNT(*)
            FROM ai_requests
            WHERE status = 'RUNNING'
              AND leased_until > UTC_TIMESTAMP(6)
        """)#租约截止时间大于当前时间，说明请求正在运行
    ).scalar_one()

    user_count = db.execute(
        text("""
            SELECT COUNT(*)
            FROM ai_requests
            WHERE user_id = :user_id
              AND status = 'RUNNING'
              AND leased_until > UTC_TIMESTAMP(6)
        """),
        {"user_id": user_id},
    ).scalar_one()

    return int(global_count), int(user_count)

#登记 AI 请求

def insert_request(
    db: Session,
    request_id: str,
    user_id: int,
    note_id: int | None,
    request_date: date,
    lease_seconds: int,
    operation: str = "SUMMARY",
) -> None:
    db.execute(
        text("""
            INSERT INTO ai_requests (
                request_id,
                user_id,
                note_id,
                operation,
                request_date,
                status,
                leased_until
            )
            VALUES (
                :request_id,
                :user_id,
                :note_id,
                :operation,
                :request_date,
                'RUNNING',
                DATE_ADD(
                    UTC_TIMESTAMP(6),
                    INTERVAL :lease_seconds SECOND
                )
            )
        """),
        {
            "request_id": request_id,
            "user_id": user_id,
            "note_id": note_id,
            "operation": operation,
            "request_date": request_date,
            "lease_seconds": lease_seconds,
        },
    )


def finish_request(
    db: Session,
    request_id: str,
    status: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
) -> None:
    db.execute(
        text("""
            UPDATE ai_requests
            SET status = :status,
                finished_at = UTC_TIMESTAMP(6),
                prompt_tokens = :prompt_tokens,
                completion_tokens = :completion_tokens
            WHERE request_id = :request_id
              AND status = 'RUNNING'
        """),
        {
            "request_id": request_id,
            "status": status,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        },
    )
