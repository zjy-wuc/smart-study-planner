import hashlib
import logging

from contextlib import contextmanager
from datetime import datetime, timedelta
from ipaddress import ip_address
from typing import Iterator

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import engine
from app.core.clock import utc_db_now

from app.repositories.auth import (
    lock_repository,
    verification_repository,
    auth_event_repository,
)


logger = logging.getLogger(__name__)


# ==================== 限流事件类型 ====================

PASSWORD_ATTEMPT = "PASSWORD_ATTEMPT"
EMAIL_CODE_ATTEMPT = "EMAIL_CODE_ATTEMPT"

PASSWORD_FAILED = "PASSWORD_FAILED"
PASSWORD_LOCKED = "PASSWORD_LOCKED"
PASSWORD_CLEAR = "PASSWORD_CLEAR"


# ==================== 通用异常 ====================


def reject_rate_limit(
    message: str = "操作过于频繁，请稍后重试",
) -> None:

    raise HTTPException(
        status_code=429,
        detail={
            "code": "RATE_LIMITED",
            "message": message,
        },
    )


# ==================== IP 地址规范化 ====================


def normalize_ip(value: str) -> str:
    address = ip_address(value)

    mapped = getattr(
        address,
        "ipv4_mapped",
        None,
    )

    if mapped is not None:
        address = mapped

    return str(address)


# ==================== MySQL 命名锁 ====================


def _lock_name(scope: str) -> str:

    raw = (
        f"{settings.DB_NAME}:{scope}"
    ).encode("utf-8")

    digest = hashlib.sha256(raw).hexdigest()

    return f"ssp:{digest[:60]}"


@contextmanager
def admission_session(
    scope: str,
) -> Iterator[Session]:
    """
    在同一条物理连接上：
    获取命名锁、执行数据库事务、释放命名锁。

    业务调用者负责 db.commit()。
    """

    name = _lock_name(scope)

    with engine.connect() as connection:

        acquired = False

        try:
            try:
                acquired = lock_repository.acquire_lock(
                    connection,
                    name,
                    settings.AUTH_LOCK_TIMEOUT_SECONDS,
                )

                # 结束 GET_LOCK 产生的隐式事务。
                # 命名锁仍由当前连接持有。
                connection.commit()

            except Exception:
                connection.invalidate()
                raise

            if not acquired:
                reject_rate_limit(
                    "系统繁忙，请稍后重试"
                )

            with Session(bind=connection) as db:
                yield db

        finally:
            if acquired and not connection.invalidated:

                try:
                    # 确保没有残留业务事务
                    connection.rollback()

                    released = (
                        lock_repository.release_lock(
                            connection,
                            name,
                        )
                    )

                    connection.commit()

                    if not released:
                        connection.invalidate()
                        logger.error(
                            "Authentication lock release failed"
                        )

                except Exception:
                    connection.invalidate()

                    logger.error(
                        "Authentication lock cleanup failed"
                    )


# ==================== 邮件额度 ====================


def check_email_quota(
    db: Session,
    *,
    email: str,
    ip: str,
    now: datetime,
) -> None:
    """必须在全站邮件命名锁内调用"""

    # UTC 自然日开始时间
    day_start = now.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    last_send = (
        verification_repository.find_last_send_time(
            db,
            email,
        )
    )

    if last_send is not None:

        cooldown_end = (
            last_send
            + timedelta(
                seconds=(
                    settings.EMAIL_CODE_COOLDOWN_SECONDS
                )
            )
        )

        if now < cooldown_end:
            reject_rate_limit(
                "验证码发送过于频繁，请稍后重试"
            )

    email_count = (
        verification_repository.count_email_sends(
            db,
            email=email,
            since=day_start,
        )
    )

    if email_count >= settings.EMAIL_DAILY_LIMIT:
        reject_rate_limit("今日发送额度已达到上限")

    ip_count = (
        verification_repository.count_ip_sends(
            db,
            ip=ip,
            since=day_start,
        )
    )

    if ip_count >= settings.EMAIL_IP_DAILY_LIMIT:
        reject_rate_limit("今日发送额度已达到上限")

    global_count = (
        verification_repository.count_global_sends(
            db,
            since=day_start,
        )
    )

    if global_count >= settings.EMAIL_GLOBAL_DAILY_LIMIT:
        reject_rate_limit("今日发送额度已达到上限")


