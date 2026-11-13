
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.repositories import (
    schedule_repository,
    step_repository,
)
from app.schemas.schedule import ScheduleReplace
from app.services import plan_service
from app.services.plan_rules import get_plan_days


def _require_draft_leaf(
    db: Session,
    plan_id: int,
    step_id: int,
    user_id: int,
    for_update: bool = False,
):
    """统一检查草稿计划与叶子节点"""

    plan = plan_service.get_owned_plan(
        db=db,
        plan_id=plan_id,
        user_id=user_id,
        for_update=for_update,
    )

    if plan["status"] != "DRAFT":
        raise HTTPException(
            status_code=409,
            detail="只有草稿计划可以编辑每日安排",
        )

    step = step_repository.find_step(
        db=db,
        plan_id=plan_id,
        step_id=step_id,
    )

    if step is None:
        raise HTTPException(
            status_code=404,
            detail="学习步骤不存在",
        )

    if step["node_type"] != "LEAF":
        raise HTTPException(
            status_code=409,
            detail="只有叶子节点可以安排每日任务",
        )

    if step["schedule_mode"] not in (
        "DAILY_CUSTOM",
        "DAILY_MANUAL",
    ):
        raise HTTPException(
            status_code=409,
            detail="此执行模式不需要手动逐日安排",
        )

    return plan, step


def get_schedule(
    db: Session,
    plan_id: int,
    step_id: int,
    user_id: int,
) -> list[dict]:
    """查询当前叶子节点的草稿安排"""

    _require_draft_leaf(
        db, plan_id, step_id, user_id
    )

    return schedule_repository.find_entries(
        db, step_id
    )


def replace_schedule(
    db: Session,
    plan_id: int,
    step_id: int,
    user_id: int,
    data: ScheduleReplace,
) -> list[dict]:
    """
    一次替换某个叶子节点的草稿安排。
    保存可以不完整，开始计划时再统一校验。
    """

    try:
        plan, step = _require_draft_leaf(
            db=db,
            plan_id=plan_id,
            step_id=step_id,
            user_id=user_id,
            for_update=True,
        )

        valid_dates = set(get_plan_days(
            plan["start_date"],
            plan["end_date"],
        ))

        mode = step["schedule_mode"]
        seen_dates = set()
        entries = []

        for item in data.entries:

            if item.task_date not in valid_dates:
                raise HTTPException(
                    status_code=422,
                    detail="任务日期不在计划周期内",
                )

            if mode == "DAILY_CUSTOM":

                if not item.content:
                    raise HTTPException(
                        status_code=422,
                        detail="BOOLEAN 每日任务必须填写内容",
                    )

                if item.target_quantity is not None:
                    raise HTTPException(
                        status_code=422,
                        detail="BOOLEAN 不能填写数量",
                    )

            else:
                if item.target_quantity is None:
                    raise HTTPException(
                        status_code=422,
                        detail="NUMERIC 必须填写每日目标",
                    )

                if item.content is not None:
                    raise HTTPException(
                        status_code=422,
                        detail="NUMERIC 只需要填写数量",
                    )

                if item.task_date in seen_dates:
                    raise HTTPException(
                        status_code=422,
                        detail="NUMERIC 同一天只能有一条安排",
                    )

            seen_dates.add(item.task_date)

            entries.append({
                "task_date": item.task_date,
                "content": item.content,
                "target_quantity": item.target_quantity,
            })

        # 同一个事务中：删除旧安排，插入新安排
        schedule_repository.soft_delete_entries(
            db, step_id
        )

        schedule_repository.insert_entries(
            db, step_id, entries
        )

        db.commit()

    except Exception:
        db.rollback()
        raise

    return get_schedule(
        db, plan_id, step_id, user_id
    )
