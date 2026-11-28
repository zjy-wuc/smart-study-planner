"""在隔离环境初始化首个管理员账号（A7.1）。

设计约束：
1. 复用现有注册流程（auth_service.register）：密码策略、PBKDF2 哈希、
   注册事件记录均由业务代码负责，不绕过任何安全机制。
2. 本脚本只负责两件事：
   - 在 mail 未启用的隔离环境中生成一条 REGISTER 验证码记录（不发送邮件）；
   - 注册成功后通过受控 SQL 将 role 置为 ADMIN。
3. 密码只从环境变量或标准输入读取，禁止命令行明文传参，
   禁止打印密码/哈希等敏感信息。
4. 数据库安全守卫：默认仅允许隔离库；正式库必须显式双重确认。

用法：
    set SSP_ADMIN_PASSWORD=...        (或使用 --password-stdin)
    python scripts/bootstrap_admin.py --username admin --email admin@example.com

仅用于迁移预演库 / 演示库，正式环境初始化需单独授权。
"""

import argparse
import getpass
import json
import os
import sys
from datetime import timedelta

from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings  # noqa: E402
from app.core.clock import utc_db_now  # noqa: E402
from app.core.security import (  # noqa: E402
    generate_email_code,
    hash_email_code,
)
from app.database import SessionLocal, engine  # noqa: E402
from app.repositories.auth import verification_repository  # noqa: E402
from app.schemas.auth import EmailCodePurpose  # noqa: E402
from app.schemas.user import UserCreate  # noqa: E402
from app.services.auth import auth_service  # noqa: E402

ALLOWED_DATABASES = frozenset(
    {"ssp_v3_release_rehearsal", "ssp_v3_demo"}
)
PRODUCTION_DATABASES = frozenset({"smart_study_planner"})
BOOTSTRAP_IP = "127.0.0.1"
BOOTSTRAP_UA = "bootstrap-admin-a71"


def _current_database() -> str:
    with engine.connect() as conn:
        return conn.execute(text("SELECT DATABASE()")).scalar_one()


def _guard(database: str, allow_production: bool) -> None:
    if database in ALLOWED_DATABASES:
        return
    if database in PRODUCTION_DATABASES and allow_production:
        if os.environ.get("SSP_CONFIRM_PRODUCTION_BOOTSTRAP") != "YES":
            raise SystemExit(
                "拒绝执行：正式库初始化需要同时设置 "
                "SSP_CONFIRM_PRODUCTION_BOOTSTRAP=YES"
            )
        return
    raise SystemExit(
        f"拒绝执行：当前数据库 {database!r} 不在允许清单 "
        f"{sorted(ALLOWED_DATABASES)}。正式库需 --allow-production 并双重确认。"
    )


def _read_password(use_stdin: bool) -> str:
    if use_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
    elif os.environ.get("SSP_ADMIN_PASSWORD"):
        password = os.environ["SSP_ADMIN_PASSWORD"]
    else:
        password = getpass.getpass("管理员密码（输入不回显）: ")
    if not password:
        raise SystemExit("拒绝执行：密码为空")
    return password


def _issue_register_code(db, email: str) -> str:
    now = utc_db_now()
    code = generate_email_code()
    code_hash = hash_email_code(
        email=email,
        purpose=EmailCodePurpose.REGISTER.value,
        code=code,
    )
    verification_id = verification_repository.insert_verification(
        db,
        email=email,
        purpose=EmailCodePurpose.REGISTER.value,
        code_hash=code_hash,
        request_ip=BOOTSTRAP_IP,
        now=now,
        expires_at=now + timedelta(minutes=settings.EMAIL_CODE_EXPIRE_MINUTES),
    )
    # 本地隔离环境不发送邮件，直接标记为已投递，供注册流程正常校验
    db.execute(
        text(
            "UPDATE email_verifications SET send_status='SENT' "
            "WHERE id=:i"
        ),
        {"i": verification_id},
    )
    db.commit()
    return code


def main() -> int:
    parser = argparse.ArgumentParser(description="初始化隔离环境首个管理员")
    parser.add_argument("--username", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--nickname", default="管理员")
    parser.add_argument("--password-stdin", action="store_true")
    parser.add_argument("--allow-production", action="store_true")
    args = parser.parse_args()

    database = _current_database()
    _guard(database, args.allow_production)

    password = _read_password(args.password_stdin)

    with SessionLocal() as db:
        from app.schemas.user import normalize_email

        email = normalize_email(args.email)
        exists = db.execute(
            text(
                "SELECT id FROM users WHERE username=:u OR email=:e LIMIT 1"
            ),
            {"u": args.username, "e": email},
        ).scalar_one_or_none()
        if exists is not None:
            raise SystemExit("拒绝执行：用户名或邮箱已存在，不覆盖既有账号")

        # 复用现有注册流程所需的验证码记录（本地不发送邮件）
        code = _issue_register_code(db, email)
        data = UserCreate(
            username=args.username,
            email=email,
            password=password,
            code=code,
            nickname=args.nickname,
        )
        del password

        pair, user = auth_service.register(
            db,
            data=data,
            ip=BOOTSTRAP_IP,
            user_agent=BOOTSTRAP_UA,
        )
        del pair

        db.execute(
            text("UPDATE users SET role='ADMIN' WHERE id=:i"),
            {"i": user["id"]},
        )
        db.commit()

        role = db.execute(
            text("SELECT role FROM users WHERE id=:i"), {"i": user["id"]}
        ).scalar_one()

    print(
        json.dumps(
            {
                "database": database,
                "user_id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "role": role,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())