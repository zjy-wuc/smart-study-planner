from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.core.clock import business_today

from app.repositories.admin import statistics_repository

from app.services.knowledge import ai_runtime_service

AI_STATUSES = (
    "SUCCESS",
    "ERROR",
    "TIMEOUT",
    "CANCELLED",
    "BLOCKED",
    "STALE",
    "RUNNING",
    "RUNNING_EXPIRED",
    "OTHER",
)

AI_OPERATIONS = (
    "GENERATE",
    "ORGANIZE",
    "SUMMARY",
    "ASK",
    "PRACTICE_GENERATE",
    "PRACTICE_GRADE",
    "OTHER",
)


def get_dashboard(
    db: Session,
) -> dict:

    today = business_today()

    start_date = today - timedelta(days=6)

    start_at = datetime.combine(
        start_date,
        time.min,
    )

    end_exclusive = datetime.combine(
        today + timedelta(days=1),
        time.min,
    )

    # 1. 用户统计

    user_counts = statistics_repository.get_user_counts(
        db,
    )

    new_user_rows = (
        statistics_repository.get_daily_new_users(
            db,
            start_at,
            end_exclusive,
        )
    )

    # 2. 学习打卡统计

    total_checkins = (
        statistics_repository.count_checkins(db)
    )

    learning_rows = (
        statistics_repository.get_daily_learning_activity(
            db,
            start_at,
            end_exclusive,
        )
    )

    # 3. 计划统计

    raw_plan_counts = (
        statistics_repository.get_plan_status_counts(db)
    )

    plan_counts = {
        "DRAFT": raw_plan_counts.get("DRAFT", 0),
        "ACTIVE": raw_plan_counts.get("ACTIVE", 0),
        "ENDED": raw_plan_counts.get("ENDED", 0),
    }

    # 4. 笔记统计

    note_count = statistics_repository.count_notes(db)

    # 5. 今日 AI 用量

    today_ai_requests = (
        statistics_repository.count_ai_requests(
            db,
            today,
        )
    )

    # 6. 将数据库结果转换为日期映射

    new_user_map = {
        str(row["date"]): int(row["new_user_count"])
        for row in new_user_rows
    }

    learning_map = {
        str(row["date"]): row
        for row in learning_rows
    }

    # 7. 补齐连续7天数据

    daily_trend = []

    for offset in range(7):

        current_date = start_date + timedelta(
            days=offset,
        )

        date_key = current_date.isoformat()

        learning = learning_map.get(date_key, {})

        daily_trend.append({
            "date": date_key,
            "new_user_count": new_user_map.get(
                date_key, 0,
            ),
            "active_user_count": int(
                learning.get("active_user_count", 0)
            ),
            "checkin_count": int(
                learning.get("checkin_count", 0)
            ),
        })

    # 最后一项始终为今天

    today_trend = daily_trend[-1]

    # 8. 返回 Dashboard 数据

    return {
        "as_of_date": today.isoformat(),

        "overview": {
            "total_users": int(
                user_counts["total_users"]
            ),
            "enabled_users": int(
                user_counts["enabled_users"]
            ),
            "disabled_users": int(
                user_counts["disabled_users"]
            ),

            "new_users_today": (
                today_trend["new_user_count"]
            ),

            "learning_active_users_today": (
                today_trend["active_user_count"]
            ),

            "total_checkins": total_checkins,

            "today_checkins": (
                today_trend["checkin_count"]
            ),

            "total_plans": sum(
                plan_counts.values()
            ),

            "active_plans": plan_counts["ACTIVE"],

            "total_notes": note_count,

            "today_ai_requests": today_ai_requests,
        },

        "daily_trend": daily_trend,

        "plan_status_distribution": plan_counts,
    }


def get_ai_statistics(
    db: Session,
) -> dict:

    today = business_today()

    start_date = today - timedelta(days=6)

    end_exclusive = today + timedelta(days=1)

    # 1. 近7日 AI 调用趋势

    daily_rows = (
        statistics_repository.get_daily_ai_counts(
            db,
            start_date,
            end_exclusive,
        )
    )

    daily_map = {
        str(row["date"]): int(row["request_count"])
        for row in daily_rows
    }

    daily_trend = []

    for offset in range(7):

        current_date = start_date + timedelta(
            days=offset,
        )

        date_key = current_date.isoformat()

        daily_trend.append({
            "date": date_key,
            "request_count": daily_map.get(
                date_key, 0,
            ),
        })

    today_used = daily_trend[-1]["request_count"]

    # 2. 请求状态及当前有效并发

    ai_state = statistics_repository.get_ai_state(
        db,
        today,
    )

    status_counts = {
        status: 0
        for status in AI_STATUSES
    }

    for status, count in ai_state["status_counts"].items():

        key = (
            status
            if status in status_counts
            else "OTHER"
        )

        status_counts[key] += count

    # 3. AI 功能分布

    raw_operation_counts = (
        statistics_repository.get_ai_operation_counts(
            db,
            today,
        )
    )

    operation_counts = {
        operation: 0
        for operation in AI_OPERATIONS
    }

    for operation, count in raw_operation_counts.items():

        key = (
            operation
            if operation in operation_counts
            else "OTHER"
        )

        operation_counts[key] += count

    # 4. 当前生效的额度
    # A3 阶段 Guard 仍使用静态 settings。
    # A4 接入动态配置后，统一替换这里。

    runtime_config = ai_runtime_service.public_config(
        ai_runtime_service.read_config(db)
    )

    global_daily_limit = runtime_config[
        "effective_global_daily_limit"
    ]

    return {
        "as_of_date": today.isoformat(),

        "overview": {
            "today_used": today_used,

            "today_remaining": max(
                global_daily_limit - today_used,
                0,
            ),

            "today_success": status_counts["SUCCESS"],

            "today_failed": (
                status_counts["ERROR"]
                + status_counts["TIMEOUT"]
            ),

            "today_cancelled": (
                status_counts["CANCELLED"]
            ),

            "current_active": ai_state["active_count"],
        },

        "config": {
    "enabled": runtime_config[
        "effective_enabled"
    ],

    "configured_enabled": runtime_config[
        "enabled"
    ],

    "user_daily_limit": runtime_config[
        "effective_user_daily_limit"
    ],

    "global_daily_limit": global_daily_limit,

    "user_concurrency": (
        settings.AI_USER_CONCURRENCY
    ),

    "global_concurrency": (
        settings.AI_GLOBAL_CONCURRENCY
    ),

    "model_configured": runtime_config[
        "model_configured"
    ],
},
        "daily_trend": daily_trend,

        "status_distribution": status_counts,

        "operation_distribution": operation_counts,
    }