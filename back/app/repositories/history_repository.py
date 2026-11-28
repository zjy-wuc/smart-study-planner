from sqlalchemy import text
from sqlalchemy.orm import Session


CHECKIN_FROM = """
    FROM study_records AS r
    JOIN daily_tasks AS t ON t.id = r.task_id
    JOIN study_plans AS p ON p.id = t.plan_id
    JOIN plan_steps AS s ON s.id = t.step_id AND s.plan_id = p.id
    WHERE r.user_id = :user_id
      AND p.user_id = :user_id
      AND p.deleted_at IS NULL
      AND r.recorded_at < :end_at
"""


def list_checkins(db: Session, user_id: int, start_at, end_at, plan_id: int | None, page: int, page_size: int) -> dict:
    where = CHECKIN_FROM + (" AND p.id = :plan_id" if plan_id is not None else "")
    if start_at is not None:
        where += " AND r.recorded_at >= :start_at"
    params = {"user_id": user_id, "end_at": end_at, "plan_id": plan_id, "start_at": start_at}
    total = db.scalar(text(f"SELECT COUNT(*) {where}"), params)
    rows = db.execute(text(f"""
        SELECT r.id, r.task_id, r.event_type, r.recorded_value, r.recorded_at,
               t.content, t.step_id, t.deleted_at AS task_deleted_at,
               p.id AS plan_id, p.name AS plan_name, s.name AS step_name
        {where}
        ORDER BY r.recorded_at DESC, r.id DESC
        LIMIT :limit OFFSET :offset
    """), {**params, "limit": page_size, "offset": (page - 1) * page_size}).mappings().all()
    return {"items": [dict(row) for row in rows], "total": int(total or 0), "page": page, "page_size": page_size}


def get_checkin_summary(db: Session, user_id: int, end_at) -> dict:
    plans = db.execute(text("""
        SELECT id, name FROM study_plans
        WHERE user_id = :user_id AND deleted_at IS NULL
        ORDER BY id DESC
    """), {"user_id": user_id}).mappings().all()
    steps = db.execute(text("""
        SELECT s.id, s.plan_id, s.parent_id, s.name, s.deleted_at
        FROM plan_steps AS s
        JOIN study_plans AS p ON p.id = s.plan_id
        WHERE p.user_id = :user_id AND p.deleted_at IS NULL
        ORDER BY s.sort_order, s.id
    """), {"user_id": user_id}).mappings().all()
    dates = db.execute(text(f"""
        SELECT DISTINCT p.id AS plan_id, t.step_id, DATE(r.recorded_at) AS checkin_date
        {CHECKIN_FROM}
        ORDER BY checkin_date DESC
    """), {"user_id": user_id, "end_at": end_at}).mappings().all()
    return {"plans": [dict(row) for row in plans], "steps": [dict(row) for row in steps], "dates": [dict(row) for row in dates]}


def list_reviews(db: Session, user_id: int, page: int, page_size: int) -> dict:
    where = """
        FROM knowledge_review_records AS r
        JOIN knowledge_notes AS n ON n.id = r.note_id AND n.user_id = r.user_id
        WHERE r.user_id = :user_id
    """
    total = db.scalar(text(f"SELECT COUNT(*) {where}"), {"user_id": user_id})
    rows = db.execute(text(f"""
        SELECT r.id, r.note_id, r.reviewed_at, n.title AS note_title,
               n.plan_id, n.deleted_at AS note_deleted_at
        {where}
        ORDER BY r.reviewed_at DESC, r.id DESC
        LIMIT :limit OFFSET :offset
    """), {"user_id": user_id, "limit": page_size, "offset": (page - 1) * page_size}).mappings().all()
    return {"items": [dict(row) for row in rows], "total": int(total or 0), "page": page, "page_size": page_size}
