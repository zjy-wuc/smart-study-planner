from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.core.clock import utc_db_now

from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    hash_refresh_token,
)

from app.schemas.auth import (
    EmailCodePurpose,
    TokenPair,
)

from app.schemas.user import (
    UserCreate,
    UserPublic,
    normalize_email,
)

from app.repositories.auth import (
    user_repository,
    session_repository,
    token_repository,
    auth_event_repository,
)

from app.services.auth import (
    session_service,
    verification_service,
    rate_limit_service,
)


reject_auth = session_service.reject_auth


# 用于不存在账号时的模拟密码验证，
# 减少通过响应时间判断账号是否存在的风险。
DUMMY_PASSWORD_HASH = hash_password(
    "ssp-dummy-password-not-a-real-account"
)


# ==================== 公共用户信息 ====================


def public_user(user: dict) -> dict:
    """只返回允许对外公开的用户字段"""

    data = dict(user)

    verified_at = data["email_verified_at"]

    if verified_at.tzinfo is None:
        data["email_verified_at"] = (
            verified_at.replace(tzinfo=timezone.utc)
        )

    return UserPublic.model_validate(
        data,
    ).model_dump(mode="json")


# ==================== 密码规则 ====================


def validate_new_password(password: str) -> None:

    common_passwords = {
        "12345678",
        "123456789",
        "1234567890",
        "password",
        "password123",
        "qwerty123",
        "11111111",
        "00000000",
        "87654321",
        "abcdefgh",
        "iloveyou",
    }

    if (
        not 8 <= len(password) <= 64
        or password.lower() in common_passwords
        or len(set(password)) == 1
    ):
        reject_auth(
            "INVALID_PASSWORD",
            "密码不符合安全要求",
            status_code=400,
        )


# ==================== Token 签发 ====================


def _build_token_pair(
    *,
    user_id: int,
    family_id: str,
    absolute_expires_at: datetime,
) -> tuple[TokenPair, datetime]:

    # 数据库中的 UTC naive 时间转换为 aware 时间
    deadline = absolute_expires_at.replace(
        tzinfo=timezone.utc,
    )

    claims = {
        "sub": str(user_id),
        "family_id": family_id,
    }

    access_token = create_access_token(
        claims,
        expires_at=deadline,
    )

    refresh_token = create_refresh_token(
        claims,
        expires_at=deadline,
    )

    access_payload = decode_access_token(
        access_token,
    )

    refresh_payload = decode_refresh_token(
        refresh_token,
    )

    if (
        access_payload is None
        or refresh_payload is None
    ):
        raise RuntimeError("Token 签发失败")

    refresh_expires_at = datetime.fromtimestamp(
        refresh_payload["exp"],
        tz=timezone.utc,
    ).replace(tzinfo=None)

    expires_in = max(
        0,
        access_payload["exp"]
        - int(datetime.now(timezone.utc).timestamp()),
    )

    pair = TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )

    return pair, refresh_expires_at


def _create_login(
    db: Session,
    *,
    user: dict,
    user_agent: str | None,
    ip: str,
    now: datetime,
) -> tuple[TokenPair, dict]:
    """
    在当前事务中创建会话与双 Token。

    不主动提交事务。
    """

    session = session_service.create_session(
        db,
        user_id=user["id"],
        user_agent=user_agent,
        now=now,
    )

    family_id = session["family_id"]

    pair, expires_at = _build_token_pair(
        user_id=user["id"],
        family_id=family_id,
        absolute_expires_at=(
            session["absolute_expires_at"]
        ),
    )

    token_repository.insert_token(
        db,
        user_id=user["id"],
        family_id=family_id,
        token_hash=hash_refresh_token(
            pair.refresh_token,
        ),
        expires_at=expires_at,
        now=now,
    )

    auth_event_repository.insert_event(
        db,
        event_type="LOGIN_SUCCESS",
        user_id=user["id"],
        family_id=family_id,
        ip=ip,
        now=now,
    )

    return pair, public_user(user)


# ==================== 邮箱注册 ====================


