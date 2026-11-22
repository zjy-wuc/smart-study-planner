
import json
from dataclasses import dataclass
from typing import AsyncIterator, Literal

import httpx

from app.config import settings


class ProviderError(Exception):
    def __init__(
        self,
        code: str,
        usage: dict | None = None,
    ):
        super().__init__(code)
        self.code = code
        self.usage = usage


@dataclass(frozen=True)
class ProviderEvent:
    kind: Literal["delta", "finish"]
    text: str = ""
    usage: dict | None = None


async def stream_completion(
    messages: list[dict[str, str]],
) -> AsyncIterator[ProviderEvent]:
    api_key = settings.DEEPSEEK_API_KEY

    if not api_key:
        raise ProviderError("MODEL_UNAVAILABLE")

    payload = {
        "model": settings.DEEPSEEK_MODEL,
        "messages": messages,
        "stream": True,
        "stream_options": {
            "include_usage": True,
        },
        "thinking": {"type": "disabled"},
        "max_tokens": settings.AI_MAX_OUTPUT_TOKENS,
        "safety_check": {"level": "high"},
    }

    timeout = httpx.Timeout(
        connect=10.0,
        read=90.0,
        write=10.0,
        pool=10.0,
    )

    finish_reason: str | None = None
    usage: dict | None = None
    received_done = False

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
                        raise ProviderError(
                            "MODEL_RATE_LIMITED"
                        )

                    if response.status_code in (401, 403):
                        raise ProviderError(
                            "MODEL_AUTH_FAILED"
                        )

                    if response.status_code == 400:
                        raw = (
                            await response.aread()
                        )[:2048].decode(
                            "utf-8",
                            errors="ignore",
                        )
                        if "Content Exists Risk" in raw:
                            raise ProviderError("MODEL_BLOCKED")

                    raise ProviderError(
                        "MODEL_UPSTREAM_ERROR"
                    )

                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue

                    data = line[5:].strip()

                    if not data:
                        continue

                    if data == "[DONE]":
                        received_done = True
                        break

                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError as exc:
                        raise ProviderError(
                            "MODEL_INVALID_RESPONSE",
                            usage,
                        ) from exc

                    if not isinstance(chunk, dict):
                        raise ProviderError(
                            "MODEL_INVALID_RESPONSE",
                            usage,
                        )

                    chunk_usage = chunk.get("usage")
                    if isinstance(chunk_usage, dict):
                        usage = chunk_usage

                    # HTTP 200 之后仍可能收到上游错误
                    if isinstance(chunk.get("error"), dict):
                        raise ProviderError(
                            "MODEL_UPSTREAM_ERROR",
                            usage,
                        )

                    choices = chunk.get("choices")
                    if not isinstance(choices, list) or not choices:
                        raise ProviderError(
                            "MODEL_INVALID_RESPONSE",
                            usage,
                        )

                    choice = choices[0]
                    if not isinstance(choice, dict):
                        raise ProviderError(
                            "MODEL_INVALID_RESPONSE",
                            usage,
                        )

                    delta = choice.get("delta") or {}
                    if not isinstance(delta, dict):
                        raise ProviderError(
                            "MODEL_INVALID_RESPONSE",
                            usage,
                        )

                    content = delta.get("content")
                    if isinstance(content, str) and content:
                        yield ProviderEvent(
                            kind="delta",
                            text=content,
                        )

                    reason = choice.get("finish_reason")
                    if reason is not None:
                        finish_reason = reason

        if finish_reason == "content_filter":
            raise ProviderError("MODEL_BLOCKED", usage)

        if not received_done:
            raise ProviderError(
                "MODEL_STREAM_INTERRUPTED",
                usage,
            )

        if finish_reason != "stop":
            raise ProviderError(
                "MODEL_INCOMPLETE",
                usage,
            )

        yield ProviderEvent(
            kind="finish",
            usage=usage,
        )

    except ProviderError:
        raise

    except httpx.TimeoutException as exc:
        raise ProviderError(
            "MODEL_TIMEOUT",
            usage,
        ) from exc

    except httpx.HTTPError as exc:
        raise ProviderError(
            "MODEL_NETWORK_ERROR",
            usage,
        ) from exc
