from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session


def insert_token(
    db: Session,
    *,
    user_id: int,
    family_id: str,
    token_hash: str,
    expires_at: datetime,
    now: datetime,
) -> None:

    db.execute(
        text("""
            INSERT INTO refresh_tokens (
                user_id,
                family_id,
                token_hash,
                expires_at,
                created_at
            )
            VALUES (
                :user_id,
                :family_id,
                :token_hash,
                :expires_at,
                :now
            )
        """),
        {
            "user_id": user_id,
            "family_id": family_id,
            "token_hash": token_hash,
            "expires_at": expires_at,
            "now": now,
        },
    )


def find_by_hash(
    db: Session,
    token_hash: str,
    for_update: bool = False,
) -> dict | None:

    sql = """
        SELECT id, user_id, family_id,
               token_hash, expires_at,
               revoked_at, replaced_by,
               created_at
        FROM refresh_tokens
        WHERE token_hash = :token_hash
    """

    if for_update:
        sql += " FOR UPDATE"

    row = db.execute(
        text(sql),
        {"token_hash": token_hash},
    ).mappings().first()

    return dict(row) if row is not None else None


def mark_rotated(
    db: Session,
    *,
    token_id: int,
    new_token_hash: str,
    now: datetime,
) -> int:

    result = db.execute(
        text("""
            UPDATE refresh_tokens
            SET revoked_at = :now,
                replaced_by = :new_token_hash
            WHERE id = :token_id
              AND revoked_at IS NULL
              AND replaced_by IS NULL
              AND expires_at > :now
        """),
        {
            "token_id": token_id,
            "new_token_hash": new_token_hash,
            "now": now,
        },
    )

    return result.rowcount


def revoke_family(
    db: Session,
    *,
    user_id: int,
    family_id: str,
    now: datetime,
) -> int:

    result = db.execute(
        text("""
            UPDATE refresh_tokens
            SET revoked_at = :now
            WHERE user_id = :user_id
              AND family_id = :family_id
              AND revoked_at IS NULL
        """),
        {
            "user_id": user_id,
            "family_id": family_id,
            "now": now,
        },
    )

    return result.rowcount


def revoke_all_tokens(
    db: Session,
    *,
    user_id: int,
    now: datetime,
    exclude_family_id: str | None = None,
) -> int:

    result = db.execute(
        text("""
            UPDATE refresh_tokens
            SET revoked_at = :now
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
            "exclude_family_id": exclude_family_id,
        },
    )

    return result.rowcount