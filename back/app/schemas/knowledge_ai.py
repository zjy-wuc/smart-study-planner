
from dataclasses import dataclass

from pydantic import field_validator


from app.config import settings

from pydantic import BaseModel, Field

#表示这个对象在创建后，不能通过普通属性赋值修改字段
@dataclass(frozen=True)#是 Python 标准库提供的装饰器，可以自动为类生成初始化方法等常用方法。
class NoteSnapshot:#快照
    note_id: int
    title: str
    content_md: str
    version: str


class SummaryOutput(BaseModel):
    overview: str = Field(min_length=1)
    key_points: str = Field(min_length=1)
    outline: str = Field(min_length=1)



#主题生成
class GenerateNoteRequest(BaseModel):
    topic: str = Field(
        min_length=2,
        max_length=100,
        description="需要生成笔记的主题",
    )

    instructions: str | None = Field(
        default=None,
        max_length=500,
        description="用户对生成内容的补充要求",
    )

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, value: str) -> str:
        value = value.strip()

        if len(value) < 2:
            raise ValueError("主题至少需要两个字符")

        return value

    @field_validator("instructions")
    @classmethod
    def normalize_instructions(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()
        return value or None





class QAHistoryTurn(BaseModel):
    """一轮由用户问题和成功完成的 AI 回答组成。"""

    question: str = Field(
        min_length=1,
        max_length=1000,
    )

    answer: str = Field(
        min_length=1,
        max_length=settings.AI_MAX_OUTPUT_CHARS,
    )

    @field_validator("question", "answer", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class AskNoteRequest(BaseModel):
    """A4 知识问答的请求参数。"""

    question: str = Field(
        min_length=1,
        max_length=1000,
        description="用户本次提出的学习问题",
    )

    # 前端正常只发送最近三轮。
    # 后端允许少量冗余历史，但最终只使用最近三轮。
    # 额外上限防止客户端发送无限长的历史数组。
    history: list[QAHistoryTurn] = Field(
        default_factory=list,
        max_length=20,
    )

    @field_validator("question", mode="before")
    @classmethod
    def normalize_question(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value
