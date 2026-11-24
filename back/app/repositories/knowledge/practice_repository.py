import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from typing import cast
from sqlalchemy.engine import CursorResult

def _as_record(row) -> dict | None:
    """将完整练习记录转换为可返回的字典。"""

    if row is None:
        return None

    record = dict(row)

    questions = record.pop("questions_json")

    if isinstance(questions, str):
        questions = json.loads(questions)

    record["questions"] = questions
    record["score"] = float(record["score"])
    record["created_at"] = record["created_at"].isoformat()

    if "source_note_deleted" in record:
        record["source_note_deleted"] = bool(
            record["source_note_deleted"]
        )

    return record


def _as_summary(row) -> dict:
    """历史列表摘要，不包含完整题目 JSON。"""

    record = dict(row)

    record["score"] = float(record["score"])
    record["created_at"] = record["created_at"].isoformat()
    record["source_note_deleted"] = bool(
        record["source_note_deleted"]
    )

    return record


def find_by_generation(
    db: Session,
    user_id: int,
    generation_id: str,
) -> dict | None:
    """按用户及生成标识查询，防止重复保存。"""

    row = db.execute(
        text("""
            SELECT
                id,
                user_id,
                note_id,
                note_title_snapshot,
                generation_id,
                question_count,
                score,
                questions_json,
                created_at
            FROM practice_records
            WHERE user_id = :user_id
              AND generation_id = :generation_id
        """),
        {
            "user_id": user_id,
            "generation_id": generation_id,
        },
    ).mappings().first()

    return _as_record(row)


def find_existing_note_id(
    db: Session,
    user_id: int,
    note_id: int,
) -> int | None:
    """判断原笔记是否仍然存在，包括软删除笔记。"""

    result = db.execute(
        text("""
            SELECT id
            FROM knowledge_notes
            WHERE id = :note_id
              AND user_id = :user_id
            FOR UPDATE
        """),
        {
            "note_id": note_id,
            "user_id": user_id,
        },
    ).scalar_one_or_none()

    return int(result) if result is not None else None


def insert_record(
    db: Session,
    user_id: int,
    note_id: int | None,
    note_title_snapshot: str,
    generation_id: str,
    question_count: int,
    score: float,
    questions: list[dict],
) -> None:
    """保存已经完整批改成功的练习。"""

    db.execute(
        text("""
            INSERT INTO practice_records (
                user_id,
                note_id,
                note_title_snapshot,
                generation_id,
                question_count,
                score,
                questions_json
            )
            VALUES (
                :user_id,
                :note_id,
                :note_title_snapshot,
                :generation_id,
                :question_count,
                :score,
                :questions_json
            )
        """),
        {
            "user_id": user_id,
            "note_id": note_id,
            "note_title_snapshot": note_title_snapshot,
            "generation_id": generation_id,
            "question_count": question_count,
            "score": score,
            "questions_json": json.dumps(
                questions,
                ensure_ascii=False,
            ),
        },
    )


def list_records(
    db: Session,
    user_id: int,
    note_id: int | None,
    page: int,
    page_size: int,
) -> dict:
    """分页查询本人历史，可按原笔记 ID 筛选。"""

    where_sql = "p.user_id = :user_id"

    params = {
        "user_id": user_id,
    }

    if note_id is not None:
        where_sql += " AND p.note_id = :note_id"
        params["note_id"] = note_id

    total = db.execute(
        text(f"""
            SELECT COUNT(*)
            FROM practice_records AS p
            WHERE {where_sql}
        """),
        params,
    ).scalar_one()

    rows = db.execute(
        text(f"""
            SELECT
                p.id,
                p.note_id,
                p.note_title_snapshot,
                p.question_count,
                p.score,
                p.created_at,
                CASE
                    WHEN n.id IS NULL THEN 1
                    ELSE 0
                END AS source_note_deleted
            FROM practice_records AS p
            LEFT JOIN knowledge_notes AS n
              ON n.id = p.note_id
             AND n.deleted_at IS NULL
            WHERE {where_sql}
            ORDER BY p.created_at DESC, p.id DESC
            LIMIT :limit OFFSET :offset
        """),
        {
            **params,
            "limit": page_size,
            "offset": (page - 1) * page_size,
        },
    ).mappings().all()

    return {
        "items": [_as_summary(row) for row in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


def find_record(
    db: Session,
    record_id: int,
    user_id: int,
) -> dict | None:
    """查询本人单条练习的完整历史。"""

    row = db.execute(
        text("""
            SELECT
                p.id,
                p.user_id,
                p.note_id,
                p.note_title_snapshot,
                p.generation_id,
                p.question_count,
                p.score,
                p.questions_json,
                p.created_at,
                CASE
                    WHEN n.id IS NULL THEN 1
                    ELSE 0
                END AS source_note_deleted
            FROM practice_records AS p
            LEFT JOIN knowledge_notes AS n
              ON n.id = p.note_id
             AND n.deleted_at IS NULL
            WHERE p.id = :record_id
              AND p.user_id = :user_id
        """),
        {
            "record_id": record_id,
            "user_id": user_id,
        },
    ).mappings().first()

    return _as_record(row)


def delete_record(
    db: Session,
    record_id: int,
    user_id: int,
) -> int:
    """只允许物理删除当前用户自己的记录。"""

    result = db.execute(
        text("""
            DELETE FROM practice_records
            WHERE id = :record_id
              AND user_id = :user_id
        """),
        {
            "record_id": record_id,
            "user_id": user_id,
        },
    )

    return cast(CursorResult, result).rowcount