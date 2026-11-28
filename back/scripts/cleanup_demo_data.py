"""定向清理演示数据（默认只预览，不删除）。

安全规则：
- 默认 dry-run，仅统计将要删除的行；必须显式 --execute 才执行删除。
- 只按 demo_ 用户、[DEMO] 审计与 Seed Manifest 定位数据，禁止 TRUNCATE
  与无条件 DELETE。
- admin / REED 账号默认永久保留；--include-special-study-data 才清理其
  预置学习数据，且必须提供 Seed Manifest。
- 清理前检查真实用户是否依赖预置数据；存在依赖时保留相关演示用户并报告。
- 正式库需 --allow-production 且设置 SSP_CONFIRM_PRODUCTION_CLEANUP=YES。

用法：
    set DB_NAME=ssp_v3_demo
    python scripts/cleanup_demo_data.py --manifest <清单路径>            # 预览
    python scripts/cleanup_demo_data.py --manifest <清单路径> --execute  # 执行
"""

import argparse
import json
import os
import sys
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "scripts"))

from sqlalchemy import bindparam, text  # noqa: E402

from app.database import engine  # noqa: E402
from demo_seed.manifest import latest_manifest_for, load_manifest  # noqa: E402

PRODUCTION_DATABASE = "smart_study_planner"
ISOLATED_DATABASES = frozenset({"ssp_v3_demo", "ssp_v3_release_rehearsal"})
SPECIAL_USERNAMES = ("admin", "REED")
DEMO_PATTERN = r"^demo_[0-9]+$"
DEMO_TAG = "[DEMO]"
CHUNK_SIZE = 500


def guard(conn, allow_production: bool) -> str:
    database = conn.execute(text("SELECT DATABASE()")).scalar_one()
    if database in ISOLATED_DATABASES:
        return database
    if database != PRODUCTION_DATABASE:
        raise SystemExit(f"拒绝执行：未知数据库 {database!r}")
    if not allow_production:
        raise SystemExit("正式库清理必须显式添加 --allow-production")
    if os.environ.get("SSP_CONFIRM_PRODUCTION_CLEANUP") != "YES":
        raise SystemExit(
            "正式库清理需要设置环境变量 SSP_CONFIRM_PRODUCTION_CLEANUP=YES"
        )
    return database


def _ids(conn, sql: str, **params) -> list[int]:
    return [int(row[0]) for row in conn.execute(text(sql), params).all()]


def _chunks(seq, size: int = CHUNK_SIZE):
    seq = list(seq)
    for start in range(0, len(seq), size):
        yield seq[start : start + size]


def _count_ids(conn, table: str, column: str, ids) -> int:
    total = 0
    for chunk in _chunks(ids):
        total += int(
            conn.execute(
                text(f"SELECT COUNT(*) FROM {table} WHERE {column} IN :ids").bindparams(
                    bindparam("ids", expanding=True)
                ),
                {"ids": chunk},
            ).scalar_one()
        )
    return total


def _delete_ids(conn, table: str, column: str, ids) -> int:
    deleted = 0
    for chunk in _chunks(ids):
        result = conn.execute(
            text(f"DELETE FROM {table} WHERE {column} IN :ids").bindparams(
                bindparam("ids", expanding=True)
            ),
            {"ids": chunk},
        )
        deleted += int(result.rowcount or 0)
    return deleted


def _plan_owner_map(conn) -> dict[int, int]:
    return {
        int(plan_id): int(user_id)
        for plan_id, user_id in conn.execute(
            text("SELECT id, user_id FROM study_plans")
        ).all()
    }


def _task_owner_map(conn) -> dict[int, int]:
    return {
        int(task_id): int(user_id)
        for task_id, user_id in conn.execute(
            text(
                "SELECT t.id, p.user_id FROM daily_tasks t "
                "JOIN study_plans p ON p.id = t.plan_id"
            )
        ).all()
    }


def _note_owner_map(conn) -> dict[int, int]:
    return {
        int(note_id): int(user_id)
        for note_id, user_id in conn.execute(
            text("SELECT id, user_id FROM knowledge_notes")
        ).all()
    }


