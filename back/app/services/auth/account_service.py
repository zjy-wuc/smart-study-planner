from datetime import timedelta
'''处理密码、邮箱和设备管理等敏感操作'''
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.core.clock import utc_db_now

from app.core.security import (
    hash_password,
    verify_password,
)

from app.schemas.auth import (
    EmailCodePurpose,
    PasswordResetRequest,
    PasswordChangeRequest,
    EmailChangeRequest,
)

from app.repositories.auth import (
    user_repository,
    session_repository,
    auth_event_repository,
)

from app.services.auth import (
    auth_service,
    session_service,
    verification_service,
    rate_limit_service,
)


reject_auth = session_service.reject_auth


# 密码确认 


def _require_password(
    db: Session,
    *,
    user: dict,
    password: str,
    ip: str,
) -> None:
    """
    验证敏感操作所需的当前密码。

    调用前必须持有 users 行锁。
    """

    now = utc_db_now()

    if rate_limit_service.is_password_locked(
        db,
        user["id"],
        now,
    ):
        rate_limit_service.reject_rate_limit(
            "密码尝试次数过多，请稍后重试",
        )

    if not verify_password(
        password,
        user["password_hash"],
    ):

        rate_limit_service.record_password_failure(
            db,
            user_id=user["id"],
            identifier=user["username"],
            ip=ip,
            now=utc_db_now(),
        )

        # 调用本函数前不得进行其他业务写入。
        # 持久化密码失败次数。
        db.commit()

        reject_auth(
            "INVALID_PASSWORD",
            "当前密码错误",
        )


def _record_event(
    db: Session,
    *,
    event_type: str,
    user_id: int,
    ip: str,
    family_id: str | None = None,
) -> None:

    auth_event_repository.insert_event(
        db,
        event_type=event_type,
        user_id=user_id,
        family_id=family_id,
        ip=ip,
        now=utc_db_now(),
    )


# 忘记密码 


def reset_password(
    db: Session,
    *,
    data: PasswordResetRequest,
    ip: str,
) -> int:

    rate_limit_service.reserve_email_code_attempt(ip)

    auth_service.validate_new_password(
        data.new_password,
    )

    with db.begin():

        # 1. 锁定邮箱对应的用户
        user = user_repository.find_by_email(
            db,
            email=data.email,
            for_update=True,
        )

        if user is None or not user["is_active"]:
            verification_service.reject_invalid_code()

        user_id = user["id"]

        # 2. 校验 RESET_PASSWORD 验证码
        record = (
            verification_service.check_verification(
                db,
                email=user["email"],
                purpose=EmailCodePurpose.RESET_PASSWORD,
                code=data.code,
                user_id=user_id,
                valid_after=max(
    user["password_updated_at"],
    user["email_verified_at"],
),
            )
        )

        if record is None:

            db.commit()

            verification_service.reject_invalid_code()

        # 3. 更新密码
        password_hash = hash_password(
            data.new_password,
        )

        now = utc_db_now()

        user_repository.update_password(
            db,
            user_id=user_id,
            password_hash=password_hash,
            now=now,
        )

        # 4. 撤销全部会话
        session_service.revoke_user_sessions(
            db,
            user_id=user_id,
            now=now,
            reason="PASSWORD_RESET",
        )

        # 5. 消费验证码
        consumed = (
            verification_service.consume_verification(
                db,
                record["id"],
            )
        )

        if not consumed:
            verification_service.reject_invalid_code()

        # 6. 清除密码失败限制
        rate_limit_service.clear_password_failures(
            db,
            user_id=user_id,
            now=now,
        )

        # 7. 记录安全事件
        _record_event(
            db,
            event_type="PASSWORD_RESET",
            user_id=user_id,
            ip=ip,
        )

    return user_id


# 主动修改密码 


