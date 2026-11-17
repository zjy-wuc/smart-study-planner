
from collections import defaultdict
from datetime import date
from typing import NoReturn

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.clock import business_today
from app.repositories.steps import active_step_repository, step_repository
from app.repositories.tasks import daily_task_repository
from app.repositories.schedules import schedule_repository
from app.schemas.active_step import (
    ActiveStepNode,
    ActiveStepTreeCreate,
)
from app.services.plans import plan_service
from app.services.steps import step_service
from app.services.plans.plan_rules import (
    distribute_numeric_target,
    get_plan_days,
)


def _reject(
    message: str,
    status_code: int = 409,
) -> NoReturn:
    """统一抛出业务异常"""

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


def _remaining_days(
    plan: dict,
) -> list[date]:
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

    if rule is None:
        _reject("叶子节点必须配置执行规则", 422)

    mode = rule.schedule_mode
    node_entries = node.entries or []

    if mode not in ("DAILY_CUSTOM", "DAILY_MANUAL"):

        if node_entries:
            _reject("该执行模式不需要填写每日安排", 422)

        return []

    if not node_entries:
        _reject("逐日安排必须填写内容", 422)

    if mode == "DAILY_CUSTOM" and rule.task_type != "BOOLEAN":
        _reject("DAILY_CUSTOM 只适用于 BOOLEAN 任务", 422)

    if mode == "DAILY_MANUAL" and rule.task_type != "NUMERIC":
        _reject("DAILY_MANUAL 只适用于 NUMERIC 任务", 422)

    day_set = set(days)

    by_date: dict[date, int] = defaultdict(int)

    entries: list[dict] = []
    total = 0

    for item in node_entries:

        if item.task_date not in day_set:
            _reject("安排日期不在剩余执行周期内", 422)

        if mode == "DAILY_CUSTOM":

            if not item.content:
                _reject("BOOLEAN 每日安排必须填写内容", 422)

            if item.target_quantity is not None:
                _reject("BOOLEAN 每日安排不能填写数量", 422)

        else:

            quantity = item.target_quantity

            if quantity is None:
                _reject("NUMERIC 每日安排必须填写数量", 422)

            if item.content is not None:
                _reject("NUMERIC 每日安排只需要填写数量", 422)

            total += quantity

        by_date[item.task_date] += 1

        entries.append({
            "task_date": item.task_date,
            "content": item.content,
            "target_quantity": item.target_quantity,
        })

    for day in days:

        if by_date[day] == 0:
            _reject(f"{day} 缺少每日安排", 422)

        if mode == "DAILY_MANUAL" and by_date[day] != 1:
            _reject(f"{day} 只能有一条数量安排", 422)

    if mode == "DAILY_MANUAL":

        if rule.total_target is None:
            _reject("NUMERIC 任务必须设置总目标", 422)

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

    if rule is None:
        _reject("叶子节点缺少执行规则", 422)

    tasks: list[dict] = []

    def add(
        day: date,
        content: str,
        quantity: int | None = None,
    ) -> None:
        tasks.append({
            "step_id": step_id,
            "task_date": day,
            "task_type": rule.task_type,
            "content": content,
            "target_quantity": quantity,
        })

    if rule.task_type == "BOOLEAN":

        if rule.schedule_mode == "REPEAT":

            repeat_content = rule.repeat_content

            if not repeat_content:
                _reject("重复任务必须设置执行内容", 422)

            for day in days:
                add(day, repeat_content)

        elif rule.schedule_mode == "DAILY_CUSTOM":

            for entry in entries:

                content = entry["content"]

                if not content:
                    _reject("BOOLEAN 每日任务内容不能为空", 422)

                add(
                    entry["task_date"],
                    content,
                )

        else:
            _reject("BOOLEAN 任务执行模式无效", 422)

    elif rule.task_type == "NUMERIC":

        if rule.schedule_mode == "AUTO_DISTRIBUTE":

            total_target = rule.total_target

            if total_target is None:
                _reject("NUMERIC 任务必须设置总目标", 422)

            distribution = distribute_numeric_target(
                total_target,
                days[0],
                days[-1],
            )

            for day in days:
                add(
                    day,
                    node.name,
                    distribution[day],
                )

        elif rule.schedule_mode == "DAILY_MANUAL":

            for entry in entries:

                quantity = entry["target_quantity"]

                if quantity is None:
                    _reject("NUMERIC 每日数量不能为空", 422)

                add(
                    entry["task_date"],
                    node.name,
                    quantity,
                )

        else:
            _reject("NUMERIC 任务执行模式无效", 422)

    else:
        _reject("不支持的任务类型", 422)

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

    if node.node_type == "GROUP":

        children = node.children or []

        if not children:
            _reject("分类节点必须包含子节点", 422)

    else:
        children = []

        if node.children:
            _reject("叶子节点不能包含子节点", 422)

        # 先验证执行规则，避免插入后才发现配置错误
        entries = _validate_entries(node, days)

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

        for child in children:
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

    if entries:

        schedule_repository.insert_entries(
            db=db,
            step_id=step_id,
            entries=entries,
        )

    generated_tasks = _build_tasks(
        node=node,
        step_id=step_id,
        days=days,
        entries=entries,
    )

    tasks.extend(generated_tasks)

    return step_id


def create_active_tree(
    db: Session,
    plan_id: int,
    user_id: int,
    data: ActiveStepTreeCreate,
) -> dict:
    """在执行中的计划里新增节点，并补齐剩余周期的任务"""

    created_ids: list[int] = []
    tasks: list[dict] = []

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

        tree = step_service.get_step_tree(
            db=db,
            plan_id=plan_id,
            user_id=user_id,
        )

        db.commit()

    except Exception:
        db.rollback()
        raise

    return {
        "created_step_ids": created_ids,
        "generated_task_count": len(tasks),
        "tree": tree,
    }


def delete_active_tree(
    db: Session,
    plan_id: int,
    step_id: int,
    user_id: int,
) -> dict:
    """逻辑删除节点及其后代，并向上清理变空的分类节点"""

    deleted_ids: list[int] = []

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

        nodes = active_step_repository.list_active_nodes(
            db=db,
            plan_id=plan_id,
        )

        target_id_set = set(target_ids)

        # 删除后必须至少保留一个有效叶子节点
        remaining_leaves = [
            node
            for node in nodes
            if node["node_type"] == "LEAF"
            and node["id"] not in target_id_set
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

        # 向上清理已经没有子节点的分类节点
        parent_id = step["parent_id"]

        while parent_id is not None:

            parent = step_repository.find_step(
                db=db,
                plan_id=plan_id,
                step_id=parent_id,
            )

            if parent is None:
                break

            children_count = step_repository.count_active_children(
                db=db,
                parent_id=parent_id,
            )

            if children_count > 0:
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
