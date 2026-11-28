"""A7.1 答辩演示数据 Seed Script（独立演示库）。

安全约束：
- 仅允许写入 ssp_v3_demo / ssp_v3_release_rehearsal，其他库（含正式库）一律拒绝。
- 不调用真实 AI 模型、不发送邮件、不使用真实个人信息。
- 管理端密码/演示用户密码均从环境变量读取，禁止硬编码管理员密码。
- 演示数据带明确标记（demo_ 用户名、演示计划/笔记、[DEMO] 审计原因），
  可按标记整体清理，不会混入真实用户统计。

用法：
    set DB_NAME=ssp_v3_demo
    set SSP_ADMIN_PASSWORD=...          # 仅当库中尚无 ADMIN 时使用
    set SSP_SEED_DEMO_PASSWORD=...      # 可选，默认 DemoPass123
    python scripts/seed_demo.py --reset
"""

import argparse
import json
import os
import random
import sys
import uuid
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.clock import business_today  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.database import engine  # noqa: E402

ALLOWED_DATABASES = frozenset({"ssp_v3_demo", "ssp_v3_release_rehearsal"})
DEMO_PREFIX = "demo_"
DEMO_TAG = "[DEMO]"
RNG_SEED = 20261128
USER_COUNT = 30
BANNED_USERS = {28, 29, 30}
NOTE_USERS = 20
NOTE_PER_USER = 5
PRACTICE_COUNT = 50
AI_REQUEST_COUNT = 200
AUDIT_COUNT = 20

rng = random.Random(RNG_SEED)
today = business_today()
now = datetime.now(timezone.utc).replace(tzinfo=None)


def dt(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute))


def insert(conn, sql: str, **params):
    return conn.execute(text(sql), params).lastrowid


def guard(conn) -> str:
    database = conn.execute(text("SELECT DATABASE()")).scalar_one()
    if database not in ALLOWED_DATABASES:
        raise SystemExit(
            f"拒绝执行：当前数据库 {database!r} 不在演示库白名单 "
            f"{sorted(ALLOWED_DATABASES)}"
        )
    return database


def reset_demo_data(conn) -> None:
    user_ids = [
        r[0]
        for r in conn.execute(
            text("SELECT id FROM users WHERE username REGEXP '^demo_[0-9]+$'")
        ).all()
    ]
    if user_ids:
        ids = ",".join(str(i) for i in user_ids)
        for sql in (
            "DELETE FROM task_rollovers WHERE source_task_id IN "
            "(SELECT id FROM daily_tasks WHERE plan_id IN "
            "(SELECT id FROM study_plans WHERE user_id IN (" + ids + "))) "
            "OR target_task_id IN (SELECT id FROM daily_tasks WHERE plan_id IN "
            "(SELECT id FROM study_plans WHERE user_id IN (" + ids + ")))",
            "DELETE FROM study_records WHERE user_id IN (" + ids + ")",
            "DELETE FROM practice_records WHERE user_id IN (" + ids + ")",
            "DELETE FROM knowledge_review_records WHERE user_id IN (" + ids + ")",
            "DELETE FROM knowledge_notes WHERE user_id IN (" + ids + ")",
            "DELETE FROM focus_sessions WHERE user_id IN (" + ids + ")",
            "DELETE FROM daily_tasks WHERE plan_id IN "
            "(SELECT id FROM study_plans WHERE user_id IN (" + ids + "))",
            "DELETE FROM schedule_entries WHERE step_id IN "
            "(SELECT id FROM plan_steps WHERE plan_id IN "
            "(SELECT id FROM study_plans WHERE user_id IN (" + ids + ")))",
            "DELETE FROM plan_steps WHERE plan_id IN "
            "(SELECT id FROM study_plans WHERE user_id IN (" + ids + ")) "
            "AND parent_id IS NOT NULL",
            "DELETE FROM plan_steps WHERE plan_id IN "
            "(SELECT id FROM study_plans WHERE user_id IN (" + ids + "))",
            "DELETE FROM study_plans WHERE user_id IN (" + ids + ")",
            "DELETE FROM ai_requests WHERE user_id IN (" + ids + ")",
            "DELETE FROM email_verifications WHERE user_id IN (" + ids + ")",
            "DELETE FROM login_sessions WHERE user_id IN (" + ids + ")",
            "DELETE FROM refresh_tokens WHERE user_id IN (" + ids + ")",
            "DELETE FROM auth_events WHERE user_id IN (" + ids + ")",
            "DELETE FROM users WHERE id IN (" + ids + ")",
        ):
            conn.execute(text(sql))
    conn.execute(
        text("DELETE FROM admin_audit_logs WHERE reason LIKE :p"),
        {"p": DEMO_TAG + "%"},
    )


