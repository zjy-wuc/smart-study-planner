
from sqlalchemy import text
from sqlalchemy.orm import Session


def find_effective_leaves(
    db: Session,
    plan_id: int,
) -> list[dict]:
    """查询计划中所有未删除的叶子节点"""

    sql = text("""
        SELECT
            id,
            parent_id,
            name,
            task_type
        FROM plan_steps
        WHERE plan_id = :plan_id
          AND node_type = 'LEAF'
          AND deleted_at IS NULL
        ORDER BY id
    """)

    result = db.execute(sql, {
        "plan_id": plan_id,
    })

    return [
        dict(row)
        for row in result.mappings().all()
    ]


def find_progress_tasks(
    db: Session,
    plan_id: int,
) -> list[dict]:
    """
    查询有效叶子节点下的全部有效任务。

    has_rollover：
    判断当前任务是否曾作为顺延来源。
    BOOLEAN 统计需要使用这个字段。
    """

    sql = text("""
        SELECT
            t.id,
            t.step_id,
            t.task_type,
            t.status,
            t.target_quantity,
            t.actual_quantity,
            t.rollover_out_quantity,

            EXISTS (
                SELECT 1
                FROM task_rollovers AS r
                WHERE r.source_task_id = t.id
            ) AS has_rollover

        FROM daily_tasks AS t

        JOIN plan_steps AS s
          ON s.id = t.step_id
         AND s.plan_id = t.plan_id

        WHERE t.plan_id = :plan_id
          AND t.deleted_at IS NULL
          AND s.deleted_at IS NULL
          AND s.node_type = 'LEAF'

        ORDER BY t.step_id, t.id
    """)

    result = db.execute(sql, {
        "plan_id": plan_id,
    })

    return [
        dict(row)
        for row in result.mappings().all()
    ]
