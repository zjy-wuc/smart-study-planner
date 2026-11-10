
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

#更新refresh token
def rotate_refresh_token(
    db: Session,
    refresh_token: str,
) -> dict:
    """
    使用旧 Refresh Token 换取新 Token Pair。

    如果检测到已经轮换过的 Token 被再次使用，
    则撤销整个 family。
    """

    # 1. 验证 JWT
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

    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user id",
        )

    token_hash = hash_refresh_token(refresh_token)

    # 标记是否检测到了重放
    replay_detected = False

    # 正常轮换时保存新 Token
    token_pair = None

    try:
        # 2. 开启数据库事务
        with db.begin():

            # 3. 锁定当前 Refresh Token
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

            # 4. 验证 JWT 和数据库记录是否匹配
            if (
                old_token["user_id"] != user_id
                or old_token["family_id"] != family_id
            ):
                raise HTTPException(
                    status_code=401,
                    detail="Refresh token mismatch",
                )

            # 4.1 检查用户账号状态
            user_sql = text("""
                SELECT is_active
                FROM users
                WHERE id = :user_id
                FOR UPDATE
            """)

            user_result = db.execute(
                user_sql,
                {"user_id": user_id},
            )

            user = user_result.mappings().first()

            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={
                        "code": "USER_NOT_FOUND",
                        "message": "User not found",
                    },
                )

            if not user["is_active"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "code": "ACCOUNT_DISABLED",
                        "message": "Account is disabled",
                    },
                )

            # 获取锁之后再获取当前时间
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            # 5. 检测 Token 重放
            if old_token["replaced_by"] is not None:

                replay_detected = True

                # 撤销整个 family 中所有尚未撤销的 Token
                revoke_sql = text("""
                    UPDATE tb_refresh_token
                    SET revoked_at = :now
                    WHERE
                        user_id = :user_id
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
                # 7. 正常轮换：生成新 Token
                token_data = _build_token_pair(
                    user_id=user_id,
                    family_id=family_id,
                )

                new_token_hash = token_data["token_hash"]

                # 8. 条件更新旧 Token
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

                if update_result.rowcount != 1:
                    raise HTTPException(
                        status_code=401,
                        detail="Refresh token has already been used",
                    )

                # 9. 保存新 Token
                _insert_refresh_token(
                    db=db,
                    user_id=user_id,
                    family_id=family_id,
                    token_hash=new_token_hash,
                    expires_at=token_data["expires_at"],
                )

                token_pair = token_data["token_pair"]

        # 到这里，事务已经正常提交

    except Exception:
        db.rollback()
        raise

    # 10. 必须在事务提交之后返回 401
    if replay_detected:
        raise HTTPException(
            status_code=401,
            detail="Refresh token replay detected; session revoked",
        )

    return token_pair
    







#退出当前会话
def revoke_current_session(
    db: Session,
    refresh_token: str,
) -> None:
    """
    撤销当前 Refresh Token 所属的整个 family。
    """

    # 验证 Refresh Token
    payload = decode_refresh_token(refresh_token)

    if payload is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired refresh token",
        )

    user_id = payload.get("sub")
    family_id = payload.get("family_id")

    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=401,
            detail="Invalid refresh token payload",
        )

    if not family_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid refresh token payload",
        )

    token_hash = hash_refresh_token(refresh_token)

    try:
        # 查询数据库，确认这个 Token 确实存在
        result = db.execute(
            text("""
                SELECT user_id, family_id
                FROM tb_refresh_token
                WHERE token_hash = :token_hash
                FOR UPDATE
            """),
            {"token_hash": token_hash},
        )

        record = result.mappings().first()

        if (
            record is None
            or record["user_id"] != user_id
            or record["family_id"] != family_id
        ):
            raise HTTPException(
                status_code=401,
                detail="Refresh token not found",
            )

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # 撤销当前 family 所有尚未撤销的 Token
        db.execute(
            text("""
                UPDATE tb_refresh_token
                SET revoked_at = :now
                WHERE
                    user_id = :user_id
                    AND family_id = :family_id
                    AND revoked_at IS NULL
            """),
            {
                "now": now,
                "user_id": user_id,
                "family_id": family_id,
            },
        )

        db.commit()

    except Exception:
        db.rollback()
        raise   

#撤销所有会话
def revoke_all_sessions(
    db: Session,
    user_id: int,
) -> None:
    """
    撤销当前用户的所有 Refresh Token。
    """

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    try:
        db.execute(
            text("""
                UPDATE tb_refresh_token
                SET revoked_at = :now
                WHERE
                    user_id = :user_id
                    AND revoked_at IS NULL
            """),
            {
                "now": now,
                "user_id": user_id,
            },
        )

        db.commit()

    except Exception:
        db.rollback()
        raise 