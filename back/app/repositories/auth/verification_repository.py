from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session


# ==================== 创建验证码 ====================


def insert_verification(
    db: Session,
    *,
    email: str,
    purpose: str,
    code_hash: str,
    request_ip: str,
    now: datetime,
    expires_at: datetime,
    user_id: int | None = None,
    family_id: str | None = None,
) -> int:

    result = db.execute(
        text("""
            INSERT INTO email_verifications (
                email,
                purpose,
                user_id,
                family_id,
                code_hash,
                request_ip,
                created_at,
                expires_at,
                send_status
            )
            VALUES (
                :email,
                :purpose,
                :user_id,
                :family_id,
                :code_hash,
                :request_ip,
                :now,
                :expires_at,
                'PENDING'
            )
        """),
        {
            "email": email,
            "purpose": purpose,
            "user_id": user_id,
            "family_id": family_id,
            "code_hash": code_hash,
            "request_ip": request_ip,
            "now": now,
            "expires_at": expires_at,
        },
    )

    return int(result.lastrowid)


# ==================== 查询最新验证码 ====================


def find_latest_verification(
    db: Session,
    email: str,
    purpose: str,
    for_update: bool = False,
    *,
    user_id: int | None = None,
    family_id: str | None = None,
) -> dict | None:

    sql = """
        SELECT id, email, purpose,
               user_id, family_id,
               code_hash, attempts,
               created_at, expires_at,
               consumed_at, invalidated_at,
               send_status
        FROM email_verifications
        WHERE email = :email
          AND purpose = :purpose
    """

    params = {
        "email": email,
        "purpose": purpose,
    }

    if family_id is not None:

        sql += """
            AND user_id = :user_id
            AND family_id = :family_id
        """

        params.update({
            "user_id": user_id,
            "family_id": family_id,
        })

    sql += """
        ORDER BY created_at DESC, id DESC
        LIMIT 1
    """

    if for_update:
        sql += " FOR UPDATE"

    row = db.execute(
        text(sql),
        params,
    ).mappings().first()

    return dict(row) if row is not None else None
# ==================== 作废旧验证码 ====================

def invalidate_previous(
    db: Session,
    *,
    email: str,
    purpose: str,
    now: datetime,
    user_id: int | None = None,
    family_id: str | None = None,
) -> int:

    sql = """
        UPDATE email_verifications
        SET invalidated_at = :now
        WHERE email = :email
          AND purpose = :purpose
          AND consumed_at IS NULL
          AND invalidated_at IS NULL
    """

    params = {
        "email": email,
        "purpose": purpose,
        "now": now,
    }

    if family_id is not None:

        sql += """
            AND user_id = :user_id
            AND family_id = :family_id
        """

        params.update({
            "user_id": user_id,
            "family_id": family_id,
        })

    result = db.execute(
        text(sql),
        params,
    )

    return result.rowcount

# ==================== 邮件发送结果 ====================


def mark_send_result(#记录邮件发送结果
    db: Session,
    verification_id: int,
    sent: bool,
) -> int:

    result = db.execute(
        text("""
            UPDATE email_verifications
            SET send_status = :send_status
            WHERE id = :verification_id
              AND send_status = 'PENDING'
        """),
        {
            "verification_id": verification_id,
            "send_status": "SENT" if sent else "FAILED",
        },
    )

    return result.rowcount


# ==================== 记录错误次数 ====================


def increment_attempts(
    db: Session,
    *,
    verification_id: int,
    now: datetime,
    max_attempts: int,
) -> int:
#记录登录失败次数
    result = db.execute(
        text("""
            UPDATE email_verifications
            SET attempts = attempts + 1
            WHERE id = :verification_id
              AND send_status = 'SENT'
              AND consumed_at IS NULL
              AND invalidated_at IS NULL
              AND expires_at > :now
              AND attempts < :max_attempts
        """),
        {
            "verification_id": verification_id,
            "now": now,
            "max_attempts": max_attempts,
        },
    )

    return result.rowcount


# ==================== 消费验证码 ====================


def consume_verification(
    db: Session,
    *,
    verification_id: int,
    now: datetime,
    max_attempts: int,
) -> int:

    result = db.execute(
        text("""
            UPDATE email_verifications
            SET consumed_at = :now
            WHERE id = :verification_id
              AND send_status = 'SENT'
              AND consumed_at IS NULL
              AND invalidated_at IS NULL
              AND expires_at > :now
              AND attempts < :max_attempts
        """),
        {
            "verification_id": verification_id,
            "now": now,
            "max_attempts": max_attempts,
        },
    )

    return result.rowcount


# ==================== 发送冷却时间 ====================

#记录上次发送时间
def find_last_send_time(
    db: Session,
    email: str,
) -> datetime | None:

    return db.execute(
        text("""
            SELECT MAX(created_at)
            FROM email_verifications
            WHERE email = :email
        """),
        {"email": email},
    ).scalar()


# ==================== 邮箱发送额度 ====================


def count_email_sends(
    db: Session,
    email: str,
    since: datetime,
) -> int:

    count = db.execute(
        text("""
            SELECT COUNT(*)
            FROM email_verifications
            WHERE email = :email
              AND created_at >= :since
        """),
        {
            "email": email,
            "since": since,
        },
    ).scalar_one()

    return int(count)


# ==================== IP 发送额度 ====================


def count_ip_sends(
    db: Session,
    ip: str,
    since: datetime,
) -> int:

    count = db.execute(
        text("""
            SELECT COUNT(*)
            FROM email_verifications
            WHERE request_ip = :ip
              AND created_at >= :since
        """),
        {
            "ip": ip,
            "since": since,
        },
    ).scalar_one()

    return int(count)


# ==================== 全站发送额度 ====================


def count_global_sends(
    db: Session,
    since: datetime,
) -> int:

    count = db.execute(
        text("""
            SELECT COUNT(*)
            FROM email_verifications
            WHERE created_at >= :since
        """),
        {"since": since},
    ).scalar_one()

    return int(count)