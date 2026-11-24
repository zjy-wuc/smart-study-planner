"""A5 练习历史：查询、详情与删除。"""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.repositories.knowledge import practice_repository


def list_practice_history(
    db: Session,
    user_id: int,
    note_id: int | None,
    page: int,
    page_size: int,
) -> dict:
    """查询当前用户的练习历史。"""

    return practice_repository.list_records(
        db=db,
        user_id=user_id,
        note_id=note_id,
        page=page,
        page_size=page_size,
    )


def get_practice_history(
    db: Session,
    record_id: int,
    user_id: int,
) -> dict:
    """获取完整历史详情。"""

    record = practice_repository.find_record(
        db=db,
        record_id=record_id,
        user_id=user_id,
    )

    if record is None:
        raise HTTPException(
            status_code=404,
            detail="练习记录不存在",
        )

    return record


def delete_practice_history(
    db: Session,
    record_id: int,
    user_id: int,
) -> None:
    """物理删除本人练习记录。"""

    try:
        affected = practice_repository.delete_record(
            db=db,
            record_id=record_id,
            user_id=user_id,
        )

        if affected == 0:
            raise HTTPException(
                status_code=404,
                detail="练习记录不存在",
            )

        db.commit()

    except Exception:
        db.rollback()
        raise