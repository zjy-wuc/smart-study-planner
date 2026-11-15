
from fastapi import HTTPException
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.clock import business_today
from app.repositories import (
    task_repository,
    active_task_repository,
)
from app.schemas.active_task import ActiveTaskUpdate
from app.services import task_service


def _reject(message: str):
    raise HTTPException(
        status_code=409,
        detail=message,
    )


def update_active_task(
    db: Session,
    task_id: int,
    user_id: int,
    data: ActiveTaskUpdate,
) -> dict:
    """
    修改 ACTIVE 计划未来尚未开始的任务。

    NUMERIC 修改成功后，在同一事务中更新叶子总目标。
    """

    try:
        # 锁定任务，同时验证所属用户
        task = task_repository.find_owned_task(
            db=db,
            task_id=task_id,
            user_id=user_id,
            for_update=True,
        )

        if task is None:
            raise HTTPException(
                status_code=404,
                detail="任务不存在",
            )

        today = business_today()

        if task["plan_status"] != "ACTIVE":
            _reject("只有 ACTIVE 计划允许修改任务")

        if task["task_date"] <= today:
            _reject("只能修改未来日期的任务")

        if task["status"] != "PENDING":
            _reject("任务已经开始或完成，不能修改")

        if active_task_repository.has_study_history(
            db=db,
            task_id=task_id,
        ):
            _reject("任务存在打卡历史，不能修改")

        # 只能提交一个字段，不能同时修改内容和数量
        fields = data.model_fields_set

        if task["task_type"] == "BOOLEAN":

            if fields != {"content"}:
                _reject("BOOLEAN 任务只能修改 content")

            if data.content is None:
                _reject("BOOLEAN 任务内容不能为空")

            changed = (
                active_task_repository.update_future_boolean(
                    db=db,
                    task_id=task_id,
                    today=today,
                    content=data.content,
                )
            )

            if changed != 1:
                _reject("任务状态已变化，修改失败")

            result_extra = {}

        elif task["task_type"] == "NUMERIC":

            if fields != {"target_quantity"}:
                _reject(
                    "NUMERIC 任务只能修改 target_quantity"
                )

            if data.target_quantity is None:
                _reject("NUMERIC 目标数量不能为空")

            incoming = (
                active_task_repository.get_incoming_quantity(
                    db=db,
                    task_id=task_id,
                )
            )

            if data.target_quantity < incoming:
                _reject(
                    "新目标不能低于已经承接的顺延数量"
                )

            changed = (
                active_task_repository.update_future_numeric(
                    db=db,
                    task_id=task_id,
                    today=today,
                    target_quantity=data.target_quantity,
                )
            )

            if changed != 1:
                _reject("任务状态或顺延关系已变化")

            # 关键：和每日任务修改保持同一个事务
            new_total = (
                active_task_repository
                .recalculate_numeric_leaf_total(
                    db=db,
                    plan_id=task["plan_id"],
                    step_id=task["step_id"],
                )
            )

            result_extra = {
                "leaf_total_target": new_total,
            }

        else:
            _reject("不支持的任务类型")

        db.commit()

    except OperationalError as exc:
        db.rollback()

        error_code = getattr(
            exc.orig, "args", (None,)
        )[0]

        if error_code in (1205, 1213):
            raise HTTPException(
                status_code=409,
                detail="任务正在被其他请求修改，请重试",
            ) from exc

        raise

    except Exception:
        db.rollback()
        raise

    # 提交成功后再查询最新任务
    task = task_service.get_task(
        db=db,
        task_id=task_id,
        user_id=user_id,
    )

    return {
        "task": task,
        **result_extra,
    }
