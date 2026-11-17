
from datetime import datetime, timezone
from typing import Any, TypedDict, cast

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.engine import CursorResult
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


class TokenData(TypedDict):
    token_pair: dict[str, Any]
    token_hash: str
    expires_at: datetime


def _utc_now() -> datetime:
    """返回 UTC 时间，适配数据库中的无时区 DATETIME"""

    return datetime.now(
        timezone.utc
    ).replace(tzinfo=None)


def _build_token_pair(
    user_id: int,
    family_id: str,
) -> TokenData:
    """
    创建 Access Token 和 Refresh Token。

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
        raise ValueError(
            "Refresh Token generation failed"
        )

    expires_at = datetime.fromtimestamp(
        payload["exp"],
        tz=timezone.utc,
    ).replace(tzinfo=None)

    token_pair = TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="Bearer",
        expires_in=(
            settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        ),
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
) -> None:
    """向数据库保存 Refresh Token 摘要"""

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

    db.execute(
        sql,
        {
            "user_id": user_id,
            "token_hash": token_hash,
            "family_id": family_id,
            "expires_at": expires_at,
        },
    )


def issue_token_pair(
    db: Session,
    user_id: int,
) -> dict:
    """新登录：创建 family 并签发 Token Pair"""

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

    检测到已轮换 Token 再次使用时，
    撤销整个 family。

    重放检测后的撤销必须先提交事务，
    再向客户端返回 401。
    """

    # 1. 验证 JWT
    payload = decode_refresh_token(refresh_token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    raw_user_id = payload.get("sub")
    family_id = payload.get("family_id")

    if raw_user_id is None or not isinstance(
        family_id, str
    ) or not family_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token payload",
        )

    try:
        user_id = int(raw_user_id)

    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user id",
        )

    token_hash = hash_refresh_token(refresh_token)

    replay_detected = False

    token_pair: dict[str, Any] | None = None

    try:
        # 2. 锁定旧 Refresh Token
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

        old_token = db.execute(
            select_sql,
            {"token_hash": token_hash},
        ).mappings().first()

        if old_token is None:
            raise HTTPException(
                status_code=401,
                detail="Refresh token not found",
            )

        # 3. 验证 JWT 与数据库记录是否匹配
        if (
            old_token["user_id"] != user_id
            or old_token["family_id"] != family_id
        ):
            raise HTTPException(
                status_code=401,
                detail="Refresh token mismatch",
            )

        # 4. 检查用户账号是否有效
        user_sql = text("""
            SELECT is_active
            FROM users
            WHERE id = :user_id
            FOR UPDATE
        """)

        user = db.execute(
            user_sql,
            {"user_id": user_id},
        ).mappings().first()

        if user is None:
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "USER_NOT_FOUND",
                    "message": "User not found",
                },
            )

        if not user["is_active"]:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "ACCOUNT_DISABLED",
                    "message": "Account is disabled",
                },
            )

        # 获取锁之后再读取当前时间
        now = _utc_now()

        # 5. 检查 Token 是否发生重放
        if old_token["replaced_by"] is not None:

            replay_detected = True

            # 撤销整个 family 的有效 Refresh Token
            revoke_sql = text("""
                UPDATE tb_refresh_token
                SET revoked_at = :now
                WHERE user_id = :user_id
                  AND family_id = :family_id
                  AND revoked_at IS NULL
            """)

            db.execute(
                revoke_sql,
                {
                    "now": now,
                    "user_id": user_id,
                    "family_id": family_id,
                },
            )

        # 6. 普通失效检查
        elif (
            old_token["revoked_at"] is not None
            or old_token["expires_at"] <= now
        ):
            raise HTTPException(
                status_code=401,
                detail="Refresh token already revoked or expired",
            )

        else:
            # 7. 正常轮换：生成新的 Token Pair
            token_data = _build_token_pair(
                user_id=user_id,
                family_id=family_id,
            )

            new_token_hash = token_data["token_hash"]

            # 8. 更新旧 Token
            update_sql = text("""
                UPDATE tb_refresh_token
                SET
                    revoked_at = :now,
                    replaced_by = :new_token_hash
                WHERE id = :id
                  AND revoked_at IS NULL
                  AND replaced_by IS NULL
                  AND expires_at > :now
            """)

            update_result = cast(
                CursorResult[Any],
                db.execute(
                    update_sql,
                    {
                        "now": now,
                        "new_token_hash": new_token_hash,
                        "id": old_token["id"],
                    },
                ),
            )

            if update_result.rowcount != 1:
                raise HTTPException(
                    status_code=401,
                    detail="Refresh token has already been used",
                )

            # 9. 保存新 Refresh Token
            _insert_refresh_token(
                db=db,
                user_id=user_id,
                family_id=family_id,
                token_hash=new_token_hash,
                expires_at=token_data["expires_at"],
            )

            token_pair = token_data["token_pair"]

        # 10. 统一提交事务
        # 重放撤销和正常轮换都在这里提交
        db.commit()

    except Exception:
        db.rollback()
        raise

    # 11. 重放发生时，撤销操作已经提交
    if replay_detected:
        raise HTTPException(
            status_code=401,
            detail=(
                "Refresh token replay detected; "
                "session revoked"
            ),
        )

    if token_pair is None:
        raise RuntimeError(
            "Refresh Token rotation did not produce a token pair"
        )

    return token_pair


def revoke_current_session(
    db: Session,
    refresh_token: str,
) -> None:
    """
    撤销当前 Refresh Token 所属的整个 family。
    """

    payload = decode_refresh_token(refresh_token)

    if payload is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired refresh token",
        )

    raw_user_id = payload.get("sub")
    family_id = payload.get("family_id")

    if raw_user_id is None or not isinstance(
        family_id, str
    ) or not family_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid refresh token payload",
        )

    try:
        user_id = int(raw_user_id)

    except (ValueError, TypeError):
        raise HTTPException(
            status_code=401,
            detail="Invalid refresh token payload",
        )

    token_hash = hash_refresh_token(refresh_token)

    try:
        # 1. 锁定并验证当前 Token
        select_sql = text("""
            SELECT user_id, family_id
            FROM tb_refresh_token
            WHERE token_hash = :token_hash
            FOR UPDATE
        """)

        record = db.execute(
            select_sql,
            {"token_hash": token_hash},
        ).mappings().first()

        if (
            record is None
            or record["user_id"] != user_id
            or record["family_id"] != family_id
        ):
            raise HTTPException(
                status_code=401,
                detail="Refresh token not found",
            )

        now = _utc_now()

        # 2. 撤销当前 family 全部有效 Token
        revoke_sql = text("""
            UPDATE tb_refresh_token
            SET revoked_at = :now
            WHERE user_id = :user_id
              AND family_id = :family_id
              AND revoked_at IS NULL
        """)

        db.execute(
            revoke_sql,
            {
                "now": now,
                "user_id": user_id,
                "family_id": family_id,
            },
        )

        # 3. 提交事务
        db.commit()

    except Exception:
        db.rollback()
        raise


def revoke_all_sessions(
    db: Session,
    user_id: int,
) -> None:
    """撤销当前用户的所有 Refresh Token"""

    now = _utc_now()

    try:
        sql = text("""
            UPDATE tb_refresh_token
            SET revoked_at = :now
            WHERE user_id = :user_id
              AND revoked_at IS NULL
        """)

        db.execute(
            sql,
            {
                "now": now,
                "user_id": user_id,
            },
        )

        db.commit()

    except Exception:
        db.rollback()
        raise
