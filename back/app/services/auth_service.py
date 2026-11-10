
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    create_family_id,
    hash_refresh_token,
    decode_refresh_token,
)
from app.schemas.auth import TokenPair


def issue_token_pair(db: Session, user_id: int) -> dict:
    """
    为一次新的登录创建 Token Pair，
    并将 Refresh Token 的摘要保存到数据库。
    """

    # 1. 为本次登录创建独立的会话家族
    family_id = create_family_id()

    # 2. 生成 Access Token
    access_token = create_access_token({
        "sub": str(user_id),
    })

    # 3. 生成 Refresh Token
    refresh_token = create_refresh_token({
        "sub": str(user_id),
        "family_id": family_id,
    })

    # 4. 计算 Refresh Token 摘要
    token_hash = hash_refresh_token(refresh_token)

    # 5. 从 JWT 中取得真实过期时间
    payload = decode_refresh_token(refresh_token)
    if payload is None:
        raise ValueError("Refresh Token generation failed")

    expires_at = datetime.fromtimestamp(
        payload["exp"],
        tz=timezone.utc,
    ).replace(tzinfo=None)

    # 6. 只将摘要写入数据库，不保存原始 Token
    sql = text("""
        INSERT INTO tb_refresh_token (
            user_id,
            token_hash,
            family_id,
            expires_at
        )
        VALUES (
            :user_id,
            :token_hash,
            :family_id,
            :expires_at
        )
    """)

    try:
        db.execute(sql, {
            "user_id": user_id,
            "token_hash": token_hash,
            "family_id": family_id,
            "expires_at": expires_at,
        })

        db.commit()

    except Exception:
        db.rollback()
        raise

    # 7. 组织 Token Pair
    token_pair = TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="Bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    return token_pair.model_dump()
