
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session


def has_rollover_from_source(
    db: Session,
    source_task_id: int,
) -> bool:
    """检查来源是否有历史顺延，目标删除后仍保留约束。"""

    sql = text("""
        SELECT id
        FROM task_rollovers
        WHERE source_task_id = :source_id
        LIMIT 1
        FOR UPDATE
    """)

    result = db.scalar(sql, {
        "source_id": source_task_id,
    })

    return result is not None


def find_numeric_target(
    db: Session,
    plan_id: int,
    step_id: int,
    target_date: date,
) -> dict | None:
    """锁定目标日期已有的有效 NUMERIC 任务"""

    sql = text("""
        SELECT
            t.id,
            t.target_quantity,
            t.actual_quantity,
            t.rollover_out_quantity,
            t.status
        FROM daily_tasks AS t
        WHERE t.plan_id = :plan_id
          AND t.step_id = :step_id
          AND t.task_date = :target_date
          AND t.task_type = 'NUMERIC'
          AND t.deleted_at IS NULL
        FOR UPDATE
    """)

    row = db.execute(sql, {
        "plan_id": plan_id,
        "step_id": step_id,
        "target_date": target_date,
    }).mappings().first()

    if row is None:
        return None

    target = dict(row)
    # 使用锁定读获取最新的打卡历史，避免事务快照过期。
    target["has_study_records"] = db.scalar(text("""
        SELECT id FROM study_records
        WHERE task_id = :target_id
        LIMIT 1 FOR UPDATE
    """), {"target_id": target["id"]}) is not None
    return target


def insert_rollover_target(
    db: Session,
    source: dict,
    target_date: date,
    quantity: int | None,
) -> int:
    """创建新的未来任务"""

    sql = text("""
        INSERT INTO daily_tasks (
            plan_id,
            step_id,
            task_date,
            task_type,
            content,
            target_quantity,
            status
        )
        VALUES (
            :plan_id,
            :step_id,
            :task_date,
            :task_type,
            :content,
            :target_quantity,
            'PENDING'
        )
    """)

    result = db.execute(sql, {
        "plan_id": source["plan_id"],
        "step_id": source["step_id"],
        "task_date": target_date,
        "task_type": source["task_type"],
        "content": source["content"],
        "target_quantity": quantity,
    })

    return result.lastrowid


def add_quantity_to_target(
    db: Session,
    target_task_id: int,
    quantity: int,
) -> int:
    """合并数量到未开始的 NUMERIC 任务"""

    sql = text("""
        UPDATE daily_tasks
        SET target_quantity = target_quantity + :quantity
        WHERE id = :target_id
          AND task_type = 'NUMERIC'
          AND status = 'PENDING'
          AND actual_quantity = 0
          AND rollover_out_quantity = 0
          AND NOT EXISTS (
              SELECT 1 FROM study_records AS r
              WHERE r.task_id = :target_id
          )
          AND deleted_at IS NULL
    """)

    result = db.execute(sql, {
        "target_id": target_task_id,
        "quantity": quantity,
    })

    return result.rowcount


def add_source_rollover_quantity(
    db: Session,
    source_task_id: int,
    quantity: int,
    expected_out: int,
    expected_actual: int,
    expected_target: int,
) -> int:
    """原子结算来源任务并记录已转移数量。"""

    sql = text("""
        UPDATE daily_tasks
        SET rollover_out_quantity = rollover_out_quantity + :quantity,
            status = 'COMPLETED',
            completed_at = UTC_TIMESTAMP()
        WHERE id = :source_id
          AND task_type = 'NUMERIC'
          AND status IN ('PENDING', 'IN_PROGRESS', 'OVERDUE')
          AND actual_quantity = :expected_actual
          AND target_quantity = :expected_target
          AND rollover_out_quantity = :expected_out
          AND :quantity > 0
          AND actual_quantity + rollover_out_quantity + :quantity = target_quantity
          AND deleted_at IS NULL
    """)

    result = db.execute(sql, {
        "source_id": source_task_id,
        "quantity": quantity,
        "expected_out": expected_out,
        "expected_actual": expected_actual,
        "expected_target": expected_target,
    })

    return result.rowcount


def insert_rollover_relation(
    db: Session,
    source_task_id: int,
    target_task_id: int,
    quantity: int | None,
) -> int:
    """保存来源任务与目标任务之间的关系"""

    sql = text("""
        INSERT INTO task_rollovers (
            source_task_id,
            target_task_id,
            quantity
        )
        VALUES (
            :source_id,
            :target_id,
            :quantity
        )
    """)

    result = db.execute(sql, {
        "source_id": source_task_id,
        "target_id": target_task_id,
        "quantity": quantity,
    })

    return result.lastrowid
