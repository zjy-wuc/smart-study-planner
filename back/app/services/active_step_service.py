
from collections import defaultdict
from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.clock import business_today
from app.repositories import (
    active_step_repository,
    daily_task_repository,
    schedule_repository,
    step_repository,
)
from app.schemas.active_step import ActiveStepNode, ActiveStepTreeCreate
from app.services import plan_service, step_service
from app.services.plan_rules import (
    distribute_numeric_target,
    get_plan_days,
)


def _reject(message: str, status_code: int = 409):
    raise HTTPException(
        status_code=status_code,
        detail=message,
    )


def _require_active_plan(
    db: Session,
    plan_id: int,
    user_id: int,
    for_update: bool = False,
) -> dict:
    """检查计划存在、属于当前用户且处于执行中"""

    plan = plan_service.get_owned_plan(
        db=db,
        plan_id=plan_id,
        user_id=user_id,
        for_update=for_update,
    )

    if plan["status"] != "ACTIVE":
        _reject("只有执行中的计划可以新增或删除节点")

    return plan


def _remaining_days(plan: dict) -> list[date]:
    """计划剩余需要生成任务的日期（含今天）"""

    today = business_today()

    days = [
        day
        for day in get_plan_days(
            plan["start_date"],
            plan["end_date"],
        )
        if day >= today
    ]

    if not days:
        _reject("计划剩余周期不足，无法新增任务")

    return days


def _validate_entries(
    node: ActiveStepNode,
    days: list[date],
) -> list[dict]:
    """校验逐日安排，返回可写入 schedule_entries 的数据"""

    rule = node.rule
    mode = rule.schedule_mode

    if mode not in ("DAILY_CUSTOM", "DAILY_MANUAL"):

        if node.entries:
            _reject("该执行模式不需要填写每日安排", 422)

        return []

    if not node.entries:
        _reject("逐日安排必须填写内容", 422)

    day_set = set(days)
    by_date = defaultdict(list)
    entries = []

    for item in node.entries:

        if item.task_date not in day_set:
            _reject("安排日期不在剩余执行周期内", 422)

        if mode == "DAILY_CUSTOM":

            if not item.content:
                _reject("BOOLEAN 每日安排必须填写内容", 422)

            if item.target_quantity is not None:
                _reject("BOOLEAN 每日安排不能填写数量", 422)

        else:

            if item.target_quantity is None:
                _reject("NUMERIC 每日安排必须填写数量", 422)

            if item.content is not None:
                _reject("NUMERIC 每日安排只需要填写数量", 422)

        by_date[item.task_date].append(item)

        entries.append({
            "task_date": item.task_date,
            "content": item.content,
            "target_quantity": item.target_quantity,
        })

    for day in days:

        if not by_date[day]:
            _reject(f"{day} 缺少每日安排", 422)

        if mode == "DAILY_MANUAL" and len(by_date[day]) != 1:
            _reject(f"{day} 只能有一条数量安排", 422)

    if mode == "DAILY_MANUAL":
        total = sum(
            entry["target_quantity"]
            for entry in entries
        )

        if total != rule.total_target:
            _reject("每日数量合计必须等于总目标", 422)

    return entries


def _build_tasks(
    node: ActiveStepNode,
    step_id: int,
    days: list[date],
    entries: list[dict],
) -> list[dict]:
    """根据执行规则生成剩余周期的每日任务"""

    rule = node.rule
    tasks = []

    def add(
        day: date,
        content: str,
        quantity: int | None = None,
    ):
        tasks.append({
            "step_id": step_id,
            "task_date": day,
            "task_type": rule.task_type,
            "content": content,
            "target_quantity": quantity,
        })

    if rule.task_type == "BOOLEAN":

        if rule.schedule_mode == "REPEAT":
            for day in days:
                add(day, rule.repeat_content)

        else:
            for entry in entries:
                add(entry["task_date"], entry["content"])

    else:

        if rule.schedule_mode == "AUTO_DISTRIBUTE":
            distribution = distribute_numeric_target(
                rule.total_target,
                days[0],
                days[-1],
            )

            for day in days:
                add(day, node.name, distribution[day])

        else:
            for entry in entries:
                add(
                    entry["task_date"],
                    node.name,
                    entry["target_quantity"],
                )

    return tasks