def _step_owner_map(conn) -> dict[int, int]:
    return {
        int(step_id): int(user_id)
        for step_id, user_id in conn.execute(
            text(
                "SELECT s.id, p.user_id FROM plan_steps s "
                "JOIN study_plans p ON p.id = s.plan_id"
            )
        ).all()
    }


def collect(
    conn,
    *,
    include_special: bool,
    manifest: dict | None,
) -> dict:
    """收集待删除主键，并计算依赖保护范围。"""

    database = conn.execute(text("SELECT DATABASE()")).scalar_one()
    all_user_ids = {
        int(row[0]): row[1]
        for row in conn.execute(text("SELECT id, username FROM users")).all()
    }
    demo_ids = set(
        _ids(
            conn,
            "SELECT id FROM users WHERE username REGEXP :p",
            p=DEMO_PATTERN,
        )
    )
    special_ids = {
        user_id
        for user_id, name in all_user_ids.items()
        if name in SPECIAL_USERNAMES
    }
    real_ids = set(all_user_ids) - demo_ids - special_ids

    warnings: list[str] = []
    manifest_check: dict = {}
    if manifest:
        if manifest.get("database") != database:
            raise SystemExit(
                f"清单数据库 {manifest.get('database')} 与当前连接 {database} 不一致"
            )
        manifest_demo = {int(item) for item in manifest.get("demo_user_ids", [])}
        missing = sorted(manifest_demo - demo_ids)
        extra = sorted(demo_ids - manifest_demo)
        if missing:
            warnings.append(f"清单中 {len(missing)} 个演示用户已不存在（可能已清理）")
        if extra:
            warnings.append(f"发现 {len(extra)} 个不在清单中的演示用户（将一并清理）")
        manifest_check = {
            "batch_id": manifest.get("batch_id"),
            "manifest_demo_users": len(manifest_demo),
            "missing_demo_users": len(missing),
            "extra_demo_users": len(extra),
        }

    plan_owner = _plan_owner_map(conn)
    task_owner = _task_owner_map(conn)
    note_owner = _note_owner_map(conn)
    step_owner = _step_owner_map(conn)

    demo_plans = {pid for pid, owner in plan_owner.items() if owner in demo_ids}
    demo_steps = {sid for sid, owner in step_owner.items() if owner in demo_ids}
    demo_tasks = {tid for tid, owner in task_owner.items() if owner in demo_ids}

    # ---------- 真实数据依赖检查 ----------
    protected: dict[int, list[str]] = defaultdict(list)
    dependency_checks = {}

    def protect(owner: int | None, reason: str) -> None:
        if owner in demo_ids:
            protected[owner].append(reason)

    if real_ids:
        rows = conn.execute(
            text(
                "SELECT DISTINCT user_id, plan_id, step_id FROM knowledge_notes "
                "WHERE user_id IN :ids AND deleted_at IS NULL "
                "AND (plan_id IN :plans OR step_id IN :steps)"
            ).bindparams(
                bindparam("ids", expanding=True),
                bindparam("plans", expanding=True),
                bindparam("steps", expanding=True),
            ),
            {"ids": list(real_ids), "plans": list(demo_plans) or [-1],
             "steps": list(demo_steps) or [-1]},
        ).all()
        dependency_checks["real_notes_on_demo_plans"] = len(rows)
        for _uid, pid, sid in rows:
            protect(plan_owner.get(pid) or step_owner.get(sid), "real_note")

        rows = conn.execute(
            text(
                "SELECT DISTINCT user_id, plan_id, task_id FROM focus_sessions "
                "WHERE user_id IN :ids AND (plan_id IN :plans OR task_id IN :tasks)"
            ).bindparams(
                bindparam("ids", expanding=True),
                bindparam("plans", expanding=True),
                bindparam("tasks", expanding=True),
            ),
            {"ids": list(real_ids), "plans": list(demo_plans) or [-1],
             "tasks": list(demo_tasks) or [-1]},
        ).all()
        dependency_checks["real_focus_on_demo"] = len(rows)
        for _uid, pid, tid in rows:
            protect(plan_owner.get(pid) or task_owner.get(tid), "real_focus")

        rows = conn.execute(
            text(
                "SELECT DISTINCT user_id, note_id FROM practice_records "
                "WHERE user_id IN :ids AND note_id IN :notes"
            ).bindparams(
                bindparam("ids", expanding=True),
                bindparam("notes", expanding=True),
            ),
            {"ids": list(real_ids), "notes": list(note_owner) or [-1]},
        ).all()
        dependency_checks["real_practice_on_demo_notes"] = len(rows)
        for _uid, note_id in rows:
            protect(note_owner.get(note_id), "real_practice")

        rows = conn.execute(
            text(
                "SELECT DISTINCT user_id, note_id FROM ai_requests "
                "WHERE user_id IN :ids AND note_id IN :notes"
            ).bindparams(
                bindparam("ids", expanding=True),
                bindparam("notes", expanding=True),
            ),
            {"ids": list(real_ids), "notes": list(note_owner) or [-1]},
        ).all()
        dependency_checks["real_ai_on_demo_notes"] = len(rows)
        for _uid, note_id in rows:
            protect(note_owner.get(note_id), "real_ai")

    protected_ids = set(protected)
    effective_demo = demo_ids - protected_ids
    effective_plans = {pid for pid in demo_plans if plan_owner[pid] in effective_demo}
    effective_steps = {sid for sid in demo_steps if step_owner[sid] in effective_demo}
    effective_tasks = {tid for tid in demo_tasks if task_owner[tid] in effective_demo}

    protected_report = [
        {
            "user_id": uid,
            "username": all_user_ids.get(uid),
            "reasons": sorted(set(reasons)),
        }
        for uid, reasons in sorted(protected.items())
    ]

    # ---------- 特殊账号预置学习数据（可选） ----------
    special_scope: dict[str, list] = {}
    special_blocked = False
    special_dependencies: dict[str, int] = {}
    if include_special:
        if not manifest:
            raise SystemExit(
                "--include-special-study-data 必须提供 --manifest，"
                "避免误删特殊账号的真实数据"
            )
        tables = manifest.get("tables", {})

        def owned(
            table: str,
            id_column: str,
            candidates,
            join_owner: str | None = None,
        ) -> list:
            if not candidates:
                return []
            found = set()
            for chunk in _chunks(candidates):
                if join_owner:
                    sql = (
                        f"SELECT t.{id_column}, p.user_id FROM {table} t "
                        f"JOIN study_plans p ON p.id = t.plan_id "
                        f"WHERE t.{id_column} IN :c"
                    )
                else:
                    sql = (
                        f"SELECT {id_column}, user_id FROM {table} "
                        f"WHERE {id_column} IN :c"
                    )
                rows = conn.execute(
                    text(sql).bindparams(bindparam("c", expanding=True)),
                    {"c": chunk},
                ).all()
                for row_id, owner in rows:
                    if int(owner) in special_ids:
                        found.add(row_id)
            return sorted(found)

        plan_candidates = [int(item) for item in tables.get("study_plans", {}).get("ids", [])]
        step_candidates = [int(item) for item in tables.get("plan_steps", {}).get("ids", [])]
        task_candidates = [int(item) for item in tables.get("daily_tasks", {}).get("ids", [])]
        special_scope["study_plans"] = owned("study_plans", "id", plan_candidates)
        special_scope["plan_steps"] = owned(
            "plan_steps", "id", step_candidates, join_owner="plan_id"
        )
        special_scope["daily_tasks"] = owned(
            "daily_tasks", "id", task_candidates, join_owner="plan_id"
        )
        for table in (
            "study_records", "knowledge_notes", "knowledge_review_records",
            "focus_sessions", "practice_records",
        ):
            special_scope[table] = owned(
                table,
                "id",
                [int(item) for item in tables.get(table, {}).get("ids", [])],
            )
        special_scope["ai_requests"] = owned(
            "ai_requests",
            "request_id",
            [str(item) for item in tables.get("ai_requests", {}).get("ids", [])],
        )
        special_scope["task_rollovers"] = [
            int(item) for item in tables.get("task_rollovers", {}).get("ids", [])
        ]

        # 真实数据是否依赖特殊账号的预置学习数据
        special_plans = set(special_scope["study_plans"])
        special_steps = set(special_scope["plan_steps"])
        special_tasks = set(special_scope["daily_tasks"])
        special_notes = set(special_scope["knowledge_notes"])
        if real_ids:
            special_dependencies = {
                "real_notes_on_special": int(
                    conn.execute(
                        text(
                            "SELECT COUNT(*) FROM knowledge_notes WHERE user_id IN :r "
                            "AND deleted_at IS NULL AND (plan_id IN :p OR step_id IN :s)"
                        ).bindparams(
                            bindparam("r", expanding=True),
                            bindparam("p", expanding=True),
                            bindparam("s", expanding=True),
                        ),
                        {"r": list(real_ids), "p": list(special_plans) or [-1],
                         "s": list(special_steps) or [-1]},
                    ).scalar_one()
                ),
                "real_focus_on_special": int(
                    conn.execute(
                        text(
                            "SELECT COUNT(*) FROM focus_sessions WHERE user_id IN :r "
                            "AND (plan_id IN :p OR task_id IN :t)"
                        ).bindparams(
                            bindparam("r", expanding=True),
                            bindparam("p", expanding=True),
                            bindparam("t", expanding=True),
                        ),
                        {"r": list(real_ids), "p": list(special_plans) or [-1],
                         "t": list(special_tasks) or [-1]},
                    ).scalar_one()
                ),
                "real_practice_on_special_notes": int(
                    conn.execute(
                        text(
                            "SELECT COUNT(*) FROM practice_records WHERE user_id IN :r "
                            "AND note_id IN :n"
                        ).bindparams(
                            bindparam("r", expanding=True),
                            bindparam("n", expanding=True),
                        ),
                        {"r": list(real_ids), "n": list(special_notes) or [-1]},
                    ).scalar_one()
                ),
                "real_ai_on_special_notes": int(
                    conn.execute(
                        text(
                            "SELECT COUNT(*) FROM ai_requests WHERE user_id IN :r "
                            "AND note_id IN :n"
                        ).bindparams(
                            bindparam("r", expanding=True),
                            bindparam("n", expanding=True),
                        ),
                        {"r": list(real_ids), "n": list(special_notes) or [-1]},
                    ).scalar_one()
                ),
            }
        dependency_checks.update(special_dependencies)
        special_blocked = any(special_dependencies.values())
        if special_blocked:
            warnings.append("检测到真实数据依赖，已跳过特殊账号预置数据清理")
            special_scope = {}

    plan_ids = effective_plans | set(special_scope.get("study_plans", []))
    step_ids = effective_steps | set(special_scope.get("plan_steps", []))
    task_ids = effective_tasks | set(special_scope.get("daily_tasks", []))
    record_ids = set(special_scope.get("study_records", []))
    note_ids = set(special_scope.get("knowledge_notes", []))
    review_ids = set(special_scope.get("knowledge_review_records", []))
    focus_ids = set(special_scope.get("focus_sessions", []))
    practice_ids = set(special_scope.get("practice_records", []))
    ai_ids = set(special_scope.get("ai_requests", []))
    audit_ids = (
        [int(item) for item in manifest.get("tables", {}).get("admin_audit_logs", {}).get("ids", [])]
        if manifest
        else []
    )

    return {
        "database": database,
        "demo_users_total": len(demo_ids),
        "demo_users_to_clean": len(effective_demo),
        "protected": protected_report,
        "dependencies": dependency_checks,
        "manifest": manifest_check,
        "special_cleanup": include_special and not special_blocked,
        "warnings": warnings,
        "scopes": {
            "users": sorted(effective_demo),
            "study_plans": sorted(plan_ids),
            "plan_steps": sorted(step_ids),
            "daily_tasks": sorted(task_ids),
            "study_records": sorted(record_ids),
            "knowledge_notes": sorted(note_ids),
            "knowledge_review_records": sorted(review_ids),
            "focus_sessions": sorted(focus_ids),
            "practice_records": sorted(practice_ids),
            "ai_requests": sorted(ai_ids),
            "admin_audit_logs": sorted(audit_ids),
        },
    }