def register(
    db: Session,
    *,
    data: UserCreate,
    ip: str,
    user_agent: str | None,
) -> tuple[TokenPair, dict]:

    rate_limit_service.reserve_email_code_attempt(ip)

    validate_new_password(data.password)

    try:
        with db.begin():

            record = (
                verification_service.check_verification(
                    db,
                    email=data.email,
                    purpose=EmailCodePurpose.REGISTER,
                    code=data.code,
                )
            )

            if record is None:

                # 当前还没有账号等业务写入，
                # 仅持久化可能增加的错误次数。
                db.commit()

                verification_service.reject_invalid_code()

            now = utc_db_now()

            user_id = user_repository.insert_user(
                db,
                username=data.username,
                email=data.email,
                password_hash=hash_password(
                    data.password,
                ),
                nickname=(
                    data.nickname or data.username
                ),
                now=now,
            )

            user = user_repository.find_by_id(
                db,
                user_id=user_id,
            )

            if user is None:
                raise RuntimeError("新建用户查询失败")

            consumed = (
                verification_service.consume_verification(
                    db,
                    record["id"],
                )
            )

            if not consumed:
                verification_service.reject_invalid_code()

            auth_event_repository.insert_event(
                db,
                event_type="REGISTER_SUCCESS",
                user_id=user_id,
                ip=ip,
                now=now,
            )

            result = _create_login(
                db,
                user=user,
                user_agent=user_agent,
                ip=ip,
                now=now,
            )

        return result

    except IntegrityError as exc:

        # MySQL 1062：唯一约束冲突
        args = exc.orig.args

        if args and args[0] == 1062:

            constraint = str(exc.orig)

            if "uk_users_username" in constraint:
                reject_auth(
                    "USERNAME_EXISTS",
                    "用户名已存在",
                    status_code=409,
                )

            if "uk_users_email" in constraint:
                reject_auth(
                    "EMAIL_UNAVAILABLE",
                    "邮箱不可用于注册",
                    status_code=409,
                )

        raise


# ==================== 密码登录 ====================


def _find_login_user(
    db: Session,
    identifier: str,
) -> dict | None:
    """支持用户名或邮箱登录，并锁定用户行"""

    identifier = identifier.strip()

    if "@" in identifier:

        try:
            email = normalize_email(identifier)

        except ValueError:
            return None

        return user_repository.find_by_email(
            db,
            email=email,
            for_update=True,
        )

    return user_repository.find_by_username(
        db,
        username=identifier,
        for_update=True,
    )


def login_with_password(
    db: Session,
    *,
    identifier: str,
    password: str,
    ip: str,
    user_agent: str | None,
) -> tuple[TokenPair, dict]:

    rate_limit_service.reserve_password_attempt(ip)

    if (
        not 1 <= len(identifier) <= 254
        or not 8 <= len(password) <= 64
    ):
        reject_auth(
            "INVALID_CREDENTIALS",
            "账号或密码错误",
        )

    with db.begin():

        user = _find_login_user(
            db,
            identifier,
        )

        if user is None:

            verify_password(
                password,
                DUMMY_PASSWORD_HASH,
            )

            reject_auth(
                "INVALID_CREDENTIALS",
                "账号或密码错误",
            )

        user_id = user["id"]
        now = utc_db_now()

        if rate_limit_service.is_password_locked(
            db,
            user_id,
            now,
        ):
            rate_limit_service.reject_rate_limit(
                "密码尝试次数过多，请稍后重试",
            )

        correct = verify_password(
            password,
            user["password_hash"],
        )

        if not correct:

            rate_limit_service.record_password_failure(
                db,
                user_id=user_id,
                identifier=user["username"],
                ip=ip,
                now=utc_db_now(),
            )

            # 密码失败事件必须持久化
            db.commit()

            reject_auth(
                "INVALID_CREDENTIALS",
                "账号或密码错误",
            )

        if not user["is_active"]:
            reject_auth(
                "ACCOUNT_DISABLED",
                "账号已被禁用",
                status_code=403,
            )

        rate_limit_service.clear_password_failures(
            db,
            user_id=user_id,
            now=utc_db_now(),
        )

        result = _create_login(
            db,
            user=user,
            user_agent=user_agent,
            ip=ip,
            now=utc_db_now(),
        )

    return result


# ==================== 邮箱验证码登录 ====================


def login_with_email(
    db: Session,
    *,
    email: str,
    code: str,
    ip: str,
    user_agent: str | None,
) -> tuple[TokenPair, dict]:

    rate_limit_service.reserve_email_code_attempt(ip)

    with db.begin():

        user = user_repository.find_by_email(
            db,
            email=normalize_email(email),
            for_update=True,
        )

        if user is None or not user["is_active"]:
            verification_service.reject_invalid_code()

        record = (
            verification_service.check_verification(
                db,
                email=user["email"],
                purpose=EmailCodePurpose.LOGIN,
                code=code,
                user_id=user["id"],
            )
        )

        if record is None:

            db.commit()

            verification_service.reject_invalid_code()

        consumed = (
            verification_service.consume_verification(
                db,
                record["id"],
            )
        )

        if not consumed:
            verification_service.reject_invalid_code()

        result = _create_login(
            db,
            user=user,
            user_agent=user_agent,
            ip=ip,
            now=utc_db_now(),
        )

    return result


