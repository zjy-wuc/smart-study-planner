from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.core.clock import utc_db_now

from app.core.security import (
    generate_email_code,
    hash_email_code,
    verify_email_code,
)

from app.schemas.auth import EmailCodePurpose
from app.schemas.user import normalize_email

from app.repositories.auth import (
    user_repository,
    session_repository,
    verification_repository,
)

from app.services.auth import (
    mail_service,
    rate_limit_service,
)


CHANGE_EMAIL_PURPOSES = {
    EmailCodePurpose.CHANGE_EMAIL_OLD,
    EmailCodePurpose.CHANGE_EMAIL_NEW,
}


# ==================== 统一业务异常 ====================


def _reject_authentication() -> None:

    raise HTTPException(
        status_code=401,
        detail={
            "code": "INVALID_TOKEN",
            "message": "当前登录状态无效",
        },
    )


def _reject_invalid_email() -> None:

    raise HTTPException(
        status_code=400,
        detail={
            "code": "INVALID_EMAIL",
            "message": "邮箱不符合当前操作要求",
        },
    )


# ==================== 发码身份检查 ====================


def _resolve_target(
    db: Session,
    *,
    email: str,
    purpose: EmailCodePurpose,
    current_user_id: int | None,
    current_family_id: str | None,
) -> tuple[str, bool, int | None, str | None]:
    """
    返回：
    实际目标邮箱、
    是否允许真实发送、
    绑定用户 ID、
    绑定会话 ID。
    """

    # ==================== 邮箱换绑 ====================

    if purpose in CHANGE_EMAIL_PURPOSES:

        if (
            current_user_id is None
            or current_family_id is None
        ):
            _reject_authentication()

        session = (
            session_repository.find_session_with_user(
                db,
                user_id=current_user_id,
                family_id=current_family_id,
            )
        )

        if session is None:
            _reject_authentication()

        now = utc_db_now()

        idle_cutoff = now - timedelta(
            days=settings.SESSION_IDLE_EXPIRE_DAYS,
        )

        if (
            not session["is_active"]
            or session["revoked_at"] is not None
            or session["absolute_expires_at"] <= now
            or session["last_activity_at"] <= idle_cutoff
        ):
            _reject_authentication()

        current_email = session["email"]

        # 验证旧邮箱
        if purpose == EmailCodePurpose.CHANGE_EMAIL_OLD:

            if email != current_email:
                _reject_invalid_email()

            return (
                current_email,
                True,
                current_user_id,
                current_family_id,
            )

        # 验证新邮箱
        if email == current_email:
            _reject_invalid_email()

        existing_user = user_repository.find_by_email(
            db,
            email,
        )

        if existing_user is not None:

            return (
                existing_user["email"],
                False,
                current_user_id,
                current_family_id,
            )

        return (
            email,
            True,
            current_user_id,
            current_family_id,
        )

    # ==================== 公开验证码用途 ====================

    user = user_repository.find_by_email(
        db,
        email,
    )

    if user is not None:
        email = user["email"]

    # 注册
    if purpose == EmailCodePurpose.REGISTER:

        return (
            email,
            user is None,
            None,
            None,
        )

    # 验证码登录 / 忘记密码
    if user is None:

        return (
            email,
            False,
            None,
            None,
        )

    return (
        email,
        bool(user["is_active"]),
        user["id"],
        None,
    )


# ==================== 请求发送验证码 ====================


