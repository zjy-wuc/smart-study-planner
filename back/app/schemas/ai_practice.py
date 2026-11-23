from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


class GeneratePracticeRequest(BaseModel):
    note_id: int = Field(gt=0)
    question_count: Literal[5, 10, 15] = 5


class SingleChoiceQuestion(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    type: Literal["SINGLE_CHOICE"]
    stem: str = Field(min_length=5, max_length=500)
    options: dict[str, str]
    correct_answer: Literal["A", "B", "C", "D"]
    explanation: str = Field(min_length=2, max_length=1000)

    @field_validator("options")
    @classmethod
    def validate_options(cls, value: dict[str, str]):
        if set(value) != {"A", "B", "C", "D"}:
            raise ValueError("单选题必须有 A、B、C、D 四个选项")

        if any(
            not isinstance(text, str)
            or not text.strip()
            or len(text) > 200
            for text in value.values()
        ):
            raise ValueError("选项内容无效")

        if len({text.strip() for text in value.values()}) != 4:
            raise ValueError("四个选项不能重复")

        return {key: text.strip() for key, text in value.items()}


class ShortAnswerQuestion(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    type: Literal["SHORT_ANSWER"]
    stem: str = Field(min_length=5, max_length=500)
    reference_answer: str = Field(
        min_length=4,
        max_length=1500,
    )
    grading_points: list[str] = Field(
        min_length=1,
        max_length=6,
    )
    explanation: str = Field(min_length=2, max_length=1000)

    @field_validator("grading_points")
    @classmethod
    def validate_grading_points(cls, value: list[str]):
        if any(
            not point.strip() or len(point) > 200
            for point in value
        ):
            raise ValueError("简答题评分要点无效")

        return [point.strip() for point in value]


Question = Annotated[
    SingleChoiceQuestion | ShortAnswerQuestion,
    Field(discriminator="type"),
]


class GeneratedPractice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questions: list[Question] = Field(
        min_length=5,
        max_length=15,
    )