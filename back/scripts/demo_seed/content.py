"""100 篇学习笔记内容库与练习题目生成。

笔记均为可独立阅读的 Markdown 文章，包含概念、原理、案例/代码、
知识总结与复习问题。练习题目由笔记的 key_points / quizzes 派生，
保证历史 AI 练习与对应笔记内容一致。
"""

from .content_py_db_1 import NOTES as NOTES_A1
from .content_py_db_2 import NOTES as NOTES_A2
from .content_cs_1 import NOTES as NOTES_B1
from .content_cs_2 import NOTES as NOTES_B2
from .content_front_1 import NOTES as NOTES_C1
from .content_front_2 import NOTES as NOTES_C2
from .content_project_1 import NOTES as NOTES_D1
from .content_project_2 import NOTES as NOTES_D2

ALL_NOTES = (
    NOTES_A1
    + NOTES_A2
    + NOTES_B1
    + NOTES_B2
    + NOTES_C1
    + NOTES_C2
    + NOTES_D1
    + NOTES_D2
)

NOTES_BY_KEY = {item["key"]: item for item in ALL_NOTES}

if len(NOTES_BY_KEY) != len(ALL_NOTES):
    raise RuntimeError("笔记 key 存在重复，请检查内容库")

if len(ALL_NOTES) != 100:
    raise RuntimeError(f"笔记数量应为 100，实际为 {len(ALL_NOTES)}")


def render_note(item: dict) -> str:
    """把结构化笔记渲染为 Markdown 正文。"""

    lines = [
        f"# {item['title']}",
        "",
        f"> 领域：{item['domain']}｜标签：{'、'.join(item['tags'])}",
        "",
        "## 一、核心概念",
        "",
        item["concept"],
        "",
        "## 二、原理与要点",
        "",
    ]

    for index, point in enumerate(item["principles"], start=1):
        lines.append(f"{index}. {point}")

    if item.get("table"):
        lines += ["", "### 对比速查", "", item["table"]]

    lines += ["", "## 三、案例与实践", "", item["example"], ""]
    lines += ["## 四、知识总结", ""]
    lines += [f"- {point}" for point in item["summary"]]
    lines += ["", "## 五、复习问题", ""]
    lines += [
        f"{index}. {quiz['q']}"
        for index, quiz in enumerate(item["quizzes"], start=1)
    ]
    lines.append("")
    return "\n".join(lines)


def _short_question(
    index: int,
    stem: str,
    reference: str,
    grading_points: list[str],
    note_title: str,
) -> dict:
    return {
        "id": f"q{index}",
        "type": "SHORT_ANSWER",
        "stem": stem,
        "reference_answer": reference,
        "grading_points": grading_points,
        "explanation": f"对应笔记《{note_title}》中的知识点。",
    }


def build_practice_questions(item: dict, count: int = 5) -> list[dict]:
    """生成与笔记内容一致的简答题（默认 5 道）。"""

    questions: list[dict] = []
    for quiz in item["quizzes"][:2]:
        questions.append(
            _short_question(
                len(questions) + 1,
                quiz["q"],
                quiz["a"],
                [quiz["a"]],
                item["title"],
            )
        )

    key_points = item["key_points"]
    cursor = 0
    while len(questions) < count:
        point = key_points[cursor % len(key_points)]
        questions.append(
            _short_question(
                len(questions) + 1,
                f"结合笔记《{item['title']}》，说明“{point}”的含义与作用。",
                point,
                [point],
                item["title"],
            )
        )
        cursor += 1

    return questions[:count]


def build_practice_record(item: dict) -> tuple[float, list[dict]]:
    """构造一条已批改完成的练习记录（分数与题目一一对应）。"""

    questions = build_practice_questions(item)
    patterns = [
        (100, "CORRECT"),
        (80, "PARTIAL"),
        (100, "CORRECT"),
        (60, "PARTIAL"),
        (0, "INCORRECT"),
    ]

    total = 0.0
    materialized: list[dict] = []
    for question, (score_percent, status) in zip(questions, patterns):
        reference = question["reference_answer"]
        grading_points = question["grading_points"]

        if status == "CORRECT":
            submitted = reference
            feedback = None
        elif status == "PARTIAL":
            submitted = f"只答出了部分要点：{reference[: max(4, len(reference) // 2)]}"
            feedback = {
                "mastered_points": grading_points[:1],
                "missing_points": grading_points[1:],
                "suggestion": "补充完整定义、适用场景与关键限制。",
            }
        else:
            submitted = "凭印象作答，未覆盖笔记中的关键点。"
            feedback = {
                "mastered_points": [],
                "missing_points": grading_points,
                "suggestion": "回到笔记对应章节，先复述概念再做练习。",
            }

        earned = round(score_percent / len(questions), 2)
        total += earned
        materialized.append(
            {
                **question,
                "submitted_answer": submitted,
                "score_percent": score_percent,
                "earned_points": earned,
                "status": status,
                "feedback": feedback,
            }
        )

    return round(total, 2), materialized