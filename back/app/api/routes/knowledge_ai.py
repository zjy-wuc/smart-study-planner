
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.core.deps import get_current_user
from app.schemas.knowledge_ai import GenerateNoteRequest

from app.services.knowledge.ai_service import (
    prepare_summary,
    note_version_is_current,
)
from app.services.knowledge.ai_note_service import (
    stream_ai_note,
)
from app.services.knowledge.ai_guard_service import (
    admit_request,
    metered_summary,
)


router = APIRouter(
    prefix="/notes",
    tags=["Knowledge AI"],
)


def require_ai_available() -> None:
    if not settings.AI_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="AI 功能尚未启用",
        )

    if not settings.DEEPSEEK_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="AI 模型尚未配置",
        )


def stream_response(generator) -> StreamingResponse:
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


# 主题生成笔记：不需要已有笔记
@router.post("/ai/generate")
def generate_note(
    data: GenerateNoteRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    require_ai_available()

    user_id = int(current_user["id"])

    admission = admit_request(
        db=db,
        user_id=user_id,
        note_id=None,
        operation="GENERATE",
    )

    return stream_response(
        metered_summary(
            snapshot=None,
            admission=admission,
            event_stream=stream_ai_note(
                mode="generate",
                topic=data.topic,
                instructions=data.instructions,
            ),
        )
    )


# 整理已有笔记：只读取数据库已保存内容
@router.post("/{note_id}/ai/organize")
def organize_note(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    require_ai_available()

    user_id = int(current_user["id"])

    try:
        snapshot = prepare_summary(
            db=db,
            note_id=note_id,
            user_id=user_id,
        )
    finally:
        db.rollback()

    admission = admit_request(
        db=db,
        user_id=user_id,
        note_id=note_id,
        operation="ORGANIZE",
    )

    return stream_response(
        metered_summary(
            snapshot=snapshot,
            admission=admission,
            version_check=note_version_is_current,
            event_stream=stream_ai_note(
                mode="organize",
                snapshot=snapshot,
            ),
        )
    )


# 已有的三段式 AI 总结
@router.post("/{note_id}/ai/summary")
def generate_summary(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    require_ai_available()

    user_id = int(current_user["id"])

    try:
        snapshot = prepare_summary(
            db=db,
            note_id=note_id,
            user_id=user_id,
        )
    finally:
        db.rollback()

    admission = admit_request(
        db=db,
        user_id=user_id,
        note_id=note_id,
        operation="SUMMARY",
    )

    return stream_response(
        metered_summary(
            snapshot=snapshot,
            admission=admission,
            version_check=note_version_is_current,
        )
    )
