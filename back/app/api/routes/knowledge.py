
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.response import success
from app.schemas.knowledge import NoteCreate, NoteUpdate
from app.services.knowledge import note_service


router = APIRouter(
    prefix="/notes",
    tags=["Knowledge Notes"],
)


@router.post("", status_code=201)
def create_note(
    data: NoteCreate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = note_service.create_note(
        db=db,
        user_id=user["id"],
        data=data,
    )

    return success(
        data=note,
        message="知识笔记创建成功",
        code=201,
    )


@router.get("")
def list_notes(
    keyword: str | None = Query(default=None, max_length=100),
    tag: str | None = Query(default=None, max_length=50),
    plan_id: int | None = Query(default=None, gt=0),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = note_service.list_notes(
        db=db,
        user_id=user["id"],
        keyword=keyword,
        tag=tag,
        plan_id=plan_id,
        page=page,
        page_size=page_size,
    )

    return success(data=result)


# 静态路径放在 /{note_id} 前面
@router.get("/trash")
def list_deleted_notes(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = note_service.list_notes(
        db=db,
        user_id=user["id"],
        deleted=True,
        page=page,
        page_size=page_size,
    )

    return success(data=result)


@router.get("/{note_id}")
def get_note(
    note_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = note_service.get_note(
        db=db,
        note_id=note_id,
        user_id=user["id"],
    )

    return success(data=note)


@router.patch("/{note_id}")
def update_note(
    note_id: int,
    data: NoteUpdate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = note_service.update_note(
        db=db,
        note_id=note_id,
        user_id=user["id"],
        data=data,
    )

    return success(
        data=note,
        message="知识笔记修改成功",
    )


@router.delete("/{note_id}")
def delete_note(
    note_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note_service.delete_note(
        db=db,
        note_id=note_id,
        user_id=user["id"],
    )

    return success(message="笔记已移入回收站")


@router.post("/{note_id}/restore")
def restore_note(
    note_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = note_service.restore_note(
        db=db,
        note_id=note_id,
        user_id=user["id"],
    )

    return success(
        data=note,
        message="笔记恢复成功",
    )


@router.post("/{note_id}/reviews", status_code=201)
def add_review(
    note_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    review = note_service.add_review(
        db=db,
        note_id=note_id,
        user_id=user["id"],
    )

    return success(
        data=review,
        message="复习记录保存成功",
        code=201,
    )


@router.get("/{note_id}/reviews")
def get_reviews(
    note_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    reviews = note_service.get_reviews(
        db=db,
        note_id=note_id,
        user_id=user["id"],
    )

    return success(data=reviews)
