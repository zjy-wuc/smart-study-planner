
import asyncio
import json
import logging

from contextlib import aclosing
from dataclasses import dataclass
from typing import AsyncGenerator, AsyncIterator, Callable
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


# ============================================================
# 1. AI 请求准入结果
# ============================================================

@dataclass(frozen=True)
class Admission:
    """
    表示一次已经通过额度与并发检查的 AI 请求。

    request_id:
        本次 AI 请求的唯一标识，对应 ai_requests.request_id。

    user_id:
        发起请求的用户 ID。

    note_id:
        关联的原始笔记 ID。

        SUMMARY  -> 原笔记 ID
        ORGANIZE -> 原笔记 ID
        GENERATE -> None

    frozen=True:
        防止准入成功后意外修改这些字段。
    """

    request_id: str
    user_id: int
    note_id: int | None


# ============================================================
# 2. 统一处理额度限制
# ============================================================

def _reject_limit(
    code: str,
    message: str,
) -> None:
    """
    抛出 AI 限额异常。

    HTTP 429 表示请求过于频繁或者达到额度限制。

    detail 使用字典，方便前端通过错误码判断：
        AI_USER_DAILY_LIMIT
        AI_GLOBAL_DAILY_LIMIT
        AI_USER_BUSY
        AI_GLOBAL_BUSY
    """

    raise HTTPException(
        status_code=429,
        detail={
            "code": code,
            "message": message,
        },
    )


# ============================================================
# 3. 申请 AI 调用名额
# ============================================================

def admit_request(
    db: Session,
    user_id: int,
    note_id: int | None,
    operation: str = "SUMMARY",
) -> Admission:
    """
    为一次 AI 请求申请调用名额。

    执行流程：
        1. 验证 AI 操作类型
        2. 检查租约配置
        3. 生成 request_id
        4. 获取数据库准入锁
        5. 检查全站每日额度
        6. 检查用户每日额度
        7. 检查全站并发
        8. 检查用户并发
        9. 插入 RUNNING 请求记录
       10. 提交事务并返回 Admission

    核心原则：

    多个后端进程共用 MySQL 额度记录。

    必须先获取数据库行锁，再检查额度，
    否则并发请求可能同时通过检查，导致超额。

    本函数不调用 DeepSeek。
    """

    # ---------- 1. 校验操作类型 ----------

    allowed_operations = {
        "SUMMARY",
        "GENERATE",
        "ORGANIZE",
    }

    if operation not in allowed_operations:
        raise ValueError(
            "Unsupported AI operation"
        )

    # ---------- 2. 检查时间配置 ----------

    # 租约必须长于允许的整条流执行时间。
    # 避免一个仍在执行的请求提前失去并发占用记录。
    if (
        settings.AI_LEASE_SECONDS
        <= settings.AI_MAX_STREAM_SECONDS
    ):
        raise RuntimeError(
            "AI lease must exceed stream timeout"
        )

    # ---------- 3. 准备请求信息 ----------

    request_id = str(uuid4())

    # 使用项目统一的业务日期（北京时间）。
    today = business_today()

    try:
        # ---------- 4. 获取数据库准入锁 ----------

        # Repository 内部使用 SELECT ... FOR UPDATE。
        #
        # 同一时刻只有一个事务能够完成准入检查，
        # 其他事务需要等待该事务 COMMIT / ROLLBACK。
        ai_guard_repository.lock_admission(db)

        # ---------- 5. 查询每日调用次数 ----------

        global_daily, user_daily = (
            ai_guard_repository.daily_counts(
                db=db,
                request_date=today,
                user_id=user_id,
            )
        )

        # 全站额度优先检查。
        if global_daily >= settings.AI_GLOBAL_DAILY_LIMIT:
            _reject_limit(
                "AI_GLOBAL_DAILY_LIMIT",
                "今日全站 AI 调用额度已用完",
            )

        # 当前用户自己的每日额度。
        if user_daily >= settings.AI_USER_DAILY_LIMIT:
            _reject_limit(
                "AI_USER_DAILY_LIMIT",
                "你今天的 AI 调用额度已用完",
            )

        # ---------- 6. 查询当前并发数量 ----------

        # 只统计：
        # status = RUNNING
        # 且 leased_until 还没有过期的请求。
        global_active, user_active = (
            ai_guard_repository.active_counts(
                db=db,
                user_id=user_id,
            )
        )

        # 全站并发限制。
        if global_active >= settings.AI_GLOBAL_CONCURRENCY:
            _reject_limit(
                "AI_GLOBAL_BUSY",
                "AI 服务繁忙，请稍后重试",
            )

        # 单用户并发限制。
        if user_active >= settings.AI_USER_CONCURRENCY:
            _reject_limit(
                "AI_USER_BUSY",
                "你已有正在生成的 AI 请求",
            )

        # ---------- 7. 创建 AI 请求记录 ----------

        # 请求成功准入后，就计入当天的调用次数。
        #
        # 本阶段采用：
        # 即使模型随后失败，也不退还准入次数。
        #
        # GENERATE 对应 note_id=None，
        # 所以数据库该字段必须允许 NULL。
        ai_guard_repository.insert_request(
            db=db,
            request_id=request_id,
            user_id=user_id,
            note_id=note_id,
            request_date=today,
            lease_seconds=settings.AI_LEASE_SECONDS,
            operation=operation,
        )

        # ---------- 8. 提交事务 ----------

        # COMMIT 会：
        # 1. 保存 RUNNING 记录
        # 2. 释放 FOR UPDATE 行锁
        #
        # DeepSeek 调用必须发生在 COMMIT 之后。
        db.commit()

        # ---------- 9. 返回准入信息 ----------

        return Admission(
            request_id=request_id,
            user_id=user_id,
            note_id=note_id,
        )

    except Exception:
        # 无论是额度异常还是数据库异常，
        # 都需要回滚当前事务、释放数据库锁。
        db.rollback()
        raise


