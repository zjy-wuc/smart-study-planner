from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session


def find_by_id(
    db: Session,
    user_id: int,
    for_update: bool = False,
) -> dict | None:

    sql = """
        SELECT id, username, password_hash,
               email, email_verified_at,
               password_updated_at,
               nickname, avatar_url, is_active
        FROM users
        WHERE id = :user_id
    """

    if for_update:
        sql += " FOR UPDATE"

    row = db.execute(
        text(sql),
        {"user_id": user_id},
    ).mappings().first()

    return dict(row) if row is not None else None


def find_by_username(
    db: Session,
    username: str,
    for_update: bool = False,
) -> dict | None:

    sql = """
        SELECT id, username, password_hash,
               email, email_verified_at,
               password_updated_at,
               nickname, avatar_url, is_active
        FROM users
        WHERE username = :username
    """

    if for_update:
        sql += " FOR UPDATE"

    row = db.execute(
        text(sql),
        {"username": username},
    ).mappings().first()

    return dict(row) if row is not None else None


def find_by_email(
    db: Session,
    email: str,
    for_update: bool = False,
) -> dict | None:

    sql = """
        SELECT id, username, password_hash,
               email, email_verified_at,
               password_updated_at,
               nickname, avatar_url, is_active
        FROM users
        WHERE email = :email
    """

    if for_update:
        sql += " FOR UPDATE"

    row = db.execute(
        text(sql),
        {"email": email},
    ).mappings().first()

    return dict(row) if row is not None else None


def insert_user(
    db: Session,
    *,
    username: str,
    password_hash: str,
    email: str,
    nickname: str,
    now: datetime,
) -> int:

    result = db.execute(
        text("""
            INSERT INTO users (
                username,
                password_hash,
                password_updated_at,
                email,
                email_verified_at,
                nickname
            )
            VALUES (
                :username,
                :password_hash,
                :now,
                :email,
                :now,
                :nickname
            )
        """),
        {
            "username": username,
            "password_hash": password_hash,
            "email": email,
            "nickname": nickname,
            "now": now,
        },
    )

    return int(result.lastrowid)

def find_profile(
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
                avatar_url,
                email_verified_at,
                is_active,
                created_at,
                updated_at
            FROM users
            WHERE id = :user_id
        """),
        {"user_id": user_id},
    ).mappings().first()

    return dict(row) if row is not None else None


def update_nickname(
    db: Session,
    *,
    user_id: int,
    nickname: str,
) -> int:

    result = db.execute(
        text("""
            UPDATE users
            SET nickname = :nickname,
                updated_at = NOW()
            WHERE id = :user_id
        """),
        {
            "user_id": user_id,
            "nickname": nickname,
        },
    )

    return result.rowcount
