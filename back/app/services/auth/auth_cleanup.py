import logging

from datetime import timedelta

from app.config import settings
from app.core.clock import utc_db_now

from app.repositories.auth import cleanup_repository

from app.services.auth import (
    avatar_service,
    rate_limit_service,
)


logger = logging.getLogger(__name__)
 

def run_auth_cleanup() -> dict:

    result = {
        "email_verifications": 0,
        "refresh_tokens": 0,
        "login_sessions": 0,
        "auth_events": 0,
        "orphan_avatars": 0,
        "failed": False,
    }

    try:
        with rate_limit_service.admission_session(
            "auth-cleanup",
        ) as db:

            now = utc_db_now()

            # 必须覆盖当日邮件额度及冷却窗口
            verification_retention = max(
                timedelta(days=2),
                timedelta(
                    seconds=(
                        settings.EMAIL_CODE_COOLDOWN_SECONDS
                    ),
                    days=1,
                ),
            )

            verification_cutoff = (
                now - verification_retention
            )

            token_cutoff = (
                now - timedelta(days=30)
            )

            # 保留安全日志的同时，
            # 不得提前删除仍用于限流的事件。
            event_retention = max(
                timedelta(
                    days=settings.AUTH_EVENT_RETENTION_DAYS,
                ),
                timedelta(
                    minutes=settings.AUTH_IP_WINDOW_MINUTES,
                ),
                timedelta(
                    minutes=settings.PASSWORD_LOCK_MINUTES,
                ),
            )

            event_cutoff = now - event_retention

            # 1. 清理过期验证码
            result["email_verifications"] = (
                cleanup_repository
                .delete_expired_verifications(
                    db,
                    created_cutoff=verification_cutoff,
                    expires_cutoff=(
                        now - timedelta(days=1)
                    ),
                )
            )

            db.commit()

            # 2. 清理过期 Refresh Token
            result["refresh_tokens"] = (
                cleanup_repository.delete_expired_tokens(
                    db,
                    cutoff=token_cutoff,
                )
            )

            db.commit()

            # 3. 清理已经失效的历史 Session
            result["login_sessions"] = (
                cleanup_repository
                .delete_inactive_sessions(
                    db,
                    cutoff=token_cutoff,
                )
            )

            db.commit()

            # 4. 清理历史认证事件
            result["auth_events"] = (
                cleanup_repository.delete_old_auth_events(
                    db,
                    cutoff=event_cutoff,
                )
            )

            db.commit()

        # 不同时持有认证清理锁和头像锁
        result["orphan_avatars"] = (
            avatar_service.cleanup_orphan_avatars()
        )

    except Exception:

        result["failed"] = True

        # 不记录可能含敏感 SQL 参数的异常详情
        logger.warning(
            "Authentication cleanup failed"
        )

    logger.info(
        "Authentication cleanup result: %s",
        result,
    )

    return result