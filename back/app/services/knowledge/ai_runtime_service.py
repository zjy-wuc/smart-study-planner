from datetime import timezone

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.repositories.admin import ai_config_repository


def read_config(
    db: Session,
) -> dict:

    try:
        config = ai_config_repository.find_config(
            db
        )

    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "AI_CONFIG_UNAVAILABLE",
                "message": "AI 配置暂时不可用",
            },
        ) from None

    if config is None:

        raise HTTPException(
            status_code=503,
            detail={
                "code": "AI_CONFIG_UNAVAILABLE",
                "message": "AI 运行配置不存在",
            },
        )

    config["enabled"] = bool(config["enabled"])

    return config


def effective_limits(
    config: dict,
) -> tuple[int, int]:

    user_limit = min(
        config["user_daily_limit"],
        settings.AI_USER_DAILY_HARD_LIMIT,
    )

    global_limit = min(
        config["global_daily_limit"],
        settings.AI_GLOBAL_DAILY_HARD_LIMIT,
    )

    return user_limit, global_limit


def public_config(
    config: dict,
) -> dict:

    user_limit, global_limit = effective_limits(
        config
    )

    updated_at = config["updated_at"]

    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(
            tzinfo=timezone.utc,
        )

    model_configured = bool(
        settings.DEEPSEEK_API_KEY
    )

    return {
        "id": config["id"],

        "enabled": config["enabled"],

        "user_daily_limit": (
            config["user_daily_limit"]
        ),

        "global_daily_limit": (
            config["global_daily_limit"]
        ),

        "effective_enabled": (
            config["enabled"] and model_configured
        ),

        "effective_user_daily_limit": user_limit,
        "effective_global_daily_limit": global_limit,

        "hard_user_daily_limit": (
            settings.AI_USER_DAILY_HARD_LIMIT
        ),

        "hard_global_daily_limit": (
            settings.AI_GLOBAL_DAILY_HARD_LIMIT
        ),

        "user_concurrency": (
            settings.AI_USER_CONCURRENCY
        ),

        "global_concurrency": (
            settings.AI_GLOBAL_CONCURRENCY
        ),

        "user_rate_limit": (
            settings.AI_USER_RATE_LIMIT
        ),

        "rate_window_seconds": (
            settings.AI_RATE_WINDOW_SECONDS
        ),

        "model_configured": model_configured,

        "updated_at": updated_at,
    }