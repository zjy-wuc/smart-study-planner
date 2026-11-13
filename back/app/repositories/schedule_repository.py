
from sqlalchemy import text
from sqlalchemy.orm import Session


def find_entries(
    db: Session,
    step_id: int,
) -> list[dict]:
    """查询一个叶子节点的有效草稿安排"""

    sql = text("""
        SELECT
            id, step_id, task_date,
            content, target_quantity,
            sort_order
        FROM schedule_entries
        WHERE step_id = :step_id
          AND deleted_at IS NULL
        ORDER BY task_date, sort_order, id
    """)

    result = db.execute(sql, {
        "step_id": step_id,
    })

    return [
        dict(row)
        for row in result.mappings().all()
    ]


def soft_delete_entries(
    db: Session,
    step_id: int,
):
    """逻辑删除旧安排"""

    db.execute(
        text("""
            UPDATE schedule_entries
            SET deleted_at = UTC_TIMESTAMP()
            WHERE step_id = :step_id
              AND deleted_at IS NULL
        """),
        {"step_id": step_id},
    )


def insert_entries(
    db: Session,
    step_id: int,
    entries: list[dict],
):
    """批量插入新安排"""

    if not entries:
        return

    sql = text("""
        INSERT INTO schedule_entries (
            step_id,
            task_date,
            content,
            target_quantity,
            sort_order
        )
        VALUES (
            :step_id,
            :task_date,
            :content,
            :target_quantity,
            :sort_order
        )
    """)

    params = [
        {
            "step_id": step_id,
            "task_date": entry["task_date"],
            "content": entry["content"],
            "target_quantity": entry["target_quantity"],
            "sort_order": index,
        }
        for index, entry in enumerate(entries)
    ]

    db.execute(sql, params)