def ensure_admin(conn) -> int:
    admin_id = conn.execute(
        text("SELECT id FROM users WHERE role='ADMIN' ORDER BY id LIMIT 1")
    ).scalar_one_or_none()
    if admin_id:
        return admin_id
    password = os.environ.get("SSP_ADMIN_PASSWORD")
    if not password:
        raise SystemExit(
            "库中尚无 ADMIN 账号：请先执行 scripts/bootstrap_admin.py，"
            "或设置 SSP_ADMIN_PASSWORD 供演示库初始化"
        )
    return insert(
        conn,
        "INSERT INTO users (username, password_hash, password_updated_at, email, "
        "email_verified_at, nickname, is_active, role) "
        "VALUES (:u, :h, :now, :e, :now, :n, 1, 'ADMIN')",
        u="admin",
        h=hash_password(password),
        now=now,
        e="admin@example.com",
        n="演示管理员",
    )


def seed_users(conn) -> list[int]:
    demo_password = os.environ.get("SSP_SEED_DEMO_PASSWORD", "DemoPass123")
    password_hash = hash_password(demo_password)
    ids = []
    names = ["小林", "小陈", "小王", "小李", "小赵", "小周", "小吴", "小郑", "小钱", "小孙"]
    for i in range(1, USER_COUNT + 1):
        active = 0 if i in BANNED_USERS else 1
        ids.append(
            insert(
                conn,
                "INSERT INTO users (username, password_hash, password_updated_at, "
                "email, email_verified_at, nickname, is_active, role, created_at) "
                "VALUES (:u, :h, :now, :e, :now, :n, :a, 'USER', :c)",
                u=f"{DEMO_PREFIX}{i:02d}",
                h=password_hash,
                now=now,
                e=f"demo{i:02d}@example.com",
                n=names[i % len(names)] + f"{i:02d}",
                a=active,
                c=now - timedelta(days=rng.randint(30, 90)),
            )
        )
    return ids


def seed_plans_and_steps(conn, users: list[int]):
    plans = []
    for index, user_id in enumerate(users, start=1):
        variants = [("ACTIVE", today - timedelta(days=30), today + timedelta(days=16))]
        if index <= 8:
            variants.append(("DRAFT", today + timedelta(days=1), today + timedelta(days=30)))
        elif index <= 22:
            variants.append(("ENDED", today - timedelta(days=45), today - timedelta(days=31)))
        else:
            variants.append(("ACTIVE", today - timedelta(days=7), today + timedelta(days=23)))

        for k, (status, start, end) in enumerate(variants, start=1):
            started_at = dt(start, 8) if status != "DRAFT" else None
            ended_at = dt(end, 20) if status == "ENDED" else None
            plan_id = insert(
                conn,
                "INSERT INTO study_plans (user_id, name, description, start_date, "
                "end_date, status, started_at, ended_at, created_at) "
                "VALUES (:u, :n, :d, :s, :e, :st, :sa, :ea, :c)",
                u=user_id,
                n=f"演示计划 {index:02d}-{k}",
                d=f"{DEMO_TAG} 答辩演示用学习计划",
                s=start,
                e=end,
                st=status,
                sa=started_at,
                ea=ended_at,
                c=dt(start, 7),
            )
            group_id = insert(
                conn,
                "INSERT INTO plan_steps (plan_id, parent_id, name, description, "
                "node_type, sort_order) VALUES (:p, NULL, :n, :d, 'GROUP', 0)",
                p=plan_id,
                n="阶段一 · 基础巩固",
                d=f"{DEMO_TAG} 分组节点",
            )
            boolean_id = insert(
                conn,
                "INSERT INTO plan_steps (plan_id, parent_id, name, description, "
                "node_type, task_type, schedule_mode, repeat_content, sort_order) "
                "VALUES (:p, :g, :n, :d, 'LEAF', 'BOOLEAN', 'REPEAT', :r, 1)",
                p=plan_id,
                g=group_id,
                n="每日背诵",
                d=f"{DEMO_TAG} 布尔型任务",
                r="背诵 20 分钟",
            )
            numeric_id = insert(
                conn,
                "INSERT INTO plan_steps (plan_id, parent_id, name, description, "
                "node_type, task_type, schedule_mode, total_target, sort_order) "
                "VALUES (:p, :g, :n, :d, 'LEAF', 'NUMERIC', 'AUTO_DISTRIBUTE', 300, 2)",
                p=plan_id,
                g=group_id,
                n="每日刷题",
                d=f"{DEMO_TAG} 数值型任务",
            )
            plans.append(
                {
                    "id": plan_id,
                    "user_id": user_id,
                    "status": status,
                    "start": start,
                    "end": end,
                    "boolean_step": boolean_id,
                    "numeric_step": numeric_id,
                }
            )
    return plans


