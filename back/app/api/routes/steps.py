
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.response import success

from app.schemas.step import (
    StepCreate,
    StepUpdate,
    StepRule,
)

from app.services import step_service


router = APIRouter(
    prefix="/plans/{plan_id}/steps",
    tags=["Plan Steps"],
)


@router.post("", status_code=201)
def create_step(
    plan_id: int,
    data: StepCreate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = step_service.create_step(
        db=db,
        plan_id=plan_id,
        user_id=user["id"],
        data=data,
    )

    return success(
        data=result,
        message="学习步骤创建成功",
        code=201,
    )


@router.get("")
def get_step_tree(
    plan_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tree = step_service.get_step_tree(
        db=db,
        plan_id=plan_id,
        user_id=user["id"],
    )

    return success(data=tree)


@router.patch("/{step_id}")
def update_step(
    plan_id: int,
    step_id: int,
    data: StepUpdate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    step = step_service.update_step(
        db=db,
        plan_id=plan_id,
        step_id=step_id,
        user_id=user["id"],
        data=data,
    )

    return success(
        data=step,
        message="学习步骤修改成功",
    )


@router.put("/{step_id}/rule")
def update_step_rule(
    plan_id: int,
    step_id: int,
    data: StepRule,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    step = step_service.update_step_rule(
        db=db,
        plan_id=plan_id,
        step_id=step_id,
        user_id=user["id"],
        rule=data,
    )

    return success(
        data=step,
        message="执行规则修改成功",
    )


@router.delete("/{step_id}")
def delete_step(
    plan_id: int,
    step_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    step_service.delete_step(
        db=db,
        plan_id=plan_id,
        step_id=step_id,
        user_id=user["id"],
    )

    return success(
        message="学习步骤删除成功"
    )
