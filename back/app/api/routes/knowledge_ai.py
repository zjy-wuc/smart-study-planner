
"""A3 AI 笔记接口：Router 只做依赖注入、准入和调用编排。"""

from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import get_current_user
from app.database import get_db
from app.schemas.knowledge_ai import GenerateNoteRequest

from app.services.knowledge.ai_guard_service import (
    admit_request,
    metered_ai_stream,
)

from app.services.knowledge.ai_note_service import (
    prepare_note_snapshot,
    stream_generate_note,
    stream_organize_note,
    stream_summary_note,
    validate_generate_input,
)


router = APIRouter(
    prefix="/notes",
    tags=["Knowledge AI"],
)


def require_ai_available() -> None:
    """关闭功能或未配置模型时，直接拒绝，不占用请求额度。"""

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


def stream_response(
    generator: AsyncGenerator[str, None],
) -> StreamingResponse:
    """三个业务使用同一 SSE 响应头。"""

    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/ai/generate")
def generate_note(
    data: GenerateNoteRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """按主题生成新笔记候选稿；AI 不直接写入 knowledge_notes。"""

    require_ai_available()

    # 先检查输入，再申请额度。
    validate_generate_input(
        data.topic,
        data.instructions,
    )

    user_id = int(current_user["id"])

    admission = admit_request(
        db=db,
        user_id=user_id,
        note_id=None,
        operation="GENERATE",
    )

    return stream_response(
        metered_ai_stream(
            admission=admission,
            event_stream=stream_generate_note(
                data.topic,
                data.instructions,
            ),
        )
    )


@router.post("/{note_id}/ai/organize")
def organize_note(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """只使用已保存原笔记；整理结果必须由用户另存为新笔记。"""

    require_ai_available()
    user_id = int(current_user["id"])

    try:
        snapshot = prepare_note_snapshot(
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
        metered_ai_stream(
            admission=admission,
            event_stream=stream_organize_note(
                snapshot,
                user_id,
            ),
        )
    )


@router.post("/{note_id}/ai/summary")
def generate_summary(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """总结已保存笔记；仅展示与复制，AI 不自动保存总结。"""

    require_ai_available()
    user_id = int(current_user["id"])

    try:
        snapshot = prepare_note_snapshot(
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
        metered_ai_stream(
            admission=admission,
            event_stream=stream_summary_note(
                snapshot,
                user_id,
            ),
        )
    )
