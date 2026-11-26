from datetime import datetime, timezone

from fastapi import HTTPException, Request, Response

from app.config import settings
from app.core.security import decode_refresh_token

from ipaddress import ip_address

from app.response import success
from app.schemas.auth import TokenPair



def require_auth_request(request: Request) -> None:
    """保护涉及认证和 Cookie 的 POST 请求"""

    origin = request.headers.get("origin")#获取 Origin 请求头

    csrf_header = request.headers.get(
        "X-CSRF-Protection",
    )

    if (
        origin not in settings.AUTH_ALLOWED_ORIGINS
        or csrf_header != "1"
    ):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "CSRF_REJECTED",
                "message": "不允许的请求来源",
            },
        )


def get_refresh_cookie(
    request: Request,
) -> str | None:

    return request.cookies.get(
        settings.REFRESH_COOKIE_NAME,
    )


def set_refresh_cookie(
    response: Response,
    refresh_token: str,
) -> None:

    payload = decode_refresh_token(
        refresh_token,
    )

    if payload is None:
        raise RuntimeError("无法设置无效的 Refresh Token")

    max_age = max(#计算 Cookie 的有效期
        0,
        payload["exp"]
        - int(datetime.now(timezone.utc).timestamp()),
    )

    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=max_age,
        httponly=True,#禁止 JavaScript 读取
        secure=settings.REFRESH_COOKIE_SECURE,
        samesite="lax",#限制跨站 Cookie 发送
        path=settings.REFRESH_COOKIE_PATH,
    )

    response.headers["Cache-Control"] = "no-store"


def clear_refresh_cookie(
    response: Response,
) -> None:

    response.delete_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        path=settings.REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.REFRESH_COOKIE_SECURE,
        samesite="lax",
    )

    response.headers["Cache-Control"] = "no-store"






def get_request_ip(request: Request) -> str:

    if request.client is None:
        raise HTTPException(
            status_code=400,
            detail="无法获取客户端地址",
        )

    try:
        address = ip_address(
            request.client.host,
        )

    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="无效的客户端地址",
        ) from None

    mapped = getattr(
        address,
        "ipv4_mapped",
        None,
    )

    if mapped is not None:
        address = mapped

    return str(address)


def create_auth_response(
    pair: TokenPair,
    *,
    user: dict | None = None,
    message: str = "success",
    code: int = 200,
) -> Response:
    """Access 放入 JSON，Refresh 放入 Cookie"""

    data = pair.model_dump(
        exclude={"refresh_token"},
    )

    if user is not None:
        data["user"] = user

    response = success(
        data=data,
        message=message,
        code=code,
    )

    set_refresh_cookie(
        response,
        pair.refresh_token,
    )

    return response