# ============================================================
# 4. 更新 AI 请求最终状态
# ============================================================

def _finish_request_record(
    request_id: str,
    status: str,
    usage: dict | None,
) -> None:
    """
    将 ai_requests 中的 RUNNING 请求更新为最终状态。

    可能状态：
        SUCCESS
        ERROR
        BLOCKED
        TIMEOUT
        CANCELLED
        STALE

    使用独立的短生命周期 Session，
    避免流式执行阶段持有原来的数据库事务。

    usage 中通常包含：
        prompt_tokens
        completion_tokens

    未获取到 Token 用量时，保存 NULL，
    不能把未知用量错误记录为 0。
    """

    usage = usage or {}

    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")

    def valid_token_count(
        value: object,
    ) -> int | None:
        """
        校验模型返回的 Token 数量。

        只接受非负整数。
        明确排除 bool，因为 Python 中 bool 是 int 的子类。
        """

        if (
            isinstance(value, int)
            and not isinstance(value, bool)
            and value >= 0
        ):
            return value

        return None

    # 每一次状态结算，都使用新的数据库 Session。
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

            # 状态结算成功后才提交。
            db.commit()

        except Exception:
            db.rollback()
            raise


# ============================================================
# 5. 解析应用层 SSE 事件
# ============================================================

def _event_name(frame: str) -> str:
    """
    提取 SSE 帧的事件名称。

    输入示例：
        event: delta
        data: {"text":"你好"}

    返回：
        delta

    此函数处理的是应用内部构造的 SSE 帧，
    不负责解析 DeepSeek 原始流。
    """

    first_line = frame.split("\n", 1)[0]

    return (
        first_line
        .removeprefix("event: ")
        .strip()
    )


def _event_data(frame: str) -> dict:
    """
    提取 SSE 帧中的 JSON 数据。

    输入：
        event: done
        data: {"usage":{"prompt_tokens":100}}

    输出：
        {"usage":{"prompt_tokens":100}}

    如果 JSON 格式错误，异常会交给上层统一处理。
    """

    for line in frame.splitlines():
        if line.startswith("data: "):
            value = json.loads(line[6:])

            return (
                value
                if isinstance(value, dict)
                else {}
            )

    return {}


