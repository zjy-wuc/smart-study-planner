from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class CheckinStatistics(BaseModel):
    total_count: int = Field(ge=0)#总打卡次数
    last_7_days_count: int = Field(ge=0)
    last_30_days_count: int = Field(ge=0)
    current_streak_days: int = Field(ge=0)#当前连打天数


class PlanStatistics(BaseModel):
    active_count: int = Field(ge=0)
    ended_count: int = Field(ge=0)



class DailyCheckinTrend(BaseModel):
    date: date
    checkin_count: int = Field(ge=0)#某天打卡结果




#总的
class StatisticsOverview(BaseModel):
    as_of_date: date#北京时间

    checkins: CheckinStatistics
    plans: PlanStatistics

    trend_days: Literal[7, 30]
    daily_trend: list[DailyCheckinTrend]#对应范围打卡数据