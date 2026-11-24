import asyncio
import json

import pytest

from fastapi import HTTPException
from pydantic import ValidationError

from app.core.practice_ticket import (
    create_practice_ticket,
)
from app.schemas.ai_practice_submit import (
    PracticeAnswer,
    SubmitPracticeRequest,
)
from app.services.knowledge.ai_provider import ProviderError
from app.services.knowledge.ai_service import CheckedCompletionEvent
from app.services.knowledge import (
    ai_practice_grading_service as grading,
)


def make_paper():
    questions = [
        {
            "id": "q1",
            "type": "SINGLE_CHOICE",
            "stem": "Access Token 的作用是什么？",
            "options": {
                "A": "访问 API",
                "B": "创建数据库",
                "C": "保存密码",
                "D": "执行 SQL",
            },
            "correct_answer": "A",
            "explanation": "用于访问受保护的 API。",
        },
        {
            "id": "q2",
            "type": "SINGLE_CHOICE",
            "stem": "Refresh Token 用于什么？",
            "options": {
                "A": "删除数据",
                "B": "保存密码",
                "C": "获取新的 Access Token",
                "D": "创建用户表",
            },
            "correct_answer": "C",
            "explanation": "用于获取新的访问令牌。",
        },
        {
            "id": "q3",
            "type": "SINGLE_CHOICE",
            "stem": "旧 Refresh Token 轮换后怎样？",
            "options": {
                "A": "永久有效",
                "B": "延长有效期",
                "C": "变成密码",
                "D": "失效",
            },
            "correct_answer": "D",
            "explanation": "轮换后旧令牌失效。",
        },
        {
            "id": "q4",
            "type": "SHORT_ANSWER",
            "stem": "解释 Refresh Token 轮换的作用。",
            "reference_answer": "生成新令牌，旧令牌失效，并检测重放。",
            "grading_points": [
                "生成新令牌",
                "旧令牌失效",
                "识别重放",
            ],
            "explanation": "轮换有助于识别旧令牌的异常使用。",
        },
        {
            "id": "q5",
            "type": "SHORT_ANSWER",
            "stem": "解释两类 Token 的职责区别。",
            "reference_answer": "Access 用于鉴权，Refresh 用于续期。",
            "grading_points": [
                "Access 用于鉴权",
                "Refresh 用于续期",
            ],
            "explanation": "两个 Token 有不同职责。",
        },
    ]

    return {
        "purpose": "A5_GENERATION",
        "version": 1,
        "generation_id": "11111111-1111-4111-8111-111111111111",
        "user_id": 7,
        "note_id": 12,
        "note_title_snapshot": "JWT 双 Token 认证",
        "note_version": "v1",
        "note_content": (
            "Access Token 用于鉴权。"
            "Refresh Token 用于续期。"
            "轮换后旧令牌失效，可以检测重放。"
        ),
        "question_count": 5,
        "questions": questions,
    }


def make_context():
    ticket = create_practice_ticket(make_paper())

    request = SubmitPracticeRequest(
        practice_ticket=ticket,
        answers=[
            PracticeAnswer(id="q1", answer="A"),
            PracticeAnswer(id="q2", answer="B"),
            PracticeAnswer(id="q3", answer="D"),
            PracticeAnswer(
                id="q4",
                answer="生成新令牌，旧令牌失效。",
            ),
        ],
    )

    return grading.prepare_submission(
        request,
        user_id=7,
    )


def test_normalize_skipped_answers():
    context = make_context()

    assert context.answers["q1"] == "A"
    assert context.answers["q5"] is None


def test_reject_unknown_question():
    with pytest.raises(HTTPException) as exc:
        grading.normalize_answers(
            make_paper()["questions"],
            [PracticeAnswer(id="q99", answer="A")],
        )

    assert exc.value.status_code == 422


def test_reject_duplicate_answer():
    with pytest.raises(HTTPException) as exc:
        grading.normalize_answers(
            make_paper()["questions"],
            [
                PracticeAnswer(id="q1", answer="A"),
                PracticeAnswer(id="q1", answer="B"),
            ],
        )

    assert exc.value.status_code == 422


def test_locked_submission_preserves_answers():
    original = make_context()

    retry = grading.prepare_submission(
        SubmitPracticeRequest(
            submission_ticket=original.submission_ticket,
        ),
        user_id=7,
    )

    assert retry.answers == original.answers
    assert retry.paper == original.paper
    assert retry.submission_ticket == original.submission_ticket


def test_retry_cannot_supply_new_answers():
    context = make_context()

    with pytest.raises(ValidationError):
        SubmitPracticeRequest(
            submission_ticket=context.submission_ticket,
            answers=[
                PracticeAnswer(id="q1", answer="B")
            ],
        )


