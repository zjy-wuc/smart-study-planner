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


# ==================== 登录限流配置 ====================
MAX_FAILED_ATTEMPTS = 5          # 窗口期内最多失败次数
RATE_LIMIT_WINDOW = 60           # 窗口期（秒），即 1 分钟内
failed_login_attempts: dict[str, list[float]] = defaultdict(list)


def _is_rate_limited(client_ip: str) -> bool:
    """检查该 IP 是否在窗口期内失败次数超限"""
    now = time.time()
    # 只保留窗口期内的失败记录
    failed_login_attempts[client_ip] = [
        ts for ts in failed_login_attempts[client_ip]
        if now - ts < RATE_LIMIT_WINDOW
    ]
    return len(failed_login_attempts[client_ip]) >= MAX_FAILED_ATTEMPTS


def _record_failed_attempt(client_ip: str) -> None:
    """记录一次失败登录的时间戳"""
    failed_login_attempts[client_ip].append(time.time())


def _clear_failed_attempts(client_ip: str) -> None:
    """登录成功后清空该 IP 的失败记录"""
    failed_login_attempts.pop(client_ip, None)
# =====================================================