def seed_tasks(conn, plans) -> list[dict]:
    tasks = []
    for plan in plans:
        if plan["status"] == "DRAFT":
            continue
        if plan["status"] == "ENDED":
            dates = [plan["end"] - timedelta(days=offset) for offset in (2, 1, 0)]
        elif plan["start"] == today - timedelta(days=30):
            dates = [today - timedelta(days=offset) for offset in (29, 22, 15, 8, 1, 0)]
        else:
            dates = [today - timedelta(days=offset) for offset in range(2, -1, -1)]

        for day in dates:
            is_today = day == today
            # 布尔任务
            if is_today:
                boolean_status = rng.choices(
                    ["COMPLETED", "PENDING", "IN_PROGRESS"], weights=[30, 40, 30]
                )[0]
            else:
                boolean_status = rng.choices(
                    ["COMPLETED", "PENDING", "OVERDUE"], weights=[65, 25, 10]
                )[0]
            completed = boolean_status == "COMPLETED"
            task = {
                "plan_id": plan["id"],
                "user_id": plan["user_id"],
                "step_id": plan["boolean_step"],
                "task_date": day,
                "task_type": "BOOLEAN",
                "target": None,
                "actual": 1 if completed else 0,
                "rollover_out": 0,
                "status": boolean_status,
                "completed_at": dt(day, rng.randint(9, 21), 30) if completed else None,
            }
            tasks.append(_insert_task(conn, task))
            # 数值任务
            target = rng.choice([20, 30, 40])
            if is_today:
                numeric_status = rng.choices(
                    ["COMPLETED", "IN_PROGRESS", "PENDING"], weights=[30, 30, 40]
                )[0]
            else:
                numeric_status = rng.choices(
                    ["COMPLETED", "IN_PROGRESS", "PENDING", "OVERDUE"],
                    weights=[60, 10, 22, 8],
                )[0]
            if numeric_status == "COMPLETED":
                actual = target
            elif numeric_status == "IN_PROGRESS":
                actual = max(1, int(target * rng.uniform(0.2, 0.8)))
            else:
                actual = 0
            task = {
                "plan_id": plan["id"],
                "user_id": plan["user_id"],
                "step_id": plan["numeric_step"],
                "task_date": day,
                "task_type": "NUMERIC",
                "target": target,
                "actual": actual,
                "rollover_out": 0,
                "status": numeric_status,
                "completed_at": dt(day, rng.randint(10, 22), 15)
                if numeric_status == "COMPLETED"
                else None,
            }
            tasks.append(_insert_task(conn, task))
    return tasks


def _insert_task(conn, task: dict) -> dict:
    content = (
        f"{DEMO_TAG} 背诵任务"
        if task["task_type"] == "BOOLEAN"
        else f"{DEMO_TAG} 刷题 {task['target']} 道"
    )
    task["id"] = insert(
        conn,
        "INSERT INTO daily_tasks (plan_id, step_id, task_date, task_type, content, "
        "target_quantity, actual_quantity, rollover_out_quantity, status, "
        "completed_at, created_at) "
        "VALUES (:p, :s, :d, :t, :c, :q, :a, :r, :st, :ca, :cr)",
        p=task["plan_id"],
        s=task["step_id"],
        d=task["task_date"],
        t=task["task_type"],
        c=content,
        q=task["target"],
        a=task["actual"],
        r=task["rollover_out"],
        st=task["status"],
        ca=task["completed_at"],
        cr=min(dt(task["task_date"], 7), now),
    )
    return task


