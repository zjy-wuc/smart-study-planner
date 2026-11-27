from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Path,
    Query,
)

from sqlalchemy.orm import Session

from app.database import get_db
from app.core.deps import require_admin
from app.core.auth_cookie import require_auth_request
from app.response import success

from app.schemas.admin import (
    AdminAction,
    AdminActionRequest,
    AdminUserStatus,
)

from app.services.admin import (
    user_service,
    audit_service,
)


router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
)


UserId = Annotated[
    int,
    Path(gt=0, le=2**64 - 1),
]


@router.get("/users")
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str = Query("", max_length=254),
    status: AdminUserStatus | None = Query(None),
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):

    return success(
        data=user_service.list_users(
            db,
            page=page,
            page_size=page_size,
            keyword=keyword,
            status=status,
        )
    )


@router.get("/users/{user_id}")
def get_user_detail(
    user_id: UserId,
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):

    return success(
        data=user_service.get_user_detail(
            db,
            user_id,
        )
    )


@router.post(
    "/users/{user_id}/ban",
    dependencies=[Depends(require_auth_request)],
)
def ban_user(
    user_id: UserId,
    data: AdminActionRequest,
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):

    return success(
        data=user_service.change_user_state(
            db,
            admin=admin,
            user_id=user_id,
            action="BAN_USER",
            data=data,
        )
    )


@router.post(
    "/users/{user_id}/unban",
    dependencies=[Depends(require_auth_request)],
)
def unban_user(
    user_id: UserId,
    data: AdminActionRequest,
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):

    return success(
        data=user_service.change_user_state(
            db,
            admin=admin,
            user_id=user_id,
            action="UNBAN_USER",
            data=data,
        )
    )


@router.post(
    "/users/{user_id}/revoke-sessions",
    dependencies=[Depends(require_auth_request)],
)
def revoke_user_sessions(
    user_id: UserId,
    data: AdminActionRequest,
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):

    return success(
        data=user_service.change_user_state(
            db,
            admin=admin,
            user_id=user_id,
            action="REVOKE_SESSIONS",
            data=data,
        )
    )


@router.get("/audit-logs")
def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    action: AdminAction | None = Query(None),
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):

    return success(
        data=audit_service.list_audit_logs(
            db,
            page=page,
            page_size=page_size,
            action=action,
        )
    )