def preview(conn, plan: dict) -> dict:
    scopes = plan["scopes"]
    users = scopes["users"]
    plans = scopes["study_plans"]
    steps = scopes["plan_steps"]
    tasks = scopes["daily_tasks"]
    counts = {
        "users": len(users),
        "study_plans": len(plans),
        "plan_steps": len(steps),
        "daily_tasks": len(tasks),
        "study_records": _count_ids(conn, "study_records", "user_id", users)
        + len(scopes["study_records"]),
        "knowledge_notes": _count_ids(conn, "knowledge_notes", "user_id", users)
        + len(scopes["knowledge_notes"]),
        "knowledge_review_records": _count_ids(
            conn, "knowledge_review_records", "user_id", users
        ) + len(scopes["knowledge_review_records"]),
        "focus_sessions": _count_ids(conn, "focus_sessions", "user_id", users)
        + len(scopes["focus_sessions"]),
        "practice_records": _count_ids(conn, "practice_records", "user_id", users)
        + len(scopes["practice_records"]),
        "ai_requests": _count_ids(conn, "ai_requests", "user_id", users)
        + _count_ids(conn, "ai_requests", "request_id", scopes["ai_requests"]),
        "task_rollovers": _count_task_rollovers(conn, tasks),
        "schedule_entries": _count_ids(conn, "schedule_entries", "step_id", steps),
        "admin_audit_logs": _count_audits(conn, scopes["admin_audit_logs"]),
    }
    return counts


