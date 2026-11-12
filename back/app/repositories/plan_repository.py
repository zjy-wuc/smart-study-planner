
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


# 查询计划时统一返回的字段
PLAN_COLUMNS = """
    id,
    user_id,
    name,
    description,
    start_date,
    end_date,
    status,
    started_at,
    ended_at,
    deleted_at,
    created_at,
    updated_at
"""


def insert_plan(
    db: Session,
    user_id: int,
    name: str,
    description: str | None,
    start_date: date,
    end_date: date,
) -> int:
    """插入新的学习计划，返回新计划 ID"""

    sql = text("""
        INSERT INTO study_plans (
            user_id,
            name,
            description,
            start_date,
            end_date,
            status
        )
        VALUES (
            :user_id,
            :name,
            :description,
            :start_date,
            :end_date,
            'DRAFT'
        )
    """)

    result = db.execute(sql, {
        "user_id": user_id,
        "name": name,
        "description": description,
        "start_date": start_date,
        "end_date": end_date,
    })

    return result.lastrowid


def find_plan_by_id(
    db: Session,
    plan_id: int,
    user_id: int,
    for_update: bool = False,
) -> dict | None:
    """根据 ID 查询当前用户的计划"""

    lock_sql = "FOR UPDATE" if for_update else ""

    sql = text(f"""
        SELECT {PLAN_COLUMNS}
        FROM study_plans
        WHERE id = :plan_id
          AND user_id = :user_id
          AND deleted_at IS NULL
        {lock_sql}
    """)

    result = db.execute(sql, {
        "plan_id": plan_id,
        "user_id": user_id,
    })

    row = result.mappings().first()

    return dict(row) if row is not None else None


def find_plans_by_user(
    db: Session,
    user_id: int,
) -> list[dict]:
    """查询当前用户的全部有效计划"""

    sql = text(f"""
        SELECT {PLAN_COLUMNS}
        FROM study_plans
        WHERE user_id = :user_id
          AND deleted_at IS NULL
        ORDER BY created_at DESC, id DESC
    """)

    result = db.execute(sql, {
        "user_id": user_id,
    })

    return [
        dict(row)
        for row in result.mappings().all()
    ]


def update_plan_fields(
    db: Session,
    plan_id: int,
    user_id: int,
    changes: dict[str, Any],
) -> None:
    """更新计划的指定字段"""

    allowed_fields = {
        "name",
        "description",
        "start_date",
        "end_date",
    }

    # 只允许修改白名单中的字段
    if not changes:
        raise ValueError("没有需要更新的字段")

    if not set(changes).issubset(allowed_fields):
        raise ValueError("存在不允许更新的字段")

    set_clause = ", ".join(
        f"{field} = :{field}"
        for field in changes
    )

    sql = text(f"""
        UPDATE study_plans
        SET {set_clause}
        WHERE id = :plan_id
          AND user_id = :user_id
          AND deleted_at IS NULL
    """)

    params = {
        **changes,#解包changes字典，将键值对转换为参数绑定
        "plan_id": plan_id,
        "user_id": user_id,
    }

    db.execute(sql, params)

#软删除计划
def soft_delete_plan(
    db: Session,
    plan_id: int,
    user_id: int,
) -> None:
    """逻辑删除计划，不物理删除数据"""

    sql = text("""
        UPDATE study_plans
        SET deleted_at = UTC_TIMESTAMP()
        WHERE id = :plan_id
          AND user_id = :user_id
          AND deleted_at IS NULL
    """)

    db.execute(sql, {
        "plan_id": plan_id,
        "user_id": user_id,
    })
