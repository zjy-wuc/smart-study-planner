
from datetime import date
from typing import Annotated

from pydantic import (
    BaseModel,
    Field,
    StringConstraints,
    model_validator,
)


# 统一定义计划名称的校验规则
PlanName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=100,
    ),
]


class PlanCreate(BaseModel):
    """创建学习计划时的数据格式"""

    name: PlanName

    description: str | None = Field(
        default=None,
        max_length=2000,
    )

    start_date: date
    end_date: date
#自动校验器
    @model_validator(mode="after")
    def check_dates(self):
        if self.start_date > self.end_date:
            raise ValueError("开始日期不能晚于结束日期")

        return self


class PlanUpdate(BaseModel):
    """修改学习计划时的数据格式"""

    name: PlanName | None = None

    description: str | None = Field(
        default=None,
        max_length=2000,
    )

    start_date: date | None = None
    end_date: date | None = None