def _insert_tree(
    db: Session,
    plan_id: int,
    parent_id: int | None,
    node: ActiveStepNode,
    days: list[date],
    created_ids: list[int],
    tasks: list[dict],
) -> int:
    """递归插入节点，同时收集需要创建的每日任务"""

    sort_order = active_step_repository.next_sort_order(
        db=db,
        plan_id=plan_id,
        parent_id=parent_id,
    )

    step_id = active_step_repository.insert_node(
        db=db,
        plan_id=plan_id,
        parent_id=parent_id,
        node=node,
        sort_order=sort_order,
    )

    created_ids.append(step_id)

    if node.node_type == "GROUP":

        for child in node.children:
            _insert_tree(
                db=db,
                plan_id=plan_id,
                parent_id=step_id,
                node=child,
                days=days,
                created_ids=created_ids,
                tasks=tasks,
            )

        return step_id

    entries = _validate_entries(node, days)

    if entries:
        schedule_repository.insert_entries(
            db=db,
            step_id=step_id,
            entries=entries,
        )

    tasks.extend(
        _build_tasks(
            node=node,
            step_id=step_id,
            days=days,
            entries=entries,
        )
    )

    return step_id


def create_active_tree(
    db: Session,
    plan_id: int,
    user_id: int,
    data: ActiveStepTreeCreate,
) -> dict:
    """在执行中的计划里新增节点，并补齐剩余周期的任务"""

    try:
        plan = _require_active_plan(
            db=db,
            plan_id=plan_id,
            user_id=user_id,
            for_update=True,
        )

        if data.parent_id is not None:

            parent = step_repository.find_step(
                db=db,
                plan_id=plan_id,
                step_id=data.parent_id,
            )

            if parent is None:
                _reject("父节点不存在", 404)

            if parent["node_type"] != "GROUP":
                _reject("只能在分类节点下新增子节点")

        days = _remaining_days(plan)

        created_ids: list[int] = []
        tasks: list[dict] = []

        _insert_tree(
            db=db,
            plan_id=plan_id,
            parent_id=data.parent_id,
            node=data.node,
            days=days,
            created_ids=created_ids,
            tasks=tasks,
        )

        daily_task_repository.insert_tasks(
            db=db,
            plan_id=plan_id,
            tasks=tasks,
        )

        db.commit()

    except Exception:
        db.rollback()
        raise

    return {
        "created_step_ids": created_ids,
        "generated_task_count": len(tasks),
        "tree": step_service.get_step_tree(
            db=db,
            plan_id=plan_id,
            user_id=user_id,
        ),
    }


def delete_active_tree(
    db: Session,
    plan_id: int,
    step_id: int,
    user_id: int,
) -> dict:
    """逻辑删除节点及其后代，并向上清理变空的分类节点"""

    try:
        _require_active_plan(
            db=db,
            plan_id=plan_id,
            user_id=user_id,
            for_update=True,
        )

        step = step_repository.find_step(
            db=db,
            plan_id=plan_id,
            step_id=step_id,
        )

        if step is None:
            _reject("学习节点不存在", 404)

        target_ids = step_repository.find_descendant_ids(
            db=db,
            plan_id=plan_id,
            step_id=step_id,
        )

        # 删除后计划必须仍然保留至少一个有效叶子节点
        nodes = active_step_repository.list_active_nodes(
            db=db,
            plan_id=plan_id,
        )

        remaining_leaves = [
            node
            for node in nodes
            if node["node_type"] == "LEAF"
            and node["id"] not in target_ids
        ]

        if not remaining_leaves:
            _reject("计划必须至少保留一个有效叶子节点")

        deleted_ids = list(target_ids)

        active_step_repository.soft_delete_node_tasks(
            db=db,
            plan_id=plan_id,
            node_ids=target_ids,
        )

        active_step_repository.soft_delete_nodes(
            db=db,
            plan_id=plan_id,
            node_ids=target_ids,
        )

        # 向上清理因为没有子节点而变空的分类节点
        parent_id = step["parent_id"]

        while parent_id is not None:

            parent = step_repository.find_step(
                db=db,
                plan_id=plan_id,
                step_id=parent_id,
            )

            if parent is None:
                break

            has_children = any(
                node["parent_id"] == parent_id
                for node in active_step_repository.list_active_nodes(
                    db=db,
                    plan_id=plan_id,
                )
            )

            if has_children:
                break

            active_step_repository.soft_delete_nodes(
                db=db,
                plan_id=plan_id,
                node_ids=[parent_id],
            )

            deleted_ids.append(parent_id)
            parent_id = parent["parent_id"]

        db.commit()

    except Exception:
        db.rollback()
        raise

    return {
        "deleted_step_ids": deleted_ids,
        "deleted_step_count": len(deleted_ids),
    }
