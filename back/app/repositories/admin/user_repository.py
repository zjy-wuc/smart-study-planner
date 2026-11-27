from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.clock import business_today


def list_users(
    db: Session,
    *,
    keyword: str,
    is_active: int | None,
    limit: int,
    offset: int,
) -> list[dict]:

    rows = db.execute(
        text("""
            SELECT
                id,
                username,
                nickname,
                email,
                avatar_url,
                role,
                is_active,
                created_at
            FROM users
            WHERE (
                :keyword = ''
                OR LOCATE(:keyword, username) > 0
                OR email = :email
            )
            AND (
                :is_active IS NULL
                OR is_active = :is_active
            )
            ORDER BY created_at DESC, id DESC
            LIMIT :limit OFFSET :offset
        """),
        {
            "keyword": keyword,
            "email": keyword.lower(),
            "is_active": is_active,
            "limit": limit,
            "offset": offset,
        },
    ).mappings().all()

    return [dict(row) for row in rows]


def count_users(
    db: Session,
    *,
    keyword: str,
    is_active: int | None,
) -> int:

    result = db.execute(
        text("""
            SELECT COUNT(*)
            FROM users
            WHERE (
                :keyword = ''
                OR LOCATE(:keyword, username) > 0
                OR email = :email
            )
            AND (
                :is_active IS NULL
                OR is_active = :is_active
            )
        """),
        {
            "keyword": keyword,
            "email": keyword.lower(),
            "is_active": is_active,
        },
    ).scalar_one()

    return int(result)


def find_user_detail(
    db: Session,
    user_id: int,
) -> dict | None:

    row = db.execute(
        text("""
            SELECT
                id,
                username,
                nickname,
                email,
                email_verified_at,
                avatar_url,
                role,
                is_active,
                created_at,
                updated_at
            FROM users
            WHERE id = :user_id
        """),
        {"user_id": user_id},
    ).mappings().first()

    return dict(row) if row is not None else None


def get_user_statistics(
    db: Session,
    user_id: int,
) -> dict:

    row = db.execute(
        text("""
            SELECT
                (
                    SELECT COUNT(*)
                    FROM study_plans
                    WHERE user_id = :user_id
                      AND status = 'ACTIVE'
                      AND deleted_at IS NULL
                ) AS active_plan_count,

                (
                    SELECT COUNT(*)
                    FROM knowledge_notes
                    WHERE user_id = :user_id
                      AND deleted_at IS NULL
                ) AS note_count,

                (
                    SELECT COUNT(*)
                    FROM ai_requests
                    WHERE user_id = :user_id
                      AND request_date = :today
                ) AS today_ai_requests
        """),
        {
            "user_id": user_id,
            "today": business_today(),
        },
    ).mappings().one()

    return dict(row)


def update_user_active(
    db: Session,
    *,
    user_id: int,
    is_active: bool,
) -> None:

    db.execute(
        text("""
            UPDATE users
            SET is_active = :is_active
            WHERE id = :user_id
        """),
        {
            "user_id": user_id,
            "is_active": int(is_active),
        },
    )