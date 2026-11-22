
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.core.deps import get_current_user
from app.services.knowledge.ai_service import (
    prepare_summary,
    stream_summary,
)


router = APIRouter(
    prefix="/notes",
    tags=["Knowledge AI"],
)


@router.post("/{note_id}/ai/summary")
def generate_summary(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
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

    try:
        snapshot = prepare_summary(
            db=db,
            note_id=note_id,
            user_id=int(current_user["id"]),
        )
    finally:
        # SELECT 开启的事务应在外部模型调用前结束。
        # 后续异步生成只持有 NoteSnapshot。
        db.rollback()

    return StreamingResponse(
        stream_summary(snapshot),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
