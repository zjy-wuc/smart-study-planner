"""演示数据生成核心。

入口脚本（seed_demo.py / init_production_demo.py）负责数据库守卫与授权，
本模块只负责在已通过校验的连接上生成数据、记录清单并做一致性校验。

安全约束：
- 不调用真实 AI 模型、不发送邮件。
- 密码只从调用方传入，不写入清单、日志或报告。
- 所有模拟 AI 请求都在历史日期，今日请求数为 0。
"""

import getpass
import json
import os
import random
import sys
import uuid
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import text

from app.core.clock import business_today
from app.core.security import hash_password

from .content import ALL_NOTES, NOTES_BY_KEY, build_practice_record, render_note
from .manifest import SeedManifest

DEMO_PREFIX = "demo_"
DEMO_TAG = "[DEMO]"
DEMO_USER_COUNT = 29
BANNED_DEMO_INDEXES = {28, 29}
DEMO_NOTE_USER_COUNT = 18
NOTES_PER_DEMO_USER = 4
RNG_SEED = 20261128

PRODUCTION_DATABASE = "smart_study_planner"
ISOLATED_DATABASES = frozenset({"ssp_v3_demo", "ssp_v3_release_rehearsal"})

REQUIRED_TABLES = frozenset(
    {
        "users",
        "auth_events",
        "email_verifications",
        "login_sessions",
        "refresh_tokens",
        "study_plans",
        "plan_steps",
        "daily_tasks",
        "schedule_entries",
        "task_rollovers",
        "study_records",
        "focus_sessions",
        "knowledge_notes",
        "knowledge_review_records",
        "practice_records",
        "ai_requests",
        "admin_audit_logs",
        "ai_runtime_config",
        "ai_guard_mutex",
    }
)

REQUIRED_COLUMNS = {
    "users": {"username", "password_hash", "email", "is_active", "role"},
    "study_plans": {"user_id", "status", "start_date", "end_date"},
    "plan_steps": {"plan_id", "parent_id", "node_type", "task_type"},
    "daily_tasks": {
        "plan_id",
        "step_id",
        "task_date",
        "task_type",
        "status",
        "numeric_active_date",
    },
    "study_records": {"task_id", "user_id", "event_type", "recorded_value"},
    "task_rollovers": {"source_task_id", "target_task_id", "quantity"},
    "knowledge_notes": {"user_id", "title", "content_md", "tags"},
    "knowledge_review_records": {"note_id", "user_id", "reviewed_at"},
    "practice_records": {
        "user_id",
        "note_id",
        "generation_id",
        "question_count",
        "score",
        "questions_json",
    },
    "focus_sessions": {"user_id", "status", "focused_seconds", "focus_date"},
    "ai_requests": {
        "request_id",
        "user_id",
        "operation",
        "request_date",
        "status",
        "leased_until",
    },
    "admin_audit_logs": {"admin_id", "action", "reason", "created_at"},
    "ai_runtime_config": {"enabled", "user_daily_limit", "global_daily_limit"},
}

SPECIALS = {
    "admin": {
        "username": "admin",
        "email": "467782984@qq.com",
        "nickname": "管理员",
        "role": "ADMIN",
        "password_env": "SSP_ADMIN_PASSWORD",
    },
    "REED": {
        "username": "REED",
        "email": "zhangjingyu448@gmail.com",
        "nickname": "REED",
        "role": "USER",
        "password_env": "SSP_REED_PASSWORD",
    },
}

ADMIN_NOTE_KEYS = [
    "ssp-01",
    "ssp-02",
    "ssp-03",
    "ssp-04",
    "ssp-05",
    "ssp-06",
    "py-09",
    "py-10",
    "fa-07",
    "my-07",
    "rd-06",
    "dsa-08",
]

REED_NOTE_KEYS = [
    "ssp-07",
    "ssp-08",
    "ssp-09",
    "ssp-10",
    "py-01",
    "py-02",
    "fa-01",
    "fa-02",
    "my-01",
    "rd-01",
    "java-01",
    "java-02",
    "dsa-01",
    "net-01",
    "os-01",
    "react-01",
]

EXPECTED_SPECIAL = {
    "admin": {
        "plans": 6,
        "steps": 30,
        "tasks": (90, 120),
        "records": 65,
        "notes": 12,
        "reviews": 20,
        "focus": 25,
        "practice": 8,
        "ai": 20,
        "rollovers": 5,
    },
    "REED": {
        "plans": 8,
        "steps": 45,
        "tasks": (135, 175),
        "records": 100,
        "notes": 16,
        "reviews": 30,
        "focus": 40,
        "practice": 12,
        "ai": 30,
        "rollovers": 8,
    },
}

ADMIN_PLANS = [
    ("Python 核心语法与工程实践", "Python", "ACTIVE", -30, 10, 10),
    ("FastAPI 接口与认证", "FastAPI", "ACTIVE", -20, 15, 6),
    ("MySQL 索引与事务", "MySQL", "ACTIVE", -14, 14, 6),
    ("Redis 缓存与并发", "Redis", "ACTIVE", -10, 20, 6),
    ("数据结构与算法刷题", "数据结构与算法", "ENDED", -40, -10, 5),
    ("Smart Study Planner 项目复盘", "Smart Study Planner 项目开发", "DRAFT", 1, 30, 0),
]

REED_PLANS = [
    ("Python 进阶与异步编程", "Python", "ACTIVE", -28, 12, 7),
    ("FastAPI 项目实战", "FastAPI", "ACTIVE", -24, 16, 6),
    ("MySQL 与 Redis 数据层", "MySQL", "ACTIVE", -20, 18, 6),
    ("Java 并发与 JVM", "Java", "ACTIVE", -18, 20, 5),
    ("算法与数据结构专项", "数据结构与算法", "ACTIVE", -14, 22, 6),
    ("计算机网络与操作系统", "计算机网络", "ENDED", -45, -12, 5),
    ("React 与 Next.js 前端", "React 与 Next.js", "ENDED", -35, -8, 5),
    ("高等数学与英语冲刺", "高等数学", "DRAFT", 1, 40, 0),
]

LEAF_NAMES = {
    "BOOLEAN": ["每日精读", "错题回顾", "概念复述"],
    "NUMERIC": ["专项练习", "代码实操", "题目训练"],
}

# 每个计划包含的叶子任务数：admin 6×3=18 叶 + 6×2 分组 = 30 步；
# REED 5×4 + 3×3 = 29 叶 + 8×2 分组 = 45 步。
ADMIN_LEAF_COUNTS = [3, 3, 3, 3, 3, 3]
REED_LEAF_COUNTS = [4, 4, 4, 4, 4, 3, 3, 3]


class SeedError(RuntimeError):
    """演示数据生成或校验失败。"""


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def dt(day: date, hour: int = 0, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute))


def insert(conn, sql: str, **params):
    return conn.execute(text(sql), params).lastrowid


def _ids(conn, sql: str, **params) -> list:
    return [row[0] for row in conn.execute(text(sql), params).all()]


def _in(ids) -> str:
    values = [str(int(item)) for item in ids]
    return ",".join(values) if values else "NULL"


def _in_values(ids) -> str:
    if not ids:
        return "NULL"
    escaped = []
    for item in ids:
        if isinstance(item, int):
            escaped.append(str(item))
        else:
            escaped.append("'" + str(item).replace("'", "''") + "'")
    return ",".join(escaped)


def current_database(conn) -> str:
    return conn.execute(text("SELECT DATABASE()")).scalar_one()


def validate_schema(conn) -> str:
    database = current_database(conn)
    tables = {
        row[0]
        for row in conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = DATABASE()"
            )
        ).all()
    }
    missing = sorted(REQUIRED_TABLES - tables)
    if missing:
        raise SeedError(f"目标库 {database} 缺少表：{missing}")
    for table, required in REQUIRED_COLUMNS.items():
        actual = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = DATABASE() AND table_name = :t"
                ),
                {"t": table},
            ).all()
        }
        absent = sorted(required - actual)
        if absent:
            raise SeedError(f"表 {table} 缺少关键字段：{absent}")
    return database


