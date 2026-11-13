
from sqlalchemy.orm import Session

from app.repositories import daily_task_repository
from app.services import plan_service


def list_plan_tasks(
    db: Session,
    plan_id: int,
    user_id: int,
) -> list[dict]:
    """查询当前用户计划的有效每日任务"""

    plan_service.get_owned_plan(
        db=db,
        plan_id=plan_id,
        user_id=user_id,
    )

    return daily_task_repository.find_plan_tasks(
        db, plan_id
    )