def test_reject_other_user():
    context = make_context()

    with pytest.raises(HTTPException) as exc:
        grading.prepare_submission(
            SubmitPracticeRequest(
                submission_ticket=context.submission_ticket,
            ),
            user_id=8,
        )

    assert exc.value.status_code == 403


def test_calculate_partial_score():
    context = make_context()

    grades = {
        "q4": {
            "id": "q4",
            "score": 80,
            "mastered_points": [
                "新令牌生成",
                "旧令牌失效",
            ],
            "missing_points": ["重放检测"],
            "suggestion": "补充重放检测的作用。",
        }
    }

    score, questions = grading.calculate_result(
        context,
        grades,
    )

    assert score == 56.0
    assert [q["status"] for q in questions] == [
        "CORRECT",
        "INCORRECT",
        "CORRECT",
        "PARTIAL",
        "SKIPPED",
    ]

    assert questions[3]["earned_points"] == 16.0
    assert questions[4]["earned_points"] == 0.0


def test_reject_missing_ai_grade():
    raw = json.dumps({
        "grades": [
            {
                "id": "q4",
                "score": 80,
                "mastered_points": [],
                "missing_points": [],
                "suggestion": "继续学习。",
            },
        ]
    })

    with pytest.raises(ProviderError) as exc:
        grading.parse_grading_result(
            raw,
            expected_ids=["q4", "q5"],
        )

    assert exc.value.code == "INVALID_PRACTICE_GRADE"


def test_stream_grading_success(monkeypatch):
    context = make_context()

    async def fake_completion(messages):
        yield CheckedCompletionEvent(
            kind="finish",
            text=json.dumps({
                "grades": [
                    {
                        "id": "q4",
                        "score": 80,
                        "mastered_points": ["理解轮换"],
                        "missing_points": ["重放检测"],
                        "suggestion": "补充重放检测。",
                    }
                ]
            }),
            usage={
                "prompt_tokens": 30,
                "completion_tokens": 50,
            },
        )

    saved_scores = []

    def fake_save(paper, score, questions):
        saved_scores.append(score)
        return {
            "id": 1,
            "generation_id": paper["generation_id"],
            "score": score,
            "questions": questions,
        }

    monkeypatch.setattr(
        grading,
        "stream_checked_completion",
        fake_completion,
    )
    monkeypatch.setattr(
        grading,
        "save_success_result",
        fake_save,
    )

    async def collect():
        return [
            frame
            async for frame in grading.stream_grade_practice(
                context
            )
        ]

    frames = asyncio.run(collect())

    assert [frame.split("\n", 1)[0] for frame in frames] == [
        "event: start",
        "event: reviewing",
        "event: done",
    ]

    done = json.loads(frames[-1].split("data: ", 1)[1])

    assert done["record"]["score"] == 56.0
    assert saved_scores == [56.0]

    start = json.loads(frames[0].split("data: ", 1)[1])
    assert start["submission_ticket"]


def test_ai_failure_does_not_save(monkeypatch):
    context = make_context()
    saved = []

    async def fake_completion(messages):
        raise ProviderError("MODEL_TIMEOUT")
        yield  # 保持为异步生成器

    monkeypatch.setattr(
        grading,
        "stream_checked_completion",
        fake_completion,
    )
    monkeypatch.setattr(
        grading,
        "save_success_result",
        lambda *args: saved.append(True),
    )

    async def collect():
        return [
            frame
            async for frame in grading.stream_grade_practice(
                context
            )
        ]

    frames = asyncio.run(collect())

    assert frames[0].startswith("event: start")
    assert frames[-1].startswith("event: error")
    assert saved == []


def test_all_short_answers_skipped_no_ai(monkeypatch):
    paper = make_paper()
    ticket = create_practice_ticket(paper)

    context = grading.prepare_submission(
        SubmitPracticeRequest(
            practice_ticket=ticket,
            answers=[
                PracticeAnswer(id="q1", answer="A"),
            ],
        ),
        user_id=7,
    )

    assert grading.needs_ai_grading(context) is False

    def forbidden_ai(messages):
        raise AssertionError("不应该调用 AI")

    monkeypatch.setattr(
        grading,
        "stream_checked_completion",
        forbidden_ai,
    )

    def fake_save(paper, score, questions):
        return {
            "id": 1,
            "score": score,
            "questions": questions,
        }

    monkeypatch.setattr(
        grading,
        "save_success_result",
        fake_save,
    )

    async def collect():
        return [
            frame
            async for frame in grading.stream_grade_practice(
                context
            )
        ]

    frames = asyncio.run(collect())
    done = json.loads(frames[-1].split("data: ", 1)[1])

    assert done["record"]["score"] == 20.0
    assert frames[-1].startswith("event: done")
