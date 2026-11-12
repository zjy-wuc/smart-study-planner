
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.response import success

from app.schemas.plan import PlanCreate, PlanUpdate
from app.services import plan_service


router = APIRouter(
    prefix="/plans",
    tags=["Study Plans"],
)


@router.post("", status_code=201)
def create_plan(
    data: PlanCreate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plan = plan_service.create_plan(
        db=db,
        user_id=user["id"],
        data=data,
    )

    return success(
        data=plan,
        message="计划创建成功",
        code=201,
    )


@router.get("")
def list_plans(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plans = plan_service.list_plans(
        db=db,
        user_id=user["id"],
    )

    return success(data=plans)


@router.get("/{plan_id}")
def get_plan(
    plan_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plan = plan_service.get_owned_plan(
        db=db,
        plan_id=plan_id,
        user_id=user["id"],
    )

    return success(data=plan)


@router.patch("/{plan_id}")
def update_plan(
    plan_id: int,
    data: PlanUpdate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plan = plan_service.update_plan(
        db=db,
        plan_id=plan_id,
        user_id=user["id"],
        data=data,
    )

    return success(
        data=plan,
        message="计划修改成功",
    )


@router.delete("/{plan_id}")
def delete_plan(
    plan_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plan_service.delete_plan(
        db=db,
        plan_id=plan_id,
        user_id=user["id"],
    )

    return success(
        message="计划删除成功",
    )
