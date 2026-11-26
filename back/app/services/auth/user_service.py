from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.repositories.auth import user_repository

from app.services.auth.auth_service import (
    public_user,
)


def require_owner(
    user_id: int,
    current_user_id: int,
) -> None:

    if user_id != current_user_id:

        raise HTTPException(
            status_code=403,
            detail="无权操作其他用户",
        )


def get_profile(
    db: Session,
    *,
    user_id: int,
    current_user_id: int,
) -> dict:

    require_owner(
        user_id,
        current_user_id,
    )

    user = user_repository.find_profile(
        db,
        user_id,
    )

    if user is None:

        raise HTTPException(
            status_code=404,
            detail="用户不存在",
        )

    return {
        **public_user(user),
        "created_at": user["created_at"],
        "updated_at": user["updated_at"],
    }


def update_nickname(
    db: Session,
    *,
    user_id: int,
    current_user_id: int,
    nickname: str,
) -> None:

    require_owner(
        user_id,
        current_user_id,
    )

    with db.begin():

        user = user_repository.find_by_id(
            db,
            user_id=user_id,
            for_update=True,
        )

        if user is None:
            raise HTTPException(
                status_code=404,
                detail="用户不存在",
            )

        if not user["is_active"]:
            raise HTTPException(
                status_code=403,
                detail="账号已被禁用",
            )

        if user["nickname"] != nickname:

            user_repository.update_nickname(
                db,
                user_id=user_id,
                nickname=nickname,
            )