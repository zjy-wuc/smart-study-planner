
from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.clock import business_today
from app.repositories import task_repository


# 允许继续打卡的任务状态
CHECKIN_ALLOWED_STATUSES = {
    "PENDING",
    "IN_PROGRESS",
    "OVERDUE",
}


def _require_task(
    db: Session,
    task_id: int,
    user_id: int,
    for_update: bool = False,
) -> dict:
    """查询当前用户的任务，不存在就返回 404"""

    task = task_repository.find_owned_task(
        db=db,
        task_id=task_id,
        user_id=user_id,
        for_update=for_update,
    )

    if task is None:
        raise HTTPException(
            status_code=404,
            detail="任务不存在",
        )

    return task


def _format_task(task: dict, today: date) -> dict:
    """
    给查询结果增加逾期展示信息。

    这里不修改数据库中任务的真实状态。
    """

    result = dict(task)

    is_overdue = (
        task["plan_status"] == "ACTIVE"
        and task["task_date"] < today
        and task["status"] in CHECKIN_ALLOWED_STATUSES
    )

    result["is_overdue"] = is_overdue

    result["display_status"] = (
        "OVERDUE"
        if is_overdue
        else task["status"]
    )

    return result


def _validate_checkin(
    task: dict,
    today: date,
):
    """统一检查任务是否允许打卡"""

    if task["plan_status"] != "ACTIVE":
        raise HTTPException(
            status_code=409,
            detail="只有执行中的计划允许打卡",
        )

    # 即使定时结束任务尚未运行，也不能越过周期打卡
    if (
        today < task["plan_start_date"]
        or today > task["plan_end_date"]
    ):
        raise HTTPException(
            status_code=409,
            detail="当前不在计划执行周期内",
        )

    if task["status"] == "COMPLETED":
        raise HTTPException(
            status_code=409,
            detail="已完成的任务不能再次打卡",
        )

    if task["status"] == "ENDED":
        raise HTTPException(
            status_code=409,
            detail="已停止的任务不能继续打卡",
        )

    if task["status"] not in CHECKIN_ALLOWED_STATUSES:
        raise HTTPException(
            status_code=409,
            detail="当前任务状态不允许打卡",
        )

    # 可以补打卡过去的任务，但不提前打卡未来任务
    if task["task_date"] > today:
        raise HTTPException(
            status_code=409,
            detail="未来任务不能提前打卡",
        )


def get_task(
    db: Session,
    task_id: int,
    user_id: int,
) -> dict:
    """查询任务详情"""

    task = _require_task(db, task_id, user_id)

    return _format_task(
        task,
        business_today(),
    )


def list_today_tasks(
    db: Session,
    user_id: int,
) -> list[dict]:
    """查询当前用户所有计划的今日任务"""

    today = business_today()

    tasks = task_repository.find_today_tasks(
        db=db,
        user_id=user_id,
        today=today,
    )

    return [
        _format_task(task, today)
        for task in tasks
    ]


def complete_boolean_task(
    db: Session,
    task_id: int,
    user_id: int,
) -> dict:
    """BOOLEAN 任务完成打卡"""

    try:
        task = _require_task(
            db,
            task_id,
            user_id,
            for_update=True,
        )

        _validate_checkin(
            task,
            business_today(),
        )

        if task["task_type"] != "BOOLEAN":
            raise HTTPException(
                status_code=409,
                detail="此接口只允许 BOOLEAN 任务使用",
            )

        # 第一步：更新当前任务状态
        task_repository.mark_boolean_completed(
            db=db,
            task_id=task_id,
        )

        # 第二步：保存打卡历史
        task_repository.insert_study_record(
            db=db,
            task_id=task_id,
            user_id=user_id,
            event_type="BOOLEAN_COMPLETE",
            recorded_value=None,
            task_date=task["task_date"],
        )

        # 两步全部成功才提交
        db.commit()

    except Exception:
        db.rollback()
        raise

    return get_task(db, task_id, user_id)


def update_numeric_task(
    db: Session,
    task_id: int,
    user_id: int,
    actual_quantity: int,
) -> dict:
    """NUMERIC 更新当天累计完成数量"""

    try:
        task = _require_task(
            db,
            task_id,
            user_id,
            for_update=True,
        )

        _validate_checkin(
            task,
            business_today(),
        )

        if task["task_type"] != "NUMERIC":
            raise HTTPException(
                status_code=409,
                detail="此接口只允许 NUMERIC 任务使用",
            )

        target = task["target_quantity"]

        if target is None:
            raise HTTPException(
                status_code=409,
                detail="NUMERIC 任务缺少目标数量",
            )

        # 阻止同样的累计值重复创建历史记录
        # 零目标任务允许首次提交 0 来确认完成
        if (
            actual_quantity == task["actual_quantity"]
            and target != 0
        ):
            raise HTTPException(
                status_code=409,
                detail="累计数量没有变化，请勿重复提交",
            )

        if actual_quantity >= target:
            new_status = "COMPLETED"

        elif actual_quantity > 0:
            new_status = "IN_PROGRESS"

        else:
            new_status = "PENDING"

        # 第一步：更新任务当前状态
        task_repository.update_numeric_progress(
            db=db,
            task_id=task_id,
            actual_quantity=actual_quantity,
            new_status=new_status,
        )

        # 第二步：记录本次提交的累计数量
        task_repository.insert_study_record(
            db=db,
            task_id=task_id,
            user_id=user_id,
            event_type="NUMERIC_PROGRESS",
            recorded_value=actual_quantity,
            task_date=task["task_date"],
        )

        db.commit()

    except Exception:
        db.rollback()
        raise

    return get_task(db, task_id, user_id)


def get_task_records(
    db: Session,
    task_id: int,
    user_id: int,
) -> list[dict]:
    """查看当前用户某个任务的打卡历史"""

    _require_task(
        db, task_id, user_id
    )

    return task_repository.find_study_records(
        db, task_id
    )


def delete_task(
    db: Session,
    task_id: int,
    user_id: int,
):
    """逻辑删除任务，保留打卡历史"""

    try:
        _require_task(
            db,
            task_id,
            user_id,
            for_update=True,
        )

        task_repository.soft_delete_task(
            db=db,
            task_id=task_id,
        )

        db.commit()

    except Exception:
        db.rollback()
        raise