def seed_rollovers(conn, tasks: list[dict], plans) -> None:
    active_plans = {p["id"]: p for p in plans if p["status"] == "ACTIVE"}
    numeric_candidates = [
        t
        for t in tasks
        if t["task_type"] == "NUMERIC"
        and t["plan_id"] in active_plans
        and t["task_date"] == today
        and t["status"] == "COMPLETED"
    ]
    for source in numeric_candidates[:8]:
        remaining = rng.choice([5, 8, 10])
        if source["target"] <= remaining:
            continue
        source["actual"] = source["target"] - remaining
        source["rollover_out"] = remaining
        conn.execute(
            text(
                "UPDATE daily_tasks SET actual_quantity=:a, rollover_out_quantity=:r, "
                "status='COMPLETED', completed_at=:c WHERE id=:i"
            ),
            {"a": source["actual"], "r": remaining, "c": source["completed_at"], "i": source["id"]},
        )
        target = {
            "plan_id": source["plan_id"],
            "user_id": source["user_id"],
            "step_id": source["step_id"],
            "task_date": today + timedelta(days=1),
            "task_type": "NUMERIC",
            "target": remaining,
            "actual": 0,
            "rollover_out": 0,
            "status": "PENDING",
            "completed_at": None,
        }
        _insert_task(conn, target)
        conn.execute(
            text(
                "INSERT INTO task_rollovers (source_task_id, target_task_id, quantity) "
                "VALUES (:s, :t, :q)"
            ),
            {"s": source["id"], "t": target["id"], "q": remaining},
        )

    boolean_candidates = [
        t
        for t in tasks
        if t["task_type"] == "BOOLEAN"
        and t["plan_id"] in active_plans
        and t["task_date"] == today
        and t["status"] == "PENDING"
    ]
    for source in boolean_candidates[:4]:
        target = {
            "plan_id": source["plan_id"],
            "user_id": source["user_id"],
            "step_id": source["step_id"],
            "task_date": today + timedelta(days=1),
            "task_type": "BOOLEAN",
            "target": None,
            "actual": 0,
            "rollover_out": 0,
            "status": "PENDING",
            "completed_at": None,
        }
        _insert_task(conn, target)
        conn.execute(
            text(
                "INSERT INTO task_rollovers (source_task_id, target_task_id, quantity) "
                "VALUES (:s, :t, NULL)"
            ),
            {"s": source["id"], "t": target["id"]},
        )


def seed_records(conn, tasks: list[dict]) -> None:
    for task in tasks:
        if task["status"] == "COMPLETED":
            if task["task_type"] == "BOOLEAN":
                event = "BOOLEAN_COMPLETE"
                value = None
            else:
                event = "NUMERIC_PROGRESS"
                value = task["actual"]
            conn.execute(
                text(
                    "INSERT INTO study_records (task_id, user_id, event_type, "
                    "recorded_value, task_date, recorded_at) "
                    "VALUES (:t, :u, :e, :v, :d, :r)"
                ),
                {
                    "t": task["id"],
                    "u": task["user_id"],
                    "e": event,
                    "v": value,
                    "d": task["task_date"],
                    "r": task["completed_at"] or dt(task["task_date"], 20),
                },
            )
        elif task["status"] == "IN_PROGRESS" and task["actual"] > 0:
            first = task["actual"] // 2 or task["actual"]
            for value in (first, task["actual"] - first):
                if value <= 0:
                    continue
                conn.execute(
                    text(
                        "INSERT INTO study_records (task_id, user_id, event_type, "
                        "recorded_value, task_date, recorded_at) "
                        "VALUES (:t, :u, 'NUMERIC_PROGRESS', :v, :d, :r)"
                    ),
                    {
                        "t": task["id"],
                        "u": task["user_id"],
                        "v": value,
                        "d": task["task_date"],
                        "r": dt(task["task_date"], rng.randint(9, 22)),
                    },
                )


