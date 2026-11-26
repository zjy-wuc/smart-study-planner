import logging

from datetime import timedelta

from app.config import settings
from app.database import SessionLocal
from app.core.clock import utc_db_now

from app.repositories.auth import session_repository


logger = logging.getLogger(__name__)


ACTIVE_PATH_PREFIXES = (
    "/plans",
    "/tasks",
    "/notes",
    "/focus",
    "/statistics",
    "/ai/practices",
)


def is_activity_path(path: str) -> bool:

    # 后台提醒轮询不算有效活动
    if path == "/tasks/today/unchecked-count":
        return False

    return any(
        path == prefix
        or path.startswith(prefix + "/")
        for prefix in ACTIVE_PATH_PREFIXES
    )


def record_activity(
    user_id: int,
    family_id: str,
) -> None:

    try:
        with SessionLocal() as db:

            now = utc_db_now()

            idle_cutoff = now - timedelta(
                days=settings.SESSION_IDLE_EXPIRE_DAYS,
            )

            write_cutoff = now - timedelta(
                seconds=(
                    settings.SESSION_ACTIVITY_INTERVAL_SECONDS
                ),
            )

            session_repository.touch_session(
                db,
                user_id=user_id,
                family_id=family_id,
                now=now,
                idle_cutoff=idle_cutoff,
                write_cutoff=write_cutoff,
            )

            db.commit()

    except Exception:
        # 活跃时间更新失败不应破坏已成功的学习业务。
        logger.warning(
            "Session activity update failed"
        )