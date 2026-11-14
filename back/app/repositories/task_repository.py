from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session


TASK_COLUMNS = """
    t.id,
    t.plan_id,
    t.step_id,
    s.name AS step_name,
    t.task_date,
    t.task_type,
    t.content,
    t.target_quantity,
    t.actual_quantity,
    t.rollover_out_quantity,
    t.status,
    t.completed_at,
    t.created_at,
    t.updated_at,
    p.status AS plan_status,
    p.start_date AS plan_start_date,
    p.end_date AS plan_end_date,
    EXISTS (SELECT 1 FROM task_rollovers AS r
            WHERE r.source_task_id = t.id) AS has_rollover
"""


def find_owned_task(
    db: Session,
    task_id: int,
    user_id: int,
    for_update: bool = False,
) -> dict | None:
    """
    根据任务 ID 查询当前用户的有效任务。

    for_update=True 时锁定数据库记录，
    防止两个请求同时修改同一个任务。
    """

    lock_sql = "FOR UPDATE" if for_update else ""

    sql = text(f"""
        SELECT {TASK_COLUMNS}
        FROM daily_tasks AS t
        JOIN study_plans AS p
          ON t.plan_id = p.id
        JOIN plan_steps AS s
          ON t.step_id = s.id
         AND s.plan_id = p.id
        WHERE t.id = :task_id
          AND p.user_id = :user_id
          AND t.deleted_at IS NULL
          AND p.deleted_at IS NULL
          AND s.deleted_at IS NULL
        {lock_sql}
    """)

    result = db.execute(sql, {
        "task_id": task_id,
        "user_id": user_id,
    })

    row = result.mappings().first()

    if row is None:
        return None

    task = dict(row)
    if for_update:
        # 锁定读避免使用此前认证查询建立的旧事务快照。
        task["has_rollover"] = db.scalar(text("""
            SELECT id FROM task_rollovers
            WHERE source_task_id = :task_id
            LIMIT 1 FOR UPDATE
        """), {"task_id": task_id}) is not None
    return task


def find_today_tasks(
    db: Session,
    user_id: int,
    today: date,
) -> list[dict]:
    """查询当前用户所有 ACTIVE 计划的今日任务"""

    sql = text(f"""
        SELECT {TASK_COLUMNS}
        FROM daily_tasks AS t
        JOIN study_plans AS p
          ON t.plan_id = p.id
        JOIN plan_steps AS s
          ON t.step_id = s.id
         AND s.plan_id = p.id
        WHERE p.user_id = :user_id
          AND p.status = 'ACTIVE'
          AND p.start_date <= :today
          AND p.end_date >= :today
          AND t.task_date = :today
          AND t.deleted_at IS NULL
          AND p.deleted_at IS NULL
          AND s.deleted_at IS NULL
        ORDER BY t.plan_id, t.step_id, t.id
    """)

    result = db.execute(sql, {
        "user_id": user_id,
        "today": today,
    })

    return [
        dict(row)
        for row in result.mappings().all()
    ]


def mark_boolean_completed(
    db: Session,
    task_id: int,
) -> None:
    """将 BOOLEAN 任务更新为 COMPLETED"""

    sql = text("""
        UPDATE daily_tasks
        SET status = 'COMPLETED',
            completed_at = UTC_TIMESTAMP()
        WHERE id = :task_id
          AND task_type = 'BOOLEAN'
          AND NOT EXISTS (
              SELECT 1 FROM task_rollovers AS r
              WHERE r.source_task_id = :task_id
          )
          AND status IN (
              'PENDING',
              'IN_PROGRESS',
              'OVERDUE'
          )
          AND deleted_at IS NULL
    """)

    result = db.execute(sql, {
        "task_id": task_id,
    })

    if result.rowcount != 1:
        raise RuntimeError("BOOLEAN 任务状态更新失败")


def update_numeric_progress(
    db: Session,
    task_id: int,
    actual_quantity: int,
    new_status: str,
) -> None:
    """更新 NUMERIC 当前累计数量与状态"""

    sql = text("""
        UPDATE daily_tasks
        SET actual_quantity = :actual_quantity,
            status = :new_status,
            completed_at = CASE
                WHEN :new_status = 'COMPLETED'
                THEN UTC_TIMESTAMP()
                ELSE NULL
            END
        WHERE id = :task_id
          AND task_type = 'NUMERIC'
          AND rollover_out_quantity = 0
          AND status IN (
              'PENDING',
              'IN_PROGRESS',
              'OVERDUE'
          )
          AND deleted_at IS NULL
    """)

    result = db.execute(sql, {
        "task_id": task_id,
        "actual_quantity": actual_quantity,
        "new_status": new_status,
    })

    if result.rowcount != 1:
        raise RuntimeError("NUMERIC 任务数量更新失败")


def insert_study_record(
    db: Session,
    task_id: int,
    user_id: int,
    event_type: str,
    recorded_value: int | None,
    task_date: date,
) -> int:
    """写入一次打卡历史记录"""

    sql = text("""
        INSERT INTO study_records (
            task_id,
            user_id,
            event_type,
            recorded_value,
            task_date
        )
        VALUES (
            :task_id,
            :user_id,
            :event_type,
            :recorded_value,
            :task_date
        )
    """)

    result = db.execute(sql, {
        "task_id": task_id,
        "user_id": user_id,
        "event_type": event_type,
        "recorded_value": recorded_value,
        "task_date": task_date,
    })

    return result.lastrowid


def find_study_records(
    db: Session,
    task_id: int,
) -> list[dict]:
    """查询指定任务的历史打卡记录"""

    sql = text("""
        SELECT
            id,
            task_id,
            event_type,
            recorded_value,
            task_date,
            recorded_at
        FROM study_records
        WHERE task_id = :task_id
        ORDER BY recorded_at, id
    """)

    result = db.execute(sql, {
        "task_id": task_id,
    })

    return [
        dict(row)
        for row in result.mappings().all()
    ]


def soft_delete_task(
    db: Session,
    task_id: int,
) -> None:
    """逻辑删除任务，不删除打卡历史"""

    sql = text("""
        UPDATE daily_tasks
        SET deleted_at = UTC_TIMESTAMP()
        WHERE id = :task_id
          AND deleted_at IS NULL
    """)

    result = db.execute(sql, {
        "task_id": task_id,
    })

    if result.rowcount != 1:
        raise RuntimeError("任务删除失败")
