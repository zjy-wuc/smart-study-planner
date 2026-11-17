
import json
from typing import Any, cast

from sqlalchemy import bindparam, text
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session


NOTE_COLUMNS = """
    id, user_id, plan_id, step_id,
    title, content_md, tags,
    created_at, updated_at, deleted_at
"""


def _as_note(row) -> dict | None:
    """将数据库查询结果转换为笔记字典。"""

    if row is None:
        return None

    note = dict(row)

    if isinstance(note["tags"], str):
        note["tags"] = json.loads(note["tags"])

    return note


def find_note(
    db: Session,
    note_id: int,
    user_id: int,
    deleted: bool = False,
    for_update: bool = False,
) -> dict | None:
    """查询属于当前用户的正常笔记或回收站笔记。"""

    deleted_condition = (
        "deleted_at IS NOT NULL"
        if deleted
        else "deleted_at IS NULL"
    )

    lock_sql = "FOR UPDATE" if for_update else ""

    sql = text(f"""
        SELECT {NOTE_COLUMNS}
        FROM knowledge_notes
        WHERE id = :note_id
          AND user_id = :user_id
          AND {deleted_condition}
        {lock_sql}
    """)

    row = db.execute(
        sql,
        {
            "note_id": note_id,
            "user_id": user_id,
        },
    ).mappings().first()

    return _as_note(row)


def list_notes(
    db: Session,
    user_id: int,
    deleted: bool,
    keyword: str | None,
    tag: str | None,
    plan_id: int | None,
    page: int,
    page_size: int,
) -> dict:
    """笔记列表、搜索、标签筛选和分页。"""

    conditions = [
        "user_id = :user_id",
        (
            "deleted_at IS NOT NULL"
            if deleted
            else "deleted_at IS NULL"
        ),
    ]

    # 参数可能包含 int、str 等类型
    params: dict[str, Any] = {
        "user_id": user_id,
    }

    if keyword:
        conditions.append("""
            (
                LOCATE(:keyword, title) > 0
                OR LOCATE(:keyword, content_md) > 0
            )
        """)
        params["keyword"] = keyword

    if tag:
        conditions.append(
            "JSON_CONTAINS(tags, JSON_QUOTE(:tag)) = 1"
        )
        params["tag"] = tag

    if plan_id is not None:
        conditions.append("plan_id = :plan_id")
        params["plan_id"] = plan_id

    where_sql = " AND ".join(conditions)

    total = db.execute(
        text(f"""
            SELECT COUNT(*)
            FROM knowledge_notes
            WHERE {where_sql}
        """),
        params,
    ).scalar_one()

    rows = db.execute(
        text(f"""
            SELECT {NOTE_COLUMNS}
            FROM knowledge_notes
            WHERE {where_sql}
            ORDER BY updated_at DESC, id DESC
            LIMIT :limit OFFSET :offset
        """),
        {
            **params,
            "limit": page_size,
            "offset": (page - 1) * page_size,
        },
    ).mappings().all()

    return {
        "items": [_as_note(row) for row in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


def insert_note(
    db: Session,
    user_id: int,
    values: dict,
) -> int:
    """新增笔记，返回数据库生成的 ID。"""

    sql = text("""
        INSERT INTO knowledge_notes (
            user_id, plan_id, step_id,
            title, content_md, tags
        )
        VALUES (
            :user_id, :plan_id, :step_id,
            :title, :content_md, :tags
        )
    """)

    result = cast(
        CursorResult,
        db.execute(
            sql,
            {
                "user_id": user_id,
                "plan_id": values["plan_id"],
                "step_id": values["step_id"],
                "title": values["title"],
                "content_md": values["content_md"],
                "tags": json.dumps(
                    values["tags"],
                    ensure_ascii=False,
                ),
            },
        ),
    )

    lastrowid = result.lastrowid

    if lastrowid is None:
        raise RuntimeError(
            "新增笔记失败：数据库未返回自增 ID"
        )

    return int(lastrowid)


def update_note(
    db: Session,
    note_id: int,
    user_id: int,
    changes: dict,
) -> int:
    """只更新允许修改的字段。"""

    allowed_fields = {
        "title",
        "content_md",
        "tags",
        "plan_id",
        "step_id",
    }

    assignments: list[str] = []

    # 修复 Pylance 对参数字典的类型推断
    params: dict[str, Any] = {
        "note_id": note_id,
        "user_id": user_id,
    }

    for field, value in changes.items():
        if field not in allowed_fields:
            raise ValueError("不允许修改的笔记字段")

        assignments.append(f"{field} = :{field}")

        params[field] = (
            json.dumps(value, ensure_ascii=False)
            if field == "tags"
            else value
        )

    if not assignments:
        return 0

    assignments.append("updated_at = NOW()")

    sql = text(f"""
        UPDATE knowledge_notes
        SET {", ".join(assignments)}
        WHERE id = :note_id
          AND user_id = :user_id
          AND deleted_at IS NULL
    """)

    result = cast(
        CursorResult,
        db.execute(sql, params),
    )

    return result.rowcount


def soft_delete_note(
    db: Session,
    note_id: int,
    user_id: int,
) -> int:
    """将笔记移入回收站。"""

    result = cast(
        CursorResult,
        db.execute(
            text("""
                UPDATE knowledge_notes
                SET deleted_at = NOW()
                WHERE id = :note_id
                  AND user_id = :user_id
                  AND deleted_at IS NULL
            """),
            {
                "note_id": note_id,
                "user_id": user_id,
            },
        ),
    )

    return result.rowcount


def restore_note(
    db: Session,
    note_id: int,
    user_id: int,
) -> int:
    """从回收站恢复笔记。"""

    result = cast(
        CursorResult,
        db.execute(
            text("""
                UPDATE knowledge_notes
                SET deleted_at = NULL
                WHERE id = :note_id
                  AND user_id = :user_id
                  AND deleted_at IS NOT NULL
            """),
            {
                "note_id": note_id,
                "user_id": user_id,
            },
        ),
    )

    return result.rowcount


def detach_plan(
    db: Session,
    plan_id: int,
) -> None:
    """计划软删除时解除全部关联，包括回收站笔记。"""

    db.execute(
        text("""
            UPDATE knowledge_notes
            SET plan_id = NULL,
                step_id = NULL,
                updated_at = NOW()
            WHERE plan_id = :plan_id
        """),
        {"plan_id": plan_id},
    )


def detach_steps(
    db: Session,
    step_ids: list[int],
) -> None:
    """LEAF 或子树软删除时解除步骤关联。"""

    if not step_ids:
        return

    sql = text("""
        UPDATE knowledge_notes
        SET step_id = NULL,
            updated_at = NOW()
        WHERE step_id IN :step_ids
    """).bindparams(
        bindparam("step_ids", expanding=True),
    )

    db.execute(
        sql,
        {"step_ids": step_ids},
    )