def _count_task_rollovers(conn, task_ids) -> int:
    if not task_ids:
        return 0
    return int(
        conn.execute(
            text(
                "SELECT COUNT(*) FROM task_rollovers "
                "WHERE source_task_id IN :ids OR target_task_id IN :ids"
            ).bindparams(bindparam("ids", expanding=True)),
            {"ids": list(task_ids)},
        ).scalar_one()
    )


def _count_audits(conn, audit_ids) -> int:
    if audit_ids:
        return _count_ids(conn, "admin_audit_logs", "id", audit_ids)
    return int(
        conn.execute(
            text("SELECT COUNT(*) FROM admin_audit_logs WHERE reason LIKE :p"),
            {"p": DEMO_TAG + "%"},
        ).scalar_one()
    )


def execute(conn, plan: dict) -> dict:
    scopes = plan["scopes"]
    users = scopes["users"]
    plans = scopes["study_plans"]
    steps = scopes["plan_steps"]
    tasks = scopes["daily_tasks"]
    deleted: dict[str, int] = {}

    if tasks:
        deleted["task_rollovers"] = int(
            conn.execute(
                text(
                    "DELETE FROM task_rollovers "
                    "WHERE source_task_id IN :ids OR target_task_id IN :ids"
                ).bindparams(bindparam("ids", expanding=True)),
                {"ids": tasks},
            ).rowcount or 0
        )
    deleted["study_records"] = _delete_ids(conn, "study_records", "user_id", users) + _delete_ids(
        conn, "study_records", "id", scopes["study_records"]
    )
    deleted["practice_records"] = _delete_ids(conn, "practice_records", "user_id", users) + _delete_ids(
        conn, "practice_records", "id", scopes["practice_records"]
    )
    deleted["knowledge_review_records"] = _delete_ids(
        conn, "knowledge_review_records", "user_id", users
    ) + _delete_ids(
        conn, "knowledge_review_records", "id", scopes["knowledge_review_records"]
    )
    deleted["knowledge_notes"] = _delete_ids(conn, "knowledge_notes", "user_id", users) + _delete_ids(
        conn, "knowledge_notes", "id", scopes["knowledge_notes"]
    )
    deleted["focus_sessions"] = _delete_ids(conn, "focus_sessions", "user_id", users) + _delete_ids(
        conn, "focus_sessions", "id", scopes["focus_sessions"]
    )
    deleted["ai_requests"] = _delete_ids(conn, "ai_requests", "user_id", users) + _delete_ids(
        conn, "ai_requests", "request_id", scopes["ai_requests"]
    )
    deleted["daily_tasks"] = _delete_ids(conn, "daily_tasks", "id", tasks)
    deleted["schedule_entries"] = _delete_ids(conn, "schedule_entries", "step_id", steps)
    if steps:
        # 先断开自引用外键，再删除步骤。
        for chunk in _chunks(steps):
            conn.execute(
                text("UPDATE plan_steps SET parent_id = NULL WHERE id IN :ids").bindparams(
                    bindparam("ids", expanding=True)
                ),
                {"ids": chunk},
            )
    deleted["plan_steps"] = _delete_ids(conn, "plan_steps", "id", steps)
    deleted["study_plans"] = _delete_ids(conn, "study_plans", "id", plans)
    for table in ("email_verifications", "login_sessions", "refresh_tokens", "auth_events"):
        deleted[table] = _delete_ids(conn, table, "user_id", users)
    deleted["users"] = _delete_ids(conn, "users", "id", users)

    audit_ids = scopes["admin_audit_logs"]
    if audit_ids:
        deleted["admin_audit_logs"] = _delete_ids(conn, "admin_audit_logs", "id", audit_ids)
    else:
        deleted["admin_audit_logs"] = int(
            conn.execute(
                text("DELETE FROM admin_audit_logs WHERE reason LIKE :p"),
                {"p": DEMO_TAG + "%"},
            ).rowcount or 0
        )
    return deleted


