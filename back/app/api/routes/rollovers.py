
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.response import success
from app.schemas.rollover import RolloverRequest
from app.services import rollover_service


router = APIRouter(
    prefix="/tasks",
    tags=["Task Rollover"],
)


@router.post("/{task_id}/rollover")
def rollover_task(
    task_id: int,
    data: RolloverRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = rollover_service.rollover_task(
        db=db,
        task_id=task_id,
        user_id=user["id"],
        target_date=data.target_date,
    )

    return success(
        data=result,
        message="任务顺延成功",
    )