# ==================== IP 认证准入 ====================


def _reserve_ip_attempt(
    ip: str,
    event_type: str,
    max_attempts: int,
) -> None:

    ip = normalize_ip(ip)

    scope = f"auth-ip:{event_type}:{ip}"

    with admission_session(scope) as db:

        now = utc_db_now()

        since = now - timedelta(
            minutes=settings.AUTH_IP_WINDOW_MINUTES,
        )

        count = auth_event_repository.count_ip_events(
            db,
            ip=ip,
            event_type=event_type,
            since=since,
        )

        if count >= max_attempts:
            reject_rate_limit()

        auth_event_repository.insert_event(
            db,
            event_type=event_type,
            ip=ip,
            now=now,
        )

        db.commit()


def reserve_password_attempt(ip: str) -> None:

    _reserve_ip_attempt(
        ip=ip,
        event_type=PASSWORD_ATTEMPT,
        max_attempts=(
            settings.PASSWORD_IP_MAX_ATTEMPTS
        ),
    )


def reserve_email_code_attempt(ip: str) -> None:

    _reserve_ip_attempt(
        ip=ip,
        event_type=EMAIL_CODE_ATTEMPT,
        max_attempts=(
            settings.EMAIL_CODE_IP_MAX_ATTEMPTS
        ),
    )


# ==================== 账号密码锁定 ====================


def _latest_counter_reset(
    db: Session,
    user_id: int,
) -> int:

    cleared = (
        auth_event_repository.find_latest_user_event(
            db,
            user_id,
            PASSWORD_CLEAR,
        )
    )

    locked = (
        auth_event_repository.find_latest_user_event(
            db,
            user_id,
            PASSWORD_LOCKED,
        )
    )

    cleared_id = cleared["id"] if cleared else 0
    locked_id = locked["id"] if locked else 0

    return max(cleared_id, locked_id)


def is_password_locked(
    db: Session,
    user_id: int,
    now: datetime,
) -> bool:

    locked = (
        auth_event_repository.find_latest_user_event(
            db,
            user_id,
            PASSWORD_LOCKED,
        )
    )

    if locked is None:
        return False

    cleared = (
        auth_event_repository.find_latest_user_event(
            db,
            user_id,
            PASSWORD_CLEAR,
        )
    )

    if cleared and cleared["id"] > locked["id"]:
        return False

    unlock_at = (
        locked["created_at"]
        + timedelta(
            minutes=settings.PASSWORD_LOCK_MINUTES,
        )
    )

    return now < unlock_at


def record_password_failure(
    db: Session,
    *,
    user_id: int,
    identifier: str,
    ip: str,
    now: datetime,
) -> bool:
    """
    记录密码失败事件。

    必须先锁定 users 对应行，
    并且确认账号当前未处于密码锁定期。

    返回是否达到锁定阈值。
    不主动提交事务。
    """

    after_id = _latest_counter_reset(
        db,
        user_id,
    )

    since = now - timedelta(
        days=settings.AUTH_EVENT_RETENTION_DAYS,
    )

    failed_count = (
        auth_event_repository.count_user_events(
            db,
            user_id=user_id,
            event_type=PASSWORD_FAILED,
            since=since,
            after_id=after_id,
        )
    )

    auth_event_repository.insert_event(
        db,
        event_type=PASSWORD_FAILED,
        user_id=user_id,
        identifier=identifier,
        ip=ip,
        now=now,
    )

    should_lock = (
        failed_count + 1
        >= settings.PASSWORD_MAX_FAILED_ATTEMPTS
    )

    if should_lock:

        auth_event_repository.insert_event(
            db,
            event_type=PASSWORD_LOCKED,
            user_id=user_id,
            identifier=identifier,
            ip=ip,
            now=now,
        )

    return should_lock


def clear_password_failures(
    db: Session,
    *,
    user_id: int,
    now: datetime,
) -> None:
    """重置连续密码失败计数，不提交事务"""

    auth_event_repository.insert_event(
        db,
        event_type=PASSWORD_CLEAR,
        user_id=user_id,
        now=now,
    )