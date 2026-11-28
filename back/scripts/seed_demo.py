"""隔离演示库演示数据入口（答辩预演 / 隔离验证）。

安全约束：
- 仅允许写入 ssp_v3_demo / ssp_v3_release_rehearsal，正式库由
  init_production_demo.py 专用入口负责，本脚本一律拒绝。
- 不调用真实 AI 模型、不发送邮件、不使用真实个人信息。
- 特殊账号（admin / REED）密码只从环境变量或本地交互输入读取，
  不写入脚本、日志、清单或 Git。
- 生成数据全部带标记（demo_ 用户名、[DEMO] 审计原因），并写入
  Seed Manifest，可按清单与标记定向清理。

用法：
    set DB_NAME=ssp_v3_demo
    set SSP_ADMIN_PASSWORD=...        # 首次创建 admin 时必需
    set SSP_REED_PASSWORD=...         # 首次创建 REED 时必需
    set SSP_SEED_DEMO_PASSWORD=...    # 可选，模拟用户统一密码
    python scripts/seed_demo.py --reset
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
    SPECIALS,
    SeedError,
    initialize,
)


def _special_passwords(prompt: bool) -> dict[str, str | None]:
    """读取特殊账号密码：环境变量优先，可选本地交互输入。"""
    values: dict[str, str | None] = {}
    for key, spec in SPECIALS.items():
        value = os.environ.get(spec["password_env"])
        if not value and prompt and sys.stdin.isatty():
            value = getpass.getpass(f"{key} 密码（输入不回显）: ") or None
        values[key] = value
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description="生成隔离演示库演示数据")
    parser.add_argument("--reset", action="store_true", help="先清理已有演示数据再重建")
    parser.add_argument(
        "--rotate-special-passwords",
        action="store_true",
        help="显式重置特殊账号密码（需提供对应环境变量或交互输入）",
    )
    parser.add_argument(
        "--prompt-passwords",
        action="store_true",
        help="缺少环境变量时允许本地交互输入特殊账号密码",
    )
    parser.add_argument("--batch-id", default=None, help="覆盖批次标识")
    args = parser.parse_args()

    batch_id = args.batch_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") \
        + "-" + uuid.uuid4().hex[:6]
    demo_password = os.environ.get("SSP_SEED_DEMO_PASSWORD", "DemoPass123")

    with engine.begin() as conn:
        database = conn.execute(text("SELECT DATABASE()")).scalar_one()
        if database not in ISOLATED_DATABASES:
            raise SystemExit(
                f"拒绝执行：当前数据库 {database!r} 不在隔离演示库白名单 "
                f"{sorted(ISOLATED_DATABASES)}；正式库请使用 "
                "scripts/init_production_demo.py"
            )

        manifest, summary = initialize(
            conn,
            database=database,
            mode="isolated",
            batch_id=batch_id,
            demo_password=demo_password,
            special_passwords=_special_passwords(args.prompt_passwords),
            rotate_special_passwords=args.rotate_special_passwords,
            reset_demo=args.reset,
        )

    manifest_path = manifest.write()
    output = {
        **summary,
        "manifest": str(manifest_path),
        "demo_user_count": summary.pop("demo_users"),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SeedError as exc:
        raise SystemExit(f"演示数据生成失败：{exc}")