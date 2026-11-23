
"""A2 AI 公共守卫：共享额度、并发限制、流式请求状态结算。"""

import asyncio
import json
import logging
from contextlib import aclosing
from dataclasses import dataclass
from typing import AsyncGenerator
from uuid import uuid4

import anyio
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.core.clock import business_today
from app.database import SessionLocal
from app.repositories.knowledge import ai_guard_repository
from app.services.knowledge.ai_service import _sse

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Admission:
    """通过 MySQL 准入检查的请求；主题生成不绑定笔记 ID。"""

    request_id: str
    user_id: int
    note_id: int | None


def _reject_limit(code: str, message: str) -> None:
    """额度和并发拒绝都返回 HTTP 429，以及可识别的业务错误码。"""
    raise HTTPException(
        status_code=429,
        detail={"code": code, "message": message},
    )


def admit_request(
    db: Session,
    user_id: int,
    note_id: int | None,
    operation: str = "SUMMARY",
) -> Admission:
    """在同一个数据库事务中原子检查额度、并发，并写入 RUNNING。

    多进程通过 ai_guard_mutex 的 FOR UPDATE 串行准入；
    在调用 DeepSeek 之前 COMMIT，避免模型生成期间占用数据库行锁。
    """
    if operation not in {"SUMMARY", "GENERATE", "ORGANIZE", "ASK"}:
        raise ValueError("Unsupported AI operation")

    if settings.AI_LEASE_SECONDS <= settings.AI_MAX_STREAM_SECONDS:
        raise RuntimeError("AI lease must exceed stream timeout")

    request_id = str(uuid4())
    today = business_today()

    try:
        ai_guard_repository.lock_admission(db)

        global_daily, user_daily = ai_guard_repository.daily_counts(
            db=db,
            request_date=today,
            user_id=user_id,
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

        global_active, user_active = ai_guard_repository.active_counts(
            db=db,
            user_id=user_id,
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

        # 一旦成功准入，便占用当天一次请求额度；失败不自动退还。
        ai_guard_repository.insert_request(
            db=db,
            request_id=request_id,
            user_id=user_id,
            note_id=note_id,
            request_date=today,
            lease_seconds=settings.AI_LEASE_SECONDS,
            operation=operation,
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
    """独立短事务结算状态；未获取用量时写 NULL 而不是 0。"""

    usage = usage or {}

    def valid_token_count(value: object) -> int | None:
        # bool 是 int 的子类，但 True/False 不是合法 Token 用量。
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
                    usage.get("prompt_tokens")
                ),
                completion_tokens=valid_token_count(
                    usage.get("completion_tokens")
                ),
            )
            db.commit()

        except Exception:
            db.rollback()
            raise


def _event_name(frame: str) -> str:
    """只解析应用内部构造的 SSE 帧，不解析厂商原始响应。"""
    return frame.split("\n", 1)[0].removeprefix("event: ").strip()


def _event_data(frame: str) -> dict:
    for line in frame.splitlines():
        if line.startswith("data: "):
            value = json.loads(line[6:])
            return value if isinstance(value, dict) else {}

    return {}


async def metered_ai_stream(
    admission: Admission,
    event_stream: AsyncGenerator[str, None],
) -> AsyncGenerator[str, None]:
    """与具体 AI 业务无关的流式生命周期管理器。

    - start/delta/reviewing：直接转发，为临时结果；
    - done：先写 SUCCESS 再发送成功事件；
    - blocked/error：结算对应状态，再发送终止事件；
    - 取消、超时与意外错误：尽力落库，避免长期占用并发。
    """

    final_status = "ERROR"
    usage: dict | None = None
    recorded = False

    async def settle(status: str) -> None:
        nonlocal final_status, recorded

        final_status = status

        # 同步 SQLAlchemy 写入放入工作线程；
        # 成功返回才算结算完成。
        await anyio.to_thread.run_sync(
            _finish_request_record,
            admission.request_id,
            status,
            usage,
        )

        recorded = True

    try:
        async with asyncio.timeout(settings.AI_MAX_STREAM_SECONDS):

            # 业务流必须是 AsyncGenerator，以支持 aclose() 清理连接。
            async with aclosing(event_stream):

                async for frame in event_stream:
                    event = _event_name(frame)

                    if event not in {"done", "blocked", "error"}:
                        yield frame
                        continue

                    payload = _event_data(frame)

                    if isinstance(payload.get("usage"), dict):
                        usage = payload["usage"]

                    if event == "done":
                        # 必须先提交数据库，才发送成功事件。
                        await settle("SUCCESS")
                        yield frame
                        return

                    if event == "blocked":
                        await settle("BLOCKED")
                        yield frame
                        return

                    # 业务流可通过状态元数据声明 STALE。
                    # Guard 不需要认识 NOTE_CHANGED 等业务错误码。
                    error_status = (
                        "STALE"
                        if payload.get("status") == "STALE"
                        else "ERROR"
                    )

                    await settle(error_status)
                    yield frame
                    return

                # 没有终止事件就结束，属于协议不完整。
                # 不允许视为成功。
                await settle("ERROR")

                yield _sse(
                    "error",
                    {
                        "code": "AI_STREAM_INTERRUPTED",
                        "message": "AI 响应提前结束",
                    },
                )

    except TimeoutError:
        # 先把 TIMEOUT 写入数据库，再向客户端报告超时。
        try:
            await settle("TIMEOUT")

        except Exception:
            logger.exception(
                "ai_timeout_settlement_failed request_id=%s",
                admission.request_id,
            )

            yield _sse(
                "error",
                {
                    "code": "AI_INTERNAL_ERROR",
                    "message": "AI 生成失败",
                },
            )

        else:
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
                # shield 降低取消信号打断结算的风险；
                # 但不能抵御进程强制终止。
                #，就再尝试把状态写入数据库
                with anyio.CancelScope(shield=True):
                    await anyio.to_thread.run_sync(
                        _finish_request_record,
                        admission.request_id,
                        final_status,
                        usage,
                    )

            except Exception:
                # RUNNING 可能残留。
                # 租约到期后不再计入并发数量。
                logger.exception(
                    "ai_request_finalization_failed request_id=%s",
                    admission.request_id,
                )
