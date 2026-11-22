##限额服务
import asyncio
import json
import logging
from dataclasses import dataclass
from uuid import uuid4
from typing import AsyncIterator

import anyio
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.core.clock import business_today
from app.database import SessionLocal
from app.repositories.knowledge import ai_guard_repository
from app.schemas.knowledge_ai import NoteSnapshot
from app.services.knowledge.ai_service import (
    stream_summary,
    _sse,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Admission:
    request_id: str
    user_id: int
    note_id: int

#统一拒绝额度不足的请求
def _reject_limit(code: str, message: str) -> None:
    raise HTTPException(
        status_code=429,
        detail={
            "code": code,
            "message": message,
        },
    )


def admit_request(
    db: Session,
    user_id: int,
    note_id: int,
) -> Admission:
    """
    使用 MySQL 事务原子申请 AI 调用名额。

    每个成功准入的请求都会占用一次日额度；
    调用失败也不返还本次准入次数。
    """
    if settings.AI_LEASE_SECONDS <= settings.AI_MAX_STREAM_SECONDS:
        raise RuntimeError(
            "AI lease must exceed stream timeout"
        )

    request_id = str(uuid4())
    today = business_today()

    try:
        ai_guard_repository.lock_admission(db)

        global_daily, user_daily = (
            ai_guard_repository.daily_counts(
                db=db,
                request_date=today,
                user_id=user_id,
            )
        )

        if global_daily >= settings.AI_GLOBAL_DAILY_LIMIT:
            _reject_limit(
                "AI_GLOBAL_DAILY_LIMIT",
                "今日全站 AI 调用额度已用完",
            )

        if user_daily >= settings.AI_USER_DAILY_LIMIT:
            _reject_limit(
                "AI_USER_DAILY_LIMIT",
                "你今天的 AI 调用额度已用完",
            )

        global_active, user_active = (
            ai_guard_repository.active_counts(
                db=db,
                user_id=user_id,
            )
        )

        if global_active >= settings.AI_GLOBAL_CONCURRENCY:
            _reject_limit(
                "AI_GLOBAL_BUSY",
                "AI 服务繁忙，请稍后重试",
            )

        if user_active >= settings.AI_USER_CONCURRENCY:
            _reject_limit(
                "AI_USER_BUSY",
                "你已有正在生成的 AI 请求",
            )

        ai_guard_repository.insert_request(
            db=db,
            request_id=request_id,
            user_id=user_id,
            note_id=note_id,
            request_date=today,
            lease_seconds=settings.AI_LEASE_SECONDS,
        )

        db.commit()

        return Admission(
            request_id=request_id,
            user_id=user_id,
            note_id=note_id,
        )

    except Exception:
        db.rollback()
        raise


def _finish_request_record(
    request_id: str,
    status: str,
    usage: dict | None,
) -> None:
    """
    在独立的短事务中记录完成状态。
    不复用流开始前的数据库 Session。
    """
    usage = usage or {}

    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
#结束时重新创建一个短生命周期的 Session
    with SessionLocal() as db:
        try:
            ai_guard_repository.finish_request(
                db=db,
                request_id=request_id,
                status=status,
                prompt_tokens=(
                    prompt_tokens
                    if isinstance(prompt_tokens, int)
                    and prompt_tokens >= 0
                    else None
                ),
                completion_tokens=(
                    completion_tokens
                    if isinstance(completion_tokens, int)
                    and completion_tokens >= 0
                    else None
                ),
            )
            db.commit()

        except Exception:
            db.rollback()
            raise


def _event_name(frame: str) -> str:
    first_line = frame.split("\n", 1)[0]
    return first_line.removeprefix("event: ").strip()


def _event_data(frame: str) -> dict:
    for line in frame.splitlines():
        if line.startswith("data: "):
            value = json.loads(line[6:])
            return value if isinstance(value, dict) else {}
    return {}

#给 AI 流添加计量和生命周期管理
async def metered_summary(
    snapshot: NoteSnapshot,
    admission: Admission,
) -> AsyncIterator[str]:
    """
    包装原有总结流，添加：
    - 整体执行超时
    - 成功/失败/取消状态
    - Token 用量记录
    - 并发名额释放

   
    """
    final_status = "ERROR"
    usage = None

    try:
        async with asyncio.timeout(#限制整个代码块执行的总时间
            settings.AI_MAX_STREAM_SECONDS
        ):
            async for frame in stream_summary(snapshot):
                event = _event_name(frame)

                if event == "done":
                    final_status = "SUCCESS"
                    usage = _event_data(frame).get("usage")

                elif event == "blocked":
                    final_status = "BLOCKED"

                elif event == "error":
                    final_status = "ERROR"

                yield frame

    except TimeoutError:
        final_status = "TIMEOUT"
        yield _sse(
            "error",
            {
                "code": "AI_TOTAL_TIMEOUT",
                "message": "本次 AI 生成超时",
            },
        )

    except asyncio.CancelledError:
        final_status = "CANCELLED"
        raise

    except Exception:
        final_status = "ERROR"
        logger.exception(
            "ai_stream_unexpected request_id=%s",
            admission.request_id,
        )
        yield _sse(
            "error",
            {
                "code": "AI_INTERNAL_ERROR",
                "message": "AI 生成失败",
            },
        )

    finally:
        try:
            await anyio.to_thread.run_sync(
                _finish_request_record,
                admission.request_id,
                final_status,
                usage,
            )
        except Exception:
            # 记录失败不能泄露密钥或原始笔记。
            # 租约过期后仍可释放并发名额。
            logger.exception(
                "ai_request_finalization_failed request_id=%s",
                admission.request_id,
            )