# ==================== Refresh Token 轮换 ====================


def rotate_refresh_token(
    db: Session,
    *,
    refresh_token: str,
    ip: str,
) -> TokenPair:

    payload = decode_refresh_token(refresh_token)

    if payload is None:
        reject_auth(
            "REFRESH_INVALID",
            "Refresh Token 无效或已过期",
        )

    user_id = int(payload["sub"])
    family_id = payload["family_id"]

    token_hash = hash_refresh_token(
        refresh_token,
    )

    with db.begin():

        # 统一加锁顺序：
        # 用户 -> Session -> Refresh Token

        user = user_repository.find_by_id(
            db,
            user_id=user_id,
            for_update=True,
        )

        if user is None:
            reject_auth(
                "REFRESH_INVALID",
                "登录用户不存在",
            )

        if not user["is_active"]:
            reject_auth(
                "ACCOUNT_DISABLED",
                "账号已被禁用",
                status_code=403,
            )

        session = session_repository.find_session(
            db,
            user_id=user_id,
            family_id=family_id,
            for_update=True,
        )

        record = token_repository.find_by_hash(
            db,
            token_hash=token_hash,
            for_update=True,
        )

        now = utc_db_now()

        session = session_service.require_active_session(
            session,
            now,
        )

        if (
            record is None
            or record["user_id"] != user_id
            or record["family_id"] != family_id
        ):
            reject_auth(
                "REFRESH_INVALID",
                "Refresh Token 不存在",
            )

        # ==================== 重放检测 ====================

        if record["replaced_by"] is not None:

            session_service.revoke_session(
                db,
                user_id=user_id,
                family_id=family_id,
                now=now,
                reason="REFRESH_REPLAY",
            )

            auth_event_repository.insert_event(
                db,
                event_type="REFRESH_REPLAY",
                user_id=user_id,
                family_id=family_id,
                ip=ip,
                now=now,
            )

            # 必须先提交撤销，再返回异常。
            db.commit()

            reject_auth(
                "SESSION_REVOKED",
                "登录会话存在异常，请重新登录",
            )

        if (
            record["revoked_at"] is not None
            or record["expires_at"] <= now
        ):
            reject_auth(
                "REFRESH_INVALID",
                "Refresh Token 无效或已过期",
            )

        # ==================== 正常轮换 ====================

        pair, expires_at = _build_token_pair(
            user_id=user_id,
            family_id=family_id,
            absolute_expires_at=(
                session["absolute_expires_at"]
            ),
        )

        new_hash = hash_refresh_token(
            pair.refresh_token,
        )

        affected = token_repository.mark_rotated(
            db,
            token_id=record["id"],
            new_token_hash=new_hash,
            now=now,
        )

        if affected != 1:
            reject_auth(
                "REFRESH_INVALID",
                "Refresh Token 轮换失败",
            )

        token_repository.insert_token(
            db,
            user_id=user_id,
            family_id=family_id,
            token_hash=new_hash,
            expires_at=expires_at,
            now=now,
        )

    return pair


# ==================== 退出当前会话 ====================


def revoke_current_session(
    db: Session,
    *,
    refresh_token: str | None,
    ip: str,
) -> None:

    if not refresh_token:
        return

    payload = decode_refresh_token(
        refresh_token,
    )

    if payload is None:
        return

    user_id = int(payload["sub"])
    family_id = payload["family_id"]

    with db.begin():

        user = user_repository.find_by_id(
            db,
            user_id=user_id,
            for_update=True,
        )

        if user is None:
            return

        session = session_repository.find_session(
            db,
            user_id=user_id,
            family_id=family_id,
            for_update=True,
        )

        if session is None:
            return

        record = token_repository.find_by_hash(
            db,
            token_hash=hash_refresh_token(
                refresh_token,
            ),
            for_update=True,
        )

        if (
            record is None
            or record["user_id"] != user_id
            or record["family_id"] != family_id
        ):
            return

        if session["revoked_at"] is not None:
            return

        now = utc_db_now()

        session_service.revoke_session(
            db,
            user_id=user_id,
            family_id=family_id,
            now=now,
            reason="LOGOUT",
        )

        auth_event_repository.insert_event(
            db,
            event_type="LOGOUT",
            user_id=user_id,
            family_id=family_id,
            ip=ip,
            now=now,
        )