def change_password(
    db: Session,
    *,
    user_id: int,
    family_id: str,
    data: PasswordChangeRequest,
    ip: str,
) -> None:

    rate_limit_service.reserve_password_attempt(ip)

    auth_service.validate_new_password(
        data.new_password,
    )

    with db.begin():

        # 1. 锁定用户及当前会话
        user, session = (
            session_service.lock_current_user(
                db,
                user_id=user_id,
                family_id=family_id,
            )
        )

        # 2. 验证旧密码
        _require_password(
            db,
            user=user,
            password=data.old_password,
            ip=ip,
        )

        # 3. 更新密码
        password_hash = hash_password(
            data.new_password,
        )

        now = utc_db_now()

        user_repository.update_password(
            db,
            user_id=user_id,
            password_hash=password_hash,
            now=now,
        )

        # 4. 保留当前会话，撤销其他会话
        session_service.revoke_user_sessions(
            db,
            user_id=user_id,
            now=now,
            reason="PASSWORD_CHANGE",
            exclude_family_id=family_id,
        )

        # 5. 重置密码失败计数
        rate_limit_service.clear_password_failures(
            db,
            user_id=user_id,
            now=now,
        )

        # 6. 记录事件
        _record_event(
            db,
            event_type="PASSWORD_CHANGE",
            user_id=user_id,
            family_id=family_id,
            ip=ip,
        )


#  邮箱换绑 

def change_email(
    db: Session,
    *,
    user_id: int,
    family_id: str,
    data: EmailChangeRequest,
    ip: str,
) -> dict:

    # 两种准入限制都需要通过。
    # 在业务事务及用户行锁之前完成。
    rate_limit_service.reserve_password_attempt(ip)
    rate_limit_service.reserve_email_code_attempt(ip)

    try:
        with db.begin():

            # 1. 重新锁定用户及当前会话
            user, session = (
                session_service.lock_current_user(
                    db,
                    user_id=user_id,
                    family_id=family_id,
                )
            )

            # 2. 验证当前密码
            _require_password(
                db,
                user=user,
                password=data.password,
                ip=ip,
            )

            old_email = user["email"]
            new_email = data.new_email

            # 3. 检查新邮箱
            if new_email == old_email:

                reject_auth(
                    "EMAIL_UNAVAILABLE",
                    "新邮箱不能与原邮箱相同",
                    status_code=409,
                )

            existing_user = user_repository.find_by_email(
                db,
                email=new_email,
            )

            if existing_user is not None:

                reject_auth(
                    "EMAIL_UNAVAILABLE",
                    "新邮箱不可用",
                    status_code=409,
                )

            # 4. 校验旧邮箱验证码
            old_record = (
                verification_service.check_verification(
                    db,
                    email=old_email,
                    purpose=(
                        EmailCodePurpose.CHANGE_EMAIL_OLD
                    ),
                    code=data.old_email_code,
                    user_id=user_id,
                    family_id=family_id,
                    valid_after=max(
    user["password_updated_at"],
    user["email_verified_at"],
),
                )
            )

            if old_record is None:

                db.commit()

                verification_service.reject_invalid_code()

            # 5. 校验新邮箱验证码
            new_record = (
                verification_service.check_verification(
                    db,
                    email=new_email,
                    purpose=(
                        EmailCodePurpose.CHANGE_EMAIL_NEW
                    ),
                    code=data.new_email_code,
                    user_id=user_id,
                    family_id=family_id,
                    valid_after=max(
    user["password_updated_at"],
    user["email_verified_at"],
),
                )
            )

            if new_record is None:

                # 旧验证码仅通过校验，尚未消费。
                db.commit()

                verification_service.reject_invalid_code()

            # 6. 两个验证码均正确后才更新邮箱
            now = utc_db_now()

            user_repository.update_email(
                db,
                user_id=user_id,
                email=new_email,
                now=now,
            )

            # 7. 保留当前会话
            session_service.revoke_user_sessions(
                db,
                user_id=user_id,
                now=now,
                reason="EMAIL_CHANGE",
                exclude_family_id=family_id,
            )

            # 8. 消费两个验证码
            old_consumed = (
                verification_service.consume_verification(
                    db,
                    old_record["id"],
                )
            )

            new_consumed = (
                verification_service.consume_verification(
                    db,
                    new_record["id"],
                )
            )

            if not old_consumed or not new_consumed:
                verification_service.reject_invalid_code()

            # 9. 重置密码失败计数
            rate_limit_service.clear_password_failures(
                db,
                user_id=user_id,
                now=now,
            )

            # 10. 记录安全事件
            _record_event(
                db,
                event_type="EMAIL_CHANGE",
                user_id=user_id,
                family_id=family_id,
                ip=ip,
            )

            # 11. 返回更新后的用户资料
            updated_user = dict(user)

            updated_user["email"] = new_email
            updated_user["email_verified_at"] = now

            result = auth_service.public_user(
                updated_user,
            )

        return result

    except IntegrityError as exc:

        args = exc.orig.args

        if (
            args
            and args[0] == 1062
            and "uk_users_email" in str(exc.orig)
        ):
            reject_auth(
                "EMAIL_UNAVAILABLE",
                "新邮箱不可用",
                status_code=409,
            )

        raise


