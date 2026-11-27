from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session


def find_config(
    db: Session,
) -> dict | None:

    row = db.execute(
        text("""
            SELECT
                id,
                enabled,
                user_daily_limit,
                global_daily_limit,
                updated_at
            FROM ai_runtime_config
            WHERE id = 1
        """)
    ).mappings().first()

    return dict(row) if row is not None else None


def update_config(
    db: Session,
    *,
    enabled: bool,
    user_daily_limit: int,
    global_daily_limit: int,
    now: datetime,
) -> None:

    db.execute(
        text("""
            UPDATE ai_runtime_config
            SET enabled = :enabled,
                user_daily_limit = :user_daily_limit,
                global_daily_limit = :global_daily_limit,
                updated_at = :now
            WHERE id = 1
        """),
        {
            "enabled": int(enabled),
            "user_daily_limit": user_daily_limit,
            "global_daily_limit": global_daily_limit,
            "now": now,
        },
    )