
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.core.deps import get_current_user

from app.services.knowledge.ai_service import prepare_summary
from app.services.knowledge.ai_guard_service import (
    admit_request,
    metered_summary,
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

    user_id = int(current_user["id"])

    # 1. 读取笔记并验证所有权
    try:
        snapshot = prepare_summary(
            db=db,
            note_id=note_id,
            user_id=user_id,
        )
    finally:
        # 结束笔记读取事务。
        # 后续外部 AI 请求不持有笔记行锁。
        db.rollback()

    # 2. 原子申请全站 + 用户额度
    # admit_request 内部负责 commit / rollback
    admission = admit_request(
        db=db,
        user_id=user_id,
        note_id=note_id,
    )

    
    return StreamingResponse(
        metered_summary(snapshot, admission),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
