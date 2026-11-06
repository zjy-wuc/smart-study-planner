from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.database import get_db


# 从请求头中提取 Token
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# 根据 Token 获取当前用户
def get_current_user(
    #依赖注入
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    payload = decode_access_token(token)
    #check token
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id = payload.get("sub")
    #check user_id
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    sql = text("""
        SELECT id, username, nickname
        FROM users
        WHERE id = :user_id
    """)

    result = db.execute(sql, {"user_id": user_id})
    user = result.mappings().first()
    #check user
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return dict(user)