def request_email_code(
    *,
    email: str,
    purpose: EmailCodePurpose,
    request_ip: str,
    current_user_id: int | None = None,
    current_family_id: str | None = None,
) -> None:

    email = normalize_email(email)
    purpose = EmailCodePurpose(purpose)

    request_ip = rate_limit_service.normalize_ip(
        request_ip,
    )

    if not mail_service.mail_ready():

        raise HTTPException(
            status_code=503,
            detail={
                "code": "MAIL_UNAVAILABLE",
                "message": "邮件服务暂不可用",
            },
        )

    # ==================== 第一阶段 ====================
    # 加锁、检查额度、创建 PENDING 记录

    with rate_limit_service.admission_session(
        "mail-quota"
    ) as db:

        (
            email,
            eligible,
            bound_user_id,
            bound_family_id,
        ) = _resolve_target(
            db,
            email=email,
            purpose=purpose,
            current_user_id=current_user_id,
            current_family_id=current_family_id,
        )

        now = utc_db_now()

        rate_limit_service.check_email_quota(
            db,
            email=email,
            ip=request_ip,
            now=now,
        )

        code = generate_email_code()

        code_hash = hash_email_code(
            email=email,
            purpose=purpose.value,
            code=code,
        )

        verification_repository.invalidate_previous(
            db,
            email=email,
            purpose=purpose.value,
            now=now,
            user_id=bound_user_id,
            family_id=bound_family_id,
        )

        verification_id = (
            verification_repository.insert_verification(
                db,
                email=email,
                purpose=purpose.value,
                code_hash=code_hash,
                request_ip=request_ip,
                now=now,
                expires_at=now + timedelta(
                    minutes=(
                        settings.EMAIL_CODE_EXPIRE_MINUTES
                    ),
                ),
                user_id=bound_user_id,
                family_id=bound_family_id,
            )
        )

        db.commit()

    # ==================== 第二阶段 ====================
    # 已释放数据库命名锁，调用邮件服务

    sent = False

    try:
        if eligible:

            sent = mail_service.send_verification_code(
                email=email,
                code=code,
                purpose=purpose,
            )

    finally:

        # ==================== 第三阶段 ====================
        # 使用独立事务记录发送结果

        with SessionLocal() as db:

            affected = (
                verification_repository.mark_send_result(
                    db,
                    verification_id=verification_id,
                    sent=sent,
                )
            )

            if affected != 1:

                raise RuntimeError(
                    "验证码发送状态更新失败"
                )

            db.commit()


# ==================== 校验验证码 ====================


def check_verification(
    db: Session,
    *,
    email: str,
    purpose: EmailCodePurpose,
    code: str,
    user_id: int | None = None,
    family_id: str | None = None,
) -> dict | None:
    """
    锁定并验证最新验证码。

    正确：返回验证码记录。
    错误：必要时增加失败次数并返回 None。

    本函数不消费验证码，也不提交事务。
    """

    purpose = EmailCodePurpose(purpose)
    email = normalize_email(email)

    # 检查调用参数中的绑定关系
    if purpose in CHANGE_EMAIL_PURPOSES:

        if user_id is None or family_id is None:
            raise ValueError("换绑验证码必须绑定用户和会话")

    elif family_id is not None:
        raise ValueError("当前验证码用途不绑定会话")

    if purpose in {
        EmailCodePurpose.LOGIN,
        EmailCodePurpose.RESET_PASSWORD,
    }:

        if user_id is None:
            raise ValueError("当前验证码用途必须绑定用户")

    if (
        purpose == EmailCodePurpose.REGISTER
        and user_id is not None
    ):
        raise ValueError("注册验证码不能绑定已有用户")

    record = (
        verification_repository.find_latest_verification(
            db,
            email=email,
            purpose=purpose.value,
            for_update=True,
            user_id=user_id,
            family_id=family_id,
        )
    )

    if record is None:
        return None

    # 在获取行锁之后读取当前时间
    now = utc_db_now()

    # 验证码必须处于有效状态
    if (
        record["send_status"] != "SENT"
        or record["consumed_at"] is not None
        or record["invalidated_at"] is not None
        or record["expires_at"] <= now
        or record["attempts"]
        >= settings.EMAIL_CODE_MAX_ATTEMPTS
    ):
        return None

    # 校验账号绑定
    if record["user_id"] != user_id:
        return None

    # 校验会话绑定
    if record["family_id"] != family_id:
        return None

    correct = verify_email_code(
        email=record["email"],
        purpose=purpose.value,
        code=code,
        stored_hash=record["code_hash"],
    )

    if not correct:

        verification_repository.increment_attempts(
            db,
            verification_id=record["id"],
            now=now,
            max_attempts=(
                settings.EMAIL_CODE_MAX_ATTEMPTS
            ),
        )

        return None

    return record


# ==================== 消费验证码 ====================


def consume_verification(
    db: Session,
    verification_id: int,
) -> bool:
    """
    消费已经通过 check_verification 的验证码。

    必须在同一个事务、同一个 Session 中调用。
    """

    affected = (
        verification_repository.consume_verification(
            db,
            verification_id=verification_id,
            now=utc_db_now(),
            max_attempts=(
                settings.EMAIL_CODE_MAX_ATTEMPTS
            ),
        )
    )

    return affected == 1


def reject_invalid_code() -> None:

    raise HTTPException(
        status_code=400,
        detail={
            "code": "EMAIL_CODE_INVALID",
            "message": "验证码错误、已过期或不可使用",
        },
    )