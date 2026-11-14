
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.response import success

from app.schemas.task import NumericProgressUpdate
from app.services import task_service


router = APIRouter(
    prefix="/tasks",
    tags=["Task Execution"],
)


# 注意：固定路径 /today 必须放在 /{task_id} 前面
@router.get("/today")
def list_today_tasks(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tasks = task_service.list_today_tasks(
        db=db,
        user_id=user["id"],
    )

    return success(data=tasks)


@router.get("/{task_id}")
def get_task(
    task_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = task_service.get_task(
        db=db,
        task_id=task_id,
        user_id=user["id"],
    )

    return success(data=task)


@router.get("/{task_id}/records")
def get_task_records(
    task_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    records = task_service.get_task_records(
        db=db,
        task_id=task_id,
        user_id=user["id"],
    )

    return success(data=records)


@router.post("/{task_id}/complete")
def complete_boolean_task(
    task_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = task_service.complete_boolean_task(
        db=db,
        task_id=task_id,
        user_id=user["id"],
    )

    return success(
        data=task,
        message="任务打卡成功",
    )


@router.put("/{task_id}/progress")
def update_numeric_task(
    task_id: int,
    data: NumericProgressUpdate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = task_service.update_numeric_task(
        db=db,
        task_id=task_id,
        user_id=user["id"],
        actual_quantity=data.actual_quantity,
    )

    return success(
        data=task,
        message="累计完成数量更新成功",
    )


@router.delete("/{task_id}")
def delete_task(
    task_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task_service.delete_task(
        db=db,
        task_id=task_id,
        user_id=user["id"],
    )

    return success(
        message="任务删除成功",
    )
