
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.repositories import plan_repository
from app.schemas.plan import PlanCreate, PlanUpdate


def get_owned_plan(
    db: Session,
    plan_id: int,
    user_id: int,
    for_update: bool = False,
) -> dict:
    """
    获取当前用户拥有的计划。
    没有找到时返回 404。
    """

    plan = plan_repository.find_plan_by_id(
        db=db,
        plan_id=plan_id,
        user_id=user_id,
        for_update=for_update,
    )

    if plan is None:
        raise HTTPException(
            status_code=404,
            detail="计划不存在",
        )

    return plan


def create_plan(
    db: Session,
    user_id: int,
    data: PlanCreate,
) -> dict:
    """创建草稿计划"""

    try:
        plan_id = plan_repository.insert_plan(
            db=db,
            user_id=user_id,
            name=data.name,
            description=data.description,
            start_date=data.start_date,
            end_date=data.end_date,
        )

        db.commit()

    except Exception:
        db.rollback()
        raise

    return get_owned_plan(db, plan_id, user_id)


def list_plans(
    db: Session,
    user_id: int,
) -> list[dict]:
    """查询当前登录用户的计划列表"""

    return plan_repository.find_plans_by_user(
        db=db,
        user_id=user_id,
    )


def update_plan(
    db: Session,
    plan_id: int,
    user_id: int,
    data: PlanUpdate,
) -> dict:
    """按照业务规则修改学习计划"""

    try:
        # 查询并锁定计划，防止并发修改
        plan = get_owned_plan(
            db=db,
            plan_id=plan_id,
            user_id=user_id,
            for_update=True,
        )

        # ENDED 不允许修改
        if plan["status"] == "ENDED":
            raise HTTPException(
                status_code=409,
                detail="已结束的计划不能修改",
            )
#只保留创建模型时明确传入的字段，排除没有提供的字段。
        changes = data.model_dump(
            exclude_unset=True
        )

        if not changes:
            raise HTTPException(
                status_code=400,
                detail="没有提供修改内容",
            )

        # 必填字段不能改成 null
        for field in (
            "name",
            "start_date",
            "end_date",
        ):
            if field in changes and changes[field] is None:
                raise HTTPException(
                    status_code=422,
                    detail=f"{field} 不能为空",
                )

        # ACTIVE 状态不能修改周期
        if plan["status"] == "ACTIVE":
            if (
                "start_date" in changes
                or "end_date" in changes
            ):
                raise HTTPException(
                    status_code=409,
                    detail="执行中的计划不能修改周期",
                )

        # 计算修改后的日期
        new_start = changes.get(
            "start_date",
            plan["start_date"],
        )

        new_end = changes.get(
            "end_date",
            plan["end_date"],
        )

        if new_start > new_end:
            raise HTTPException(
                status_code=422,
                detail="开始日期不能晚于结束日期",
            )

        plan_repository.update_plan_fields(
            db=db,
            plan_id=plan_id,
            user_id=user_id,
            changes=changes,
        )

        db.commit()

    except Exception:
        db.rollback()
        raise

    return get_owned_plan(db, plan_id, user_id)


def delete_plan(
    db: Session,
    plan_id: int,
    user_id: int,
) -> None:
    """逻辑删除学习计划"""

    try:
        # 先锁定并验证用户拥有该计划
        get_owned_plan(
            db=db,
            plan_id=plan_id,
            user_id=user_id,
            for_update=True,
        )

        plan_repository.soft_delete_plan(
            db=db,
            plan_id=plan_id,
            user_id=user_id,
        )

        db.commit()

    except Exception:
        db.rollback()
        raise
