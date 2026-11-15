
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session


def find_plan_for_update(
    db: Session,
    plan_id: int,
) -> dict | None:
    """供系统定时任务使用：锁定计划"""

    sql = text("""
        SELECT id, status, end_date
        FROM study_plans
        WHERE id = :plan_id
          AND deleted_at IS NULL
        FOR UPDATE
    """)

    row = db.execute(
        sql,
        {"plan_id": plan_id},
    ).mappings().first()

    return dict(row) if row else None


def find_expired_plan_ids(
    db: Session,
    today: date,
    limit: int = 500,
) -> list[int]:
    """查询到期但尚未结束的计划"""

    sql = text("""
        SELECT id
        FROM study_plans
        WHERE status = 'ACTIVE'
          AND end_date < :today
          AND deleted_at IS NULL
        ORDER BY id
        LIMIT :limit
    """)

    return list(
        db.scalars(sql, {
            "today": today,
            "limit": limit,
        }).all()
    )


def end_started_unfinished_tasks(
    db: Session,
    plan_id: int,
) -> int:
    """
    提前结束：已经开始但尚未完成的任务改为 ENDED。

    判断开始过的依据：
    1. 状态为 IN_PROGRESS；
    2. 当前实际数量大于 0；
    3. 存在真实打卡历史。
    """

    sql = text("""
        UPDATE daily_tasks AS t
        SET t.status = 'ENDED'
        WHERE t.plan_id = :plan_id
          AND t.deleted_at IS NULL
          AND t.status IN (
              'PENDING',
              'IN_PROGRESS',
              'OVERDUE'
          )
          AND (
              t.status = 'IN_PROGRESS'
              OR COALESCE(t.actual_quantity, 0) > 0
              OR EXISTS (
                  SELECT 1
                  FROM study_records AS r
                  WHERE r.task_id = t.id
              )
          )
    """)

    result = db.execute(sql, {
        "plan_id": plan_id,
    })

    return result.rowcount


def delete_unstarted_tasks(
    db: Session,
    plan_id: int,
) -> int:
    """提前结束：逻辑删除从未开始的任务"""

    sql = text("""
        UPDATE daily_tasks AS t
        SET t.deleted_at = UTC_TIMESTAMP()
        WHERE t.plan_id = :plan_id
          AND t.deleted_at IS NULL
          AND t.status IN (
              'PENDING',
              'IN_PROGRESS',
              'OVERDUE'
          )
          AND NOT (
              t.status = 'IN_PROGRESS'
              OR COALESCE(t.actual_quantity, 0) > 0
              OR EXISTS (
                  SELECT 1
                  FROM study_records AS r
                  WHERE r.task_id = t.id
              )
          )
    """)

    result = db.execute(sql, {
        "plan_id": plan_id,
    })

    return result.rowcount


def mark_plan_ended(
    db: Session,
    plan_id: int,
) -> int:
    """将 ACTIVE 计划切换为 ENDED"""

    sql = text("""
        UPDATE study_plans
        SET status = 'ENDED',
            ended_at = UTC_TIMESTAMP()
        WHERE id = :plan_id
          AND status = 'ACTIVE'
          AND deleted_at IS NULL
    """)

    result = db.execute(sql, {
        "plan_id": plan_id,
    })

    return result.rowcount
