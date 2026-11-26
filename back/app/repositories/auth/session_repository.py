from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session


def insert_session(
    db: Session,
    *,
    family_id: str,
    user_id: int,
    user_agent: str | None,
    now: datetime,
    absolute_expires_at: datetime,
) -> None:

    db.execute(
        text("""
            INSERT INTO login_sessions (
                family_id,
                user_id,
                user_agent,
                created_at,
                last_activity_at,
                absolute_expires_at
            )
            VALUES (
                :family_id,
                :user_id,
                :user_agent,
                :now,
                :now,
                :absolute_expires_at
            )
        """),
        {
            "family_id": family_id,
            "user_id": user_id,
            "user_agent": user_agent,
            "now": now,
            "absolute_expires_at": absolute_expires_at,
        },
    )


def find_session(
    db: Session,
    user_id: int,
    family_id: str,
    for_update: bool = False,
) -> dict | None:

    sql = """
        SELECT family_id, user_id, user_agent,
               created_at, last_activity_at,
               absolute_expires_at,
               revoked_at, revoked_reason
        FROM login_sessions
        WHERE family_id = :family_id
          AND user_id = :user_id
    """

    if for_update:
        sql += " FOR UPDATE"

    row = db.execute(
        text(sql),
        {
            "family_id": family_id,
            "user_id": user_id,
        },
    ).mappings().first()

    return dict(row) if row is not None else None


def find_session_with_user(
    db: Session,
    user_id: int,
    family_id: str,
) -> dict | None:

    row = db.execute(
        text("""
            SELECT u.id,
                   u.username,
                   u.nickname,
                   u.email,
                   u.email_verified_at,
                   u.avatar_url,
                   u.is_active,

                   s.family_id,
                   s.last_activity_at,
                   s.absolute_expires_at,
                   s.revoked_at

            FROM login_sessions AS s

            INNER JOIN users AS u
                ON s.user_id = u.id

            WHERE s.family_id = :family_id
              AND s.user_id = :user_id
        """),
        {
            "family_id": family_id,
            "user_id": user_id,
        },
    ).mappings().first()

    return dict(row) if row is not None else None

#在用户访问网站时，有条件地更新登录会话的最后活跃时间。
def touch_session(
    db: Session,
    *,#表示它后面的参数必须使用关键字传参
    user_id: int,
    family_id: str,
    now: datetime,
    idle_cutoff: datetime,
    write_cutoff: datetime,
) -> int:

    result = db.execute(
        text("""
            UPDATE login_sessions
            SET last_activity_at = :now
            WHERE user_id = :user_id
              AND family_id = :family_id
              AND revoked_at IS NULL
              AND absolute_expires_at > :now
              AND last_activity_at > :idle_cutoff
              AND last_activity_at <= :write_cutoff
        """),
        {
            "user_id": user_id,
            "family_id": family_id,
            "now": now,
            "idle_cutoff": idle_cutoff,
            "write_cutoff": write_cutoff,
        },
    )

    return result.rowcount


def list_active_sessions(
    db: Session,
    user_id: int,
    now: datetime,
    idle_cutoff: datetime,
) -> list[dict]:

    rows = db.execute(
        text("""
            SELECT family_id,
                   user_agent,
                   created_at,
                   last_activity_at,
                   absolute_expires_at
            FROM login_sessions
            WHERE user_id = :user_id
              AND revoked_at IS NULL
              AND absolute_expires_at > :now
              AND last_activity_at > :idle_cutoff
            ORDER BY last_activity_at DESC
        """),
        {
            "user_id": user_id,
            "now": now,
            "idle_cutoff": idle_cutoff,
        },
    ).mappings().all()

    return [dict(row) for row in rows]


def revoke_session(
    db: Session,
    *,
    user_id: int,
    family_id: str,
    now: datetime,
    reason: str,
) -> int:

    result = db.execute(
        text("""
            UPDATE login_sessions
            SET revoked_at = :now,
                revoked_reason = :reason
            WHERE user_id = :user_id
              AND family_id = :family_id
              AND revoked_at IS NULL
        """),
        {
            "user_id": user_id,
            "family_id": family_id,
            "now": now,
            "reason": reason,
        },
    )

    return result.rowcount


def revoke_all_sessions(
    db: Session,
    *,
    user_id: int,
    now: datetime,
    reason: str,
    exclude_family_id: str | None = None,
) -> int:

    result = db.execute(
        text("""
            UPDATE login_sessions
            SET revoked_at = :now,
                revoked_reason = :reason
            WHERE user_id = :user_id
              AND revoked_at IS NULL
              AND (
                  :exclude_family_id IS NULL
                  OR family_id <> :exclude_family_id
              )
        """),
        {
            "user_id": user_id,
            "now": now,
            "reason": reason,
            "exclude_family_id": exclude_family_id,
        },
    )

    return result.rowcount





def count_active_sessions(
    db: Session,
    *,
    user_id: int,
    now: datetime,
    idle_cutoff: datetime,
) -> int:

    count = db.execute(
        text("""
            SELECT COUNT(*)
            FROM login_sessions
            WHERE user_id = :user_id
              AND revoked_at IS NULL
              AND absolute_expires_at > :now
              AND last_activity_at > :idle_cutoff
        """),
        {
            "user_id": user_id,
            "now": now,
            "idle_cutoff": idle_cutoff,
        },
    ).scalar_one()

    return int(count)


def list_active_sessions_page(
    db: Session,
    *,
    user_id: int,
    now: datetime,
    idle_cutoff: datetime,
    limit: int,
    offset: int,
) -> list[dict]:

    rows = db.execute(
        text("""
            SELECT
                family_id,
                user_agent,
                created_at,
                last_activity_at,
                absolute_expires_at
            FROM login_sessions
            WHERE user_id = :user_id
              AND revoked_at IS NULL
              AND absolute_expires_at > :now
              AND last_activity_at > :idle_cutoff
            ORDER BY last_activity_at DESC,
                     family_id DESC
            LIMIT :limit OFFSET :offset
        """),
        {
            "user_id": user_id,
            "now": now,
            "idle_cutoff": idle_cutoff,
            "limit": limit,
            "offset": offset,
        },
    ).mappings().all()

    return [dict(row) for row in rows]