# ============================================================
# 6. AI 流式请求管理与状态结算
# ============================================================

async def metered_summary(
    snapshot: NoteSnapshot | None,
    admission: Admission,
    version_check: Callable[
        [NoteSnapshot, int], bool
    ] | None = None,
    event_stream: AsyncGenerator[str, None] | None = None,
) -> AsyncIterator[str]:
    """
    统一管理 AI SSE 流式响应。

    当前支持三种业务：

    1. SUMMARY
       snapshot 不为 None。
       不传 event_stream，默认调用 stream_summary()。

    2. GENERATE
       snapshot=None。
       传入 stream_ai_note(mode="generate") 生成器。

    3. ORGANIZE
       snapshot 为原笔记快照。
       传入 stream_ai_note(mode="organize") 生成器。
       同时传入 version_check，检查原笔记有无变化。

    核心职责：
        - 控制整条请求的最大执行时间
        - 接收业务层 SSE 事件
        - 解析 done / blocked / error
        - 验证笔记版本
        - 记录 AI 请求最终状态
        - 保存模型 Token 用量
        - 处理超时、取消与意外错误

    重要原则：

    只有数据库成功提交 SUCCESS，
    才能向前端发送 done。

    delta 是临时内容，不代表业务最终成功。
    """

    # 默认按照失败处理。
    # 只有所有成功条件满足后，才能改为 SUCCESS。
    final_status = "ERROR"

    # 保存模型的 Token 用量。
    usage: dict | None = None

    # 表示最终状态是否已经成功写入数据库。
    recorded = False

    # --------------------------------------------------------
    # 内部函数：结算请求状态
    # --------------------------------------------------------

    async def settle(status: str) -> None:
        nonlocal final_status, recorded

        final_status = status

        # 数据库操作是同步 SQLAlchemy，
        # 放入工作线程避免阻塞事件循环。
        await anyio.to_thread.run_sync(
            _finish_request_record,
            admission.request_id,
            status,
            usage,
        )

        # 只有数据库操作成功返回，才标记为已结算。
        recorded = True

    try:
        # ----------------------------------------------------
        # 1. 控制整条流的最大执行时间
        # ----------------------------------------------------

        async with asyncio.timeout(
            settings.AI_MAX_STREAM_SECONDS
        ):

            # ------------------------------------------------
            # 2. 选择实际业务流
            # ------------------------------------------------

            if event_stream is None:
                # 未传业务流，表示调用原有总结功能。
                if snapshot is None:
                    raise ValueError(
                        "Summary requires a note snapshot"
                    )

                source = stream_summary(snapshot)

            else:
                # A3 的生成和整理功能，会传入自己的流。
                source = event_stream

            # aclosing 确保正常完成、提前返回或异常时，
            # 业务异步生成器能及时关闭。
            async with aclosing(source):

                # --------------------------------------------
                # 3. 消费业务层 SSE
                # --------------------------------------------

                async for frame in source:
                    event = _event_name(frame)

                    # start / delta / reviewing
                    # 属于普通流式事件，直接向客户端转发。
                    if event not in {
                        "done",
                        "blocked",
                        "error",
                    }:
                        yield frame
                        continue

                    # ----------------------------------------
                    # 4. 读取最终事件的 Token 用量
                    # ----------------------------------------

                    payload = _event_data(frame)
                    event_usage = payload.get("usage")

                    if isinstance(event_usage, dict):
                        usage = event_usage

                    # ----------------------------------------
                    # 5. 处理成功事件 done
                    # ----------------------------------------

                    if event == "done":

                        # 整理或总结已有笔记时，
                        # 需要再次确认笔记未修改、未删除。
                        if version_check is not None:
                            if snapshot is None:
                                raise ValueError(
                                    "Version check requires a note snapshot"
                                )
                            if snapshot is None:
                                raise ValueError(
                                    "Version check requires "
                                    "a note snapshot"
                                )

                            # 使用工作线程执行同步数据库检查。
                            is_current = (
                                await anyio.to_thread.run_sync(
                                    version_check,
                                    snapshot,
                                    admission.user_id,
                                )
                            )

                            if not is_current:
                                # 笔记版本变化：
                                # 本次生成结果已经失效。
                                await settle("STALE")

                                yield _sse(
                                    "error",
                                    {
                                        "code": "NOTE_CHANGED",
                                        "message": (
                                            "笔记已修改或删除，"
                                            "本次生成结果已失效"
                                        ),
                                    },
                                )
                                return

                        # ------------------------------------
                        # 6. 先写成功状态，再发送 done
                        # ------------------------------------

                        await settle("SUCCESS")

                        # 走到这里表示数据库结算成功。
                        yield frame
                        return

                    # ----------------------------------------
                    # 7. 处理安全拒绝
                    # ----------------------------------------

                    if event == "blocked":
                        await settle("BLOCKED")

                        yield frame
                        return

                    # ----------------------------------------
                    # 8. 处理业务层错误
                    # ----------------------------------------

                    if event == "error":
                        await settle("ERROR")

                        yield frame
                        return

                # --------------------------------------------
                # 9. 流结束却没有任何终止事件
                # --------------------------------------------

                # 正常情况下，业务流应该发送：
                # done / blocked / error 其中之一。
                #
                # 如果没有，说明流提前中断，
                # 不允许将其视为成功。
                await settle("ERROR")

                yield _sse(
                    "error",
                    {
                        "code": "AI_STREAM_INTERRUPTED",
                        "message": "AI 响应提前结束",
                    },
                )

    # --------------------------------------------------------
    # 10. 整条流超时
    # --------------------------------------------------------

    except TimeoutError:
        # 这里修复 A2 验收报告指出的 P1 问题：
        #
        # 旧逻辑：
        #     先发送超时事件，再在 finally 结算。
        #
        # 新逻辑：
        #     先提交 TIMEOUT，再发送超时事件。

        try:
            await settle("TIMEOUT")

        except Exception:
            # 如果超时状态结算失败，
            # 不能假装本次超时处理已经完整成功。
            logger.exception(
                "ai_timeout_settlement_failed "
                "request_id=%s",
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

    # --------------------------------------------------------
    # 11. 客户端取消请求
    # --------------------------------------------------------

    except asyncio.CancelledError:
        # 例如浏览器 AbortController.abort()，
        # 或服务端取消当前请求任务。
        #
        # 不将取消误报为模型错误。
        final_status = "CANCELLED"

        # 继续向上抛出，让框架完成取消流程。
        # finally 负责尽力写入 CANCELLED 状态。
        raise

    # --------------------------------------------------------
    # 12. 未预期异常
    # --------------------------------------------------------

    except Exception:
        final_status = "ERROR"

        # 只记录 request_id 和异常信息，
        # 不主动记录笔记正文或模型 Prompt。
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

    # --------------------------------------------------------
    # 13. 最终兜底结算
    # --------------------------------------------------------

    finally:
        # done / blocked / error 等正常路径，
        # 之前已经 settle()，recorded 为 True。
        #
        # 对超时、取消、意外异常等情况，
        # 如果尚未成功结算，则尝试补写状态。

        if not recorded:
            try:
                # shield 用于降低取消信号中断清理流程的风险。
                # 不能保证在进程被强制终止时仍可完成写入。
                with anyio.CancelScope(shield=True):
                    await anyio.to_thread.run_sync(
                        _finish_request_record,
                        admission.request_id,
                        final_status,
                        usage,
                    )

            except Exception:
                # 最后一次结算也失败时，只记录日志。
                #
                # 租约过期后，该请求不再计入并发数量；
                # 但数据库状态可能仍为 RUNNING，
                # 后续需要由过期状态清理机制处理。
                logger.exception(
                    "ai_request_finalization_failed "
                    "request_id=%s",
                    admission.request_id,
                )
