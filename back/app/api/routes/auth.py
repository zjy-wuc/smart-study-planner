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


router = APIRouter()


# ==================== 发送邮箱验证码 ====================


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


# ==================== Refresh Token 轮换 ====================


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


# ==================== 退出当前会话 ====================


@router.post(
    "/auth/logout",
    dependencies=[Depends(require_auth_request)],
)
def logout(
    request: Request,
    db: Session = Depends(get_db),
):

    auth_service.revoke_current_session(
        db,
        refresh_token=get_refresh_cookie(
            request,
        ),
        ip=get_request_ip(request),
    )

    response = success(
        message="已退出当前会话",
    )

    clear_refresh_cookie(response)

    return response