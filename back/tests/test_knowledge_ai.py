
import asyncio
import json

import httpx
import pytest
from fastapi import HTTPException

from app.config import settings
from app.schemas.knowledge_ai import NoteSnapshot
from app.services.knowledge import (
    ai_note_service,
    ai_provider,
    ai_service,
)
from app.services.knowledge.ai_provider import (
    ProviderError,
    ProviderEvent,
)


SUMMARY = (
    "## 核心概述\n"
    "这篇笔记主要介绍 JWT 认证。\n\n"
    "## 关键知识点\n"
    "- Access Token 用于访问授权资源。\n"
    "- Refresh Token 用于更新访问凭证。\n\n"
    "## 知识提纲\n"
    "1. Token 的作用\n"
    "2. Token 的刷新"
)


def make_snapshot():
    return NoteSnapshot(
        note_id=1,
        title="JWT 认证",
        content_md="Access Token 与 Refresh Token",
        version="test-version",
    )


def collect_stream(snapshot):
    async def collect():
        return [
            event
            async for event in ai_note_service.stream_summary_note(
                snapshot,
                user_id=7,
            )
        ]

    return asyncio.run(collect())


def test_summary_structure():
    result = ai_note_service.parse_summary(SUMMARY)

    assert "JWT" in result.overview
    assert "Access Token" in result.key_points
    assert "Token 的作用" in result.outline


def test_summary_invalid_structure():
    with pytest.raises(ValueError):
        ai_note_service.parse_summary(
            "这是一段不符合结构的普通文本"
        )


def test_prepare_summary_uses_saved_note(monkeypatch):
    def fake_require_note(**kwargs):
        assert kwargs["note_id"] == 1
        assert kwargs["user_id"] == 7

        return {
            "title": "JWT 认证",
            "content_md": "已保存的 JWT 内容",
        }

    monkeypatch.setattr(
        ai_note_service,
        "_require_note",
        fake_require_note,
    )

    snapshot = ai_note_service.prepare_note_snapshot(
        db=None,
        note_id=1,
        user_id=7,
    )

    assert snapshot.content_md == "已保存的 JWT 内容"
    assert len(snapshot.version) == 64


def test_prepare_summary_rejects_missing_note(monkeypatch):
    def fake_require_note(**kwargs):
        raise HTTPException(
            status_code=404,
            detail="知识笔记不存在",
        )

    monkeypatch.setattr(
        ai_note_service,
        "_require_note",
        fake_require_note,
    )

    with pytest.raises(HTTPException) as exc:
        ai_note_service.prepare_note_snapshot(
            db=None,
            note_id=999,
            user_id=7,
        )

    assert exc.value.status_code == 404


def test_prepare_summary_rejects_credentials(monkeypatch):
    monkeypatch.setattr(
        ai_note_service,
        "_require_note",
        lambda **kwargs: {
            "title": "测试笔记",
            "content_md": "sk-" + "a" * 30,
        },
    )

    with pytest.raises(HTTPException) as exc:
        ai_note_service.prepare_note_snapshot(
            db=None,
            note_id=1,
            user_id=7,
        )

    assert exc.value.status_code == 422


def test_summary_stream_success(monkeypatch):
    def fake_note_version_is_current(snapshot, user_id):
        assert snapshot.note_id == 1
        assert snapshot.version == "test-version"
        assert user_id == 7
        return True

    async def fake_provider(messages):
        yield ProviderEvent(
            kind="delta",
            text=SUMMARY[:40],
        )
        yield ProviderEvent(
            kind="delta",
            text=SUMMARY[40:],
        )
        yield ProviderEvent(
            kind="finish",
            usage={
                "prompt_tokens": 20,
                "completion_tokens": 30,
            },
        )

    monkeypatch.setattr(
        ai_service,
        "stream_completion",
        fake_provider,
    )
    monkeypatch.setattr(
        settings,
        "AI_STREAM_CHUNK_CHARS",
        16,
    )
    monkeypatch.setattr(
        ai_note_service,
        "note_version_is_current",
        fake_note_version_is_current,
    )

    events = collect_stream(make_snapshot())

    assert any("event: start" in e for e in events)
    assert sum("event: delta" in e for e in events) > 1
    assert any("event: reviewing" in e for e in events)
    assert any("event: done" in e for e in events)
    assert not any("event: error" in e for e in events)


def test_summary_stream_invalid_output(monkeypatch):
    async def fake_provider(messages):
        yield ProviderEvent(
            kind="delta",
            text="不合法的总结格式",
        )
        yield ProviderEvent(kind="finish")

    monkeypatch.setattr(
        ai_service,
        "stream_completion",
        fake_provider,
    )

    events = collect_stream(make_snapshot())

    assert any(
        '"code": "INVALID_SUMMARY"' in e
        for e in events
    )
    assert not any("event: done" in e for e in events)


def test_summary_stream_blocked(monkeypatch):
    async def fake_provider(messages):
        yield ProviderEvent(
            kind="delta",
            text=SUMMARY,
        )
        raise ProviderError("MODEL_BLOCKED")

    monkeypatch.setattr(
        ai_service,
        "stream_completion",
        fake_provider,
    )

    events = collect_stream(make_snapshot())

    assert any("event: blocked" in e for e in events)
    assert not any("event: done" in e for e in events)


def test_provider_parses_deepseek_stream(monkeypatch):
    """
    模拟 DeepSeek 原始 SSE。
    不进行真实网络请求。
    """
    chunks = [
        {
            "choices": [{
                "delta": {"content": "你好"},
                "finish_reason": None,
            }],
            "usage": None,
        },
        {
            "choices": [{
                "delta": {},
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens": 5,
                "completion_tokens": 2,
            },
        },
    ]

    raw = "".join(
        "data: " + json.dumps(item) + "\n\n"
        for item in chunks
    ) + "data: [DONE]\n\n"

    def handler(request):
        assert request.url.path == "/chat/completions"
        return httpx.Response(200, text=raw)

    original_client = httpx.AsyncClient

    def fake_client(**kwargs):
        return original_client(
            transport=httpx.MockTransport(handler),
            **kwargs,
        )

    monkeypatch.setattr(
        ai_provider.httpx,
        "AsyncClient",
        fake_client,
    )
    monkeypatch.setattr(
        settings,
        "DEEPSEEK_API_KEY",
        "test-only-key",
    )

    async def collect():
        return [
            item
            async for item in ai_provider.stream_completion(
                [{"role": "user", "content": "你好"}]
            )
        ]

    events = asyncio.run(collect())

    assert events[0].text == "你好"
    assert events[-1].kind == "finish"
    assert events[-1].usage["prompt_tokens"] == 5


def test_provider_detects_content_filter(monkeypatch):
    raw = (
        'data: {"choices":[{"delta":{},'
        '"finish_reason":"content_filter"}]}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(request):
        return httpx.Response(200, text=raw)

    original_client = httpx.AsyncClient

    monkeypatch.setattr(
        ai_provider.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(
            transport=httpx.MockTransport(handler),
            **kwargs,
        ),
    )
    monkeypatch.setattr(
        settings,
        "DEEPSEEK_API_KEY",
        "test-only-key",
    )

    async def collect():
        return [
            item
            async for item in ai_provider.stream_completion(
                [{"role": "user", "content": "测试"}]
            )
        ]

    with pytest.raises(ProviderError) as exc:
        asyncio.run(collect())

    assert exc.value.code == "MODEL_BLOCKED"
