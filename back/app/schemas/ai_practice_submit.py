from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

#验证用户提交的单题答案
class PracticeAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=20)
    answer: str | None = Field(
        default=None,
        max_length=2000,
    )

    @field_validator("answer")
    @classmethod
    def normalize_answer(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class SubmitPracticeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    practice_ticket: str | None = Field(
        default=None,
        min_length=20,
        max_length=500000,
    )
#锁定提交后重新批改的凭证
    submission_ticket: str | None = Field(
        default=None,
        min_length=20,
        max_length=500000,
    )

    answers: list[PracticeAnswer] | None = Field(
        default=None,
        max_length=15,
    )

    @model_validator(mode="after")#基础字段校验完成后执行
    def validate_mode(self):
        first_submit = (
            self.practice_ticket is not None
            and self.answers is not None
            and self.submission_ticket is None
        )

        retry_submit = (
            self.submission_ticket is not None
            and self.practice_ticket is None
            and self.answers is None
        )

        if not (first_submit or retry_submit):
            raise ValueError(
                "首次提交需要练习凭证和答案；"
                "重新批改只能提供锁定提交凭证"
            )

        return self


class ShortAnswerGrade(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,#自动清除模型中受该配置约束的字符串首尾空白。
    )

    id: str = Field(min_length=1, max_length=20)

    score: int = Field(ge=0, le=100)
#表示用户已经掌握的知识点
    mastered_points: list[str] = Field(
        default_factory=list,
        max_length=6,
    )

    missing_points: list[str] = Field(
        default_factory=list,
        max_length=6,
    )

    suggestion: str = Field(
        min_length=1,
        max_length=500,
    )

    @field_validator(
        "mastered_points",
        "missing_points",
    )
    @classmethod
    def validate_points(
        cls,
        value: list[str],
    ) -> list[str]:
        if any(
            not point.strip() or len(point) > 200
            for point in value
        ):
            raise ValueError("评分知识点无效")

        return [point.strip() for point in value]

#表示用户对简答题的评分
class GradeBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grades: list[ShortAnswerGrade] = Field(
        min_length=1,
        max_length=6,
    )