def seed_notes(conn, users: list[int], plans) -> list[dict]:
    plans_by_user = {}
    for plan in plans:
        if plan["status"] == "ACTIVE":
            plans_by_user.setdefault(plan["user_id"], plan)
    notes = []
    for index, user_id in enumerate(users[:NOTE_USERS], start=1):
        plan = plans_by_user.get(user_id) or plans[0]
        for n in range(1, NOTE_PER_USER + 1):
            days_ago = rng.choices(
                [rng.randint(0, 6), rng.randint(7, 29)], weights=[55, 45]
            )[0]
            created = now - timedelta(days=days_ago, hours=rng.randint(0, 12))
            note_id = insert(
                conn,
                "INSERT INTO knowledge_notes (user_id, plan_id, step_id, title, "
                "content_md, tags, created_at) "
                "VALUES (:u, :p, :s, :t, :c, :g, :cr)",
                u=user_id,
                p=plan["id"],
                s=plan["numeric_step"],
                t=f"{DEMO_TAG} 演示笔记 {index:02d}-{n}",
                c=f"# 演示笔记 {index:02d}-{n}\n\n"
                "这是答辩演示用笔记，用于展示知识库与 AI 问答效果。\n\n"
                "- 知识点：函数与导数\n- 复习建议：先复习定义再做题\n",
                g=json.dumps(["演示", "数学", f"第{n}章"], ensure_ascii=False),
                cr=created,
            )
            notes.append({"id": note_id, "user_id": user_id, "title": f"{DEMO_TAG} 演示笔记 {index:02d}-{n}", "created_at": created})
    return notes


def seed_practice(conn, notes: list[dict]) -> None:
    for i in range(PRACTICE_COUNT):
        note = notes[(i * 3) % len(notes)]
        created = now - timedelta(days=rng.randint(0, 29), hours=rng.randint(0, 12))
        questions = [
            {"q": f"演示题目 {j + 1}", "a": f"参考答案 {j + 1}"} for j in range(5)
        ]
        conn.execute(
            text(
                "INSERT INTO practice_records (user_id, note_id, "
                "note_title_snapshot, generation_id, question_count, score, "
                "questions_json, created_at) "
                "VALUES (:u, :n, :t, :g, 5, :s, :q, :c)"
            ),
            {
                "u": note["user_id"],
                "n": note["id"],
                "t": note["title"],
                "g": str(uuid.uuid4()),
                "s": round(rng.uniform(60, 100), 2),
                "q": json.dumps(questions, ensure_ascii=False),
                "c": created,
            },
        )


def seed_ai_requests(conn, users: list[int], notes: list[dict], admin_id: int) -> None:
    notes_by_user = {}
    for note in notes:
        notes_by_user.setdefault(note["user_id"], []).append(note)
    statuses = (
        ["SUCCESS"] * 82 + ["ERROR"] * 7 + ["TIMEOUT"] * 4
        + ["CANCELLED"] * 3 + ["BLOCKED"] * 2 + ["STALE"] * 1
        + ["RUNNING_EXPIRED"] * 1
    )
    operations = ["ASK", "GENERATE", "SUMMARY", "ORGANIZE", "PRACTICE_GENERATE", "PRACTICE_GRADE"]
    for i in range(AI_REQUEST_COUNT):
        user_id = users[i % len(users)]
        if user_id == admin_id:
            user_id = users[(i + 1) % len(users)]
        days_ago = rng.choices(
            [rng.randint(1, 6), rng.randint(7, 29)], weights=[60, 40]
        )[0]
        created = now - timedelta(days=days_ago, hours=rng.randint(0, 20), minutes=rng.randint(0, 59))
        status = rng.choice(statuses)
        success = status == "SUCCESS"
        note = None
        if user_id in notes_by_user and rng.random() < 0.5:
            note = rng.choice(notes_by_user[user_id])
        conn.execute(
            text(
                "INSERT INTO ai_requests (request_id, user_id, note_id, operation, "
                "request_date, status, leased_until, created_at, finished_at, "
                "prompt_tokens, completion_tokens) "
                "VALUES (:r, :u, :n, :o, :d, :st, :l, :c, :f, :pt, :ct)"
            ),
            {
                "r": str(uuid.uuid4()),
                "u": user_id,
                "n": note["id"] if note else None,
                "o": operations[i % len(operations)],
                "d": created.date(),
                "st": status,
                "l": created + timedelta(seconds=180),
                "c": created,
                "f": created + timedelta(seconds=rng.randint(3, 110)) if success else None,
                "pt": rng.randint(80, 900) if success else None,
                "ct": rng.randint(40, 700) if success else None,
            },
        )


