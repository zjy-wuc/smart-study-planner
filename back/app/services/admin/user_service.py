from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.core.clock import utc_db_now

from app.repositories.admin import (
    user_repository as admin_user_repository,
    audit_repository,
)

from app.repositories.auth import (
    user_repository as auth_user_repository,
    session_repository,
)

from app.schemas.admin import (
    AdminUserAction,
    AdminUserStatus,
    AdminActionRequest,
)

from app.services.auth import session_service


def _reject(
    status_code: int,
    code: str,
    message: str,
) -> None:

    raise HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "message": message,
        },
    )


def _mask_email(email: str) -> str:

    local, domain = email.rsplit("@", 1)

    return f"{local[:1]}***@{domain}"


def _count_active_sessions(
    db: Session,
    user_id: int,
    now: datetime,
) -> int:

    idle_cutoff = now - timedelta(
        days=settings.SESSION_IDLE_EXPIRE_DAYS,
    )

    return session_repository.count_active_sessions(
        db,
        user_id=user_id,
        now=now,
        idle_cutoff=idle_cutoff,
    )


def _format_user(
    user: dict,
    *,
    mask_email: bool,
) -> dict:

    result = dict(user)

    result["is_active"] = bool(
        result["is_active"]
    )

    if mask_email:
        result["email"] = _mask_email(
            result["email"]
        )

    # 原有用户业务时间采用北京时间
    business_tz = timezone(timedelta(hours=8))

    for field in ("created_at", "updated_at"):
        value = result.get(field)

        if value is not None and value.tzinfo is None:
            result[field] = value.replace(
                tzinfo=business_tz,
            )

    # 邮箱验证时间采用 UTC
    verified_at = result.get("email_verified_at")

    if (
        verified_at is not None
        and verified_at.tzinfo is None
    ):
        result["email_verified_at"] = (
            verified_at.replace(tzinfo=timezone.utc)
        )

    return result


def list_users(
    db: Session,
    *,
    page: int,
    page_size: int,
    keyword: str,
    status: AdminUserStatus | None,
) -> dict:

    keyword = keyword.strip()

    is_active = None

    if status == "ACTIVE":
        is_active = 1

    elif status == "DISABLED":
        is_active = 0

    total = admin_user_repository.count_users(
        db,
        keyword=keyword,
        is_active=is_active,
    )

    users = admin_user_repository.list_users(
        db,
        keyword=keyword,
        is_active=is_active,
        limit=page_size,
        offset=(page - 1) * page_size,
    )

    return {
        "items": [
            _format_user(
                user,
                mask_email=True,
            )
            for user in users
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_user_detail(
    db: Session,
    user_id: int,
) -> dict:

    user = admin_user_repository.find_user_detail(
        db,
        user_id,
    )

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="用户不存在",
        )

    statistics = (
        admin_user_repository.get_user_statistics(
            db,
            user_id,
        )
    )

    statistics["active_session_count"] = (
        _count_active_sessions(
            db,
            user_id,
            utc_db_now(),
        )
    )

    return {
        **_format_user(
            user,
            mask_email=False,
        ),
        "statistics": statistics,
    }


def change_user_state(
    db: Session,
    *,
    admin: dict,
    user_id: int,
    action: AdminUserAction,
    data: AdminActionRequest,
) -> dict:

    admin_id = admin["id"]
    family_id = admin["family_id"]

    with db.begin():

        # 1. 按固定顺序锁定两名用户
        locked_users = {}

        for uid in sorted({admin_id, user_id}):

            locked_users[uid] = (
                auth_user_repository.find_by_id(
                    db,
                    uid,
                    for_update=True,
                )
            )

        operator = locked_users[admin_id]
        target = locked_users[user_id]

        # 2. 事务内重新校验操作者
        if operator is None:
            _reject(
                401,
                "SESSION_REVOKED",
                "登录身份已失效",
            )

        if not operator["is_active"]:
            _reject(
                403,
                "ACCOUNT_DISABLED",
                "账户已被禁用",
            )

        if operator["role"] != "ADMIN":
            _reject(
                403,
                "ADMIN_REQUIRED",
                "需要管理员权限",
            )

        # 3. 锁定并校验管理员当前会话
        current_session = (
            session_repository.find_session(
                db,
                admin_id,
                family_id,
                for_update=True,
            )
        )

        now = utc_db_now()

        session_service.require_active_session(
            current_session,
            now,
        )

        # 4. 校验目标用户
        if target is None:
            _reject(
                404,
                "USER_NOT_FOUND",
                "用户不存在",
            )

        if target["role"] == "ADMIN":
            _reject(
                403,
                "ADMIN_TARGET_FORBIDDEN",
                "不允许操作管理员账户",
            )

        is_active = bool(target["is_active"])

        # 5. 检查账户状态冲突
        if action == "BAN_USER" and not is_active:
            _reject(
                409,
                "USER_ALREADY_DISABLED",
                "该用户已经被封禁",
            )

        if action == "UNBAN_USER" and is_active:
            _reject(
                409,
                "USER_ALREADY_ACTIVE",
                "该用户当前未被封禁",
            )

        active_session_count = _count_active_sessions(
            db,
            user_id,
            now,
        )

        before_data = {
            "is_active": is_active,
            "active_session_count": active_session_count,
        }

        revoked_session_count = 0
        revoked_token_count = 0

        # 6. 执行账户状态变更
        if action == "BAN_USER":

            admin_user_repository.update_user_active(
                db,
                user_id=user_id,
                is_active=False,
            )

            is_active = False

        elif action == "UNBAN_USER":

            admin_user_repository.update_user_active(
                db,
                user_id=user_id,
                is_active=True,
            )

            is_active = True

        # 7. 封禁及强制下线撤销全部凭证
        if action in (
            "BAN_USER",
            "REVOKE_SESSIONS",
        ):

            (
                revoked_session_count,
                revoked_token_count,
            ) = (
                session_service
                .revoke_user_sessions_with_counts(
                    db,
                    user_id=user_id,
                    now=now,
                    reason="ADMIN",
                    exclude_family_id=None,
                )
            )

            active_session_count = 0

        after_data = {
            "is_active": is_active,
            "active_session_count": active_session_count,
            "revoked_session_count": revoked_session_count,
            "revoked_token_count": revoked_token_count,
        }

        # 8. 无实际变更的强制下线不记录审计
        changed = (
            action != "REVOKE_SESSIONS"
            or revoked_session_count > 0
            or revoked_token_count > 0
        )

        # 9. 审计与账户状态变更同事务
        if changed:

            audit_repository.insert_audit_log(
                db,
                admin_id=admin_id,
                action=action,
                target_type="USER",
                target_id=user_id,
                before_data=before_data,
                after_data=after_data,
                reason=data.reason,
                now=now,
            )

    # 离开 with db.begin() 后已完成提交
    return {
        "user_id": user_id,
        "is_active": is_active,
        "revoked_session_count": revoked_session_count,
        "revoked_token_count": revoked_token_count,
        "changed": changed,
    }