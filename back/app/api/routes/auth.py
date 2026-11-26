from fastapi import (
    APIRouter,
    Depends,
    Request,
)

from fastapi.security import (
    OAuth2PasswordRequestForm,
)

from sqlalchemy.orm import Session

from app.database import get_db
from app.response import success

from app.core.deps import (
    oauth2_scheme,
    authenticate_access,
)

from app.core.auth_cookie import (
    require_auth_request,
    get_request_ip,
    get_refresh_cookie,
    clear_refresh_cookie,
    create_auth_response,
)

from app.schemas.auth import (
    EmailCodeRequest,
    EmailCodePurpose,
    EmailLoginRequest,
)

from app.services.auth import (
    auth_service,
    verification_service,
    session_service,
)



from uuid import UUID

from fastapi import Query

from app.core.deps import get_current_user
from app.core.security import decode_refresh_token

from app.schemas.auth import (
    PasswordResetRequest,
    PasswordChangeRequest,
    EmailChangeRequest,
    SessionRevokeRequest,
)

from app.services.auth import account_service



router = APIRouter()


# 发送邮箱验证码 


@router.post(
    "/auth/email-code",
    dependencies=[Depends(require_auth_request)],
)
def send_email_code(
    data: EmailCodeRequest,
    request: Request,
    token: str | None = Depends(oauth2_scheme),
):

    user_id = None
    family_id = None

    # 邮箱换绑必须处于有效登录状态
    if data.purpose in {
        EmailCodePurpose.CHANGE_EMAIL_OLD,
        EmailCodePurpose.CHANGE_EMAIL_NEW,
    }:

        current_user = authenticate_access(token)

        user_id = current_user["id"]
        family_id = current_user["family_id"]

    verification_service.request_email_code(
        email=data.email,
        purpose=data.purpose,
        request_ip=get_request_ip(request),
        current_user_id=user_id,
        current_family_id=family_id,
    )

    return success(
        message=(
            "如果该邮箱符合当前操作条件，"
            "您将收到验证码"
        ),
    )


# ==================== 密码登录 ====================


@router.post(
    "/auth/login",
    dependencies=[Depends(require_auth_request)],
)
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):

    pair, user = auth_service.login_with_password(
        db,
        identifier=form_data.username,
        password=form_data.password,
        ip=get_request_ip(request),
        user_agent=request.headers.get(
            "user-agent",
        ),
    )

    return create_auth_response(
        pair,
        user=user,
        message="登录成功",
    )


# ==================== 邮箱验证码登录 ====================


@router.post(
    "/auth/login/email",
    dependencies=[Depends(require_auth_request)],
)
def email_login(
    data: EmailLoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):

    pair, user = auth_service.login_with_email(
        db,
        email=data.email,
        code=data.code,
        ip=get_request_ip(request),
        user_agent=request.headers.get(
            "user-agent",
        ),
    )

    return create_auth_response(
        pair,
        user=user,
        message="登录成功",
    )


#  Refresh Token 轮换 


@router.post(
    "/auth/refresh",
    dependencies=[Depends(require_auth_request)],
)
def refresh(
    request: Request,
    db: Session = Depends(get_db),
):

    refresh_token = get_refresh_cookie(
        request,
    )

    if not refresh_token:

        session_service.reject_auth(
            "REFRESH_INVALID",
            "缺少 Refresh Token",
        )

    pair = auth_service.rotate_refresh_token(
        db,
        refresh_token=refresh_token,
        ip=get_request_ip(request),
    )

    return create_auth_response(
        pair,
        message="Token refreshed",
    )


#  退出当前会话

@router.post(
    "/auth/logout",
    dependencies=[Depends(require_auth_request)],
)
def logout(
    request: Request,
    db: Session = Depends(get_db),
    token: str | None = Depends(oauth2_scheme),
):

    revoked = auth_service.revoke_current_session(
        db,
        refresh_token=get_refresh_cookie(request),
        access_token=token,
        ip=get_request_ip(request),
    )

    response = success(
        data={
            "session_revoked": revoked,
        },
        message=(
            "已退出当前会话"
            if revoked
            else "已清理 Cookie，未确认服务端会话撤销"
        ),
    )

    clear_refresh_cookie(response)

    return response





#  忘记密码


