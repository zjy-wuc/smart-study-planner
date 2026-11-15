
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.schemas.step import StepRule
from app.schemas.schedule import ScheduleEntryInput


class ActiveStepNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(
        default=None,
        max_length=255,
    )

    node_type: Literal["GROUP", "LEAF"]
    rule: StepRule | None = None

    # 只用于需要逐日自定义的叶子节点
    entries: list[ScheduleEntryInput] = Field(
        default_factory=list,
    )

    children: list["ActiveStepNode"] = Field(
        default_factory=list,
    )

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str):
        value = value.strip()

        if not value:
            raise ValueError("节点名称不能为空")

        return value

    @model_validator(mode="after")
    def validate_structure(self):
        if self.node_type == "GROUP":
            if not self.children:
                raise ValueError(
                    "GROUP 必须同时包含至少一个子节点"
                )

            if self.rule is not None or self.entries:
                raise ValueError(
                    "GROUP 不能配置执行规则或每日安排"
                )

        else:
            if self.children:
                raise ValueError(
                    "LEAF 不能包含子节点"
                )

            if self.rule is None:
                raise ValueError(
                    "LEAF 必须配置执行规则"
                )

        return self


class ActiveStepTreeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # None 表示新增为根节点
    parent_id: int | None = Field(default=None, gt=0)

    node: ActiveStepNode


ActiveStepNode.model_rebuild()
