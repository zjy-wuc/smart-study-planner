from datetime import datetime, time, timedelta

from sqlalchemy.orm import Session

from app.core.clock import business_today
from app.repositories import history_repository


def list_checkins(db: Session, user_id: int, days: int | None, plan_id: int | None, page: int, page_size: int) -> dict:
    today = business_today()
    end_at = datetime.combine(today + timedelta(days=1), time.min)
    start_at = datetime.combine(today - timedelta(days=days - 1), time.min) if days else None
    return history_repository.list_checkins(db, user_id, start_at, end_at, plan_id, page, page_size)


def get_checkin_summary(db: Session, user_id: int) -> dict:
    end_at = datetime.combine(business_today() + timedelta(days=1), time.min)
    return history_repository.get_checkin_summary(db, user_id, end_at)


def list_reviews(db: Session, user_id: int, page: int, page_size: int) -> dict:
    return history_repository.list_reviews(db, user_id, page, page_size)
