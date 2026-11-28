from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.response import success
from app.services import history_service


router = APIRouter(prefix="/history", tags=["Learning History"])


@router.get("/checkins")
def list_checkins(
    days: Literal["7", "30", "all"] = Query(default="7"),
    plan_id: int | None = Query(default=None, ge=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = history_service.list_checkins(
        db,
        user["id"],
        None if days == "all" else int(days),
        plan_id,
        page,
        page_size,
    )
    return success(data=result)


@router.get("/checkin-summary")
def get_checkin_summary(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    return success(data=history_service.get_checkin_summary(db, user["id"]))


@router.get("/reviews")
def list_reviews(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return success(data=history_service.list_reviews(db, user["id"], page, page_size))
