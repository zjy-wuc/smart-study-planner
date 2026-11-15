
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.response import success

from app.schemas.active_step import ActiveStepTreeCreate
from app.services import active_step_service


router = APIRouter(
    prefix="/plans/{plan_id}/active-steps",
    tags=["Active Step Management"],
)


@router.post("")
def create_active_tree(
    plan_id: int,
    data: ActiveStepTreeCreate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = active_step_service.create_active_tree(
        db=db,
        plan_id=plan_id,
        user_id=user["id"],
        data=data,
    )

    return success(
        data=result,
        message="学习节点新增成功",
    )


@router.delete("/{step_id}")
def delete_active_tree(
    plan_id: int,
    step_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = active_step_service.delete_active_tree(
        db=db,
        plan_id=plan_id,
        step_id=step_id,
        user_id=user["id"],
    )

    return success(
        data=result,
        message="学习节点删除成功",
    )
