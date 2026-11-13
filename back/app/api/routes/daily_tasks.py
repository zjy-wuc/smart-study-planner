
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.response import success
from app.services import daily_task_service


router = APIRouter(
    prefix="/plans/{plan_id}/tasks",
    tags=["Daily Tasks"],
)


@router.get("")
def list_plan_tasks(
    plan_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tasks = daily_task_service.list_plan_tasks(
        db=db,
        plan_id=plan_id,
        user_id=user["id"],
    )

    return success(data=tasks)
