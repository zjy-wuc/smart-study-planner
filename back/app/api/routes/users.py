from fastapi import (
    APIRouter,
    Depends,
    Request,
)

from sqlalchemy.orm import Session

from app.database import get_db
from app.response import success
from app.core.deps import get_current_user

from app.core.auth_cookie import (
    require_auth_request,
    get_request_ip,
    create_auth_response,
)

from app.schemas.user import (
    UserCreate,
    UserUpdate,
)

from app.services.auth import (
    auth_service,
    user_service,
)


router = APIRouter()


# ==================== 注册并自动登录 ====================


@router.post(
    "/users",
    status_code=201,
    dependencies=[Depends(require_auth_request)],
)
def create_user(
    data: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
):

    pair, user = auth_service.register(
        db,
        data=data,
        ip=get_request_ip(request),
        user_agent=request.headers.get(
            "user-agent",
        ),
    )

    return create_auth_response(
        pair,
        user=user,
        message="注册成功",
        code=201,
    )


# ==================== 当前用户信息 ====================


@router.get("/users/me")
def get_me(
    current_user: dict = Depends(
        get_current_user,
    ),
):

    return success(
        data=auth_service.public_user(
            current_user,
        ),
    )


# ==================== 用户资料 ====================


@router.get("/users/{user_id}")
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        get_current_user,
    ),
):

    profile = user_service.get_profile(
        db,
        user_id=user_id,
        current_user_id=current_user["id"],
    )

    return success(data=profile)


# ==================== 修改昵称 ====================


@router.put("/users/{user_id}")
def update_user(
    user_id: int,
    data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        get_current_user,
    ),
):

    user_service.update_nickname(
        db,
        user_id=user_id,
        current_user_id=current_user["id"],
        nickname=data.nickname,
    )

    return success(
        message="昵称修改成功",
    )