def ensure_infrastructure(conn) -> dict:
    now = _now()
    conn.execute(
        text(
            "INSERT IGNORE INTO ai_runtime_config "
            "(id, enabled, user_daily_limit, global_daily_limit, updated_at) "
            "VALUES (1, 1, 10, 80, :now)"
        ),
        {"now": now},
    )
    conn.execute(text("INSERT IGNORE INTO ai_guard_mutex (id) VALUES (1)"))
    row = conn.execute(
        text(
            "SELECT user_daily_limit, global_daily_limit "
            "FROM ai_runtime_config WHERE id = 1"
        )
    ).one()
    return {"user_daily_limit": int(row[0]), "global_daily_limit": int(row[1])}


def resolve_password(env_name: str, label: str) -> str:
    value = os.environ.get(env_name)
    if value:
        return value
    if sys.stdin.isatty():
        value = getpass.getpass(f"{label}（输入不回显）: ")
        if value:
            return value
    raise SeedError(
        f"缺少密码：请通过环境变量 {env_name} 或本地交互输入提供，"
        "禁止写入脚本、日志或 Git"
    )


def ensure_special_accounts(
    conn,
    manifest: SeedManifest,
    credentials: dict[str, str | None],
    rotate_passwords: bool,
) -> dict[str, dict]:
    now = _now()
    result: dict[str, dict] = {}

    for key, spec in SPECIALS.items():
        name_row = conn.execute(
            text(
                "SELECT id, username, email, role FROM users "
                "WHERE username = :u LIMIT 1"
            ),
            {"u": spec["username"]},
        ).first()
        email_row = conn.execute(
            text(
                "SELECT id, username, email, role FROM users "
                "WHERE email = :e LIMIT 1"
            ),
            {"e": spec["email"]},
        ).first()

        if name_row and email_row and name_row[0] != email_row[0]:
            raise SeedError(
                f"账号冲突：用户名 {spec['username']} 与邮箱 {spec['email']} "
                "分别属于不同用户，拒绝继续"
            )

        existing = name_row or email_row
        if existing:
            if existing[1] != spec["username"]:
                raise SeedError(
                    f"邮箱 {spec['email']} 已被其他账号 {existing[1]} 占用，拒绝继续"
                )
            user_id = int(existing[0])
            if rotate_passwords:
                password = credentials.get(key)
                if not password:
                    raise SeedError(f"轮换密码需要提供 {key} 的本地密码")
                conn.execute(
                    text(
                        "UPDATE users SET password_hash = :h, "
                        "password_updated_at = :now, email = :e, nickname = :n, "
                        "role = :r, is_active = 1 WHERE id = :i"
                    ),
                    {
                        "h": hash_password(password),
                        "now": now,
                        "e": spec["email"],
                        "n": spec["nickname"],
                        "r": spec["role"],
                        "i": user_id,
                    },
                )
            else:
                conn.execute(
                    text(
                        "UPDATE users SET email = :e, nickname = :n, "
                        "role = :r, is_active = 1 WHERE id = :i"
                    ),
                    {
                        "e": spec["email"],
                        "n": spec["nickname"],
                        "r": spec["role"],
                        "i": user_id,
                    },
                )
        else:
            password = credentials.get(key)
            if not password:
                raise SeedError(f"创建特殊账号 {key} 需要提供本地密码")
            user_id = insert(
                conn,
                "INSERT INTO users (username, password_hash, password_updated_at, "
                "email, email_verified_at, nickname, is_active, role, created_at) "
                "VALUES (:u, :h, :now, :e, :now, :n, 1, :r, :c)",
                u=spec["username"],
                h=hash_password(password),
                now=now,
                e=spec["email"],
                n=spec["nickname"],
                r=spec["role"],
                c=now - timedelta(days=60),
            )

        manifest.add("users", user_id, owner=user_id)
        manifest.add_special(
            key,
            user_id=user_id,
            username=spec["username"],
            role=spec["role"],
            email=spec["email"],
        )
        result[key] = {
            "id": user_id,
            "username": spec["username"],
            "role": spec["role"],
            "email": spec["email"],
        }

    return result


def seed_demo_users(conn, manifest: SeedManifest, password: str) -> list[dict]:
    now = _now()
    password_hash = hash_password(password)
    nicknames = [
        "小林",
        "小陈",
        "小王",
        "小李",
        "小赵",
        "小周",
        "小吴",
        "小郑",
        "小钱",
        "小孙",
    ]
    users: list[dict] = []
    for index in range(1, DEMO_USER_COUNT + 1):
        active = 0 if index in BANNED_DEMO_INDEXES else 1
        user_id = insert(
            conn,
            "INSERT INTO users (username, password_hash, password_updated_at, "
            "email, email_verified_at, nickname, is_active, role, created_at) "
            "VALUES (:u, :h, :now, :e, :now, :n, :a, 'USER', :c)",
            u=f"{DEMO_PREFIX}{index:02d}",
            h=password_hash,
            now=now,
            e=f"demo{index:02d}@example.com",
            n=nicknames[index % len(nicknames)] + f"{index:02d}",
            a=active,
            c=now - timedelta(days=30 + index),
        )
        manifest.add("users", user_id, owner=user_id)
        manifest.add_demo_user(user_id)
        users.append(
            {
                "id": user_id,
                "username": f"{DEMO_PREFIX}{index:02d}",
                "index": index,
                "is_active": active,
            }
        )
    return users


def _create_plan(
    conn,
    manifest: SeedManifest,
    user_id: int,
    name: str,
    domain: str,
    status: str,
    start: date,
    end: date,
    leaves: list[dict],
    created_at: datetime,
) -> dict:
    started_at = dt(start, 8) if status != "DRAFT" else None
    ended_at = dt(end, 20) if status == "ENDED" else None
    plan_id = insert(
        conn,
        "INSERT INTO study_plans (user_id, name, description, start_date, end_date, "
        "status, started_at, ended_at, created_at) "
        "VALUES (:u, :n, :d, :s, :e, :st, :sa, :ea, :c)",
        u=user_id,
        n=name,
        d=f"{DEMO_TAG} 演示学习计划：{domain}",
        s=start,
        e=end,
        st=status,
        sa=started_at,
        ea=ended_at,
        c=created_at,
    )
    manifest.add("study_plans", plan_id, owner=user_id)

    root_id = insert(
        conn,
        "INSERT INTO plan_steps (plan_id, parent_id, name, description, "
        "node_type, sort_order) "
        "VALUES (:p, NULL, :n, :d, 'GROUP', 0)",
        p=plan_id,
        n="阶段一 · 基础巩固",
        d=f"{DEMO_TAG} 分组节点",
    )
    manifest.add("plan_steps", root_id, owner=user_id)
    group_id = insert(
        conn,
        "INSERT INTO plan_steps (plan_id, parent_id, name, description, "
        "node_type, sort_order) "
        "VALUES (:p, :parent, :n, :d, 'GROUP', 1)",
        p=plan_id,
        parent=root_id,
        n="模块一 · 核心任务",
        d=f"{DEMO_TAG} 二级分组节点",
    )
    manifest.add("plan_steps", group_id, owner=user_id)

    leaf_rows: list[dict] = []
    for order, leaf in enumerate(leaves, start=2):
        task_type = leaf["task_type"]
        step_id = insert(
            conn,
            "INSERT INTO plan_steps (plan_id, parent_id, name, description, "
            "node_type, task_type, schedule_mode, repeat_content, total_target, "
            "sort_order) "
            "VALUES (:p, :parent, :n, :d, 'LEAF', :tt, :mode, :repeat, :target, :order)",
            p=plan_id,
            parent=group_id,
            n=leaf["name"],
            d=f"{DEMO_TAG} 叶子任务",
            tt=task_type,
            mode="REPEAT" if task_type == "BOOLEAN" else "AUTO_DISTRIBUTE",
            repeat=leaf.get("repeat_content") if task_type == "BOOLEAN" else None,
            target=leaf.get("target") if task_type == "NUMERIC" else None,
            order=order,
        )
        manifest.add("plan_steps", step_id, owner=user_id)
        leaf_rows.append(
            {
                "id": step_id,
                "task_type": task_type,
                "name": leaf["name"],
                "target": leaf.get("target"),
                "repeat_content": leaf.get("repeat_content"),
            }
        )

    return {
        "id": plan_id,
        "user_id": user_id,
        "name": name,
        "domain": domain,
        "status": status,
        "start": start,
        "end": end,
        "leaves": leaf_rows,
        "steps": [root_id, group_id] + [leaf["id"] for leaf in leaf_rows],
        "root_id": root_id,
        "group_id": group_id,
    }


