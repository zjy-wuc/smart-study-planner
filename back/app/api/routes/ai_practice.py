"""A5 AI 智能练习接口。"""

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.api.routes.knowledge_ai import (
    require_ai_available,
    stream_response,
)
from app.core.deps import get_current_user
from app.database import get_db
from app.response import success

from app.repositories.knowledge import practice_repository

from app.schemas.ai_practice import GeneratePracticeRequest
from app.schemas.ai_practice_submit import SubmitPracticeRequest

from app.services.knowledge.ai_guard_service import (
    admit_request,
    metered_ai_stream,
)
from app.services.knowledge.ai_note_service import (
    prepare_note_snapshot,
)
from app.services.knowledge.ai_practice_service import (
    validate_practice_source,
    stream_generate_practice,
)
from app.services.knowledge.ai_practice_grading_service import (
    prepare_submission,
    needs_ai_grading,
    stream_grade_practice,
    stream_saved_practice,
)
from app.services.knowledge import ai_practice_history_service


router = APIRouter(
    prefix="/ai/practices",
    tags=["AI Practice"],
)


@router.post("/generate")
def generate_practice(
    data: GeneratePracticeRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """根据一篇已保存的笔记生成练习题。"""

    require_ai_available()

    user_id = int(current_user["id"])

    try:
        snapshot = prepare_note_snapshot(
            db=db,
            note_id=data.note_id,
            user_id=user_id,
        )

        validate_practice_source(snapshot)

    finally:
        db.rollback()

    admission = admit_request(
        db=db,
        user_id=user_id,
        note_id=data.note_id,
        operation="PRACTICE_GENERATE",
    )

    return stream_response(
        metered_ai_stream(
            admission=admission,
            event_stream=stream_generate_practice(
                snapshot=snapshot,
                user_id=user_id,
                question_count=data.question_count,
            ),
        )
    )


@router.post("/submit")
def submit_practice(
    data: SubmitPracticeRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """统一提交并批改；成功后才保存。"""

    user_id = int(current_user["id"])

    context = prepare_submission(
        data=data,
        user_id=user_id,
    )

    generation_id = context.paper["generation_id"]

    try:
        existing = practice_repository.find_by_generation(
            db=db,
            user_id=user_id,
            generation_id=generation_id,
        )
    finally:
        db.rollback()

    if existing is not None:
        return stream_response(
            stream_saved_practice(existing)
        )

    if needs_ai_grading(context):
        require_ai_available()

        admission = admit_request(
            db=db,
            user_id=user_id,
            note_id=context.paper["note_id"],
            operation="PRACTICE_GRADE",
        )

        return stream_response(
            metered_ai_stream(
                admission=admission,
                event_stream=stream_grade_practice(context),
            )
        )

    # 没有已作答的简答题，不需要调用 AI。
    return stream_response(
        stream_grade_practice(context)
    )


@router.get("")
def list_practices(
    note_id: int | None = Query(default=None, gt=0),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """分页查询本人所有练习历史，支持按笔记筛选。"""

    result = ai_practice_history_service.list_practice_history(
        db=db,
        user_id=int(current_user["id"]),
        note_id=note_id,
        page=page,
        page_size=page_size,
    )

    return success(data=result)


@router.get("/{record_id}")
def get_practice(
    record_id: int = Path(gt=0),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """读取本人一条练习记录的完整题目和评分。"""

    result = ai_practice_history_service.get_practice_history(
        db=db,
        record_id=record_id,
        user_id=int(current_user["id"]),
    )

    return success(data=result)


@router.delete("/{record_id}")
def delete_practice(
    record_id: int = Path(gt=0),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """物理删除本人单条练习历史。"""

    ai_practice_history_service.delete_practice_history(
        db=db,
        record_id=record_id,
        user_id=int(current_user["id"]),
    )

    return success(message="练习历史已删除")