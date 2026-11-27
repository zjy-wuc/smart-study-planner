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
               nickname, avatar_url, is_active, role
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
               nickname, avatar_url, is_active, role
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
               nickname, avatar_url, is_active, role
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
    role,
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



def update_password(
    db: Session,
    *,
    user_id: int,
    password_hash: str,
    now: datetime,
) -> int:

    result = db.execute(
        text("""
            UPDATE users
            SET password_hash = :password_hash,
                password_updated_at = :now
            WHERE id = :user_id
        """),
        {
            "user_id": user_id,
            "password_hash": password_hash,
            "now": now,
        },
    )

    return result.rowcount


def update_email(
    db: Session,
    *,
    user_id: int,
    email: str,
    now: datetime,
) -> int:

    result = db.execute(
        text("""
            UPDATE users
            SET email = :email,
                email_verified_at = :now
            WHERE id = :user_id
        """),
        {
            "user_id": user_id,
            "email": email,
            "now": now,
        },
    )

    return result.rowcount





#头像

def update_avatar(
    db: Session,
    *,
    user_id: int,
    avatar_url: str | None,
) -> int:

    result = db.execute(
        text("""
            UPDATE users
            SET avatar_url = :avatar_url
            WHERE id = :user_id
        """),
        {
            "user_id": user_id,
            "avatar_url": avatar_url,
        },
    )

    return result.rowcount


def list_avatar_urls(db: Session) -> set[str]:

    rows = db.execute(
        text("""
            SELECT avatar_url
            FROM users
            WHERE avatar_url IS NOT NULL
        """)
    ).scalars().all()

    return set(rows)



    
    