def _leaves_for(index: int, numeric_total: int = 30, leaf_count: int = 3) -> list[dict]:
    variant = index % 3
    if variant == 0:
        leaves = [
            {"task_type": "BOOLEAN", "name": "每日精读", "repeat_content": "精读 20 分钟"},
            {"task_type": "BOOLEAN", "name": "错题回顾", "repeat_content": "回顾 5 道错题"},
            {"task_type": "NUMERIC", "name": "专项练习", "target": numeric_total},
        ]
    elif variant == 1:
        leaves = [
            {"task_type": "BOOLEAN", "name": "概念复述", "repeat_content": "口述 3 个核心概念"},
            {"task_type": "NUMERIC", "name": "代码实操", "target": numeric_total},
            {"task_type": "NUMERIC", "name": "题目训练", "target": max(10, numeric_total - 10)},
        ]
    else:
        leaves = [
            {"task_type": "BOOLEAN", "name": "每日精读", "repeat_content": "精读 20 分钟"},
            {"task_type": "NUMERIC", "name": "专项练习", "target": numeric_total},
            {"task_type": "NUMERIC", "name": "错题重做", "target": max(10, numeric_total - 15)},
        ]
    if leaf_count > len(leaves):
        leaves.append(
            {"task_type": "BOOLEAN", "name": "错题回顾", "repeat_content": "回顾 5 道错题"}
        )
    return leaves


def seed_special_plans(
    conn,
    manifest: SeedManifest,
    special: dict[str, dict],
) -> tuple[dict[str, list[dict]], dict[int, dict]]:
    plans_by_user: dict[str, list[dict]] = {"admin": [], "REED": []}
    plan_by_id: dict[int, dict] = {}
    now = _now()

    for key, specs, leaf_counts in (
        ("admin", ADMIN_PLANS, ADMIN_LEAF_COUNTS),
        ("REED", REED_PLANS, REED_LEAF_COUNTS),
    ):
        user_id = special[key]["id"]
        for index, (name, domain, status, start_offset, end_offset, _days) in enumerate(specs):
            start = business_today() + timedelta(days=start_offset)
            end = business_today() + timedelta(days=end_offset)
            leaves = _leaves_for(
                len(plans_by_user[key]) + 1,
                leaf_count=leaf_counts[index],
            )
            plan = _create_plan(
                conn,
                manifest,
                user_id,
                name,
                domain,
                status,
                start,
                end,
                leaves,
                created_at=min(dt(start, 7), now),
            )
            plans_by_user[key].append(plan)
            plan_by_id[plan["id"]] = plan

    return plans_by_user, plan_by_id


def seed_demo_plans(
    conn,
    manifest: SeedManifest,
    demo_users: list[dict],
) -> tuple[list[dict], dict[int, dict]]:
    plans: list[dict] = []
    plan_by_id: dict[int, dict] = {}
    now = _now()

    for user in demo_users:
        for variant in (1, 2):
            if variant == 1:
                status = "ACTIVE"
                start = business_today() - timedelta(days=30)
                end = business_today() + timedelta(days=16)
            elif user["index"] <= 8:
                status = "DRAFT"
                start = business_today() + timedelta(days=1)
                end = business_today() + timedelta(days=30)
            elif user["index"] <= 22:
                status = "ENDED"
                start = business_today() - timedelta(days=45)
                end = business_today() - timedelta(days=31)
            else:
                status = "ACTIVE"
                start = business_today() - timedelta(days=7)
                end = business_today() + timedelta(days=23)

            name = f"演示计划 {user['index']:02d}-{variant}"
            leaves = [
                {
                    "task_type": "BOOLEAN",
                    "name": "每日背诵",
                    "repeat_content": "背诵 20 分钟",
                },
                {
                    "task_type": "NUMERIC",
                    "name": "每日刷题",
                    "target": 30 if variant == 1 else 20,
                },
            ]
            plan = _create_plan(
                conn,
                manifest,
                user["id"],
                name,
                "综合学习",
                status,
                start,
                end,
                leaves,
                created_at=min(dt(start, 7), now),
            )
            plans.append(plan)
            plan_by_id[plan["id"]] = plan

    return plans, plan_by_id


def pick_days(start: date, end: date, count: int, status: str) -> list[date]:
    if count <= 0:
        return []
    today = business_today()
    window_end = min(end, today) if status == "ACTIVE" else end
    if window_end < start:
        window_end = start
    span = (window_end - start).days
    days: list[date] = []
    if count == 1:
        days = [window_end]
    else:
        for index in range(count):
            offset = round(index * span / (count - 1))
            day = start + timedelta(days=offset)
            if day not in days:
                days.append(day)
        cursor = 1
        while len(days) < count:
            candidate = window_end - timedelta(days=cursor)
            if candidate >= start and candidate not in days:
                days.append(candidate)
            cursor += 1

    if status == "ACTIVE" and start <= today <= end and today not in days:
        days[-1] = today

    return sorted(set(days))


def _create_task(
    conn,
    manifest: SeedManifest,
    plan: dict,
    leaf: dict,
    day: date,
    status: str,
    actual: int = 0,
    rollover_out: int = 0,
    completed_at: datetime | None = None,
    target_override: int | None = None,
    rollover_target: bool = False,
) -> dict:
    target = target_override if target_override is not None else leaf.get("target")
    if leaf["task_type"] == "BOOLEAN":
        content = leaf.get("repeat_content") or leaf["name"]
        target = None
    else:
        content = f"{leaf['name']}（目标 {target}）"
    task_id = insert(
        conn,
        "INSERT INTO daily_tasks (plan_id, step_id, task_date, task_type, content, "
        "target_quantity, actual_quantity, rollover_out_quantity, status, "
        "completed_at, created_at) "
        "VALUES (:p, :s, :d, :tt, :c, :target, :actual, :out, :status, :ca, :created)",
        p=plan["id"],
        s=leaf["id"],
        d=day,
        tt=leaf["task_type"],
        c=content,
        target=target,
        actual=actual,
        out=rollover_out,
        status=status,
        ca=completed_at,
        created=dt(day, 7),
    )
    manifest.add("daily_tasks", task_id, owner=plan["user_id"])
    return {
        "id": task_id,
        "plan_id": plan["id"],
        "user_id": plan["user_id"],
        "step_id": leaf["id"],
        "task_type": leaf["task_type"],
        "target": target,
        "task_date": day,
        "status": status,
        "actual": actual,
        "rollover_out": rollover_out,
        "completed_at": completed_at,
        "rollover_target": rollover_target,
    }


def seed_special_tasks(
    conn,
    manifest: SeedManifest,
    plans_by_user: dict[str, list[dict]],
) -> tuple[dict[str, list[dict]], dict[int, dict]]:
    tasks_by_user: dict[str, list[dict]] = {"admin": [], "REED": []}
    task_by_id: dict[int, dict] = {}
    today = business_today()

    for key, specs in (("admin", ADMIN_PLANS), ("REED", REED_PLANS)):
        plans = plans_by_user[key]
        for plan, spec in zip(plans, specs):
            days = pick_days(plan["start"], plan["end"], spec[5], plan["status"])
            for day in days:
                for leaf in plan["leaves"]:
                    target = leaf.get("target") if leaf["task_type"] == "NUMERIC" else None
                    if leaf["task_type"] == "NUMERIC":
                        target = max(10, int(target) + ((day.toordinal() % 3) - 1) * 5)
                    task = _create_task(
                        conn,
                        manifest,
                        plan,
                        {**leaf, "target": target},
                        day,
                        "PENDING",
                    )
                    tasks_by_user[key].append(task)
                    task_by_id[task["id"]] = task

    return tasks_by_user, task_by_id


