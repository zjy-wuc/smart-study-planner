import json
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session


def insert_audit_log(
    db: Session,
    *,
    admin_id: int,
    action: str,
    target_type: str,
    target_id: int,
    before_data: dict,
    after_data: dict,
    reason: str,
    now: datetime,
) -> None:
    db.execute(
        text("""
            INSERT INTO admin_audit_logs (
                admin_id,
                action,
                target_type,
                target_id,
                before_data,
                after_data,
                reason,
                created_at
            )
            VALUES (
                :admin_id,
                :action,
                :target_type,
                :target_id,
                :before_data,
                :after_data,
                :reason,
                :now
            )
        """),
        {
            "admin_id": admin_id,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "before_data": json.dumps(
                before_data, ensure_ascii=False
            ),
            "after_data": json.dumps(
                after_data, ensure_ascii=False
            ),
            "reason": reason,
            "now": now,
        },
    )


def _filter_sql(action: str | None) -> tuple[str, dict]:
    if action is None:
        return "", {}

    return "WHERE action = :action", {"action": action}


def count_logs(
    db: Session,
    *,
    action: str | None,
) -> int:

    where_sql, params = _filter_sql(action)

    result = db.execute(
        text(
            "SELECT COUNT(*) FROM admin_audit_logs "
            f"{where_sql}"
        ),
        params,
    ).scalar_one()

    return int(result)


def list_logs(
    db: Session,
    *,
    action: str | None,
    limit: int,
    offset: int,
) -> list[dict]:

    where_sql, params = _filter_sql(action)

    rows = db.execute(
        text(f"""
            SELECT
                a.id,
                a.admin_id,
                u.username AS admin_username,
                a.action,
                a.target_type,
                a.target_id,
                a.before_data,
                a.after_data,
                a.reason,
                a.created_at
            FROM admin_audit_logs AS a
            LEFT JOIN users AS u
                ON u.id = a.admin_id
            {where_sql}
            ORDER BY a.created_at DESC, a.id DESC
            LIMIT :limit OFFSET :offset
        """),
        {
            **params,
            "limit": limit,
            "offset": offset,
        },
    ).mappings().all()

    return [dict(row) for row in rows]