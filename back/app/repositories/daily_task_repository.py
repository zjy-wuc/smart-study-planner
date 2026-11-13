
from sqlalchemy import text
from sqlalchemy.orm import Session


def count_plan_tasks(
    db: Session,
    plan_id: int,
) -> int:
    """检查计划是否已有正式任务"""

    sql = text("""
        SELECT COUNT(*)
        FROM daily_tasks
        WHERE plan_id = :plan_id
    """)

    return db.scalar(sql, {
        "plan_id": plan_id,
    })


def insert_tasks(
    db: Session,
    plan_id: int,
    tasks: list[dict],
):
    """批量生成正式每日任务"""

    if not tasks:
        return

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

    params = [
        {"plan_id": plan_id, **task}
        for task in tasks
    ]

    db.execute(sql, params)


def activate_plan(
    db: Session,
    plan_id: int,
    user_id: int,
):
    """把 DRAFT 计划切换为 ACTIVE"""

    sql = text("""
        UPDATE study_plans
        SET status = 'ACTIVE',
            started_at = UTC_TIMESTAMP()
        WHERE id = :plan_id
          AND user_id = :user_id
          AND status = 'DRAFT'
          AND deleted_at IS NULL
    """)

    result = db.execute(sql, {
        "plan_id": plan_id,
        "user_id": user_id,
    })

    if result.rowcount != 1:
        raise RuntimeError(
            "计划状态更新失败"
        )


def find_plan_tasks(
    db: Session,
    plan_id: int,
) -> list[dict]:
    """查询计划当前有效的每日任务"""

    sql = text("""
        SELECT
            t.id,
            t.plan_id,
            t.step_id,
            s.name AS step_name,
            t.task_date,
            t.task_type,
            t.content,
            t.target_quantity,
            t.actual_quantity,
            t.status,
            t.completed_at
        FROM daily_tasks AS t
        JOIN plan_steps AS s
          ON t.step_id = s.id
        WHERE t.plan_id = :plan_id
          AND t.deleted_at IS NULL
          AND s.deleted_at IS NULL
        ORDER BY
            t.task_date,
            t.step_id,
            t.id
    """)

    result = db.execute(sql, {
        "plan_id": plan_id,
    })

    return [
        dict(row)
        for row in result.mappings().all()
    ]
