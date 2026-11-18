
from typing import Literal

from pydantic import BaseModel, Field


class FocusStart(BaseModel):
    session_type: Literal["POMODORO", "STOPWATCH"]

    planned_seconds: int | None = Field(
        default=None,
        gt=0,
        le=4294967295,
    )

    plan_id: int | None = Field(
        default=None,
        gt=0,
    )

    task_id: int | None = Field(
        default=None,
        gt=0,
    )
