from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import decode_access_token_detailed
from app.database import get_db


# 从请求头中提取 Token
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# 根据 Token 获取当前用户
def get_current_user(
    #依赖注入
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
#check token
    payload, error_code = decode_access_token_detailed(token)

    if payload is None:
        if error_code == "ACCESS_EXPIRED":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "ACCESS_EXPIRED",
                    "message": "Access token expired",
                },
            )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": error_code,
                "message": "Invalid access token",
            },
        )

    user_id = payload.get("sub")

    if user_id is None or not str(user_id).isdigit():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "INVALID_TOKEN_PAYLOAD",
                "message": "Invalid token payload",
            },
        )

    user_id = int(user_id)

    sql = text("""
    SELECT id, username, nickname, is_active
    FROM users
    WHERE id = :user_id
""")

    result = db.execute(sql, {"user_id": user_id})
    user = result.mappings().first()
    #check user
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
    "code": "USER_NOT_FOUND",
    "message": "User not found",
    }
        )

    if not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "ACCOUNT_DISABLED",
                "message": "Account is disabled",
            },
        )

    return dict(user)