
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.response import success

from app.schemas.active_task import ActiveTaskUpdate
from app.services.tasks import active_task_service


router = APIRouter(
    prefix="/tasks",
    tags=["Active Task Editing"],
)


@router.patch("/{task_id}")
def update_active_task(
    task_id: int,
    data: ActiveTaskUpdate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = active_task_service.update_active_task(
        db=db,
        task_id=task_id,
        user_id=user["id"],
        data=data,
    )

    return success(
        data=result,
        message="任务修改成功",
    )
