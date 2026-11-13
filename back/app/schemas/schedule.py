
from datetime import date

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


class ScheduleEntryInput(BaseModel):
    """某一天的一条草稿安排"""

    model_config = ConfigDict(extra="forbid")# 禁止额外字段输入

    task_date: date

    content: str | None = Field(
        default=None,
        max_length=255,
    )

    target_quantity: int | None = Field(
        default=None,
        ge=0,
        strict=True,#严格要求整数，不接受字符串自动转换成整数
    )

    @field_validator("content")
    @classmethod#使方法接收 cls（当前模型类）作为第一个参数，而不是实例对象 self。
    def clean_content(cls, value):
        if value is None:
            return None

        value = value.strip()
        return value or None


class ScheduleReplace(BaseModel):
    """一次保存某个叶子节点的所有草稿安排"""

    model_config = ConfigDict(extra="forbid")

    entries: list[ScheduleEntryInput] = Field(
        default_factory=list
    )
