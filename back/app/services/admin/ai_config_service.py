from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.core.clock import utc_db_now

from app.repositories.admin import (
    ai_config_repository,
    audit_repository,
)

from app.repositories.knowledge import (
    ai_guard_repository,
)

from app.schemas.admin import (
    AdminAIConfigUpdate,
)

from app.services.auth import session_service
from app.services.knowledge import ai_runtime_service


def _invalid(message: str) -> None:

    raise HTTPException(
        status_code=422,
        detail={
            "code": "AI_CONFIG_INVALID",
            "message": message,
        },
    )


def get_config(
    db: Session,
) -> dict:

    config = ai_runtime_service.read_config(db)

    return ai_runtime_service.public_config(
        config
    )


def update_config(
    db: Session,
    *,
    admin: dict,
    data: AdminAIConfigUpdate,
) -> dict:

    changes = data.model_dump(
        exclude_unset=True,
        exclude={"reason"},
    )

    if any(
        value is None
        for value in changes.values()
    ):
        _invalid("配置字段不能为 null")

    with db.begin():

        # 1. 复用 Auth V2 敏感操作权限校验
        operator, _ = (
            session_service.lock_current_user(
                db,
                user_id=admin["id"],
                family_id=admin["family_id"],
            )
        )

        if operator["role"] != "ADMIN":

            raise HTTPException(
                status_code=403,
                detail={
                    "code": "ADMIN_REQUIRED",
                    "message": "需要管理员权限",
                },
            )

        # 2. 使用与 AI 准入相同的互斥锁
        ai_guard_repository.lock_admission(db)

        # 3. 读取当前配置
        config = ai_runtime_service.read_config(
            db
        )

        before_data = {
            "enabled": config["enabled"],
            "user_daily_limit": (
                config["user_daily_limit"]
            ),
            "global_daily_limit": (
                config["global_daily_limit"]
            ),
        }

        # 4. 合并部分更新字段
        after_data = {
            **before_data,
            **changes,
        }

        user_limit = after_data["user_daily_limit"]
        global_limit = after_data["global_daily_limit"]

        # 5. 检查额度合法性
        if user_limit > global_limit:

            _invalid(
                "用户每日额度不能超过全站每日额度"
            )

        if (
            "user_daily_limit" in changes
            and user_limit
            > settings.AI_USER_DAILY_HARD_LIMIT
        ):

            _invalid(
                "用户每日额度超过开发者硬上限"
            )

        if (
            "global_daily_limit" in changes
            and global_limit
            > settings.AI_GLOBAL_DAILY_HARD_LIMIT
        ):

            _invalid(
                "全站每日额度超过开发者硬上限"
            )

        # 6. 判断是否发生实际变更
        changed = before_data != after_data

        if changed:

            now = utc_db_now()

            # 更新数据库配置
            ai_config_repository.update_config(
                db,
                enabled=after_data["enabled"],
                user_daily_limit=user_limit,
                global_daily_limit=global_limit,
                now=now,
            )

            # 同一事务写入管理员审计
            audit_repository.insert_audit_log(
                db,
                admin_id=admin["id"],
                action="UPDATE_AI_CONFIG",
                target_type="AI_CONFIG",
                target_id=1,
                before_data=before_data,
                after_data=after_data,
                reason=data.reason,
                now=now,
            )

            config = {
                **config,
                **after_data,
                "updated_at": now,
            }

    return {
        **ai_runtime_service.public_config(
            config
        ),
        "changed": changed,
    }