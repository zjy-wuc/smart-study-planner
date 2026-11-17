
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.repositories.steps import step_repository
from app.services.plans import plan_service

from app.repositories.knowledge import (
    note_repository,
    review_repository,
)
from app.schemas.knowledge import NoteCreate, NoteUpdate

from typing import NoReturn

def _reject(
    message: str,
    status_code: int = 409,
) -> NoReturn:#这个函数永远不会正常返回给调用者。
    raise HTTPException(
        status_code=status_code,
        detail=message,
    )

def _require_note(
    db: Session,
    note_id: int,
    user_id: int,
    deleted: bool = False,
    for_update: bool = False,
) -> dict:
    """必须是当前用户的笔记。"""

    note = note_repository.find_note(
        db=db,
        note_id=note_id,
        user_id=user_id,
        deleted=deleted,
        for_update=for_update,
    )

    if note is None:
        _reject("知识笔记不存在", 404)

    return note


def _validate_attachment(
    db: Session,
    user_id: int,
    plan_id: int | None,
    step_id: int | None,
) -> None:
    """校验计划及 LEAF 关联是否合法。"""

    if step_id is not None and plan_id is None:
        _reject("关联学习步骤时必须指定计划", 422)

    if plan_id is None:
        return

    # 先确认计划存在且属于当前用户。
    # 这里锁定计划，避免与计划软删除同时修改关联。
    plan_service.get_owned_plan(
        db=db,
        plan_id=plan_id,
        user_id=user_id,
        for_update=True,
    )

    if step_id is None:
        return

    step = step_repository.find_step(
        db=db,
        plan_id=plan_id,
        step_id=step_id,
    )

    if step is None:
        _reject("关联的学习步骤不存在", 404)

    if step["node_type"] != "LEAF":
        _reject("知识笔记只能关联 LEAF 节点")


def create_note(
    db: Session,
    user_id: int,
    data: NoteCreate,
) -> dict:
    try:
        _validate_attachment(
            db=db,
            user_id=user_id,
            plan_id=data.plan_id,
            step_id=data.step_id,
        )

        note_id = note_repository.insert_note(
            db=db,
            user_id=user_id,
            values=data.model_dump(),
        )

        note = _require_note(db, note_id, user_id)

        db.commit()
        return note

    except Exception:
        db.rollback()
        raise


def get_note(
    db: Session,
    note_id: int,
    user_id: int,
) -> dict:
    return _require_note(db, note_id, user_id)


def list_notes(
    db: Session,
    user_id: int,
    deleted: bool = False,
    keyword: str | None = None,
    tag: str | None = None,
    plan_id: int | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    return note_repository.list_notes(
        db=db,
        user_id=user_id,
        deleted=deleted,
        keyword=keyword.strip() if keyword else None,
        tag=tag.strip() if tag else None,
        plan_id=plan_id,
        page=page,
        page_size=page_size,
    )


def update_note(
    db: Session,
    note_id: int,
    user_id: int,
    data: NoteUpdate,
) -> dict:
    try:
        note = _require_note(db, note_id, user_id)

        changes = data.model_dump(exclude_unset=True)

        # 标题、正文、标签不能明确更新为 NULL。
        for field in ("title", "content_md", "tags"):
            if field in changes and changes[field] is None:
                _reject(f"{field} 不能为 null", 422)

        if not changes:
            return note

        # 如果修改关联关系，需要重新检查所有权和节点类型。
        if "plan_id" in changes or "step_id" in changes:
            plan_id = changes.get(
                "plan_id",
                note["plan_id"],
            )

            step_id = changes.get(
                "step_id",
                note["step_id"],
            )

            # 切换计划但未明确指定新 LEAF，
            # 默认解除原有 LEAF 关联。
            if (
                "plan_id" in changes
                and plan_id != note["plan_id"]
                and "step_id" not in changes
            ):
                step_id = None

            _validate_attachment(
                db=db,
                user_id=user_id,
                plan_id=plan_id,
                step_id=step_id,
            )

            changes["plan_id"] = plan_id
            changes["step_id"] = step_id

        affected = note_repository.update_note(
            db=db,
            note_id=note_id,
            user_id=user_id,
            changes=changes,
        )

        if affected == 0:
            # MySQL 可能将未实际改变值的 UPDATE
            # 记为 0 行，因此再次确认笔记是否仍存在。
            _require_note(db, note_id, user_id)

        result = _require_note(db, note_id, user_id)

        db.commit()
        return result

    except Exception:
        db.rollback()
        raise


def delete_note(
    db: Session,
    note_id: int,
    user_id: int,
) -> None:
    try:
        affected = note_repository.soft_delete_note(
            db=db,
            note_id=note_id,
            user_id=user_id,
        )

        if affected == 0:
            _reject("知识笔记不存在或已删除", 404)

        db.commit()

    except Exception:
        db.rollback()
        raise


def restore_note(
    db: Session,
    note_id: int,
    user_id: int,
) -> dict:
    try:
        affected = note_repository.restore_note(
            db=db,
            note_id=note_id,
            user_id=user_id,
        )

        if affected == 0:
            _reject("回收站中不存在该笔记", 404)

        note = _require_note(db, note_id, user_id)

        db.commit()
        return note

    except Exception:
        db.rollback()
        raise


def add_review(
    db: Session,
    note_id: int,
    user_id: int,
) -> dict:
    """用户主动确认完成一次复习。"""

    try:
        _require_note(
            db=db,
            note_id=note_id,
            user_id=user_id,
            for_update=True,
        )

        review = review_repository.insert_review(
            db=db,
            note_id=note_id,
            user_id=user_id,
        )

        db.commit()
        return review

    except Exception:
        db.rollback()
        raise


def get_reviews(
    db: Session,
    note_id: int,
    user_id: int,
) -> list[dict]:
    _require_note(db, note_id, user_id)

    return review_repository.list_reviews(
        db=db,
        note_id=note_id,
        user_id=user_id,
    )
