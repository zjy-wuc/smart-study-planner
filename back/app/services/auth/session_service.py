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


from datetime import timezone

from app.repositories.auth import user_repository



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






def lock_current_user(
    db: Session,
    *,
    user_id: int,
    family_id: str,
) -> tuple[dict, dict]:
    """
    敏感操作专用。

    先锁定用户，再锁定当前 Session，
    并重新验证账号和会话状态。
    """

    user = user_repository.find_by_id(
        db,
        user_id=user_id,
        for_update=True,
    )

    if user is None:
        reject_auth(
            "INVALID_TOKEN",
            "用户不存在",
        )

    if not user["is_active"]:
        reject_auth(
            "ACCOUNT_DISABLED",
            "账号已被禁用",
            status_code=403,
        )

    session = session_repository.find_session(
        db,
        user_id=user_id,
        family_id=family_id,
        for_update=True,
    )

    session = require_active_session(
        session,
        utc_db_now(),
    )

    return user, session

def revoke_user_sessions_with_counts(
    db: Session,
    *,
    user_id: int,
    now: datetime,
    reason: str,
    exclude_family_id: str | None = None,
) -> tuple[int, int]:

    session_count = (
        session_repository.revoke_all_sessions(
            db,
            user_id=user_id,
            now=now,
            reason=reason,
            exclude_family_id=exclude_family_id,
        )
    )

    token_count = (
        token_repository.revoke_all_tokens(
            db,
            user_id=user_id,
            now=now,
            exclude_family_id=exclude_family_id,
        )
    )

    return int(session_count), int(token_count)


def revoke_user_sessions(
    db: Session,
    *,
    user_id: int,
    now: datetime,
    reason: str,
    exclude_family_id: str | None = None,
) -> int:

    session_count, _ = (
        revoke_user_sessions_with_counts(
            db,
            user_id=user_id,
            now=now,
            reason=reason,
            exclude_family_id=exclude_family_id,
        )
    )

    return session_count
def _device_name(user_agent: str | None) -> str:
    """根据 User-Agent 推断设备显示名称"""

    if not user_agent:
        return "未知设备"

    ua = user_agent.lower()

    # 操作系统
    if "android" in ua:
        os_name = "Android"

    elif "iphone" in ua:
        os_name = "iPhone"

    elif "ipad" in ua:
        os_name = "iPad"

    elif "windows" in ua:
        os_name = "Windows"

    elif "macintosh" in ua or "mac os" in ua:
        os_name = "macOS"

    elif "linux" in ua:
        os_name = "Linux"

    else:
        os_name = "未知系统"

    # 浏览器
    if "edg/" in ua or "edga/" in ua or "edgios/" in ua:
        browser = "Edge"

    elif "opr/" in ua:
        browser = "Opera"

    elif "firefox/" in ua or "fxios/" in ua:
        browser = "Firefox"

    elif "chrome/" in ua or "crios/" in ua:
        browser = "Chrome"

    elif "safari/" in ua:
        browser = "Safari"

    else:
        browser = "未知浏览器"

    return f"{os_name} · {browser}"


def public_session(
    session: dict,
    *,
    current_family_id: str,
) -> dict:
    """构建对外返回的设备信息"""

    return {
        "family_id": session["family_id"],
        "device_name": _device_name(
            session["user_agent"],
        ),
        "is_current": (
            session["family_id"]
            == current_family_id
        ),
        "created_at": session["created_at"].replace(
            tzinfo=timezone.utc,
        ),
        "last_activity_at": (
            session["last_activity_at"].replace(
                tzinfo=timezone.utc,
            )
        ),
        "absolute_expires_at": (
            session["absolute_expires_at"].replace(
                tzinfo=timezone.utc,
            )
        ),
    }


def list_sessions(
    db: Session,
    *,
    user_id: int,
    current_family_id: str,
    page: int,
    page_size: int,
) -> dict:

    now = utc_db_now()

    idle_cutoff = now - timedelta(
        days=settings.SESSION_IDLE_EXPIRE_DAYS,
    )

    offset = (page - 1) * page_size

    total = session_repository.count_active_sessions(
        db,
        user_id=user_id,
        now=now,
        idle_cutoff=idle_cutoff,
    )

    rows = session_repository.list_active_sessions_page(
        db,
        user_id=user_id,
        now=now,
        idle_cutoff=idle_cutoff,
        limit=page_size,
        offset=offset,
    )

    return {
        "items": [
            public_session(
                row,
                current_family_id=current_family_id,
            )
            for row in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_current_session(
    db: Session,
    *,
    user_id: int,
    family_id: str,
) -> dict:

    session = session_repository.find_session(
        db,
        user_id=user_id,
        family_id=family_id,
    )

    session = require_active_session(
        session,
        utc_db_now(),
    )

    return public_session(
        session,
        current_family_id=family_id,
    )
