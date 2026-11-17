from sqlalchemy.orm import Session

from app.repositories.progress import progress_repository
from app.services.plans import plan_service


REASON_PLAN_NOT_ACTIVE = "PLAN_NOT_ACTIVE"
REASON_NO_VALID_TASKS = "NO_VALID_TASKS"
REASON_ZERO_TARGET = "ZERO_TARGET"
REASON_DATA_ANOMALY = "DATA_ANOMALY"
REASON_NO_COMPUTABLE_LEAF = "NO_COMPUTABLE_LEAF"


def _percent(value: float, total: float) -> float:
    return round(value / total * 100, 2)


def _boolean_leaf(step: dict, tasks: list[dict]) -> dict:
    """
    BOOLEAN 叶子按任务条数统计。

    已作为顺延来源的任务不进入分母，
    即使其顺延目标已经被删除。
    """

    candidates = [
        task
        for task in tasks
        if not task["has_rollover"]
    ]

    completed = len([
        task
        for task in candidates
        if task["status"] == "COMPLETED"
    ])

    percent = (
        _percent(completed, len(candidates))
        if candidates
        else None
    )

    return {
        "step_id": step["id"],
        "name": step["name"],
        "task_type": "BOOLEAN",
        "progress_percent": percent,
        "reason": None if percent is not None else REASON_NO_VALID_TASKS,
        "valid_task_count": len(candidates),
        "completed_task_count": completed,
        "target_total": None,
        "actual_total": None,
    }


def _numeric_leaf(step: dict, tasks: list[dict]) -> tuple[dict, list[dict]]:
    """
    NUMERIC 叶子按数量统计：

    effective_target = target_quantity - rollover_out_quantity
    progress = min(actual_quantity, effective_target) / effective_target
    """

    anomalies = []

    for task in tasks:
        target = task["target_quantity"]
        rolled_out = task["rollover_out_quantity"]

        if target is None:
            anomalies.append({
                "step_id": step["id"],
                "task_id": task["id"],
                "detail": "NUMERIC 任务缺少目标数量",
            })
        elif rolled_out > target:
            anomalies.append({
                "step_id": step["id"],
                "task_id": task["id"],
                "detail": "顺延转出数量大于任务目标数量",
            })

    if anomalies:
        return {
            "step_id": step["id"],
            "name": step["name"],
            "task_type": "NUMERIC",
            "progress_percent": None,
            "reason": REASON_DATA_ANOMALY,
            "valid_task_count": len(tasks),
            "completed_task_count": None,
            "target_total": None,
            "actual_total": None,
        }, anomalies

    target_total = sum(
        task["target_quantity"] - task["rollover_out_quantity"]
        for task in tasks
    )

    actual_total = sum(task["actual_quantity"] for task in tasks)

    if not tasks:
        percent = None
        reason = REASON_NO_VALID_TASKS
    elif target_total <= 0:
        percent = None
        reason = REASON_ZERO_TARGET
    else:
        percent = _percent(
            min(actual_total, target_total),
            target_total,
        )
        reason = None

    return {
        "step_id": step["id"],
        "name": step["name"],
        "task_type": "NUMERIC",
        "progress_percent": percent,
        "reason": reason,
        "valid_task_count": len(tasks),
        "completed_task_count": None,
        "target_total": target_total,
        "actual_total": actual_total,
    }, anomalies


def get_plan_progress(
    db: Session,
    plan_id: int,
    user_id: int,
) -> dict:
    """统计当前用户某个计划的完成率"""

    plan = plan_service.get_owned_plan(
        db=db,
        plan_id=plan_id,
        user_id=user_id,
    )

    if plan["status"] != "ACTIVE":
        return {
            "plan_id": plan_id,
            "plan_status": plan["status"],
            "progress_percent": None,
            "reason": REASON_PLAN_NOT_ACTIVE,
            "leaf_count": 0,
            "computable_leaf_count": 0,
            "leaves": [],
            "data_anomalies": [],
        }

    leaves = progress_repository.find_effective_leaves(
        db=db,
        plan_id=plan_id,
    )

    tasks = progress_repository.find_progress_tasks(
        db=db,
        plan_id=plan_id,
    )

    tasks_by_step: dict[int, list[dict]] = {}

    for task in tasks:
        tasks_by_step.setdefault(task["step_id"], []).append(task)

    leaf_results = []
    anomalies = []

    for leaf in leaves:
        leaf_tasks = tasks_by_step.get(leaf["id"], [])

        if leaf["task_type"] == "NUMERIC":
            result, leaf_anomalies = _numeric_leaf(leaf, leaf_tasks)
        else:
            result = _boolean_leaf(leaf, leaf_tasks)
            leaf_anomalies = []

        leaf_results.append(result)
        anomalies.extend(leaf_anomalies)

    computable = [
        leaf["progress_percent"]
        for leaf in leaf_results
        if leaf["progress_percent"] is not None
    ]

    if computable:
        percent = round(sum(computable) / len(computable), 2)
        reason = None
    else:
        percent = None
        reason = REASON_NO_COMPUTABLE_LEAF

    return {
        "plan_id": plan_id,
        "plan_status": plan["status"],
        "progress_percent": percent,
        "reason": reason,
        "leaf_count": len(leaf_results),
        "computable_leaf_count": len(computable),
        "leaves": leaf_results,
        "data_anomalies": anomalies,
    }
