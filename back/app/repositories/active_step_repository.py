
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.schemas.active_step import ActiveStepNode


def list_active_nodes(
    db: Session,
    plan_id: int,
) -> list[dict]:
    """查询当前计划全部未逻辑删除的节点"""

    sql = text("""
        SELECT
            id,
            parent_id,
            node_type,
            task_type
        FROM plan_steps
        WHERE plan_id = :plan_id
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


def next_sort_order(
    db: Session,
    plan_id: int,
    parent_id: int | None,
) -> int:
    """为同级新增节点计算排序值"""

    sql = text("""
        SELECT COALESCE(MAX(sort_order), -1) + 1
        FROM plan_steps
        WHERE plan_id = :plan_id
          AND parent_id <=> :parent_id
          AND deleted_at IS NULL
    """)

    return int(db.scalar(sql, {
        "plan_id": plan_id,
        "parent_id": parent_id,
    }))


def insert_node(
    db: Session,
    plan_id: int,
    parent_id: int | None,
    node: ActiveStepNode,
    sort_order: int,
) -> int:
    """插入节点，返回新节点 ID"""

    rule = (
        node.rule.model_dump()
        if node.rule is not None
        else {}
    )

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
            total_target,
            sort_order
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
            :total_target,
            :sort_order
        )
    """)

    result = db.execute(sql, {
        "plan_id": plan_id,
        "parent_id": parent_id,
        "name": node.name,
        "description": node.description,
        "node_type": node.node_type,
        "task_type": rule.get("task_type"),
        "schedule_mode": rule.get("schedule_mode"),
        "repeat_content": rule.get("repeat_content"),
        "total_target": rule.get("total_target"),
        "sort_order": sort_order,
    })

    return result.lastrowid


def soft_delete_nodes(
    db: Session,
    plan_id: int,
    node_ids: list[int],
) -> None:
    """逻辑删除指定节点集合"""

    if not node_ids:
        return

    sql = text("""
        UPDATE plan_steps
        SET deleted_at = UTC_TIMESTAMP()
        WHERE plan_id = :plan_id
          AND id IN :node_ids
          AND deleted_at IS NULL
    """).bindparams(
        bindparam("node_ids", expanding=True)
    )

    db.execute(sql, {
        "plan_id": plan_id,
        "node_ids": node_ids,
    })


def soft_delete_node_tasks(
    db: Session,
    plan_id: int,
    node_ids: list[int],
) -> None:
    """逻辑删除节点对应的每日任务，保留历史关联"""

    if not node_ids:
        return

    sql = text("""
        UPDATE daily_tasks
        SET deleted_at = UTC_TIMESTAMP()
        WHERE plan_id = :plan_id
          AND step_id IN :node_ids
          AND deleted_at IS NULL
    """).bindparams(
        bindparam("node_ids", expanding=True)
    )

    db.execute(sql, {
        "plan_id": plan_id,
        "node_ids": node_ids,
    })
