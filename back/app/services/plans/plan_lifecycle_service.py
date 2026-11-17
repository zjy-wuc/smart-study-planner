
from datetime import date

from fastapi import HTTPException
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.clock import business_today
from app.repositories.plans import plan_lifecycle_repository
from app.services.plans import plan_service


def _reject(message: str):
    raise HTTPException(
        status_code=409,
        detail=message,
    )


def end_plan_early(
    db: Session,
    plan_id: int,
    user_id: int,
) -> dict:
    """用户主动结束计划"""

    try:
        # 只允许操作自己的计划，并锁定计划
        plan = plan_service.get_owned_plan(
            db=db,
            plan_id=plan_id,
            user_id=user_id,
            for_update=True,
        )

        if plan["status"] != "ACTIVE":
            _reject("只有 ACTIVE 计划可以结束")

        today = business_today()

        # 如果计划其实已经过期，但定时器尚未更新，
        # 则按正常到期处理，不能误删历史任务。
        if today > plan["end_date"]:
            ended_count = 0
            deleted_count = 0
            end_mode = "NORMAL_EXPIRED"

        else:
            # 提前结束：已开始的未完成任务改为 ENDED
            ended_count = (
                plan_lifecycle_repository
                .end_started_unfinished_tasks(
                    db=db,
                    plan_id=plan_id,
                )
            )

            # 从未开始的任务逻辑删除
            deleted_count = (
                plan_lifecycle_repository
                .delete_unstarted_tasks(
                    db=db,
                    plan_id=plan_id,
                )
            )

            end_mode = "EARLY"

        # 最后再修改计划状态
        changed = plan_lifecycle_repository.mark_plan_ended(
            db=db,
            plan_id=plan_id,
        )

        if changed != 1:
            _reject("计划状态已经变化，请重新查询")

        db.commit()

        return {
            "plan_id": plan_id,
            "status": "ENDED",
            "end_mode": end_mode,
            "ended_task_count": ended_count,
            "deleted_task_count": deleted_count,
        }

    except OperationalError as exc:
        db.rollback()

        code = getattr(
            exc.orig, "args", (None,)
        )[0]

        if code in (1205, 1213):
            raise HTTPException(
                status_code=409,
                detail="计划正在被其他操作修改，请重试",
            ) from exc

        raise

    except Exception:
        db.rollback()
        raise


def expire_due_plan(
    db: Session,
    plan_id: int,
    today: date,
) -> bool:
    """
    系统定时处理计划到期。

    返回：
    True  = 本次成功结束计划
    False = 计划已经结束或尚未到期
    """

    try:
        plan = (
            plan_lifecycle_repository
            .find_plan_for_update(
                db=db,
                plan_id=plan_id,
            )
        )

        if plan is None:
            db.rollback()
            return False

        if plan["status"] != "ACTIVE":
            db.rollback()
            return False

        if plan["end_date"] >= today:
            db.rollback()
            return False

        # 正常到期只修改计划状态。
        # 不清除未完成任务，不修改任务历史状态。
        changed = plan_lifecycle_repository.mark_plan_ended(
            db=db,
            plan_id=plan_id,
        )

        if changed != 1:
            db.rollback()
            return False

        db.commit()
        return True

    except Exception:
        db.rollback()
        raise
