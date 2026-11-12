
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.repositories import step_repository
from app.schemas.step import (
    StepCreate,
    StepUpdate,
    StepRule,
)
from app.services import plan_service


def require_draft_plan(
    db: Session,
    plan_id: int,
    user_id: int,
):
    """检查计划存在、属于当前用户且处于草稿状态"""

    plan = plan_service.get_owned_plan(
        db=db,
        plan_id=plan_id,
        user_id=user_id,
        for_update=True,
    )

    if plan["status"] != "DRAFT":
        raise HTTPException(
            status_code=409,
            detail="本接口目前只允许编辑草稿计划",
        )

    return plan


def require_step(
    db: Session,
    plan_id: int,
    step_id: int,
) -> dict:
    """检查节点属于当前计划且未删除"""

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

    return step


def _insert_tree(
    db: Session,
    plan_id: int,
    parent_id: int | None,
    node: StepCreate,
) -> int:
    """
    递归插入整棵子树。

    这是内部辅助函数，不直接提供 HTTP 接口。
    """

    rule = node.rule

    values = {
        "name": node.name,
        "description": node.description,
        "node_type": node.node_type,
        "task_type": (
            rule.task_type if rule else None
        ),
        "schedule_mode": (
            rule.schedule_mode if rule else None
        ),
        "repeat_content": (
            rule.repeat_content if rule else None
        ),
        "total_target": (
            rule.total_target if rule else None
        ),
    }

    step_id = step_repository.insert_step(
        db=db,
        plan_id=plan_id,
        parent_id=parent_id,
        values=values,
    )

    for child in node.children:

        # 嵌套子节点的父级由程序自动决定
        if child.parent_id is not None:
            raise HTTPException(
                status_code=422,
                detail="嵌套子节点不能指定 parent_id",
            )

        _insert_tree(
            db=db,
            plan_id=plan_id,
            parent_id=step_id,
            node=child,
        )

    return step_id


def create_step(
    db: Session,
    plan_id: int,
    user_id: int,
    data: StepCreate,
) -> dict:
    """在草稿计划中新增完整节点或子树"""

    try:
        require_draft_plan(
            db, plan_id, user_id
        )

        if data.parent_id is not None:
            parent = require_step(
                db,
                plan_id,
                data.parent_id,
            )

            if parent["node_type"] != "GROUP":
                raise HTTPException(
                    status_code=409,
                    detail="不能在 LEAF 下面新增子节点",
                )

        new_step_id = _insert_tree(
            db=db,
            plan_id=plan_id,
            parent_id=data.parent_id,
            node=data,
        )

        db.commit()

    except Exception:
        db.rollback()
        raise

    return {
        "created_id": new_step_id,
        "tree": get_step_tree(
            db, plan_id, user_id
        ),
    }


def get_step_tree(
    db: Session,
    plan_id: int,
    user_id: int,
) -> list[dict]:
    """将数据库中的平面节点转换为树形结构"""

    # 先检查访问权限
    plan_service.get_owned_plan(
        db=db,
        plan_id=plan_id,
        user_id=user_id,
    )

    rows = step_repository.find_all_steps(
        db=db,
        plan_id=plan_id,
    )

    # 创建 ID -> 节点 的映射
    node_map = {
        row["id"]: {
            **row,
            "children": [],
        }
        for row in rows
    }

    roots = []

    for row in rows:
        current = node_map[row["id"]]
        parent_id = row["parent_id"]

        if parent_id is None:
            roots.append(current)

        else:
            parent = node_map.get(parent_id)

            if parent is None:
                raise HTTPException(
                    status_code=500,
                    detail="树形结构存在无效父节点",
                )

            parent["children"].append(current)

    return roots


def update_step(
    db: Session,
    plan_id: int,
    step_id: int,
    user_id: int,
    data: StepUpdate,
) -> dict:
    """修改草稿节点的名称或描述"""

    try:
        require_draft_plan(
            db, plan_id, user_id
        )

        require_step(
            db, plan_id, step_id
        )

        changes = data.model_dump(
            exclude_unset=True
        )

        if not changes:
            raise HTTPException(
                status_code=400,
                detail="没有提供修改内容",
            )

        if (
            "name" in changes
            and changes["name"] is None
        ):
            raise HTTPException(
                status_code=422,
                detail="节点名称不能为空",
            )

        step_repository.update_step_fields(
            db=db,
            plan_id=plan_id,
            step_id=step_id,
            changes=changes,
        )

        db.commit()

    except Exception:
        db.rollback()
        raise

    return require_step(
        db, plan_id, step_id
    )


def update_step_rule(
    db: Session,
    plan_id: int,
    step_id: int,
    user_id: int,
    rule: StepRule,
) -> dict:
    """修改草稿叶子节点的执行规则"""

    try:
        require_draft_plan(
            db, plan_id, user_id
        )

        step = require_step(
            db, plan_id, step_id
        )

        if step["node_type"] != "LEAF":
            raise HTTPException(
                status_code=409,
                detail="只有 LEAF 可以配置执行规则",
            )

        # 规则变化后旧的逐日草稿安排需要重新确认
        step_repository.clear_draft_schedule(
            db, step_id
        )

        step_repository.update_step_rule(
            db=db,
            plan_id=plan_id,
            step_id=step_id,
            values=rule.model_dump(),
        )

        db.commit()

    except Exception:
        db.rollback()
        raise

    return require_step(
        db, plan_id, step_id
    )


def delete_step(
    db: Session,
    plan_id: int,
    step_id: int,
    user_id: int,
):
    """删除整棵子树，并自动清理空父节点"""

    try:
        require_draft_plan(
            db, plan_id, user_id
        )

        step = require_step(
            db, plan_id, step_id
        )

        # 找到该节点及所有后代
        descendant_ids = (
            step_repository.find_descendant_ids(
                db, plan_id, step_id
            )
        )

        step_repository.soft_delete_steps(
            db=db,
            plan_id=plan_id,
            step_ids=descendant_ids,
        )

        # 从被删除节点的父节点开始向上检查
        parent_id = step["parent_id"]

        while parent_id is not None:

            parent = step_repository.find_step(
                db, plan_id, parent_id
            )

            if parent is None:
                break

            remaining = (
                step_repository.count_active_children(
                    db, parent_id
                )
            )

            if remaining > 0:
                break

            # 父节点没有子节点，自动逻辑删除
            step_repository.soft_delete_steps(
                db,
                plan_id,
                [parent_id],
            )

            parent_id = parent["parent_id"]

        db.commit()

    except Exception:
        db.rollback()
        raise
