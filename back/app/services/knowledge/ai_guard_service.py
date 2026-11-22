
import asyncio
import json
import logging
from dataclasses import dataclass
from typing import AsyncIterator, Callable
from uuid import uuid4

import anyio
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.core.clock import business_today
from app.database import SessionLocal
from app.repositories.knowledge import ai_guard_repository
from app.schemas.knowledge_ai import NoteSnapshot
from app.services.knowledge.ai_service import (
    _sse,
    stream_summary,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Admission:
    request_id: str
    user_id: int
    note_id: int


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
    if (
        settings.AI_LEASE_SECONDS
        <= settings.AI_MAX_STREAM_SECONDS
    ):
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
    usage = usage or {}

    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")

    def valid_token_count(value: object) -> int | None:
        if (
            isinstance(value, int)
            and not isinstance(value, bool)
            and value >= 0
        ):
            return value
        return None

    with SessionLocal() as db:
        try:
            ai_guard_repository.finish_request(
                db=db,
                request_id=request_id,
                status=status,
                prompt_tokens=valid_token_count(
                    prompt_tokens
                ),
                completion_tokens=valid_token_count(
                    completion_tokens
                ),
            )

            db.commit()

        except Exception:
            db.rollback()
            raise


def _event_name(frame: str) -> str:
    return (
        frame.split("\n", 1)[0]
        .removeprefix("event: ")
        .strip()
    )


def _event_data(frame: str) -> dict:
    for line in frame.splitlines():
        if line.startswith("data: "):
            value = json.loads(line[6:])
            return value if isinstance(value, dict) else {}

    return {}


async def metered_summary(
    snapshot: NoteSnapshot,
    admission: Admission,
    version_check: Callable[
        [NoteSnapshot, int], bool
    ] | None = None,
) -> AsyncIterator[str]:
    """
    核心原则：
    只有完成所有业务检查和 SUCCESS 数据库提交，
    才允许向前端发送 done。

    其他终止状态记录到 ai_requests。
    """
    final_status = "ERROR"
    usage: dict | None = None
    recorded = False

    async def settle(status: str) -> None:
        nonlocal final_status, recorded

        final_status = status

        await anyio.to_thread.run_sync(
            _finish_request_record,
            admission.request_id,
            status,
            usage,
        )

        recorded = True

    try:
        async with asyncio.timeout(
            settings.AI_MAX_STREAM_SECONDS
        ):
            async for frame in stream_summary(snapshot):
                event = _event_name(frame)

                if event not in {
                    "done", "blocked", "error"
                }:
                    yield frame
                    continue

                payload = _event_data(frame)
                event_usage = payload.get("usage")

                if isinstance(event_usage, dict):
                    usage = event_usage

                if event == "done":
                    if version_check is not None:
                        is_current = (
                            await anyio.to_thread.run_sync(
                                version_check,
                                snapshot,
                                admission.user_id,
                            )
                        )

                        if not is_current:
                            await settle("STALE")
                            yield _sse(
                                "error",
                                {
                                    "code": "NOTE_CHANGED",
                                    "message": (
                                        "笔记已修改或删除，"
                                        "本次总结已失效"
                                    ),
                                },
                            )
                            return

                    # 先提交数据库，再宣布成功。
                    await settle("SUCCESS")
                    yield frame
                    return

                if event == "blocked":
                    await settle("BLOCKED")
                    yield frame
                    return

                await settle("ERROR")
                yield frame
                return

            # 正常退出循环却没有终止事件
            await settle("ERROR")
            yield _sse(
                "error",
                {
                    "code": "AI_STREAM_INTERRUPTED",
                    "message": "AI 响应提前结束",
                },
            )

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
        if not recorded:
            try:
                # 即使请求被取消，也尽可能完成状态结算。
                with anyio.CancelScope(shield=True):
                    await anyio.to_thread.run_sync(
                        _finish_request_record,
                        admission.request_id,
                        final_status,
                        usage,
                    )

            except Exception:
                logger.exception(
                    "ai_request_finalization_failed "
                    "request_id=%s",
                    admission.request_id,
                )
