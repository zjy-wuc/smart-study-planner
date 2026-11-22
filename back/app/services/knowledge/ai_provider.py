
import json
from dataclasses import dataclass
from typing import AsyncIterator, Literal

import httpx

from app.config import settings


class ProviderError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ProviderEvent:#
    kind: Literal["delta", "finish"]
    text: str = ""
    usage: dict | None = None
  

async def stream_completion(
    messages: list[dict[str, str]],
) -> AsyncIterator[ProviderEvent]:#异步生成器
    """
    将 DeepSeek 原始 SSE 转换为应用内部事件。

    只处理模型协议，不负责：
    - 用户权限
    - 笔记读取
    - 业务结果保存
    """

    api_key = settings.DEEPSEEK_API_KEY

    if not api_key:
        raise ProviderError("MODEL_UNAVAILABLE")

    timeout = httpx.Timeout(
        connect=10.0,
        read=90.0,
        write=10.0,
        pool=10.0,
    )

    payload = {
        "model": settings.DEEPSEEK_MODEL,
        "messages": messages,
        "stream": True,
        "stream_options": {
            "include_usage": True,
        },
        "thinking": {
            "type": "disabled",
        },
        "max_tokens": 1600,
        "safety_check": {
            "level": "high",
        },
    }
#初始化流式状态变量
    finish_reason: str | None = None
    usage: dict | None = None
    stream_ended = False

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
        ) as client:

            async with client.stream(
                "POST",
                "https://api.deepseek.com/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            ) as response:

                if response.status_code != 200:
                    if response.status_code == 429:
                        raise ProviderError("MODEL_RATE_LIMITED")

                    if response.status_code in (401, 403):
                        raise ProviderError("MODEL_AUTH_FAILED")

                    if response.status_code == 400:
                        raw = (
                            await response.aread()#异步读取响应体，返回 bytes
                        )[:2048].decode(
                            "utf-8",
                            errors="ignore",#把字节转换为字符串
                        )

                        if "Content Exists Risk" in raw:
                            raise ProviderError("MODEL_BLOCKED")

                    raise ProviderError("MODEL_UPSTREAM_ERROR")

                async for line in response.aiter_lines():
                    if not line.startswith("data:"):#过滤非 data: 行
                        continue

                    data = line[5:].strip()

                    if data == "[DONE]":
                        stream_ended = True
                        break

                    if not data:
                        continue

                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError as exc:
                        raise ProviderError(
                            "MODEL_INVALID_RESPONSE"
                        ) from exc#表示异常链

                    if not isinstance(chunk, dict):
                        raise ProviderError(
                            "MODEL_INVALID_RESPONSE"
                        )


                    if isinstance(chunk.get("error"), dict):
                        raise ProviderError("MODEL_UPSTREAM_ERROR")


                        
                    if isinstance(chunk.get("usage"), dict):
                        usage = chunk["usage"]

                    choices = chunk.get("choices")

                    if not isinstance(choices, list) or not choices:
                        raise ProviderError(
                            "MODEL_INVALID_RESPONSE"
                        )

                    choice = choices[0]

                    if not isinstance(choice, dict):
                        raise ProviderError(
                            "MODEL_INVALID_RESPONSE"
                        )

                    delta = choice.get("delta") or {}

                    if not isinstance(delta, dict):
                        raise ProviderError(
                            "MODEL_INVALID_RESPONSE"
                        )

                    text = delta.get("content")

                    if isinstance(text, str) and text:
                        yield ProviderEvent(
                            kind="delta",
                            text=text,
                        )

                    reason = choice.get("finish_reason")

                    if reason is not None:
                        finish_reason = reason

        if not stream_ended:
            raise ProviderError("MODEL_STREAM_INTERRUPTED")

        if finish_reason == "content_filter":
            raise ProviderError("MODEL_BLOCKED")

        if finish_reason != "stop":
            raise ProviderError("MODEL_INCOMPLETE")

        yield ProviderEvent(
            kind="finish",
            usage=usage,
        )

    except ProviderError:
        raise

    except httpx.TimeoutException as exc:
        raise ProviderError("MODEL_TIMEOUT") from exc

    except httpx.HTTPError as exc:
        raise ProviderError("MODEL_NETWORK_ERROR") from exc
