
from datetime import datetime, timezone

from fastapi import HTTPException, status
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


def _build_token_pair(user_id: int, family_id: str) -> dict:
    """
    创建一对 Token，并准备数据库所需的信息。
    本函数不执行数据库操作。
    """

    access_token = create_access_token({
        "sub": str(user_id),
    })

    refresh_token = create_refresh_token({
        "sub": str(user_id),
        "family_id": family_id,
    })

    token_hash = hash_refresh_token(refresh_token)

    payload = decode_refresh_token(refresh_token)

    if payload is None:
        raise ValueError("Refresh Token generation failed")

    expires_at = datetime.fromtimestamp(
        payload["exp"],
        tz=timezone.utc,
    ).replace(tzinfo=None)

    token_pair = TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="Bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    return {
        "token_pair": token_pair.model_dump(),
        "token_hash": token_hash,
        "expires_at": expires_at,
    }


def _insert_refresh_token(
    db: Session,
    user_id: int,
    family_id: str,
    token_hash: str,
    expires_at: datetime,
):
    """向数据库保存 Refresh Token 摘要。"""

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

    db.execute(sql, {
        "user_id": user_id,
        "token_hash": token_hash,
        "family_id": family_id,
        "expires_at": expires_at,
    })


def issue_token_pair(db: Session, user_id: int) -> dict:
    """
    新登录：创建一个新的 family，并签发 Token Pair。
    """

    family_id = create_family_id()

    token_data = _build_token_pair(
        user_id=user_id,
        family_id=family_id,
    )

    try:
        _insert_refresh_token(
            db=db,
            user_id=user_id,
            family_id=family_id,
            token_hash=token_data["token_hash"],
            expires_at=token_data["expires_at"],
        )

        db.commit()

    except Exception:
        db.rollback()
        raise

    return token_data["token_pair"]


def rotate_refresh_token(
    db: Session,
    refresh_token: str,
) -> dict:
    """
    使用旧 Refresh Token 换取新 Token Pair。

    通过数据库事务、行锁和条件更新，
    保证同一个旧 Token 只能成功轮换一次。
    """

    # 1. 验证 JWT 签名、exp 和 Token 类型
    payload = decode_refresh_token(refresh_token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user_id = payload.get("sub")
    family_id = payload.get("family_id")

    if not user_id or not family_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token payload",
        )

    token_hash = hash_refresh_token(refresh_token)

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # 2. 开启事务
    try:
        with db.begin():

            # 3. 锁定旧 Token 对应的数据库记录
            select_sql = text("""
                SELECT
                    id,
                    user_id,
                    family_id,
                    expires_at,
                    revoked_at,
                    replaced_by
                FROM tb_refresh_token
                WHERE token_hash = :token_hash
                FOR UPDATE
            """)

            result = db.execute(
                select_sql,
                {"token_hash": token_hash},
            )

            old_token = result.mappings().first()

            if old_token is None:
                raise HTTPException(
                    status_code=401,
                    detail="Refresh token not found",
                )

            # 4. 检查数据库记录与 JWT 是否一致
            if (
                str(old_token["user_id"]) != str(user_id)
                or old_token["family_id"] != family_id
            ):
                raise HTTPException(
                    status_code=401,
                    detail="Refresh token mismatch",
                )

            # 5. 检查旧 Token 是否已经失效
            if (
                old_token["revoked_at"] is not None
                or old_token["replaced_by"] is not None
                or old_token["expires_at"] <= now
            ):
                raise HTTPException(
                    status_code=401,
                    detail="Refresh token already used or expired",
                )

            # 6. 在原 family 下生成新 Token
            token_data = _build_token_pair(
                user_id=int(user_id),
                family_id=family_id,
            )

            new_token_hash = token_data["token_hash"]

            # 7. 条件更新旧 Token
            update_sql = text("""
                UPDATE tb_refresh_token
                SET
                    revoked_at = :now,
                    replaced_by = :new_token_hash
                WHERE
                    id = :id
                    AND revoked_at IS NULL
                    AND replaced_by IS NULL
                    AND expires_at > :now
            """)

            update_result = db.execute(
                update_sql,
                {
                    "now": now,
                    "new_token_hash": new_token_hash,
                    "id": old_token["id"],
                },
            )

            # 必须恰好更新一条记录
            if update_result.rowcount != 1:
                raise HTTPException(
                    status_code=401,
                    detail="Refresh token has already been used",
                )

            # 8. 保存新 Token 摘要
            _insert_refresh_token(
                db=db,
                user_id=int(user_id),
                family_id=family_id,
                token_hash=new_token_hash,
                expires_at=token_data["expires_at"],
            )

        # 离开 with db.begin() 且没有异常，事务自动提交
        return token_data["token_pair"]

    except Exception:
        # with db.begin() 会在异常时回滚事务
        # 这里确保 Session 不残留失败事务状态
        db.rollback()
        raise
