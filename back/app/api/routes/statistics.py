from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.response import success
from app.services.statistics import statistics_service

from enum import IntEnum

class TrendDays(IntEnum):
    SEVEN = 7
    THIRTY = 30


router = APIRouter(
    prefix="/statistics",
    tags=["Statistics"],
)

#QUERY 是严格相等
@router.get("/overview")
def get_statistics_overview(
    days: TrendDays = Query(
          default=TrendDays.SEVEN,
        #参数添加说明，方便在 Swagger API 文档中查看
        description="每日打卡趋势的统计天数",
    ),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = statistics_service.get_statistics_overview(
        db=db,
        user_id=current_user["id"],
        days=days.value,
    )

    return success(
        data=result.model_dump(mode="json"),
        message="学习统计查询成功",
    )