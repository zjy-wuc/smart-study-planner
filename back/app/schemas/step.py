
from __future__ import annotations

from typing import Literal

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
)


class StepRule(BaseModel):
    """叶子节点的执行规则"""

    task_type: Literal["BOOLEAN", "NUMERIC"]

    schedule_mode: Literal[
        "REPEAT",
        "DAILY_CUSTOM",
        "AUTO_DISTRIBUTE",
        "DAILY_MANUAL",
    ]

    repeat_content: str | None = Field(
        default=None,
        max_length=255,
    )

    total_target: int | None = Field(
        default=None,
        ge=0,
        strict=True,
    )

    @model_validator(mode="after")
    def validate_rule(self):
        if self.task_type == "BOOLEAN":

            if self.schedule_mode not in (
                "REPEAT",
                "DAILY_CUSTOM",
            ):
                raise ValueError(
                    "BOOLEAN 执行模式不合法"
                )

            if self.total_target is not None:
                raise ValueError(
                    "BOOLEAN 不能设置数量目标"
                )

            if self.schedule_mode == "REPEAT":
                if (
                    not self.repeat_content
                    or not self.repeat_content.strip()
                ):
                    raise ValueError(
                        "固定重复任务必须填写内容"
                    )

        else:
            if self.schedule_mode not in (
                "AUTO_DISTRIBUTE",
                "DAILY_MANUAL",
            ):
                raise ValueError(
                    "NUMERIC 执行模式不合法"
                )

            if self.total_target is None:
                raise ValueError(
                    "NUMERIC 必须设置总目标数量"
                )

            if self.repeat_content is not None:
                raise ValueError(
                    "NUMERIC 不使用重复内容字段"
                )

        return self


class StepCreate(BaseModel):
    """创建树形节点，可嵌套子节点"""

    name: str = Field(min_length=1, max_length=100)
    description: str | None = None

    node_type: Literal["GROUP", "LEAF"]

    # 只有直接通过接口创建的节点才指定 parent_id
    parent_id: int | None = Field(default=None, gt=0)

    rule: StepRule | None = None

    children: list[StepCreate] = Field(
        default_factory=list
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str):
        value = value.strip()

        if not value:
            raise ValueError("节点名称不能为空")

        return value

    @model_validator(mode="after")
    def validate_node(self):
        if self.node_type == "GROUP":

            if self.rule is not None:
                raise ValueError(
                    "GROUP 不能设置执行规则"
                )

            if not self.children:
                raise ValueError(
                    "GROUP 必须至少有一个子节点"
                )

        else:
            if self.children:
                raise ValueError(
                    "LEAF 不能拥有子节点"
                )

            if self.rule is None:
                raise ValueError(
                    "LEAF 必须配置执行规则"
                )

        return self


class StepUpdate(BaseModel):
    """修改节点基本信息"""

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    description: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value):
        if value is None:
            return value

        value = value.strip()

        if not value:
            raise ValueError("节点名称不能为空")

        return value
