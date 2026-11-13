
from fastapi import APIRouter

from app.api.routes import (
    auth,
    system,
    users,
    plans,
    steps,
)
from app.api.routes import schedules, daily_tasks

api_router = APIRouter()

api_router.include_router(system.router)
api_router.include_router(users.router)
api_router.include_router(auth.router)
api_router.include_router(plans.router)

# 新增树形学习步骤接口
api_router.include_router(steps.router)

api_router.include_router(schedules.router)
api_router.include_router(daily_tasks.router)