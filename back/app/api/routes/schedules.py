
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.response import success
from app.schemas.schedule import ScheduleReplace
from app.services import schedule_service


router = APIRouter(
    prefix="/plans/{plan_id}/steps/{step_id}/schedule",
    tags=["Draft Schedules"],
)


@router.get("")
def get_schedule(
    plan_id: int,
    step_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    entries = schedule_service.get_schedule(
        db=db,
        plan_id=plan_id,
        step_id=step_id,
        user_id=user["id"],
    )

    return success(data=entries)


@router.put("")
def replace_schedule(
    plan_id: int,
    step_id: int,
    data: ScheduleReplace,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    entries = schedule_service.replace_schedule(
        db=db,
        plan_id=plan_id,
        step_id=step_id,
        user_id=user["id"],
        data=data,
    )

    return success(
        data=entries,
        message="每日安排保存成功",
    )
