
"""A2 AI 公共能力：SSE 编码、错误文案与模型输出分段检查。

本文件不读取知识笔记，也不知道生成、整理、总结的具体规则。
"""

import json
from contextlib import aclosing
import re
from dataclasses import dataclass
from typing import AsyncGenerator, Literal

from app.config import settings
from app.services.knowledge.ai_provider import ProviderError, stream_completion


CREDENTIAL_PATTERN = re.compile(
    r"sk-[A-Za-z0-9_-]{20,}"
    r"|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    re.IGNORECASE,
)

# 暂缓发送尾部内容，以便检测跨 SSE 片段的常见凭据格式。
OUTPUT_LOOKAHEAD_CHARS = 64


def _contains_credentials(value: str) -> bool:
    """基础凭据检查；不能替代完整的语义内容审核。"""
    return bool(CREDENTIAL_PATTERN.search(value))


def _sse(event: str, data: dict) -> str:
    """将应用事件编码为 SSE 帧（不是 DeepSeek 的原始 SSE）。"""
    return (
        f"event: {event}\n"
        f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    )


def _public_error(code: str) -> str:
    """映射面向用户的错误文案；不泄露上游异常原文。"""
    messages = {
        "MODEL_UNAVAILABLE": "AI 模型尚未配置",
        "MODEL_AUTH_FAILED": "AI 模型认证失败",
        "MODEL_RATE_LIMITED": "AI 服务请求过于频繁",
        "MODEL_TIMEOUT": "AI 生成超时",
        "MODEL_NETWORK_ERROR": "AI 服务暂时无法连接",
        "MODEL_UPSTREAM_ERROR": "AI 服务暂时不可用",
        "MODEL_INVALID_RESPONSE": "AI 返回了无效数据",
        "MODEL_STREAM_INTERRUPTED": "AI 生成意外中断",
        "MODEL_INCOMPLETE": "AI 生成内容不完整",
        "MODEL_OUTPUT_TOO_LONG": "AI 输出超过长度限制",
        "INVALID_SUMMARY": "AI 总结格式不符合要求",
        "INVALID_MARKDOWN": "生成的 Markdown 格式不符合要求",
    }
    return messages.get(code, "AI 生成失败，请稍后重试")


@dataclass(frozen=True)
class CheckedCompletionEvent:
    """公共检查后的一次文本增量，或包含完整结果的结束事件。"""

    kind: Literal["delta", "finish"]
    text: str
    usage: dict | None = None


async def stream_checked_completion(
    messages: list[dict[str, str]],
) -> AsyncGenerator[CheckedCompletionEvent, None]:
    """消费模型流、限制总长度、检查分段内容，并提供最终完整文本。

    delta 只是临时文本；finish 只表示模型与基础检查完成。
    A3 业务仍须校验笔记格式、来源版本，才能发送 SSE done。
    """
    chunk_size = settings.AI_STREAM_CHUNK_CHARS
    if chunk_size <= 0:
        raise ProviderError("MODEL_INVALID_RESPONSE")

    pending = ""
    checked_tail = ""
    all_parts: list[str] = []
    total_length = 0
    finished = False
    usage: dict | None = None

    async with aclosing(stream_completion(messages)) as provider_stream:
        async for item in provider_stream:
            if item.kind == "finish":
                finished = True
                usage = item.usage
                continue

            text = item.text
            total_length += len(text)
            if total_length > settings.AI_MAX_OUTPUT_CHARS:
                raise ProviderError("MODEL_OUTPUT_TOO_LONG", usage)

            all_parts.append(text)
            pending += text

            # 检查本段及其未发送的后续内容，再释放 chunk_size 个字符。
            while len(pending) >= chunk_size + OUTPUT_LOOKAHEAD_CHARS:
                review = checked_tail + pending[:chunk_size + OUTPUT_LOOKAHEAD_CHARS]
                if _contains_credentials(review):
                    raise ProviderError("MODEL_BLOCKED", usage)

                part = pending[:chunk_size]
                pending = pending[chunk_size:]
                checked_tail = (checked_tail + part)[-OUTPUT_LOOKAHEAD_CHARS:]
                yield CheckedCompletionEvent(kind="delta", text=part)

    if not finished:
        raise ProviderError("MODEL_STREAM_INTERRUPTED", usage)

    if _contains_credentials(checked_tail + pending):
        raise ProviderError("MODEL_BLOCKED", usage)

    if pending:
        yield CheckedCompletionEvent(kind="delta", text=pending)

    yield CheckedCompletionEvent(
        kind="finish",
        text="".join(all_parts),
        usage=usage,
    )