def post_check(conn, before: dict, plan: dict) -> dict:
    after = {
        "users_total": int(conn.execute(text("SELECT COUNT(*) FROM users")).scalar_one()),
        "real_users": int(
            conn.execute(
                text("SELECT COUNT(*) FROM users WHERE username NOT REGEXP :p "
                     "AND username NOT IN ('admin', 'REED')"),
                {"p": DEMO_PATTERN},
            ).scalar_one()
        ),
        "special_users": int(
            conn.execute(
                text("SELECT COUNT(*) FROM users WHERE username IN ('admin', 'REED')")
            ).scalar_one()
        ),
        "demo_users": int(
            conn.execute(
                text("SELECT COUNT(*) FROM users WHERE username REGEXP :p"),
                {"p": DEMO_PATTERN},
            ).scalar_one()
        ),
        "demo_audits": int(
            conn.execute(
                text("SELECT COUNT(*) FROM admin_audit_logs WHERE reason LIKE :p"),
                {"p": DEMO_TAG + "%"},
            ).scalar_one()
        ),
    }
    return {
        "before": before,
        "after": after,
        "real_users_preserved": before["real_users"] == after["real_users"],
        "special_preserved": after["special_users"] == 2,
        "protected_users_kept": after["demo_users"] == len(plan["protected"]),
    }


