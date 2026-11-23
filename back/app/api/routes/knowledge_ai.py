
"""A3 AI 笔记接口：Router 只做依赖注入、准入和调用编排。"""

from typing import AsyncGenerator


from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import get_current_user
from app.database import get_db
from app.schemas.knowledge_ai import (
    GenerateNoteRequest,
    AskNoteRequest,
)

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


from app.services.knowledge.ai_qa_service import (
    validate_qa_input,
    stream_ask_note,
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


@router.post("/{note_id}/ai/ask")
def ask_note(
    note_id: int,
    data: AskNoteRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """针对当前已保存笔记进行 AI 问答，支持最近三轮追问。"""

    # 第一阶段：校验功能开关和输入。
    # 校验失败时不能消耗 AI 额度。
    require_ai_available()
    validate_qa_input(data)

    user_id = int(current_user["id"])

    # 第二阶段：读取笔记快照。
    # 复用 A3 的权限、非空、长度和凭据检查。
    try:
        snapshot = prepare_note_snapshot(
            db=db,
            note_id=note_id,
            user_id=user_id,
        )
    finally:
        # 不让笔记读取事务持续到 AI 生成结束。
        db.rollback()

    # 第三阶段：申请共享 AI 额度。
    # ASK 使用独立的 operation 标识。
    admission = admit_request(
        db=db,
        user_id=user_id,
        note_id=note_id,
        operation="ASK",
    )

    # 第四阶段：交给公共 Guard 管理整个 SSE 生命周期。
    return stream_response(
        metered_ai_stream(
            admission=admission,
            event_stream=stream_ask_note(
                snapshot=snapshot,
                user_id=user_id,
                data=data,
            ),
        )
    )