@router.post(
    "/auth/password/reset",
    dependencies=[Depends(require_auth_request)],
)
def reset_password(
    data: PasswordResetRequest,
    request: Request,
    db: Session = Depends(get_db),
):

    user_id = account_service.reset_password(
        db,
        data=data,
        ip=get_request_ip(request),
    )

    response = success(
        message="密码重置成功，请重新登录",
    )

    # 仅清理属于被重置账号的 Cookie，
    # 避免影响浏览器中其他账号的登录状态。
    refresh_token = get_refresh_cookie(request)

    if refresh_token:

        payload = decode_refresh_token(
            refresh_token,
        )

        if (
            payload is None
            or int(payload["sub"]) == user_id
        ):
            clear_refresh_cookie(response)

    response.headers["Cache-Control"] = "no-store"

    return response


#  主动修改密码


@router.post(
    "/auth/password/change",
    dependencies=[Depends(require_auth_request)],
)
def change_password(
    data: PasswordChangeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):

    account_service.change_password(
        db,
        user_id=current_user["id"],
        family_id=current_user["family_id"],
        data=data,
        ip=get_request_ip(request),
    )

    return success(
        message="密码修改成功，其他设备已退出",
    )


#邮箱换绑 


@router.post(
    "/auth/email/change",
    dependencies=[Depends(require_auth_request)],
)
def change_email(
    data: EmailChangeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):

    user = account_service.change_email(
        db,
        user_id=current_user["id"],
        family_id=current_user["family_id"],
        data=data,
        ip=get_request_ip(request),
    )

    response = success(
        data=user,
        message="邮箱换绑成功，其他设备已退出",
    )

    response.headers["Cache-Control"] = "no-store"

    return response


#  登录设备列表


@router.get("/auth/sessions")
def list_sessions(
    page: int = Query(default=1, ge=1, le=100000),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):

    data = session_service.list_sessions(
        db,
        user_id=current_user["id"],
        current_family_id=current_user["family_id"],
        page=page,
        page_size=page_size,
    )

    response = success(data=data)

    response.headers["Cache-Control"] = "no-store"

    return response


#  当前会话信息 


@router.get("/auth/sessions/current")
def get_current_session(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):

    data = session_service.get_current_session(
        db,
        user_id=current_user["id"],
        family_id=current_user["family_id"],
    )

    response = success(data=data)

    response.headers["Cache-Control"] = "no-store"

    return response


#退出其他设备 


@router.post(
    "/auth/sessions/revoke-others",
    dependencies=[Depends(require_auth_request)],
)
def revoke_other_sessions(
    data: SessionRevokeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):

    affected = account_service.revoke_sessions(
        db,
        user_id=current_user["id"],
        current_family_id=current_user["family_id"],
        password=data.password,
        ip=get_request_ip(request),
        keep_current=True,
    )

    return success(
        data={
            "revoked_count": affected,
        },
        message="其他会话已撤销",
    )


#  撤销指定设备 


@router.post(
    "/auth/sessions/{family_id}/revoke",
    dependencies=[Depends(require_auth_request)],
)
def revoke_session(
    family_id: UUID,
    data: SessionRevokeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):

    account_service.revoke_other_session(
        db,
        user_id=current_user["id"],
        current_family_id=current_user["family_id"],
        target_family_id=str(family_id),
        password=data.password,
        ip=get_request_ip(request),
    )

    return success(
        message="目标会话已撤销",
    )


# 退出全部设备 


@router.post(
    "/auth/logout-all",
    dependencies=[Depends(require_auth_request)],
)
def logout_all(
    data: SessionRevokeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):

    affected = account_service.revoke_sessions(
        db,
        user_id=current_user["id"],
        current_family_id=current_user["family_id"],
        password=data.password,
        ip=get_request_ip(request),
        keep_current=False,
    )

    response = success(
        data={
            "revoked_count": affected,
        },
        message="全部会话已撤销",
    )

    refresh_token = get_refresh_cookie(request)

    if refresh_token:

        payload = decode_refresh_token(
            refresh_token,
        )

        if (
            payload is None
            or int(payload["sub"]) == current_user["id"]
        ):
            clear_refresh_cookie(response)

    response.headers["Cache-Control"] = "no-store"

    return response