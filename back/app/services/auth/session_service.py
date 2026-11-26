from datetime import datetime, timedelta
from typing import NoReturn

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.core.clock import utc_db_now
from app.core.security import create_family_id

from app.repositories.auth import (
    session_repository,
    token_repository,
)


def reject_auth(
    code: str,
    message: str,
    status_code: int = 401,
) -> NoReturn:

    raise HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "message": message,
        },
    )


def require_active_session(
    session: dict | None,
    now: datetime,
) -> dict:
    """检查会话是否仍然有效"""

    if session is None:
        reject_auth(
            "SESSION_REVOKED",
            "登录会话不存在",
        )

    if session["revoked_at"] is not None:
        reject_auth(
            "SESSION_REVOKED",
            "登录会话已撤销",
        )

    if session["absolute_expires_at"] <= now:
        reject_auth(
            "SESSION_EXPIRED",
            "登录会话已到达最长有效期限",
        )

    idle_cutoff = now - timedelta(
        days=settings.SESSION_IDLE_EXPIRE_DAYS,
    )

    if session["last_activity_at"] <= idle_cutoff:
        reject_auth(
            "SESSION_EXPIRED",
            "登录会话长期未活跃，请重新登录",
        )

    return session


def create_session(
    db: Session,
    *,
    user_id: int,
    user_agent: str | None,
    now: datetime,
) -> dict:
    """创建独立登录会话，不提交事务"""

    family_id = create_family_id()

    absolute_expires_at = now + timedelta(
        days=settings.SESSION_ABSOLUTE_EXPIRE_DAYS,
    )

    if user_agent:
        user_agent = user_agent[:255]

    session_repository.insert_session(
        db,
        family_id=family_id,
        user_id=user_id,
        user_agent=user_agent,
        now=now,
        absolute_expires_at=absolute_expires_at,
    )

    return {
        "family_id": family_id,
        "absolute_expires_at": absolute_expires_at,
    }


def get_active_session(
    db: Session,
    *,
    user_id: int,
    family_id: str,
) -> dict:
    """查询有效会话及用户信息"""

    session = session_repository.find_session_with_user(
        db,
        user_id=user_id,
        family_id=family_id,
    )

    session = require_active_session(
        session,
        utc_db_now(),
    )

    if not session["is_active"]:
        reject_auth(
            "ACCOUNT_DISABLED",
            "账号已被禁用",
            status_code=403,
        )

    return session


def revoke_session(
    db: Session,
    *,
    user_id: int,
    family_id: str,
    now: datetime,
    reason: str,
) -> None:
    """
    撤销 Session 及所属 Refresh Token。

    调用者负责锁定用户、会话，并提交事务。
    """

    session_repository.revoke_session(
        db,
        user_id=user_id,
        family_id=family_id,
        now=now,
        reason=reason,
    )

    token_repository.revoke_family(
        db,
        user_id=user_id,
        family_id=family_id,
        now=now,
    )