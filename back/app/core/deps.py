from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer

from app.core.security import (
    decode_access_token_detailed,
)

from app.database import SessionLocal

from app.services.auth import session_service


from fastapi import Depends, Request, HTTPException

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login",
    auto_error=False,
)


def authenticate_access(
    token: str | None,
) -> dict:
    """验证 Access Token 和对应登录会话"""

    if not token:
        session_service.reject_auth(
            "INVALID_TOKEN",
            "缺少 Access Token",
        )

    payload, error_code = (
        decode_access_token_detailed(token)
    )

    if payload is None:

        if error_code == "ACCESS_EXPIRED":

            session_service.reject_auth(
                "ACCESS_EXPIRED",
                "Access Token 已过期",
            )

        session_service.reject_auth(
            error_code or "INVALID_TOKEN",
            "Access Token 无效",
        )

    user_id = int(payload["sub"])
    family_id = payload["family_id"]

    # 使用独立的短生命周期数据库 Session。
    # 避免认证查询提前开启业务事务。
    with SessionLocal() as db:

        return session_service.get_active_session(
            db,
            user_id=user_id,
            family_id=family_id,
        )


def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
) -> dict:

    user = authenticate_access(token)

    # 保存身份，用于请求成功后的活跃时间更新，中间件要用
    request.state.auth_identity = (
        user["id"],
        user["family_id"],
    )

    return user




def require_admin(
    user: dict = Depends(get_current_user),
) -> dict:
    """校验当前用户是否具有管理员权限"""

    if user.get("role") != "ADMIN":
        raise HTTPException(
            status_code=403,
            detail={
                "code": "ADMIN_REQUIRED",
                "message": "需要管理员权限",
            },
        )

    return user