def assign_special_statuses(conn, tasks: list[dict], completed_target: int) -> None:
    today = business_today()
    past = [task for task in tasks if task["task_date"] < today]
    todays = [task for task in tasks if task["task_date"] == today]

    def complete(task: dict) -> None:
        task["status"] = "COMPLETED"
        task["actual"] = task["target"] if task["task_type"] == "NUMERIC" else 1
        task["completed_at"] = dt(task["task_date"], 19)

    completed_today = min(len(todays), max(2, completed_target // 12))
    for task in todays[:completed_today]:
        complete(task)
    remaining = completed_target - completed_today

    chosen: set[int] = set()
    if past and remaining > 0:
        for index in range(min(remaining, len(past))):
            cursor = int(index * len(past) / max(1, min(remaining, len(past))))
            while cursor in chosen:
                cursor = (cursor + 1) % len(past)
            chosen.add(cursor)
    for index, task in enumerate(past):
        if index in chosen:
            complete(task)
            remaining -= 1
        else:
            task["status"] = "OVERDUE"
            task["actual"] = 0
            task["completed_at"] = None

    # 极端情况下历史任务不足，用今日任务补足
    if remaining > 0:
        for task in todays:
            if task["status"] != "COMPLETED":
                complete(task)
                remaining -= 1
                if remaining == 0:
                    break

    for index, task in enumerate(todays):
        if task["status"] == "COMPLETED":
            continue
        if index % 3 == 0:
            task["status"] = "IN_PROGRESS"
        else:
            task["status"] = "PENDING"
        task["actual"] = 0

    # 初始插入状态为 PENDING，必须把最终状态与进度写回数据库，
    # 否则学习记录、顺延关系会与任务表不一致。
    for task in tasks:
        conn.execute(
            text(
                "UPDATE daily_tasks SET status = :st, actual_quantity = :a, "
                "completed_at = :ca WHERE id = :i"
            ),
            {
                "st": task["status"],
                "a": task["actual"],
                "ca": task["completed_at"],
                "i": task["id"],
            },
        )


def seed_demo_tasks(
    conn,
    manifest: SeedManifest,
    plans: list[dict],
    rng: random.Random,
) -> tuple[list[dict], dict[int, dict]]:
    tasks: list[dict] = []
    task_by_id: dict[int, dict] = {}
    today = business_today()

    for plan in plans:
        if plan["status"] == "DRAFT":
            continue
        if plan["status"] == "ENDED":
            count = 3
        elif plan["start"] == today - timedelta(days=30):
            count = 6
        else:
            count = 3
        days = pick_days(plan["start"], plan["end"], count, plan["status"])
        for day in days:
            for leaf in plan["leaves"]:
                is_today = day == today
                if is_today:
                    status = rng.choices(
                        ["COMPLETED", "PENDING", "IN_PROGRESS"],
                        weights=[30, 40, 30],
                    )[0]
                else:
                    status = rng.choices(
                        ["COMPLETED", "PENDING", "OVERDUE"],
                        weights=[65, 20, 15],
                    )[0]
                target = leaf.get("target") if leaf["task_type"] == "NUMERIC" else None
                if leaf["task_type"] == "NUMERIC":
                    target = max(10, int(target) + ((day.toordinal() % 4) - 1) * 5)
                actual = 0
                completed_at = None
                if status == "COMPLETED":
                    actual = target if leaf["task_type"] == "NUMERIC" else 1
                    completed_at = dt(day, 18 + (len(tasks) % 3))
                elif status == "IN_PROGRESS" and leaf["task_type"] == "NUMERIC":
                    actual = max(1, int(target) // 3)
                task = _create_task(
                    conn,
                    manifest,
                    plan,
                    {**leaf, "target": target},
                    day,
                    status,
                    actual=actual,
                    completed_at=completed_at,
                )
                tasks.append(task)
                task_by_id[task["id"]] = task

    return tasks, task_by_id


def seed_rollovers(
    conn,
    manifest: SeedManifest,
    tasks: list[dict],
    plan_by_id: dict[int, dict],
    count: int,
    special: bool,
    rng: random.Random,
) -> int:
    today = business_today()
    existing = {(task["step_id"], task["task_date"]) for task in tasks}
    candidates = [
        task
        for task in tasks
        if task["status"] == "COMPLETED"
        and task["task_type"] == "NUMERIC"
        and int(task["actual"] or 0) >= 10
        and ((task["task_date"] < today) if special else (task["task_date"] == today))
        and not task.get("rollover_target")
    ]
    candidates.sort(key=lambda item: item["task_date"], reverse=special)

    created = 0
    for task in candidates:
        if created >= count:
            break
        plan = plan_by_id.get(task["plan_id"])
        if plan is None:
            continue
        target_day = task["task_date"] + timedelta(days=1)
        if target_day > plan["end"]:
            continue
        if (task["step_id"], target_day) in existing:
            continue
        quantity = min(10, int(task["actual"]) - 1)
        if quantity <= 0:
            continue
        task["actual"] -= quantity
        task["rollover_out"] = quantity
        conn.execute(
            text(
                "UPDATE daily_tasks SET actual_quantity = :a, "
                "rollover_out_quantity = :o WHERE id = :i"
            ),
            {"a": task["actual"], "o": quantity, "i": task["id"]},
        )
        leaf = next(
            (item for item in plan["leaves"] if item["id"] == task["step_id"]),
            None,
        )
        if leaf is None:
            continue
        target = _create_task(
            conn,
            manifest,
            plan,
            leaf,
            target_day,
            "PENDING",
            target_override=quantity,
            rollover_target=True,
        )
        rollover_id = insert(
            conn,
            "INSERT INTO task_rollovers (source_task_id, target_task_id, quantity, created_at) "
            "VALUES (:s, :t, :q, :c)",
            s=task["id"],
            t=target["id"],
            q=quantity,
            c=dt(target_day, 8),
        )
        manifest.add("task_rollovers", rollover_id)
        tasks.append(target)
        existing.add((task["step_id"], target_day))
        created += 1

    return created


def seed_records(
    conn,
    manifest: SeedManifest,
    tasks: list[dict],
) -> int:
    total = 0
    for task in tasks:
        if task["status"] == "COMPLETED":
            value = task["actual"] if task["task_type"] == "NUMERIC" else None
            record_id = insert(
                conn,
                "INSERT INTO study_records (task_id, user_id, event_type, "
                "recorded_value, task_date, recorded_at) "
                "VALUES (:t, :u, :e, :v, :d, :at)",
                t=task["id"],
                u=task["user_id"],
                e="NUMERIC_PROGRESS" if task["task_type"] == "NUMERIC" else "BOOLEAN_COMPLETE",
                v=value,
                d=task["task_date"],
                at=task["completed_at"] or dt(task["task_date"], 20),
            )
            manifest.add("study_records", record_id, owner=task["user_id"])
            total += 1
        elif (
            task["status"] == "IN_PROGRESS"
            and task["task_type"] == "NUMERIC"
            and int(task["actual"] or 0) > 0
        ):
            first = int(task["actual"]) // 2
            second = int(task["actual"]) - first
            for offset, quantity in ((0, first), (1, second)):
                if quantity <= 0:
                    continue
                record_id = insert(
                    conn,
                    "INSERT INTO study_records (task_id, user_id, event_type, "
                    "recorded_value, task_date, recorded_at) "
                    "VALUES (:t, :u, 'NUMERIC_PROGRESS', :v, :d, :at)",
                    t=task["id"],
                    u=task["user_id"],
                    v=quantity,
                    d=task["task_date"],
                    at=dt(task["task_date"], 12 + offset * 6),
                )
                manifest.add("study_records", record_id, owner=task["user_id"])
                total += 1
    return total


def _pick_step(plan: dict) -> int:
    numeric = [
        leaf["id"] for leaf in plan["leaves"] if leaf["task_type"] == "NUMERIC"
    ]
    if numeric:
        return numeric[0]
    return plan["leaves"][0]["id"]


def _insert_note(
    conn,
    manifest: SeedManifest,
    user_id: int,
    plan: dict,
    item: dict,
    created_at: datetime,
) -> dict:
    note_id = insert(
        conn,
        "INSERT INTO knowledge_notes (user_id, plan_id, step_id, title, content_md, "
        "tags, created_at) VALUES (:u, :p, :s, :t, :c, :tags, :at)",
        u=user_id,
        p=plan["id"],
        s=_pick_step(plan),
        t=item["title"],
        c=render_note(item),
        tags=json.dumps(item["tags"], ensure_ascii=False),
        at=created_at,
    )
    manifest.add("knowledge_notes", note_id, owner=user_id)
    return {
        "id": note_id,
        "user_id": user_id,
        "plan_id": plan["id"],
        "step_id": _pick_step(plan),
        "title": item["title"],
        "item": item,
        "created_at": created_at,
    }


def seed_notes(
    conn,
    manifest: SeedManifest,
    special: dict[str, dict],
    plans_by_user: dict[str, list[dict]],
    demo_users: list[dict],
    demo_plans: list[dict],
) -> dict[int, list[dict]]:
    notes_by_user: dict[int, list[dict]] = {}
    now = _now()

    def plan_for(plans: list[dict], domain: str) -> dict:
        for plan in plans:
            if plan["domain"] == domain and plan["status"] != "DRAFT":
                return plan
        for plan in plans:
            if plan["status"] != "DRAFT":
                return plan
        return plans[0]

    admin_plans = plans_by_user["admin"]
    for index, key in enumerate(ADMIN_NOTE_KEYS):
        item = NOTES_BY_KEY[key]
        plan = plan_for(admin_plans, item["domain"])
        note = _insert_note(
            conn,
            manifest,
            special["admin"]["id"],
            plan,
            item,
            now - timedelta(days=28 - index, hours=index),
        )
        notes_by_user.setdefault(special["admin"]["id"], []).append(note)

    reed_plans = plans_by_user["REED"]
    for index, key in enumerate(REED_NOTE_KEYS):
        item = NOTES_BY_KEY[key]
        plan = plan_for(reed_plans, item["domain"])
        note = _insert_note(
            conn,
            manifest,
            special["REED"]["id"],
            plan,
            item,
            now - timedelta(days=29 - index, hours=index + 1),
        )
        notes_by_user.setdefault(special["REED"]["id"], []).append(note)

    special_keys = set(ADMIN_NOTE_KEYS) | set(REED_NOTE_KEYS)
    remaining = [item for item in ALL_NOTES if item["key"] not in special_keys]
    plan_by_user: dict[int, list[dict]] = {}
    for plan in demo_plans:
        plan_by_user.setdefault(plan["user_id"], []).append(plan)

    cursor = 0
    for user in demo_users[:DEMO_NOTE_USER_COUNT]:
        plans = plan_by_user.get(user["id"], [])
        if not plans:
            continue
        active_plans = [plan for plan in plans if plan["status"] != "DRAFT"] or plans
        for offset in range(NOTES_PER_DEMO_USER):
            if cursor >= len(remaining):
                break
            item = remaining[cursor]
            plan = plan_for(active_plans, item["domain"])
            note = _insert_note(
                conn,
                manifest,
                user["id"],
                plan,
                item,
                now - timedelta(days=25 - offset * 3, hours=user["index"] % 12),
            )
            notes_by_user.setdefault(user["id"], []).append(note)
            cursor += 1

    manifest.notes = [item["key"] for item in ALL_NOTES]
    return notes_by_user


def seed_reviews(
    conn,
    manifest: SeedManifest,
    notes_by_user: dict[int, list[dict]],
    special: dict[str, dict],
    demo_users: list[dict],
) -> None:
    now = _now()

    def seed_for(user_id: int, count: int, notes: list[dict]) -> None:
        for index in range(count):
            note = notes[index % len(notes)]
            review_id = insert(
                conn,
                "INSERT INTO knowledge_review_records (note_id, user_id, reviewed_at) "
                "VALUES (:n, :u, :at)",
                n=note["id"],
                u=user_id,
                at=now - timedelta(days=1 + (index * 3) % 27, hours=index % 10),
            )
            manifest.add("knowledge_review_records", review_id, owner=user_id)

    seed_for(
        special["admin"]["id"],
        20,
        notes_by_user[special["admin"]["id"]],
    )
    seed_for(
        special["REED"]["id"],
        30,
        notes_by_user[special["REED"]["id"]],
    )

    for user in demo_users[:DEMO_NOTE_USER_COUNT]:
        notes = notes_by_user.get(user["id"], [])
        if notes:
            seed_for(user["id"], 5, notes)


def seed_focus(
    conn,
    manifest: SeedManifest,
    special: dict[str, dict],
    plans_by_user: dict[str, list[dict]],
    tasks_by_user: dict[str, list[dict]],
    demo_users: list[dict],
    demo_plans: list[dict],
    demo_tasks: list[dict],
    rng: random.Random,
) -> None:
    now = _now()

    def seed_for(user_id: int, count: int, plans: list[dict], tasks: list[dict]) -> None:
        if not plans:
            return
        completed = [task for task in tasks if task["status"] == "COMPLETED"]
        pool = completed or tasks
        for index in range(count):
            plan = plans[index % len(plans)]
            task = pool[index % len(pool)] if pool else None
            day = business_today() - timedelta(days=1 + (index * 2) % 27)
            session_type = "POMODORO" if index % 2 == 0 else "STOPWATCH"
            # 约束 chk_focus_planned_seconds：POMODORO 必须有正计划时长，
            # STOPWATCH 必须为 NULL。
            planned = (1500 if index % 3 else 3000) if session_type == "POMODORO" else None
            status = "CANCELLED" if index % 9 == 0 else "COMPLETED"
            basis = planned or 1500
            focused = basis if status == "COMPLETED" else max(60, basis // 2)
            started = dt(day, 9 + index % 10)
            focus_id = insert(
                conn,
                "INSERT INTO focus_sessions (user_id, plan_id, task_id, session_type, "
                "status, planned_seconds, focused_seconds, started_at, ended_at, focus_date) "
                "VALUES (:u, :p, :t, :st, :status, :planned, :focused, :started, :ended, :d)",
                u=user_id,
                p=plan["id"],
                t=task["id"] if task else None,
                st=session_type,
                status=status,
                planned=planned,
                focused=focused,
                started=started,
                ended=started + timedelta(seconds=focused),
                d=day,
            )
            manifest.add("focus_sessions", focus_id, owner=user_id)

    seed_for(
        special["admin"]["id"],
        25,
        plans_by_user["admin"],
        tasks_by_user["admin"],
    )
    seed_for(
        special["REED"]["id"],
        40,
        plans_by_user["REED"],
        tasks_by_user["REED"],
    )

    demo_plan_by_user: dict[int, list[dict]] = {}
    for plan in demo_plans:
        demo_plan_by_user.setdefault(plan["user_id"], []).append(plan)
    demo_task_by_user: dict[int, list[dict]] = {}
    for task in demo_tasks:
        demo_task_by_user.setdefault(task["user_id"], []).append(task)

    for user in demo_users[:24]:
        plans = demo_plan_by_user.get(user["id"], [])
        tasks = demo_task_by_user.get(user["id"], [])
        if plans:
            seed_for(user["id"], 2, plans, tasks)


def seed_practice(
    conn,
    manifest: SeedManifest,
    special: dict[str, dict],
    notes_by_user: dict[int, list[dict]],
    demo_users: list[dict],
    rng: random.Random,
) -> None:
    now = _now()

    def seed_for(user_id: int, count: int, notes: list[dict]) -> None:
        for index in range(count):
            note = notes[index % len(notes)]
            score, questions = build_practice_record(note["item"])
            practice_id = insert(
                conn,
                "INSERT INTO practice_records (user_id, note_id, note_title_snapshot, "
                "generation_id, question_count, score, questions_json, created_at) "
                "VALUES (:u, :n, :title, :g, :count, :score, :questions, :at)",
                u=user_id,
                n=note["id"],
                title=note["title"],
                g=str(uuid.uuid4()),
                count=len(questions),
                score=score,
                questions=json.dumps(questions, ensure_ascii=False),
                at=now - timedelta(days=1 + (index * 4) % 26, hours=index % 8),
            )
            manifest.add("practice_records", practice_id, owner=user_id)

    seed_for(
        special["admin"]["id"],
        8,
        notes_by_user[special["admin"]["id"]],
    )
    seed_for(
        special["REED"]["id"],
        12,
        notes_by_user[special["REED"]["id"]],
    )

    demo_note_users = [
        user for user in demo_users[:DEMO_NOTE_USER_COUNT] if notes_by_user.get(user["id"])
    ]
    if demo_note_users:
        for index in range(30):
            user = demo_note_users[index % len(demo_note_users)]
            notes = notes_by_user[user["id"]]
            note = notes[(index // len(demo_note_users)) % len(notes)]
            score, questions = build_practice_record(note["item"])
            practice_id = insert(
                conn,
                "INSERT INTO practice_records (user_id, note_id, note_title_snapshot, "
                "generation_id, question_count, score, questions_json, created_at) "
                "VALUES (:u, :n, :title, :g, :count, :score, :questions, :at)",
                u=user["id"],
                n=note["id"],
                title=note["title"],
                g=str(uuid.uuid4()),
                count=len(questions),
                score=score,
                questions=json.dumps(questions, ensure_ascii=False),
                at=now - timedelta(days=1 + (index * 2) % 27, hours=index % 9),
            )
            manifest.add("practice_records", practice_id, owner=user["id"])


def seed_ai_requests(
    conn,
    manifest: SeedManifest,
    special: dict[str, dict],
    notes_by_user: dict[int, list[dict]],
    demo_users: list[dict],
    user_daily_limit: int,
    rng: random.Random,
) -> None:
    now = _now()
    statuses = [
        "SUCCESS",
        "SUCCESS",
        "SUCCESS",
        "SUCCESS",
        "SUCCESS",
        "SUCCESS",
        "ERROR",
        "TIMEOUT",
        "CANCELLED",
        "BLOCKED",
        "STALE",
        "RUNNING_EXPIRED",
    ]
    operations = [
        "PRACTICE_GENERATE",
        "PRACTICE_GRADE",
        "NOTE_SUMMARY",
        "NOTE_QA",
    ]
    used: dict[tuple[int, date], int] = {}

    def allocate(user_id: int, days_ago: int, note_id) -> None:
        cursor = days_ago
        while cursor <= 30:
            day = business_today() - timedelta(days=cursor)
            if used.get((user_id, day), 0) < user_daily_limit:
                break
            cursor += 1
        else:
            raise SeedError("无法为模拟 AI 请求分配满足每日限额的日期")
        used[(user_id, day)] = used.get((user_id, day), 0) + 1
        created = dt(day, 8 + (cursor * 3) % 12, (cursor * 7) % 60)
        status = statuses[(cursor + user_id) % len(statuses)]
        operation = operations[(cursor + note_id or 0) % len(operations)]
        leased_until = created + timedelta(seconds=180)
        finished_at = None if status in {"STALE", "RUNNING_EXPIRED"} else created + timedelta(seconds=45)
        prompt_tokens = rng.randint(260, 900) if status == "SUCCESS" else None
        completion_tokens = rng.randint(180, 700) if status == "SUCCESS" else None
        request_id = str(uuid.uuid4())
        conn.execute(
            text(
                "INSERT INTO ai_requests (request_id, user_id, note_id, operation, "
                "request_date, status, leased_until, created_at, finished_at, "
                "prompt_tokens, completion_tokens) "
                "VALUES (:rid, :u, :n, :op, :d, :st, :lease, :created, :finished, "
                ":pt, :ct)"
            ),
            {
                "rid": request_id,
                "u": user_id,
                "n": note_id,
                "op": operation,
                "d": day,
                "st": status,
                "lease": leased_until,
                "created": created,
                "finished": finished_at,
                "pt": prompt_tokens,
                "ct": completion_tokens,
            },
        )
        manifest.add("ai_requests", request_id, owner=user_id)

    admin_notes = notes_by_user[special["admin"]["id"]]
    for index in range(20):
        note = admin_notes[index % len(admin_notes)]
        allocate(special["admin"]["id"], 1 + index, note["id"])

    reed_notes = notes_by_user[special["REED"]["id"]]
    for index in range(30):
        note = reed_notes[index % len(reed_notes)]
        allocate(special["REED"]["id"], 1 + index, note["id"])

    demo_note_users = [
        user for user in demo_users if notes_by_user.get(user["id"])
    ]
    for index in range(150):
        user = demo_users[index % len(demo_users)]
        notes = notes_by_user.get(user["id"]) or (
            notes_by_user[demo_note_users[index % len(demo_note_users)]["id"]]
            if demo_note_users
            else []
        )
        note_id = notes[index % len(notes)]["id"] if notes else None
        days_ago = 1 + (index * 7 + index // len(demo_users)) % 29
        allocate(user["id"], days_ago, note_id)


def seed_audit(
    conn,
    manifest: SeedManifest,
    special: dict[str, dict],
    demo_users: list[dict],
    batch_id: str,
) -> None:
    now = _now()
    actions = [
        ("BAN_USER", "USER", {"is_active": 1}, {"is_active": 0}),
        ("UNBAN_USER", "USER", {"is_active": 0}, {"is_active": 1}),
        ("REVOKE_SESSION", "USER", {"sessions": 2}, {"sessions": 0}),
        ("UPDATE_AI_CONFIG", "AI_CONFIG", {"user_daily_limit": 10}, {"user_daily_limit": 12}),
        ("UPDATE_USER_ROLE", "USER", {"role": "USER"}, {"role": "USER"}),
    ]

    init_audit_id = insert(
        conn,
        "INSERT INTO admin_audit_logs (admin_id, action, target_type, target_id, "
        "before_data, after_data, reason, created_at) "
        "VALUES (:a, :action, 'SYSTEM', 1, :before, :after, :reason, :at)",
        a=special["admin"]["id"],
        action="SEED_DEMO_DATA",
        before="{}",
        after="{}",
        reason=f"{DEMO_TAG} batch={batch_id} 初始化演示数据",
        at=now,
    )
    manifest.add("admin_audit_logs", init_audit_id, owner=special["admin"]["id"])

    for index in range(24):
        action, target_type, before, after = actions[index % len(actions)]
        target = demo_users[index % len(demo_users)]["id"]
        target_id = 1 if target_type == "AI_CONFIG" else target
        audit_id = insert(
            conn,
            "INSERT INTO admin_audit_logs (admin_id, action, target_type, target_id, "
            "before_data, after_data, reason, created_at) "
            "VALUES (:a, :action, :tt, :ti, :before, :after, :reason, :at)",
            a=special["admin"]["id"],
            action=action,
            tt=target_type,
            ti=target_id,
            before=json.dumps(before, ensure_ascii=False),
            after=json.dumps(after, ensure_ascii=False),
            reason=f"{DEMO_TAG} 答辩演示审计：{action}",
            at=now - timedelta(days=1 + index, hours=index % 12),
        )
        manifest.add("admin_audit_logs", audit_id, owner=special["admin"]["id"])


def reset_demo_data(conn) -> dict[str, int]:
    """仅在隔离演示库中调用：清空 demo_ 用户与特殊账号的演示数据。"""
    demo_ids = _ids(
        conn,
        "SELECT id FROM users WHERE username REGEXP '^demo_[0-9]+$'",
    )
    special_ids = _ids(
        conn,
        "SELECT id FROM users WHERE username IN ('admin', 'REED')",
    )
    all_ids = demo_ids + special_ids
    counts: dict[str, int] = {}

    plan_ids = _ids(
        conn,
        "SELECT id FROM study_plans WHERE user_id IN (" + _in(demo_ids) + ") "
        "OR (user_id IN (" + _in(special_ids) + ") AND description LIKE '[DEMO]%')",
    )
    step_ids = _ids(
        conn,
        "SELECT id FROM plan_steps WHERE plan_id IN (" + _in(plan_ids) + ")",
    )
    task_ids = _ids(
        conn,
        "SELECT id FROM daily_tasks WHERE plan_id IN (" + _in(plan_ids) + ")",
    )
    note_ids = _ids(
        conn,
        "SELECT id FROM knowledge_notes WHERE user_id IN (" + _in(all_ids) + ")",
    )

    def run(label: str, sql: str) -> None:
        result = conn.execute(text(sql))
        counts[label] = int(result.rowcount or 0)

    if task_ids:
        run(
            "task_rollovers",
            "DELETE FROM task_rollovers WHERE source_task_id IN (" + _in(task_ids) + ") "
            "OR target_task_id IN (" + _in(task_ids) + ")",
        )
    if all_ids:
        run("study_records", "DELETE FROM study_records WHERE user_id IN (" + _in(all_ids) + ")")
        run("practice_records", "DELETE FROM practice_records WHERE user_id IN (" + _in(all_ids) + ")")
        run(
            "knowledge_review_records",
            "DELETE FROM knowledge_review_records WHERE user_id IN (" + _in(all_ids) + ")",
        )
        run("knowledge_notes", "DELETE FROM knowledge_notes WHERE user_id IN (" + _in(all_ids) + ")")
        run("focus_sessions", "DELETE FROM focus_sessions WHERE user_id IN (" + _in(all_ids) + ")")
        run("ai_requests", "DELETE FROM ai_requests WHERE user_id IN (" + _in(all_ids) + ")")
    if task_ids:
        run("daily_tasks", "DELETE FROM daily_tasks WHERE id IN (" + _in(task_ids) + ")")
    if step_ids:
        run("schedule_entries", "DELETE FROM schedule_entries WHERE step_id IN (" + _in(step_ids) + ")")
    if plan_ids:
        # 先断开自引用，再删除步骤，避免自引用外键在单语句删除时冲突
        conn.execute(
            text("UPDATE plan_steps SET parent_id = NULL WHERE plan_id IN (" + _in(plan_ids) + ")")
        )
        run("plan_steps", "DELETE FROM plan_steps WHERE plan_id IN (" + _in(plan_ids) + ")")
        run("study_plans", "DELETE FROM study_plans WHERE id IN (" + _in(plan_ids) + ")")
    if demo_ids:
        run("email_verifications", "DELETE FROM email_verifications WHERE user_id IN (" + _in(demo_ids) + ")")
        run("login_sessions", "DELETE FROM login_sessions WHERE user_id IN (" + _in(demo_ids) + ")")
        run("refresh_tokens", "DELETE FROM refresh_tokens WHERE user_id IN (" + _in(demo_ids) + ")")
        run("auth_events", "DELETE FROM auth_events WHERE user_id IN (" + _in(demo_ids) + ")")
        run("users", "DELETE FROM users WHERE id IN (" + _in(demo_ids) + ")")
    run("admin_audit_logs", "DELETE FROM admin_audit_logs WHERE reason LIKE '[DEMO]%'")
    return counts


def _special_counts(conn, user_id: int) -> dict[str, int]:
    plans = conn.execute(
        text("SELECT COUNT(*) FROM study_plans WHERE user_id = :u"),
        {"u": user_id},
    ).scalar_one()
    steps = conn.execute(
        text(
            "SELECT COUNT(*) FROM plan_steps s "
            "JOIN study_plans p ON p.id = s.plan_id WHERE p.user_id = :u"
        ),
        {"u": user_id},
    ).scalar_one()
    tasks = conn.execute(
        text(
            "SELECT COUNT(*) FROM daily_tasks t "
            "JOIN study_plans p ON p.id = t.plan_id WHERE p.user_id = :u"
        ),
        {"u": user_id},
    ).scalar_one()
    rollovers = conn.execute(
        text(
            "SELECT COUNT(*) FROM task_rollovers r "
            "JOIN daily_tasks t ON t.id = r.source_task_id "
            "JOIN study_plans p ON p.id = t.plan_id WHERE p.user_id = :u"
        ),
        {"u": user_id},
    ).scalar_one()
    notes = conn.execute(
        text("SELECT COUNT(*) FROM knowledge_notes WHERE user_id = :u"),
        {"u": user_id},
    ).scalar_one()
    reviews = conn.execute(
        text("SELECT COUNT(*) FROM knowledge_review_records WHERE user_id = :u"),
        {"u": user_id},
    ).scalar_one()
    focus = conn.execute(
        text("SELECT COUNT(*) FROM focus_sessions WHERE user_id = :u"),
        {"u": user_id},
    ).scalar_one()
    practice = conn.execute(
        text("SELECT COUNT(*) FROM practice_records WHERE user_id = :u"),
        {"u": user_id},
    ).scalar_one()
    ai = conn.execute(
        text("SELECT COUNT(*) FROM ai_requests WHERE user_id = :u"),
        {"u": user_id},
    ).scalar_one()
    return {
        "plans": int(plans),
        "steps": int(steps),
        "tasks": int(tasks),
        "records": int(
            conn.execute(
                text("SELECT COUNT(*) FROM study_records WHERE user_id = :u"),
                {"u": user_id},
            ).scalar_one()
        ),
        "notes": int(notes),
        "reviews": int(reviews),
        "focus": int(focus),
        "practice": int(practice),
        "ai": int(ai),
        "rollovers": int(rollovers),
    }


def validate_dataset(
    conn,
    manifest: SeedManifest,
    special: dict[str, dict],
    user_daily_limit: int,
) -> dict:
    violations: dict[str, object] = {}
    checks: dict[str, object] = {}

    def count(sql: str, **params) -> int:
        return int(conn.execute(text(sql), params).scalar_one())

    checks["tasks_outside_plan"] = count(
        "SELECT COUNT(*) FROM daily_tasks t "
        "JOIN study_plans p ON p.id = t.plan_id "
        "WHERE t.task_date < p.start_date OR t.task_date > p.end_date"
    )
    checks["task_step_mismatch"] = count(
        "SELECT COUNT(*) FROM daily_tasks t "
        "JOIN plan_steps s ON s.id = t.step_id WHERE s.plan_id <> t.plan_id"
    )
    checks["orphan_steps"] = count(
        "SELECT COUNT(*) FROM plan_steps s "
        "JOIN plan_steps parent ON parent.id = s.parent_id "
        "WHERE s.plan_id <> parent.plan_id"
    )
    checks["completed_without_record"] = count(
        "SELECT COUNT(*) FROM daily_tasks t "
        "LEFT JOIN study_records r ON r.task_id = t.id "
        "WHERE t.status = 'COMPLETED' AND r.id IS NULL"
    )
    checks["numeric_actual_mismatch"] = count(
        "SELECT COUNT(*) FROM ("
        "  SELECT t.id FROM daily_tasks t "
        "  LEFT JOIN study_records r ON r.task_id = t.id "
        "  WHERE t.task_type = 'NUMERIC' "
        "  GROUP BY t.id, t.actual_quantity "
        "  HAVING t.actual_quantity <> COALESCE(SUM(r.recorded_value), 0)"
        ") x"
    )
    checks["over_target"] = count(
        "SELECT COUNT(*) FROM daily_tasks "
        "WHERE task_type = 'NUMERIC' AND target_quantity IS NOT NULL "
        "AND actual_quantity + rollover_out_quantity > target_quantity"
    )
    checks["rollover_mismatch"] = count(
        "SELECT COUNT(*) FROM task_rollovers r "
        "JOIN daily_tasks s ON s.id = r.source_task_id "
        "JOIN daily_tasks t ON t.id = r.target_task_id "
        "WHERE s.status <> 'COMPLETED' "
        "OR s.rollover_out_quantity <> r.quantity "
        "OR t.target_quantity <> r.quantity "
        "OR t.task_date <> DATE_ADD(s.task_date, INTERVAL 1 DAY)"
    )
    checks["duplicate_numeric_tasks"] = count(
        "SELECT COUNT(*) FROM ("
        "  SELECT step_id, task_date FROM daily_tasks "
        "  WHERE task_type = 'NUMERIC' AND deleted_at IS NULL "
        "  GROUP BY step_id, task_date HAVING COUNT(*) > 1"
        ") x"
    )
    checks["note_owner_mismatch"] = count(
        "SELECT COUNT(*) FROM knowledge_notes n "
        "JOIN study_plans p ON p.id = n.plan_id "
        "WHERE n.plan_id IS NOT NULL AND p.user_id <> n.user_id"
    )
    checks["note_step_mismatch"] = count(
        "SELECT COUNT(*) FROM knowledge_notes n "
        "JOIN plan_steps s ON s.id = n.step_id "
        "JOIN study_plans p ON p.id = s.plan_id "
        "WHERE n.step_id IS NOT NULL AND (p.user_id <> n.user_id OR s.plan_id <> n.plan_id)"
    )
    checks["practice_owner_mismatch"] = count(
        "SELECT COUNT(*) FROM practice_records r "
        "JOIN knowledge_notes n ON n.id = r.note_id "
        "WHERE r.note_id IS NOT NULL AND n.user_id <> r.user_id"
    )
    checks["ai_today"] = count(
        "SELECT COUNT(*) FROM ai_requests WHERE request_date = :today",
        today=business_today(),
    )
    checks["ai_over_daily_limit"] = count(
        "SELECT COUNT(*) FROM ("
        "  SELECT user_id, request_date, COUNT(*) c FROM ai_requests "
        "  GROUP BY user_id, request_date HAVING c > :limit"
        ") x",
        limit=user_daily_limit,
    )

    note_ids = manifest.ids("knowledge_notes")
    if note_ids:
        checks["note_content_too_short"] = count(
            "SELECT COUNT(*) FROM knowledge_notes WHERE id IN (" + _in(note_ids) + ") "
            "AND (CHAR_LENGTH(content_md) < 400 OR content_md LIKE '%TODO%' "
            "OR content_md LIKE '%待补充%' OR content_md LIKE '%Lorem ipsum%')"
        )
    else:
        checks["note_content_too_short"] = 0

    audit_ids = manifest.ids("admin_audit_logs")
    if audit_ids:
        checks["audit_not_demo"] = count(
            "SELECT COUNT(*) FROM admin_audit_logs WHERE id IN (" + _in(audit_ids) + ") "
            "AND reason NOT LIKE '[DEMO]%'"
        )
    else:
        checks["audit_not_demo"] = 0

    special_ids = [item["id"] for item in special.values()]
    checks["banned_special"] = count(
        "SELECT COUNT(*) FROM users WHERE is_active = 0 AND id IN (" + _in(special_ids) + ")"
    )

    special_counts: dict[str, dict] = {}
    for key, user in special.items():
        actual = _special_counts(conn, user["id"])
        special_counts[key] = actual
        expected = EXPECTED_SPECIAL[key]
        for field, target in expected.items():
            value = actual[field]
            if isinstance(target, tuple):
                low, high = target
                if not (low <= value <= high):
                    violations[f"{key}.{field}"] = {
                        "expected": f"{low}~{high}",
                        "actual": value,
                    }
            elif value != target:
                violations[f"{key}.{field}"] = {
                    "expected": target,
                    "actual": value,
                }

    checks["special_counts"] = special_counts

    zero_checks = [
        "tasks_outside_plan",
        "task_step_mismatch",
        "orphan_steps",
        "completed_without_record",
        "numeric_actual_mismatch",
        "over_target",
        "rollover_mismatch",
        "duplicate_numeric_tasks",
        "note_owner_mismatch",
        "note_step_mismatch",
        "practice_owner_mismatch",
        "ai_today",
        "ai_over_daily_limit",
        "note_content_too_short",
        "audit_not_demo",
        "banned_special",
    ]
    for name in zero_checks:
        if checks[name] != 0:
            violations[name] = checks[name]

    if violations:
        raise SeedError(
            "数据一致性校验失败：" + json.dumps(violations, ensure_ascii=False)
        )

    return checks


def initialize(
    conn,
    *,
    database: str,
    mode: str,
    batch_id: str,
    demo_password: str,
    special_passwords: dict[str, str | None],
    rotate_special_passwords: bool = False,
    reset_demo: bool = False,
) -> tuple[SeedManifest, dict]:
    """在已通过入口守卫的连接上生成完整演示数据。

    mode: "isolated" | "production"
    """
    rng = random.Random(RNG_SEED)
    actual_database = validate_schema(conn)
    if actual_database != database:
        raise SeedError(
            f"数据库名称不一致：连接为 {actual_database}，期望 {database}"
        )

    infrastructure = ensure_infrastructure(conn)
    if reset_demo:
        reset_demo_data(conn)

    existing_demo = _ids(
        conn,
        "SELECT id FROM users WHERE username REGEXP '^demo_[0-9]+$' LIMIT 1",
    )
    if existing_demo:
        raise SeedError("检测到已存在的演示用户，拒绝重复初始化；请先执行定向清理")

    if mode == "production":
        existing_real = _ids(
            conn,
            "SELECT id FROM users WHERE username NOT IN ('admin', 'REED') LIMIT 1",
        )
        if existing_real:
            raise SeedError("目标库存在既有真实用户，禁止正式初始化")

    manifest = SeedManifest(database, batch_id, "demo_seed.generator")

    special = ensure_special_accounts(
        conn,
        manifest,
        special_passwords,
        rotate_passwords=rotate_special_passwords,
    )
    demo_users = seed_demo_users(conn, manifest, demo_password)

    special_plans, special_plan_by_id = seed_special_plans(conn, manifest, special)
    demo_plans, demo_plan_by_id = seed_demo_plans(conn, manifest, demo_users)

    special_tasks, special_task_by_id = seed_special_tasks(
        conn, manifest, special_plans
    )
    demo_tasks, demo_task_by_id = seed_demo_tasks(
        conn, manifest, demo_plans, rng
    )

    assign_special_statuses(conn, special_tasks["admin"], 65)
    assign_special_statuses(conn, special_tasks["REED"], 100)

    seed_rollovers(
        conn,
        manifest,
        special_tasks["admin"],
        special_plan_by_id,
        5,
        special=True,
        rng=rng,
    )
    seed_rollovers(
        conn,
        manifest,
        special_tasks["REED"],
        special_plan_by_id,
        8,
        special=True,
        rng=rng,
    )
    seed_rollovers(
        conn,
        manifest,
        demo_tasks,
        demo_plan_by_id,
        12,
        special=False,
        rng=rng,
    )

    seed_records(conn, manifest, special_tasks["admin"])
    seed_records(conn, manifest, special_tasks["REED"])
    seed_records(conn, manifest, demo_tasks)

    notes_by_user = seed_notes(
        conn,
        manifest,
        special,
        special_plans,
        demo_users,
        demo_plans,
    )
    seed_reviews(conn, manifest, notes_by_user, special, demo_users)
    seed_focus(
        conn,
        manifest,
        special,
        special_plans,
        special_tasks,
        demo_users,
        demo_plans,
        demo_tasks,
        rng,
    )
    seed_practice(conn, manifest, special, notes_by_user, demo_users, rng)
    seed_ai_requests(
        conn,
        manifest,
        special,
        notes_by_user,
        demo_users,
        infrastructure["user_daily_limit"],
        rng,
    )
    seed_audit(conn, manifest, special, demo_users, batch_id)

    checks = validate_dataset(
        conn,
        manifest,
        special,
        infrastructure["user_daily_limit"],
    )

    summary = {
        "database": database,
        "batch_id": batch_id,
        "mode": mode,
        "special_accounts": {
            key: {
                "user_id": value["id"],
                "username": value["username"],
                "role": value["role"],
            }
            for key, value in special.items()
        },
        "demo_users": len(demo_users),
        "counts": manifest.counts(),
        "checks": checks,
    }
    return manifest, summary