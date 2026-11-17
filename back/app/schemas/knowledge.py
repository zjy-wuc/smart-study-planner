
from pydantic import BaseModel, Field, field_validator


def normalize_tags(value: list[str] | None):
    if value is None:
        return None

    result = []
    seen = set()

    for tag in value:
        tag = tag.strip()

        if not tag or len(tag) > 50:
            raise ValueError("标签长度必须为 1～50 个字符")

        key = tag.casefold()

        if key not in seen:
            seen.add(key)
            result.append(tag)

    return result


class NoteCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content_md: str = ""
    tags: list[str] = Field(default_factory=list, max_length=20)

    plan_id: int | None = Field(default=None, gt=0)
    step_id: int | None = Field(default=None, gt=0)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str):
        value = value.strip()

        if not value:
            raise ValueError("笔记标题不能为空")

        return value

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: list[str]):
        return normalize_tags(value)


class NoteUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    content_md: str | None = None
    tags: list[str] | None = Field(default=None, max_length=20)

    plan_id: int | None = Field(default=None, gt=0)
    step_id: int | None = Field(default=None, gt=0)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None):
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError("笔记标题不能为空")

        return value

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: list[str] | None):
        return normalize_tags(value)
