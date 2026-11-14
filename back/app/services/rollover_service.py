
from datetime import date

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.clock import business_today
from app.repositories import (
    task_repository,
    rollover_repository,
)


MAX_UINT64 = 2**64 - 1

ROLLOVER_ALLOWED_STATUSES = {
    "PENDING",
    "IN_PROGRESS",
    "OVERDUE",
}


def _reject(message: str):
    raise HTTPException(
        status_code=409,
        detail=message,
    )


def _validate_rollover(
    source: dict,
    target_date: date,
    today: date,
):
    """统一检查顺延的业务条件"""

    if source["plan_status"] != "ACTIVE":
        _reject("只有执行中的计划允许顺延")

    if not (
        source["plan_start_date"]
        <= today
        <= source["plan_end_date"]
    ):
        _reject("当前不在计划执行周期内")

    if source["status"] not in ROLLOVER_ALLOWED_STATUSES:
        _reject("该任务已完成或已停止，不能顺延")

    if source["task_date"] > today:
        _reject("尚未到执行日期的任务不能提前顺延")

    if target_date <= today:
        _reject("顺延目标必须是未来日期")

    if not (
        source["plan_start_date"]
        <= target_date
        <= source["plan_end_date"]
    ):
        _reject("目标日期超出计划周期")


def _rollover_boolean(
    db: Session,
    source: dict,
    target_date: date,
) -> dict:
    """BOOLEAN：保留原任务，创建未来的新任务"""

    exists = (
        rollover_repository.has_rollover_from_source(
            db=db,
            source_task_id=source["id"],
        )
    )

    if exists:
        _reject("该任务已经顺延，不能重复创建")

    target_id = rollover_repository.insert_rollover_target(
        db=db,
        source=source,
        target_date=target_date,
        quantity=None,
    )

    rollover_repository.insert_rollover_relation(
        db=db,
        source_task_id=source["id"],
        target_task_id=target_id,
        quantity=None,
    )

    return {
        "source_task_id": source["id"],
        "target_task_id": target_id,
        "task_type": "BOOLEAN",
        "target_date": target_date,
        "rollover_quantity": None,
        "merged": False,
    }


def _rollover_numeric(
    db: Session,
    source: dict,
    target_date: date,
) -> dict:
    """NUMERIC：转移剩余数量，必要时合并目标"""

    original_target = source["target_quantity"]
    actual = source["actual_quantity"]
    already_out = source["rollover_out_quantity"]

    if original_target is None:
        _reject("来源任务缺少数量目标")

    # 当前接口一次转移全部剩余数量
    if already_out > 0:
        _reject("该任务的剩余数量已经顺延")

    remaining = (
        original_target - actual - already_out
    )

    if remaining <= 0:
        _reject("该任务没有可顺延的剩余数量")

    # 查找目标日期已经存在的 NUMERIC 任务
    target = rollover_repository.find_numeric_target(
        db=db,
        plan_id=source["plan_id"],
        step_id=source["step_id"],
        target_date=target_date,
    )

    merged = target is not None

    if target is not None:

        if target["has_study_records"]:
            _reject("目标任务已有打卡历史，不能合并")

        # 只有真正未开始的目标才允许合并
        if (
            target["status"] != "PENDING"
            or target["actual_quantity"] != 0
            or target["rollover_out_quantity"] != 0
        ):
            _reject(
                "目标日期的任务已经开始或不可合并，"
                "请选择其他日期"
            )

        target_quantity = target["target_quantity"]

        if target_quantity is None:
            _reject("目标任务缺少目标数量")

        if target_quantity + remaining > MAX_UINT64:
            _reject("合并后的目标数量超出数据库范围")

        changed = rollover_repository.add_quantity_to_target(
            db=db,
            target_task_id=target["id"],
            quantity=remaining,
        )

        if changed != 1:
            _reject("目标任务状态已改变，请重新选择日期")

        target_id = target["id"]

    else:
        # 目标日期不存在有效任务时，创建新任务
        target_id = rollover_repository.insert_rollover_target(
            db=db,
            source=source,
            target_date=target_date,
            quantity=remaining,
        )

    # 来源任务记录已经转移出去的数量
    changed = rollover_repository.add_source_rollover_quantity(
        db=db,
        source_task_id=source["id"],
        quantity=remaining,
        expected_out=already_out,
        expected_actual=actual,
        expected_target=original_target,
    )

    if changed != 1:
        _reject("来源任务已经发生变化，请重新操作")

    # 保存顺延来源关系
    rollover_repository.insert_rollover_relation(
        db=db,
        source_task_id=source["id"],
        target_task_id=target_id,
        quantity=remaining,
    )

    return {
        "source_task_id": source["id"],
        "target_task_id": target_id,
        "task_type": "NUMERIC",
        "target_date": target_date,
        "rollover_quantity": remaining,
        "merged": merged,
        "source_remaining_quantity": 0,
    }


def rollover_task(
    db: Session,
    task_id: int,
    user_id: int,
    target_date: date,
) -> dict:
    """
    统一顺延入口。

    所有数据库修改在同一事务中提交。
    """

    try:
        # 锁定来源任务，检查数据归属
        source = task_repository.find_owned_task(
            db=db,
            task_id=task_id,
            user_id=user_id,
            for_update=True,
        )

        if source is None:
            raise HTTPException(
                status_code=404,
                detail="来源任务不存在",
            )

        _validate_rollover(
            source=source,
            target_date=target_date,
            today=business_today(),
        )

        if source["task_type"] == "BOOLEAN":
            result = _rollover_boolean(
                db, source, target_date
            )

        elif source["task_type"] == "NUMERIC":
            result = _rollover_numeric(
                db, source, target_date
            )

        else:
            _reject("不支持的任务类型")

        db.commit()
        return result

    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="目标日期任务已变化，请重新选择日期",
        ) from exc

    except OperationalError as exc:
        db.rollback()
        if getattr(exc.orig, "args", ()) and exc.orig.args[0] in (1205, 1213):
            raise HTTPException(
                status_code=409,
                detail="任务正在被其他操作修改，请重试",
            ) from exc
        raise

    except Exception:
        db.rollback()
        raise
