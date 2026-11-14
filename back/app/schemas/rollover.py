
from datetime import date

from pydantic import BaseModel, ConfigDict


class RolloverRequest(BaseModel):
    """用户手动指定顺延目标日期"""

    model_config = ConfigDict(extra="forbid")

    target_date: date
