
from datetime import date
from typing import Any, cast

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session


MAX_UINT64 = 2**64 - 1


def has_study_history(
    db: Session,
    task_id: int,
) -> bool:
    """是否存在打卡历史，即使累计数量已改回 0"""

    sql = text("""
        SELECT EXISTS (
            SELECT 1
            FROM study_records
            WHERE task_id = :task_id
        )
    """)

    result = db.scalar(
        sql,
        {"task_id": task_id},
    )

    return bool(result)


def get_incoming_quantity(
    db: Session,
    task_id: int,
) -> int:
    """
    当前任务累计接收过多少 NUMERIC 顺延数量。

    历史来源即使被删除，转入数量也不能凭空消失。
    """

    sql = text("""
        SELECT COALESCE(SUM(quantity), 0)
        FROM task_rollovers
        WHERE target_task_id = :task_id
    """)

    result = db.scalar(
        sql,
        {"task_id": task_id},
    )

    return int(result or 0)


def update_future_boolean(
    db: Session,
    task_id: int,
    today: date,
    content: str,
) -> int:
    """仅修改未来、未开始、未顺延来源的 BOOLEAN 任务"""

    sql = text("""
        UPDATE daily_tasks AS t
        SET t.content = :content
        WHERE t.id = :task_id
          AND t.task_type = 'BOOLEAN'
          AND t.task_date > :today
          AND t.status = 'PENDING'
          AND t.deleted_at IS NULL
          AND NOT EXISTS (
              SELECT 1
              FROM study_records AS r
              WHERE r.task_id = t.id
          )
          AND NOT EXISTS (
              SELECT 1
              FROM task_rollovers AS r
              WHERE r.source_task_id = t.id
          )
    """)

    result = cast(
        CursorResult[Any],
        db.execute(
            sql,
            {
                "task_id": task_id,
                "today": today,
                "content": content,
            },
        ),
    )

    return result.rowcount


def update_future_numeric(
    db: Session,
    task_id: int,
    today: date,
    target_quantity: int,
) -> int:
    """安全修改未来 NUMERIC 目标，不减少已承接的顺延量"""

    sql = text("""
        UPDATE daily_tasks AS t
        SET t.target_quantity = :new_target
        WHERE t.id = :task_id
          AND t.task_type = 'NUMERIC'
          AND t.task_date > :today
          AND t.status = 'PENDING'
          AND t.actual_quantity = 0
          AND t.rollover_out_quantity = 0
          AND t.deleted_at IS NULL
          AND NOT EXISTS (
              SELECT 1
              FROM study_records AS r
              WHERE r.task_id = t.id
          )
          AND NOT EXISTS (
              SELECT 1
              FROM task_rollovers AS r
              WHERE r.source_task_id = t.id
          )
          AND :new_target >= (
              SELECT COALESCE(SUM(r.quantity), 0)
              FROM task_rollovers AS r
              WHERE r.target_task_id = t.id
          )
    """)

    result = cast(
        CursorResult[Any],
        db.execute(
            sql,
            {
                "task_id": task_id,
                "today": today,
                "new_target": target_quantity,
            },
        ),
    )

    return result.rowcount


def recalculate_numeric_leaf_total(
    db: Session,
    plan_id: int,
    step_id: int,
) -> int:
    """
    重算 NUMERIC 叶子节点的有效目标总和。

    有效目标 = target_quantity - rollover_out_quantity
    逻辑删除的任务不参与计算。
    """

    sql = text("""
        SELECT
            COALESCE(SUM(
                CASE
                    WHEN target_quantity IS NULL
                      OR rollover_out_quantity IS NULL
                      OR rollover_out_quantity > target_quantity
                    THEN 0
                    ELSE target_quantity - rollover_out_quantity
                END
            ), 0) AS effective_total,

            COALESCE(SUM(
                CASE
                    WHEN target_quantity IS NULL
                      OR rollover_out_quantity IS NULL
                      OR rollover_out_quantity > target_quantity
                    THEN 1
                    ELSE 0
                END
            ), 0) AS invalid_count

        FROM daily_tasks
        WHERE plan_id = :plan_id
          AND step_id = :step_id
          AND task_type = 'NUMERIC'
          AND deleted_at IS NULL
    """)

    row = db.execute(
        sql,
        {
            "plan_id": plan_id,
            "step_id": step_id,
        },
    ).mappings().one()

    if row["invalid_count"]:
        raise HTTPException(
            status_code=409,
            detail="存在无效的 NUMERIC 任务数量，无法重算",
        )

    total = int(row["effective_total"])

    if total < 0 or total > MAX_UINT64:
        raise HTTPException(
            status_code=409,
            detail="叶子节点总目标超出数据库范围",
        )

    update_sql = text("""
        UPDATE plan_steps
        SET total_target = :total
        WHERE id = :step_id
          AND plan_id = :plan_id
          AND node_type = 'LEAF'
          AND task_type = 'NUMERIC'
          AND deleted_at IS NULL
    """)

    result = cast(
        CursorResult[Any],
        db.execute(
            update_sql,
            {
                "total": total,
                "step_id": step_id,
                "plan_id": plan_id,
            },
        ),
    )

    if result.rowcount != 1:
        raise RuntimeError(
            "NUMERIC 叶子节点目标更新失败"
        )

    return total
