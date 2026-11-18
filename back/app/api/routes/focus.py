
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.response import success
from app.schemas.focus import FocusStart
from app.services.focus import focus_service

from typing import Literal

from app.services.focus import focus_statistics_service

router = APIRouter(
    prefix="/focus",
    tags=["Focus"],
)


@router.post("/sessions", status_code=201)
def start_focus(
    data: FocusStart,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = focus_service.start_session(
        db=db,
        user_id=user["id"],
        data=data,
    )

    return success(
        data=session,
        message="专注已开始",
        code=201,
    )


@router.get("/current")
def get_current_focus(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = focus_service.sync_current(
        db=db,
        user_id=user["id"],
    )

    return success(data=result["current"])


@router.post("/sync")
def sync_focus(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = focus_service.sync_current(
        db=db,
        user_id=user["id"],
    )

    return success(data=result)


@router.post("/sessions/{session_id}/pause")
def pause_focus(
    session_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = focus_service.operate_session(
        db=db,
        session_id=session_id,
        user_id=user["id"],
        action="pause",
    )

    return success(data=result)


@router.post("/sessions/{session_id}/resume")
def resume_focus(
    session_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = focus_service.operate_session(
        db=db,
        session_id=session_id,
        user_id=user["id"],
        action="resume",
    )

    return success(data=result)


@router.post("/sessions/{session_id}/finish")
def finish_focus(
    session_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = focus_service.operate_session(
        db=db,
        session_id=session_id,
        user_id=user["id"],
        action="finish",
    )

    return success(
        data=result,
        message="专注已结束",
    )


@router.post("/sessions/{session_id}/cancel")
def cancel_focus(
    session_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = focus_service.operate_session(
        db=db,
        session_id=session_id,
        user_id=user["id"],
        action="cancel",
    )

    return success(
        data=result,
        message="专注已取消",
    )


@router.get("/sessions")
def list_focus_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = focus_service.get_history(
        db=db,
        user_id=user["id"],
        page=page,
        page_size=page_size,
    )

    return success(data=result)



@router.get("/statistics")
def get_focus_statistics(
    days: Literal[7, 30] = Query(default=7),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = focus_statistics_service.get_focus_statistics(
        db=db,
        user_id=user["id"],
        days=days,
    )

    return success(data=result)

