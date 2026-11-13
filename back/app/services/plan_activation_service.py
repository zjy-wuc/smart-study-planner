#把用户创建的树形草稿计划，经过完整校验后，一次性生成整个计划周期的每日任务，并将计划状态从 DRAFT 改为 ACTIVE。
from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.repositories import (
    step_repository,
    schedule_repository,
    daily_task_repository,
)
from app.services import plan_service
from app.services.plan_rules import (
    get_plan_days,
    distribute_numeric_target,
)


def _reject(message: str):
    """统一拒绝无法开始的计划"""
    raise HTTPException(
        status_code=409,
        detail=message,
    )


def _validate_tree(steps: list[dict]) -> list[dict]:
    """检查树形结构完整性，并返回所有叶子节点"""

    if not steps:
        _reject("计划尚未添加学习步骤")

    nodes = {step["id"]: step for step in steps}
    children_count = defaultdict(int)
    leaf_steps = []

    for step in steps:
        parent_id = step["parent_id"]

        if parent_id is not None:
            parent = nodes.get(parent_id)

            if parent is None:
                _reject("存在无效的父节点")

            if parent["node_type"] != "GROUP":
                _reject("LEAF 节点不能拥有子节点")

            children_count[parent_id] += 1

    for step in steps:
        if step["node_type"] == "GROUP":
            if children_count[step["id"]] == 0:
                _reject(
                    f"分类节点 {step['name']} 没有子节点"
                )

        elif step["node_type"] == "LEAF":
            leaf_steps.append(step)

        else:
            _reject("存在未知节点类型")

    if not leaf_steps:
        _reject("计划必须至少有一个叶子节点")

    return leaf_steps


def _build_leaf_tasks(
    step: dict,
    days: list,
    entries: list[dict],
) -> list[dict]:
    """根据一个叶子节点的规则生成任务数据"""

    task_type = step["task_type"]
    mode = step["schedule_mode"]
    step_id = step["id"]

    tasks = []
    valid_dates = set(days)

    def add_task(day, content, quantity=None):
        tasks.append({
            "step_id": step_id,
            "task_date": day,
            "task_type": task_type,
            "content": content,
            "target_quantity": quantity,
        })

    if task_type == "BOOLEAN":

        if mode == "REPEAT":
            content = (step["repeat_content"] or "").strip()

            if not content:
                _reject(
                    f"{step['name']} 缺少重复任务内容"
                )

            for day in days:
                add_task(day, content)

        elif mode == "DAILY_CUSTOM":
            by_date = defaultdict(list)

            for entry in entries:
                day = entry["task_date"]

                if day not in valid_dates:
                    _reject("存在超出计划周期的安排")

                if (
                    not entry["content"]
                    or entry["target_quantity"] is not None
                ):
                    _reject("BOOLEAN 自定义安排不合法")

                by_date[day].append(entry)

            for day in days:
                if not by_date[day]:
                    _reject(
                        f"{step['name']} 在 {day} 缺少安排"
                    )

                for entry in by_date[day]:
                    add_task(day, entry["content"])

        else:
            _reject("BOOLEAN 执行模式不合法")

    elif task_type == "NUMERIC":

        total = step["total_target"]

        if total is None or total < 0:
            _reject(
                f"{step['name']} 总目标数量不合法"
            )

        if mode == "AUTO_DISTRIBUTE":
            distribution = distribute_numeric_target(
                total,
                days[0],
                days[-1],
            )

            for day in days:
                add_task(
                    day,
                    step["name"],
                    distribution[day],
                )

        elif mode == "DAILY_MANUAL":
            by_date = defaultdict(list)

            for entry in entries:
                day = entry["task_date"]

                if day not in valid_dates:
                    _reject("存在超出计划周期的安排")

                if (
                    entry["target_quantity"] is None
                    or entry["target_quantity"] < 0
                    or entry["content"] is not None
                ):
                    _reject("NUMERIC 每日目标不合法")

                by_date[day].append(entry)

            sum_target = 0

            for day in days:
                if len(by_date[day]) != 1:
                    _reject(
                        f"{step['name']} 在 {day} "
                        "必须有且只有一条数量安排"
                    )

                quantity = by_date[day][0]["target_quantity"]

                sum_target += quantity

                add_task(
                    day,
                    step["name"],
                    quantity,
                )

            if sum_target != total:
                _reject(
                    f"{step['name']} 每日目标合计 "
                    "不等于总目标"
                )

        else:
            _reject("NUMERIC 执行模式不合法")

    else:
        _reject(
            f"{step['name']} 未配置合法任务类型"
        )

    return tasks


def start_plan(
    db: Session,
    plan_id: int,
    user_id: int,
) -> dict:
    """
    正式开始计划。

    校验、生成每日任务、更新计划状态
    必须在同一个数据库事务中完成。
    """

    try:
        # 1. 锁定用户自己的计划
        plan = plan_service.get_owned_plan(
            db=db,
            plan_id=plan_id,
            user_id=user_id,
            for_update=True,
        )

        if plan["status"] != "DRAFT":
            _reject("只有草稿计划可以正式开始")

        # 2. 避免重复生成
        if daily_task_repository.count_plan_tasks(
            db, plan_id
        ) > 0:
            _reject("计划已经存在正式任务")

        # 3. 展开完整日期周期
        days = get_plan_days(
            plan["start_date"],
            plan["end_date"],
        )

        # 4. 检查树形结构
        steps = step_repository.find_all_steps(
            db, plan_id
        )

        leaf_steps = _validate_tree(steps)

        # 5. 根据每个叶子的规则生成任务
        all_tasks = []

        for step in leaf_steps:

            entries = schedule_repository.find_entries(
                db, step["id"]
            )

            tasks = _build_leaf_tasks(
                step=step,
                days=days,
                entries=entries,
            )

            all_tasks.extend(tasks)

        if not all_tasks:
            _reject("没有生成任何每日任务")

        # 6. 批量写入正式任务
        daily_task_repository.insert_tasks(
            db=db,
            plan_id=plan_id,
            tasks=all_tasks,
        )

        # 7. 计划切换 ACTIVE
        daily_task_repository.activate_plan(
            db=db,
            plan_id=plan_id,
            user_id=user_id,
        )

        # 8. 全部成功才提交
        db.commit()

    except Exception:
        db.rollback()
        raise

    return {
        "plan_id": plan_id,
        "status": "ACTIVE",
        "generated_count": len(all_tasks),
        "start_date": plan["start_date"],
        "end_date": plan["end_date"],
    }
