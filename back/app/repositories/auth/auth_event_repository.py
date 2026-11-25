from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session


def insert_event(
    db: Session,
    *,
    event_type: str,
    now: datetime,
    user_id: int | None = None,
    identifier: str | None = None,
    ip: str | None = None,
    family_id: str | None = None,
) -> None:

    db.execute(
        text("""
            INSERT INTO auth_events (
                user_id,
                identifier,
                event_type,
                ip,
                family_id,
                created_at
            )
            VALUES (
                :user_id,
                :identifier,
                :event_type,
                :ip,
                :family_id,
                :now
            )
        """),
        {
            "user_id": user_id,
            "identifier": identifier,
            "event_type": event_type,
            "ip": ip,
            "family_id": family_id,
            "now": now,
        },
    )


def find_latest_user_event(
    db: Session,
    user_id: int,
    event_type: str,
) -> dict | None:

    row = db.execute(
        text("""
            SELECT id, user_id, event_type, created_at
            FROM auth_events
            WHERE user_id = :user_id
              AND event_type = :event_type
            ORDER BY created_at DESC, id DESC
            LIMIT 1
        """),
        {
            "user_id": user_id,
            "event_type": event_type,
        },
    ).mappings().first()

    return dict(row) if row is not None else None


def count_user_events(
    db: Session,
    *,
    user_id: int,
    event_type: str,
    since: datetime,
    after_id: int = 0,
) -> int:

    count = db.execute(
        text("""
            SELECT COUNT(*)
            FROM auth_events
            WHERE user_id = :user_id
              AND event_type = :event_type
              AND created_at >= :since
              AND id > :after_id
        """),
        {
            "user_id": user_id,
            "event_type": event_type,
            "since": since,
            "after_id": after_id,
        },
    ).scalar_one()

    return int(count)


def count_identifier_events(
    db: Session,
    *,
    identifier: str,
    event_type: str,
    since: datetime,
) -> int:

    count = db.execute(
        text("""
            SELECT COUNT(*)
            FROM auth_events
            WHERE identifier = :identifier
              AND event_type = :event_type
              AND created_at >= :since
        """),
        {
            "identifier": identifier,
            "event_type": event_type,
            "since": since,
        },
    ).scalar_one()

    return int(count)


def count_ip_events(
    db: Session,
    *,
    ip: str,
    event_type: str,
    since: datetime,
) -> int:

    count = db.execute(
        text("""
            SELECT COUNT(*)
            FROM auth_events
            WHERE ip = :ip
              AND event_type = :event_type
              AND created_at >= :since
        """),
        {
            "ip": ip,
            "event_type": event_type,
            "since": since,
        },
    ).scalar_one()

    return int(count)