
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


MAX_UINT64 = 2**64 - 1


class ActiveTaskUpdate(BaseModel):
    """修改 ACTIVE 计划中未来尚未开始的任务"""

    model_config = ConfigDict(extra="forbid")

    content: str | None = Field(
        default=None,
        max_length=255,
    )

    target_quantity: int | None = Field(
        default=None,
        ge=0,
        le=MAX_UINT64,
        strict=True,
    )

    @field_validator("content")
    @classmethod
    def validate_content(cls, value):
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError("任务内容不能为空")

        return value
