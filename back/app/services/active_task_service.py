
from typing import NoReturn

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


def _reject(message: str) -> NoReturn:
    """统一抛出业务异常"""

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

    result_extra: dict[str, int] = {}

    try:
        # 1. 锁定任务，同时验证所属用户
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

        # 2. 校验计划和任务状态
        if task["plan_status"] != "ACTIVE":
            _reject("只有 ACTIVE 计划允许修改任务")

        if task["task_date"] <= today:
            _reject("只能修改未来日期的任务")

        if task["status"] != "PENDING":
            _reject("任务已经开始或完成，不能修改")

        # 3. 检查是否存在打卡历史
        if active_task_repository.has_study_history(
            db=db,
            task_id=task_id,
        ):
            _reject("任务存在打卡历史，不能修改")

        # 4. 只能提交一个字段
        fields = data.model_fields_set

        # 5. BOOLEAN 任务修改
        if task["task_type"] == "BOOLEAN":

            if fields != {"content"}:
                _reject(
                    "BOOLEAN 任务只能修改 content"
                )

            content = data.content

            if content is None:
                _reject(
                    "BOOLEAN 任务内容不能为空"
                )

            changed = (
                active_task_repository.update_future_boolean(
                    db=db,
                    task_id=task_id,
                    today=today,
                    content=content,
                )
            )

            if changed != 1:
                _reject(
                    "任务状态已变化，修改失败"
                )

        # 6. NUMERIC 任务修改
        elif task["task_type"] == "NUMERIC":

            if fields != {"target_quantity"}:
                _reject(
                    "NUMERIC 任务只能修改 target_quantity"
                )

            target_quantity = data.target_quantity

            if target_quantity is None:
                _reject(
                    "NUMERIC 目标数量不能为空"
                )

            # 查询当前任务累计承接的顺延数量
            incoming = (
                active_task_repository.get_incoming_quantity(
                    db=db,
                    task_id=task_id,
                )
            )

            if target_quantity < incoming:
                _reject(
                    "新目标不能低于已经承接的顺延数量"
                )

            # 修改每日任务目标
            changed = (
                active_task_repository.update_future_numeric(
                    db=db,
                    task_id=task_id,
                    today=today,
                    target_quantity=target_quantity,
                )
            )

            if changed != 1:
                _reject(
                    "任务状态或顺延关系已变化"
                )

            # 重新计算 NUMERIC 叶子节点总目标
            # 与每日任务修改保持在同一个事务中
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

        # 7. 所有操作成功后统一提交
        db.commit()

    except OperationalError as exc:
        db.rollback()

        # 安全提取数据库原始错误码
        original_args = getattr(
            exc.orig,
            "args",
            (),
        )

        error_code = (
            original_args[0]
            if original_args
            else None
        )

        # MySQL 1205: 锁等待超时
        # MySQL 1213: 检测到死锁
        if error_code in (1205, 1213):
            raise HTTPException(
                status_code=409,
                detail="任务正在被其他请求修改，请重试",
            ) from exc

        raise

    except Exception:
        db.rollback()
        raise

    # 8. 提交成功后查询最新任务
    updated_task = task_service.get_task(
        db=db,
        task_id=task_id,
        user_id=user_id,
    )

    return {
        "task": updated_task,
        **result_extra,
    }
