import time
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.security import verify_password
from app.services.auth_service import issue_token_pair
from app.response import success

from app.schemas.auth import RefreshRequest
from app.services.auth_service import (
    issue_token_pair,
    rotate_refresh_token,
)

router = APIRouter()
#登录接口,返回令牌和token种类

@router.post("/auth/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    #  查询用户
    sql = text("""
        SELECT id, username, password_hash, nickname
        FROM users
        WHERE username = :username
    """)

    result = db.execute(
        sql,
        {"username": form_data.username},
    )

    user = result.mappings().first()

    #  验证账号密码
    if user is None or not verify_password(
        form_data.password,
        user["password_hash"],
    ):
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 创建双 Token，并登记 Refresh Token 摘要
    token_pair = issue_token_pair(
        db=db,
        user_id=user["id"],
    )

    # 返回 Token 和用户信息
    return success(
        data={
            **token_pair,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "nickname": user["nickname"],
            },
        },
        message="登录成功",
        code=200,
    )




@router.post("/auth/refresh")
def refresh(
    request: RefreshRequest,
    db: Session = Depends(get_db),
):
    token_pair = rotate_refresh_token(
        db=db,
        refresh_token=request.refresh_token,
    )

    return success(
        data=token_pair,
        message="Token refreshed",
        code=200,
    )
    