def seed_audit(conn, admin_id: int, users: list[int]) -> None:
    actions = ["BAN_USER", "UNBAN_USER", "REVOKE_SESSIONS", "UPDATE_AI_CONFIG"]
    for i in range(AUDIT_COUNT):
        action = actions[i % len(actions)]
        if action == "UPDATE_AI_CONFIG":
            target_type, target_id = "AI_CONFIG", 1
            before = {"enabled": True, "user_daily_limit": 10, "global_daily_limit": 80}
            after = {"enabled": True, "user_daily_limit": 10, "global_daily_limit": 80}
            reason = f"{DEMO_TAG} 演示配置审计"
        else:
            target_type, target_id = "USER", users[i % len(users)]
            before = {"is_active": action == "UNBAN_USER"}
            after = {"is_active": action == "BAN_USER"}
            reason = f"{DEMO_TAG} 演示{action}操作"
        conn.execute(
            text(
                "INSERT INTO admin_audit_logs (admin_id, action, target_type, "
                "target_id, before_data, after_data, reason, created_at) "
                "VALUES (:a, :ac, :tt, :ti, :b, :af, :r, :c)"
            ),
            {
                "a": admin_id,
                "ac": action,
                "tt": target_type,
                "ti": target_id,
                "b": json.dumps(before, ensure_ascii=False),
                "af": json.dumps(after, ensure_ascii=False),
                "r": reason,
                "c": now - timedelta(days=rng.randint(0, 29), hours=rng.randint(0, 12)),
            },
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="生成答辩演示数据")
    parser.add_argument("--reset", action="store_true", help="先清理已有演示数据")
    args = parser.parse_args()

    with engine.begin() as conn:
        database = guard(conn)
        existing = conn.execute(
            text("SELECT COUNT(*) FROM users WHERE username REGEXP '^demo_[0-9]+$'")
        ).scalar_one()
        if existing and not args.reset:
            raise SystemExit(
                "检测到已有演示用户，请加 --reset 以幂等重建，避免重复数据"
            )
        if args.reset:
            reset_demo_data(conn)

        # 基础设施单行数据（仅演示库：AI 运行时配置与准入互斥锁）
        conn.execute(
            text(
                "INSERT IGNORE INTO ai_runtime_config (id, enabled, "
                "user_daily_limit, global_daily_limit, updated_at) "
                "VALUES (1, 1, 10, 80, :now)"
            ),
            {"now": now},
        )
        conn.execute(text("INSERT IGNORE INTO ai_guard_mutex (id) VALUES (1)"))

        admin_id = ensure_admin(conn)
        users = seed_users(conn)
        plans = seed_plans_and_steps(conn, users)
        tasks = seed_tasks(conn, plans)
        seed_rollovers(conn, tasks, plans)
        seed_records(conn, tasks)
        notes = seed_notes(conn, users, plans)
        seed_practice(conn, notes)
        seed_ai_requests(conn, users, notes, admin_id)
        seed_audit(conn, admin_id, users)

    with engine.connect() as conn:
        summary = {
            "database": database,
            "admin": conn.execute(text("SELECT COUNT(*) FROM users WHERE role='ADMIN'")).scalar_one(),
            "users": conn.execute(text("SELECT COUNT(*) FROM users WHERE role='USER'")).scalar_one(),
            "banned_users": conn.execute(text("SELECT COUNT(*) FROM users WHERE is_active=0")).scalar_one(),
            "plans": conn.execute(text("SELECT COUNT(*) FROM study_plans")).scalar_one(),
            "plans_by_status": dict(
                conn.execute(text("SELECT status, COUNT(*) FROM study_plans GROUP BY status")).all()
            ),
            "steps": conn.execute(text("SELECT COUNT(*) FROM plan_steps")).scalar_one(),
            "tasks": conn.execute(text("SELECT COUNT(*) FROM daily_tasks")).scalar_one(),
            "tasks_by_type": dict(
                conn.execute(text("SELECT task_type, COUNT(*) FROM daily_tasks GROUP BY task_type")).all()
            ),
            "rollovers": conn.execute(text("SELECT COUNT(*) FROM task_rollovers")).scalar_one(),
            "records": conn.execute(text("SELECT COUNT(*) FROM study_records")).scalar_one(),
            "notes": conn.execute(text("SELECT COUNT(*) FROM knowledge_notes")).scalar_one(),
            "practices": conn.execute(text("SELECT COUNT(*) FROM practice_records")).scalar_one(),
            "ai_requests": conn.execute(text("SELECT COUNT(*) FROM ai_requests")).scalar_one(),
            "ai_today": conn.execute(
                text("SELECT COUNT(*) FROM ai_requests WHERE request_date=:d"), {"d": today}
            ).scalar_one(),
            "audit_logs": conn.execute(text("SELECT COUNT(*) FROM admin_audit_logs")).scalar_one(),
        }
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())