"""正式库演示数据初始化专用入口。

与 seed_demo.py 的区别：
- 只允许 smart_study_planner（正式库），或显式 --rehearsal 时允许隔离库。
- 必须同时满足 --allow-production 与
  SSP_CONFIRM_PRODUCTION_INIT=YES，作为开发者明确授权。
- 初始化前校验库名、19 张表及关键字段。
- 拒绝覆盖已存在的特殊账号密码（默认只补齐资料，不重置密码）。
- 正式模式禁止 --reset，存在真实用户时拒绝执行，不删除既有业务数据。
- 使用 MySQL 命名锁防止并发初始化；初始化完成后执行一致性校验。
- 密码只从环境变量或本地交互输入读取，不写入脚本、日志或清单。

初始化期间应停止网站服务（暂停注册与业务写入），校验通过后再开放。

用法：
    set DB_NAME=smart_study_planner
    set SSP_ADMIN_PASSWORD=...
    set SSP_REED_PASSWORD=...
    set SSP_CONFIRM_PRODUCTION_INIT=YES
    python scripts/init_production_demo.py --allow-production

隔离库演练：
    set DB_NAME=ssp_v3_demo
    python scripts/init_production_demo.py --rehearsal --reset
"""

import argparse
import getpass
import json
import os
import sys
import uuid
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "scripts"))

from sqlalchemy import text  # noqa: E402

from app.database import engine  # noqa: E402
from demo_seed.generator import (  # noqa: E402
    ISOLATED_DATABASES,
    PRODUCTION_DATABASE,
    SPECIALS,
    SeedError,
    initialize,
    validate_schema,
)

CONFIRM_ENV = "SSP_CONFIRM_PRODUCTION_INIT"
LOCK_NAME = "ssp_v3_production_init"


def _special_passwords(prompt: bool) -> dict[str, str | None]:
    values: dict[str, str | None] = {}
    for key, spec in SPECIALS.items():
        value = os.environ.get(spec["password_env"])
        if not value and prompt and sys.stdin.isatty():
            value = getpass.getpass(f"{key} 密码（输入不回显）: ") or None
        values[key] = value
    return values


def _guard(conn, *, production: bool, rehearsal: bool) -> str:
    database = conn.execute(text("SELECT DATABASE()")).scalar_one()
    if production:
        if database != PRODUCTION_DATABASE:
            raise SystemExit(
                f"正式初始化要求数据库为 {PRODUCTION_DATABASE}，当前为 {database!r}"
            )
        return database
    if rehearsal:
        if database not in ISOLATED_DATABASES:
            raise SystemExit(
                f"演练模式仅允许隔离库 {sorted(ISOLATED_DATABASES)}，当前 {database!r}"
            )
        return database
    raise SystemExit(
        "必须指定运行模式：正式库使用 --allow-production，"
        "隔离库演练使用 --rehearsal"
    )


def _acquire_lock(conn) -> bool:
    return int(conn.execute(text("SELECT GET_LOCK(:n, 5)"), {"n": LOCK_NAME}).scalar_one()) == 1


def _release_lock(conn) -> None:
    conn.execute(text("SELECT RELEASE_LOCK(:n)"), {"n": LOCK_NAME})


def _existing_state(conn) -> dict:
    return {
        "users": int(conn.execute(text("SELECT COUNT(*) FROM users")).scalar_one()),
        "real_users": int(
            conn.execute(
                text(
                    "SELECT COUNT(*) FROM users "
                    "WHERE username NOT IN ('admin', 'REED')"
                )
            ).scalar_one()
        ),
        "demo_users": int(
            conn.execute(
                text("SELECT COUNT(*) FROM users WHERE username REGEXP '^demo_[0-9]+$'")
            ).scalar_one()
        ),
        "special_accounts": [
            dict(row)
            for row in conn.execute(
                text(
                    "SELECT username, email, role, is_active FROM users "
                    "WHERE username IN ('admin', 'REED') ORDER BY username"
                )
            )
            .mappings()
            .all()
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="正式库演示数据初始化专用入口")
    parser.add_argument("--allow-production", action="store_true", help="授权写入正式库")
    parser.add_argument("--rehearsal", action="store_true", help="在隔离库演练同一流程")
    parser.add_argument("--reset", action="store_true", help="仅演练模式可用：重建演示数据")
    parser.add_argument(
        "--check", action="store_true", help="只校验环境与表结构，不写入数据"
    )
    parser.add_argument(
        "--rotate-special-passwords",
        action="store_true",
        help="显式重置特殊账号密码（正式上线前应使用独立安全密码）",
    )
    parser.add_argument("--batch-id", default=None)
    args = parser.parse_args()

    production = args.allow_production and not args.rehearsal
    if args.allow_production and args.rehearsal:
        raise SystemExit("--allow-production 与 --rehearsal 不能同时使用")
    if production:
        if os.environ.get(CONFIRM_ENV) != "YES":
            raise SystemExit(
                f"缺少开发者授权：请设置环境变量 {CONFIRM_ENV}=YES 后再执行"
            )
    if args.reset and production:
        raise SystemExit("正式模式禁止 --reset：不得删除既有业务数据")

    batch_id = args.batch_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") \
        + "-" + uuid.uuid4().hex[:6]

    lock_conn = engine.connect()
    try:
        if not _acquire_lock(lock_conn):
            raise SystemExit("未能获取初始化锁，可能有另一个初始化进程正在运行")
        lock_conn.commit()

        with engine.connect() as conn:
            database = _guard(conn, production=production, rehearsal=args.rehearsal)
            validate_schema(conn)
            state = _existing_state(conn)

        if args.check:
            print(
                json.dumps(
                    {
                        "mode": "check",
                        "database": database,
                        "schema": "ok",
                        "existing": state,
                        "ready": state["real_users"] == 0 and state["demo_users"] == 0,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        with engine.begin() as conn:
            manifest, summary = initialize(
                conn,
                database=database,
                mode="production" if production else "isolated",
                batch_id=batch_id,
                demo_password=os.environ.get("SSP_SEED_DEMO_PASSWORD", "DemoPass123"),
                special_passwords=_special_passwords(prompt=True),
                rotate_special_passwords=args.rotate_special_passwords,
                reset_demo=args.reset,
            )

        manifest_path = manifest.write()
        summary["manifest"] = str(manifest_path)
        summary["authorization"] = (
            "production" if production else "rehearsal"
        )
        summary["next"] = (
            "一致性校验已通过，可开放网站；统计展示时须说明包含预置演示数据"
            if production
            else "演练完成，未触碰正式库"
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
        return 0
    finally:
        try:
            _release_lock(lock_conn)
            lock_conn.commit()
        except Exception:
            pass
        lock_conn.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SeedError as exc:
        raise SystemExit(f"初始化失败：{exc}")