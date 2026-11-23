"""A5 AI 智能练习接口。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db

from app.api.routes.knowledge_ai import (
    require_ai_available,
    stream_response,
)

from app.schemas.ai_practice import GeneratePracticeRequest

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
    """生成单篇笔记的练习题，不保存数据库。"""

    require_ai_available()

    user_id = int(current_user["id"])

    # 先进行所有权、内容、长度和凭据检查。
    try:
        snapshot = prepare_note_snapshot(
            db=db,
            note_id=data.note_id,
            user_id=user_id,
        )

        validate_practice_source(snapshot)

    finally:
        # 不让笔记查询事务跨越模型请求。
        db.rollback()

    # A5 Guard 已在上一组开发中完成：
    # 生成至少需要剩余两次 AI 调用额度。
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