def _baseline(conn) -> dict:
    return {
        "users_total": int(conn.execute(text("SELECT COUNT(*) FROM users")).scalar_one()),
        "real_users": int(
            conn.execute(
                text("SELECT COUNT(*) FROM users WHERE username NOT REGEXP :p "
                     "AND username NOT IN ('admin', 'REED')"),
                {"p": DEMO_PATTERN},
            ).scalar_one()
        ),
        "special_users": int(
            conn.execute(
                text("SELECT COUNT(*) FROM users WHERE username IN ('admin', 'REED')")
            ).scalar_one()
        ),
        "demo_users": int(
            conn.execute(
                text("SELECT COUNT(*) FROM users WHERE username REGEXP :p"),
                {"p": DEMO_PATTERN},
            ).scalar_one()
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="定向清理演示数据（默认预览）")
    parser.add_argument("--manifest", default=None, help="Seed Manifest 路径")
    parser.add_argument("--execute", action="store_true", help="实际执行删除")
    parser.add_argument(
        "--include-special-study-data",
        action="store_true",
        help="同时清理 admin/REED 的预置学习数据（保留账号，需提供清单）",
    )
    parser.add_argument("--allow-production", action="store_true")
    args = parser.parse_args()

    with engine.begin() as conn:
        database = guard(conn, args.allow_production)
        manifest_path = args.manifest
        if not manifest_path:
            latest = latest_manifest_for(database)
            if latest:
                manifest_path = str(latest)
        manifest = load_manifest(manifest_path) if manifest_path else None

        plan = collect(
            conn,
            include_special=args.include_special_study_data,
            manifest=manifest,
        )
        baseline = _baseline(conn)
        counts = preview(conn, plan)

        result = {
            "mode": "execute" if args.execute else "dry-run",
            "database": database,
            "manifest": manifest_path,
            "demo_users_total": plan["demo_users_total"],
            "demo_users_to_clean": plan["demo_users_to_clean"],
            "protected_users": plan["protected"],
            "dependencies": plan["dependencies"],
            "special_cleanup": plan["special_cleanup"],
            "warnings": plan["warnings"],
            "will_delete": counts,
        }
        if args.execute:
            result["deleted"] = execute(conn, plan)
            result["verification"] = post_check(conn, baseline, plan)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())