# 撤销指定其他会话 


def revoke_other_session(
    db: Session,
    *,
    user_id: int,
    current_family_id: str,
    target_family_id: str,
    password: str,
    ip: str,
) -> None:

    rate_limit_service.reserve_password_attempt(ip)

    if target_family_id == current_family_id:

        reject_auth(
            "INVALID_SESSION_TARGET",
            "请使用当前会话退出接口",
            status_code=400,
        )

    with db.begin():

        # 1. 锁定用户及当前会话
        user, current_session = (
            session_service.lock_current_user(
                db,
                user_id=user_id,
                family_id=current_family_id,
            )
        )

        # 2. 验证当前密码
        _require_password(
            db,
            user=user,
            password=password,
            ip=ip,
        )

        # 3. 查询并锁定目标会话
        target = session_repository.find_session(
            db,
            user_id=user_id,
            family_id=target_family_id,
            for_update=True,
        )

        now = utc_db_now()

        idle_cutoff = now - timedelta(
            days=settings.SESSION_IDLE_EXPIRE_DAYS,
        )

        if (
            target is None
            or target["revoked_at"] is not None
            or target["absolute_expires_at"] <= now
            or target["last_activity_at"] <= idle_cutoff
        ):
            reject_auth(
                "SESSION_NOT_FOUND",
                "目标会话不存在或已失效",
                status_code=404,
            )

        # 4. 撤销目标会话及对应 Token
        session_service.revoke_session(
            db,
            user_id=user_id,
            family_id=target_family_id,
            now=now,
            reason="REMOTE_REVOKE",
        )

        rate_limit_service.clear_password_failures(
            db,
            user_id=user_id,
            now=now,
        )

        # 5. 记录被撤销的目标会话
        _record_event(
            db,
            event_type="REMOTE_REVOKE",
            user_id=user_id,
            family_id=target_family_id,
            ip=ip,
        )


#  退出其他设备或全部设备


def revoke_sessions(
    db: Session,
    *,
    user_id: int,
    current_family_id: str,
    password: str,
    ip: str,
    keep_current: bool,
) -> int:

    rate_limit_service.reserve_password_attempt(ip)

    with db.begin():

        user, current_session = (
            session_service.lock_current_user(
                db,
                user_id=user_id,
                family_id=current_family_id,
            )
        )

        _require_password(
            db,
            user=user,
            password=password,
            ip=ip,
        )

        now = utc_db_now()

        reason = (
            "LOGOUT_OTHERS"
            if keep_current
            else "LOGOUT_ALL"
        )

        affected = session_service.revoke_user_sessions(
            db,
            user_id=user_id,
            now=now,
            reason=reason,
            exclude_family_id=(
                current_family_id
                if keep_current
                else None
            ),
        )

        rate_limit_service.clear_password_failures(
            db,
            user_id=user_id,
            now=now,
        )

        _record_event(
            db,
            event_type=reason,
            user_id=user_id,
            family_id=current_family_id,
            ip=ip,
        )

    return affected