import json
from datetime import timezone

from sqlalchemy.orm import Session

from app.repositories.admin import audit_repository
from app.schemas.admin import AdminAction


def list_audit_logs(
    db: Session,
    *,
    page: int,
    page_size: int,
    action: AdminAction | None,
) -> dict:

    total = audit_repository.count_logs(
        db,
        action=action,
    )

    logs = audit_repository.list_logs(
        db,
        action=action,
        limit=page_size,
        offset=(page - 1) * page_size,
    )

    for log in logs:

        for field in ("before_data", "after_data"):

            if isinstance(log[field], str):
                log[field] = json.loads(
                    log[field]
                )

        created_at = log["created_at"]

        if created_at.tzinfo is None:

            log["created_at"] = (
                created_at.replace(
                    tzinfo=timezone.utc,
                )
            )

    return {
        "items": logs,
        "total": total,
        "page": page,
        "page_size": page_size,
    }