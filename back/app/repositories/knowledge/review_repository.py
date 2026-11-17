
from sqlalchemy import text
from sqlalchemy.orm import Session


def insert_review(
    db: Session,
    note_id: int,
    user_id: int,
) -> dict:
    result = db.execute(
        text("""
            INSERT INTO knowledge_review_records (
                note_id, user_id
            )
            VALUES (:note_id, :user_id)
        """),
        {
            "note_id": note_id,
            "user_id": user_id,
        },
    )

    review_id = int(result.lastrowid)

    row = db.execute(
        text("""
            SELECT id, note_id, reviewed_at
            FROM knowledge_review_records
            WHERE id = :review_id
              AND user_id = :user_id
        """),
        {
            "review_id": review_id,
            "user_id": user_id,
        },
    ).mappings().one()

    return dict(row)


def list_reviews(
    db: Session,
    note_id: int,
    user_id: int,
) -> list[dict]:
    rows = db.execute(
        text("""
            SELECT id, note_id, reviewed_at
            FROM knowledge_review_records
            WHERE note_id = :note_id
              AND user_id = :user_id
            ORDER BY reviewed_at DESC, id DESC
        """),
        {
            "note_id": note_id,
            "user_id": user_id,
        },
    ).mappings().all()

    return [dict(row) for row in rows]
