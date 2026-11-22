
import asyncio
import json

import pytest
from fastapi import HTTPException

from app.config import settings
from app.schemas.knowledge_ai import NoteSnapshot
from app.services.knowledge import (
    ai_service,
    ai_guard_service,
    ai_note_service,
)
from app.services.knowledge.ai_provider import (
    ProviderEvent,
)


SUMMARY = (
    "## 核心概述\n概述\n"
    "## 关键知识点\n知识点\n"
    "## 知识提纲\n提纲"
)

MARKDOWN = "# JWT\n\n## 介绍\n基础知识"

SNAP = NoteSnapshot(
    42,
    "JWT",
    "JWT 原文",
    "v1",
)


def frames(generator):
    async def run():
        return [
            frame
            async for frame in generator
        ]

    return asyncio.run(run())


def events(frames_list):
    return [
        (
            frame.split("\n")[0][7:],
            json.loads(frame.split("\n")[1][6:]),
        )
        for frame in frames_list
    ]


def fake_provider(output, usage=None):
    async def provider(messages):
        for n in range(0, len(output), 4):
            yield ProviderEvent(
                "delta",
                output[n:n + 4],
            )
        yield ProviderEvent("finish", usage=usage)

    return provider


def test_generate(monkeypatch):
    monkeypatch.setattr(
        ai_service,
        "stream_completion",
        fake_provider(
            MARKDOWN,
            {
                "prompt_tokens": 3,
                "completion_tokens": 5,
            },
        ),
    )

    result = events(
        frames(
            ai_note_service.stream_generate_note("JWT")
        )
    )

    assert result[-1][0] == "done"
    assert result[-1][1]["markdown"] == MARKDOWN


def test_summary(monkeypatch):
    monkeypatch.setattr(
        ai_service,
        "stream_completion",
        fake_provider(SUMMARY),
    )
    monkeypatch.setattr(
        ai_note_service,
        "note_version_is_current",
        lambda *_: True,
    )

    result = events(
        frames(
            ai_note_service.stream_summary_note(
                SNAP,
                7,
            )
        )
    )

    assert result[-1][0] == "done"
    assert set(result[-1][1]["summary"]) == {
        "overview",
        "key_points",
        "outline",
    }


def test_stale_note(monkeypatch):
    monkeypatch.setattr(
        ai_service,
        "stream_completion",
        fake_provider(
            MARKDOWN,
            {"prompt_tokens": 3},
        ),
    )
    monkeypatch.setattr(
        ai_note_service,
        "note_version_is_current",
        lambda *_: False,
    )

    result = events(
        frames(
            ai_note_service.stream_organize_note(
                SNAP,
                7,
            )
        )
    )

    assert result[-1][0] == "error"
    assert result[-1][1]["status"] == "STALE"


def test_guard_stale(monkeypatch):
    calls = []

    monkeypatch.setattr(
        ai_service,
        "stream_completion",
        fake_provider(SUMMARY),
    )
    monkeypatch.setattr(
        ai_note_service,
        "note_version_is_current",
        lambda *_: False,
    )
    monkeypatch.setattr(
        ai_guard_service,
        "_finish_request_record",
        lambda *args: calls.append(args),
    )

    admission = ai_guard_service.Admission(
        "abc",
        7,
        42,
    )

    result = events(
        frames(
            ai_guard_service.metered_ai_stream(
                admission,
                ai_note_service.stream_summary_note(
                    SNAP,
                    7,
                ),
            )
        )
    )

    assert result[-1][0] == "error"
    assert calls[0][1] == "STALE"
    assert "done" not in [
        event[0]
        for event in result
    ]


def test_guard_success_prior_done(monkeypatch):
    calls = []

    monkeypatch.setattr(
        ai_service,
        "stream_completion",
        fake_provider(MARKDOWN),
    )
    monkeypatch.setattr(
        ai_guard_service,
        "_finish_request_record",
        lambda *args: calls.append(
            "DB:" + args[1]
        ),
    )

    admission = ai_guard_service.Admission(
        "abc",
        7,
        None,
    )

    async def collect():
        async for frame in ai_guard_service.metered_ai_stream(
            admission,
            ai_note_service.stream_generate_note("JWT"),
        ):
            if frame.startswith("event: done"):
                calls.append("DONE")

    asyncio.run(collect())

    assert calls == [
        "DB:SUCCESS",
        "DONE",
    ]


def test_guard_timeout(monkeypatch):
    calls = []

    monkeypatch.setattr(
        settings,
        "AI_MAX_STREAM_SECONDS",
        0.01,
    )
    monkeypatch.setattr(
        ai_guard_service,
        "_finish_request_record",
        lambda *args: calls.append(args[1]),
    )

    async def sleepy():
        yield "event: start\ndata: {}\n\n"
        await asyncio.sleep(0.1)

    result = events(
        frames(
            ai_guard_service.metered_ai_stream(
                ai_guard_service.Admission(
                    "abc",
                    7,
                    None,
                ),
                sleepy(),
            )
        )
    )

    assert result[-1][1]["code"] == "AI_TOTAL_TIMEOUT"
    assert calls == ["TIMEOUT"]


def test_sensitive_input():
    with pytest.raises(HTTPException):
        ai_note_service.validate_generate_input(
            "sk-" + "a" * 50,
            None,
        )


def test_cleanup_chain(monkeypatch):
    closed = []

    async def provider(messages):
        try:
            yield ProviderEvent(
                "delta",
                "Hello! " * 40,
            )
            yield ProviderEvent(
                "delta",
                "world",
            )
            yield ProviderEvent("finish")
        finally:
            closed.append(True)

    monkeypatch.setattr(
        ai_service,
        "stream_completion",
        provider,
    )

    async def take_one():
        generator = ai_note_service.stream_generate_note(
            "JWT"
        )

        result = await anext(generator)
        assert "start" in result

        result = await anext(generator)
        assert "delta" in result

        await generator.aclose()

    asyncio.run(take_one())
    assert closed


def test_organize_success(monkeypatch):
    monkeypatch.setattr(
        ai_service,
        "stream_completion",
        fake_provider(MARKDOWN),
    )
    monkeypatch.setattr(
        ai_note_service,
        "note_version_is_current",
        lambda *_: True,
    )

    result = events(
        frames(
            ai_note_service.stream_organize_note(
                SNAP,
                7,
            )
        )
    )

    assert result[-1][0] == "done"
    assert result[-1][1]["source_note_id"] == 42
    assert result[-1][1]["mode"] == "organize"


def test_summary_extra_heading_rejected():
    with pytest.raises(ValueError):
        ai_note_service.parse_summary(
            SUMMARY + "\n## 第四部分\n无"
        )


def test_provider_blocks_credential(monkeypatch):
    bad = (
        "正常内容 "
        + "sk-"
        + "x" * 35
        + "\n## 附录"
    )

    monkeypatch.setattr(
        ai_service,
        "stream_completion",
        fake_provider(bad),
    )

    result = events(
        frames(
            ai_note_service.stream_generate_note(
                "JWT"
            )
        )
    )

    assert result[-1][0] == "blocked"
    assert "done" not in [
        event[0]
        for event in result
    ]
