from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

#已过期至少24小时，且创建时间超过保留窗口
def delete_expired_verifications(
    db: Session,
    *,
    created_cutoff: datetime,
    expires_cutoff: datetime,
    limit: int = 500,
) -> int:

    result = db.execute(
        text("""
            DELETE FROM email_verifications
            WHERE created_at < :created_cutoff
              AND expires_at < :expires_cutoff
            ORDER BY created_at, id
            LIMIT :limit
        """),
        {
            "created_cutoff": created_cutoff,
            "expires_cutoff": expires_cutoff,
            "limit": limit,
        },
    )

    return result.rowcount

#已过期超过30天
def delete_expired_tokens(
    db: Session,
    *,
    cutoff: datetime,
    limit: int = 500,
) -> int:

    result = db.execute(
        text("""
            DELETE FROM refresh_tokens
            WHERE expires_at < :cutoff
            ORDER BY expires_at, id
            LIMIT :limit
        """),
        {
            "cutoff": cutoff,
            "limit": limit,
        },
    )

    return result.rowcount

#已撤销或绝对过期超过30天，并且不存在关联 Token
def delete_inactive_sessions(
    db: Session,
    *,
    cutoff: datetime,
    limit: int = 500,
) -> int:

    result = db.execute(
        text("""
            DELETE FROM login_sessions
            WHERE (
                absolute_expires_at < :cutoff
                OR revoked_at < :cutoff
            )
            AND NOT EXISTS (
                SELECT 1
                FROM refresh_tokens
                WHERE refresh_tokens.user_id
                    = login_sessions.user_id
                  AND refresh_tokens.family_id
                    = login_sessions.family_id
            )
            ORDER BY absolute_expires_at, family_id
            LIMIT :limit
        """),
        {
            "cutoff": cutoff,
            "limit": limit,
        },
    )

    return result.rowcount


def delete_old_auth_events(
    db: Session,
    *,
    cutoff: datetime,
    limit: int = 500,
) -> int:

    result = db.execute(
        text("""
            DELETE FROM auth_events
            WHERE created_at < :cutoff
            ORDER BY created_at, id
            LIMIT :limit
        """),
        {
            "cutoff": cutoff,
            "limit": limit,
        },
    )

    return result.rowcount