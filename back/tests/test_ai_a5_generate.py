import asyncio
import json
import time

import pytest

from fastapi import HTTPException

from app.core import practice_ticket
from app.schemas.knowledge_ai import NoteSnapshot
from app.services.knowledge.ai_provider import ProviderError
from app.services.knowledge.ai_service import CheckedCompletionEvent
from app.services.knowledge import ai_practice_service as practice


TOPICS = [
    "JWT Access Token 的过期校验",
    "Refresh Token 轮换与重放检测",
    "登录会话的即时撤销",
    "邮箱验证码的有效期管理",
    "密码重置后旧会话失效",
    "多设备登录的会话隔离",
    "认证 POST 请求的 CSRF 来源校验",
    "验证码尝试次数的上限控制",
    "连续登录失败后的锁定策略",
    "头像上传的文件类型校验",
    "学习计划到期后的历史数据保留",
    "每日任务顺延链的依赖顺序",
    "知识复习记录的间隔调度",
    "专注会话的暂停与恢复",
    "笔记快照版本的一致性",
]

STEM_TEMPLATES = [
    "{topic}：下列哪项做法是正确的？",
    "关于{topic}，哪一项描述符合实现要求？",
    "在{topic}场景下，应当如何处理？",
    "{topic}的正确实现方式是？",
    "下列对{topic}的理解中，正确的是？",
]


def make_paper(count=5):
    choice_count = count * 3 // 5
    questions = []

    for i in range(choice_count):
        topic = TOPICS[i]
        stem = STEM_TEMPLATES[i % len(STEM_TEMPLATES)].format(
            topic=topic,
        )
        questions.append({
            "type": "SINGLE_CHOICE",
            "stem": stem,
            "options": {
                "A": f"由服务端强制校验{topic}",
                "B": f"只在前端提示{topic}",
                "C": f"无需持久化{topic}",
                "D": f"跳过{topic}的权限判断",
            },
            "correct_answer": "A",
            "explanation": f"服务端必须对“{topic}”做强制校验。",
        })

    for i in range(count - choice_count):
        index = choice_count + i
        topic = TOPICS[index]
        stem = STEM_TEMPLATES[index % len(STEM_TEMPLATES)].format(
            topic=topic,
        )
        questions.append({
            "type": "SHORT_ANSWER",
            "stem": stem,
            "reference_answer": f"{topic}的完整处理流程说明。",
            "grading_points": [
                f"说明{topic}的关键步骤",
            ],
            "explanation": f"结合笔记理解{topic}。",
        })

    return {"questions": questions}


def make_snapshot():
    return NoteSnapshot(
        note_id=12,
        title="JWT 认证",
        content_md="JWT Access Token 与 Refresh Token "
                   "分别承担访问鉴权和会话续期职责。",
        version="snapshot-v1",
    )


def test_parse_five_questions():
    questions = practice.parse_practice_questions(
        json.dumps(make_paper(), ensure_ascii=False),
        5,
    )

    assert len(questions) == 5
    assert [q["id"] for q in questions] == [
        "q1", "q2", "q3", "q4", "q5",
    ]
    assert [q["type"] for q in questions] == (
        ["SINGLE_CHOICE"] * 3
        + ["SHORT_ANSWER"] * 2
    )


@pytest.mark.parametrize("count", [5, 10, 15])
def test_supported_question_counts(count):
    questions = practice.parse_practice_questions(
        json.dumps(make_paper(count), ensure_ascii=False),
        count,
    )

    assert len(questions) == count


def test_reject_wrong_question_count():
    with pytest.raises(ProviderError):
        practice.parse_practice_questions(
            json.dumps(make_paper(5)),
            10,
        )


def test_reject_invalid_options():
    paper = make_paper()
    paper["questions"][0]["options"] = {"A": "只有一个选项"}

    with pytest.raises(ProviderError):
        practice.parse_practice_questions(
            json.dumps(paper, ensure_ascii=False),
            5,
        )


def test_reject_duplicate_questions():
    paper = make_paper()

    paper["questions"][1]["stem"] = (
        paper["questions"][0]["stem"]
    )

    with pytest.raises(ProviderError) as exc:
        practice.parse_practice_questions(
            json.dumps(paper, ensure_ascii=False),
            5,
        )

    assert exc.value.code == "DUPLICATE_PRACTICE_QUESTIONS"


def test_reject_short_note():
    snapshot = NoteSnapshot(
        note_id=12,
        title="空笔记",
        content_md="只有一点内容",
        version="v1",
    )

    with pytest.raises(HTTPException) as exc:
        practice.validate_practice_source(snapshot)

    assert exc.value.status_code == 422


def test_public_questions_hide_answers():
    private_questions = practice.parse_practice_questions(
        json.dumps(make_paper(), ensure_ascii=False),
        5,
    )

    public_questions = practice.build_public_questions(
        private_questions
    )

    assert len(public_questions) == 5

    for question in public_questions:
        assert "correct_answer" not in question
        assert "reference_answer" not in question
        assert "grading_points" not in question
        assert "explanation" not in question


def test_stream_does_not_expose_model_delta(monkeypatch):
    raw = json.dumps(make_paper(), ensure_ascii=False)

    async def fake_completion(messages):
        yield CheckedCompletionEvent(
            kind="delta",
            text=raw,
        )
        yield CheckedCompletionEvent(
            kind="finish",
            text=raw,
            usage={
                "prompt_tokens": 10,
                "completion_tokens": 20,
            },
        )

    monkeypatch.setattr(
        practice,
        "stream_checked_completion",
        fake_completion,
    )

    async def collect():
        return [
            frame
            async for frame in practice.stream_generate_practice(
                snapshot=make_snapshot(),
                user_id=7,
                question_count=5,
            )
        ]

    frames = asyncio.run(collect())

    assert not any(
        frame.startswith("event: delta")
        for frame in frames
    )

    done = next(
        frame for frame in frames
        if frame.startswith("event: done")
    )

    result = json.loads(done.split("data: ", 1)[1])

    assert result["question_count"] == 5
    assert len(result["questions"]) == 5

    # 前端只能收到公开题目和不可读的加密凭证。
    assert "correct_answer" not in result["questions"][0]

    private_data = practice_ticket.read_practice_ticket(
        result["practice_ticket"]
    )

    assert private_data["user_id"] == 7
    assert private_data["note_id"] == 12
    assert private_data["questions"][0]["correct_answer"] == "A"


def test_practice_ticket_expires_after_24_hours():
    payload = {
        "purpose": "A5_GENERATION",
        "version": 1,
        "user_id": 7,
    }

    raw = json.dumps(payload).encode("utf-8")

    old_ticket = practice_ticket._cipher().encrypt_at_time(
        raw,
        current_time=int(time.time()) - 86500,
    ).decode("ascii")

    with pytest.raises(ValueError):
        practice_ticket.read_practice_ticket(old_ticket)


def test_tampered_ticket_is_rejected():
    ticket = practice_ticket.create_practice_ticket({
        "purpose": "A5_GENERATION",
        "version": 1,
        "user_id": 7,
    })

    tampered = (
        ticket[:30]
        + ("A" if ticket[30] != "A" else "B")
        + ticket[31:]
    )

    with pytest.raises(ValueError):
        practice_ticket.read_practice_ticket(tampered)
