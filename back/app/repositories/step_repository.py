
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session


STEP_COLUMNS = """
    id, plan_id, parent_id,
    name, description, node_type,
    task_type, schedule_mode,
    repeat_content, total_target,
    sort_order, created_at, updated_at
"""


def find_step(
    db: Session,
    plan_id: int,
    step_id: int,
) -> dict | None:
    """查询计划中的一个有效节点"""

    sql = text(f"""
        SELECT {STEP_COLUMNS}
        FROM plan_steps
        WHERE id = :step_id
          AND plan_id = :plan_id
          AND deleted_at IS NULL
    """)

    row = db.execute(sql, {
        "step_id": step_id,
        "plan_id": plan_id,
    }).mappings().first()

    return dict(row) if row else None


def find_all_steps(
    db: Session,
    plan_id: int,
) -> list[dict]:
    """一次查询计划的全部有效节点"""

    sql = text(f"""
        SELECT {STEP_COLUMNS}
        FROM plan_steps
        WHERE plan_id = :plan_id
          AND deleted_at IS NULL
        ORDER BY sort_order, id
    """)

    result = db.execute(sql, {
        "plan_id": plan_id,
    })

    return [
        dict(row)
        for row in result.mappings().all()
    ]


def insert_step(
    db: Session,
    plan_id: int,
    parent_id: int | None,
    values: dict[str, Any],
) -> int:
    """插入一个节点，返回数据库生成的 ID"""

    sql = text("""
        INSERT INTO plan_steps (
            plan_id,
            parent_id,
            name,
            description,
            node_type,
            task_type,
            schedule_mode,
            repeat_content,
            total_target
        )
        VALUES (
            :plan_id,
            :parent_id,
            :name,
            :description,
            :node_type,
            :task_type,
            :schedule_mode,
            :repeat_content,
            :total_target
        )
    """)

    result = db.execute(sql, {
        "plan_id": plan_id,
        "parent_id": parent_id,
        **values,
    })

    return result.lastrowid


def update_step_fields(
    db: Session,
    plan_id: int,
    step_id: int,
    changes: dict,
):
    """修改节点名称或描述"""

    allowed_fields = {"name", "description"}

    if not changes:
        raise ValueError("没有需要修改的字段")

    if not set(changes).issubset(allowed_fields):
        raise ValueError("包含不允许修改的字段")

    set_clause = ", ".join(
        f"{field} = :{field}"
        for field in changes
    )

    sql = text(f"""
        UPDATE plan_steps
        SET {set_clause}
        WHERE id = :step_id
          AND plan_id = :plan_id
          AND deleted_at IS NULL
    """)

    db.execute(sql, {
        **changes,
        "step_id": step_id,
        "plan_id": plan_id,
    })


def update_step_rule(
    db: Session,
    plan_id: int,
    step_id: int,
    values: dict,
):
    """替换叶子节点的执行规则"""

    sql = text("""
        UPDATE plan_steps
        SET task_type = :task_type,
            schedule_mode = :schedule_mode,
            repeat_content = :repeat_content,
            total_target = :total_target
        WHERE id = :step_id
          AND plan_id = :plan_id
          AND node_type = 'LEAF'
          AND deleted_at IS NULL
    """)

    db.execute(sql, {
        **values,
        "step_id": step_id,
        "plan_id": plan_id,
    })


def clear_draft_schedule(
    db: Session,
    step_id: int,
):
    """执行规则变化时清除旧的草稿每日安排"""

    sql = text("""
        UPDATE schedule_entries
        SET deleted_at = UTC_TIMESTAMP()
        WHERE step_id = :step_id
          AND deleted_at IS NULL
    """)

    db.execute(sql, {
        "step_id": step_id,
    })


def find_descendant_ids(
    db: Session,
    plan_id: int,
    step_id: int,
) -> list[int]:
    """找出一个节点以及它所有的后代节点"""

    sql = text("""
        WITH RECURSIVE descendants AS (
            SELECT id
            FROM plan_steps
            WHERE id = :step_id
              AND plan_id = :plan_id
              AND deleted_at IS NULL

            UNION ALL

            SELECT child.id
            FROM plan_steps AS child
            JOIN descendants AS d
              ON child.parent_id = d.id
            WHERE child.plan_id = :plan_id
              AND child.deleted_at IS NULL
        )
        SELECT id FROM descendants
    """)

    rows = db.execute(sql, {
        "plan_id": plan_id,
        "step_id": step_id,
    }).scalars().all()

    return list(rows)


def soft_delete_steps(
    db: Session,
    plan_id: int,
    step_ids: list[int],
):
    """批量逻辑删除节点"""

    if not step_ids:
        return

    sql = text("""
        UPDATE plan_steps
        SET deleted_at = UTC_TIMESTAMP()
        WHERE plan_id = :plan_id
          AND id IN :step_ids
          AND deleted_at IS NULL
    """).bindparams(
        bindparam("step_ids", expanding=True)
    )

    db.execute(sql, {
        "plan_id": plan_id,
        "step_ids": step_ids,
    })


def count_active_children(
    db: Session,
    parent_id: int,
) -> int:
    """统计某个节点剩余的有效子节点"""

    sql = text("""
        SELECT COUNT(*)
        FROM plan_steps
        WHERE parent_id = :parent_id
          AND deleted_at IS NULL
    """)

    return db.scalar(sql, {
        "parent_id": parent_id,
    })
