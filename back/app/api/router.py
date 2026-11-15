
from fastapi import APIRouter

from app.api.routes import (
    auth,
    system,
    users,
    plans,
    steps,
    tasks,
    rollovers,
    active_tasks,
     active_steps,
     progress,
     plan_lifecycle,
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
api_router.include_router(tasks.router)
api_router.include_router(rollovers.router)
api_router.include_router(active_tasks.router)
api_router.include_router(active_steps.router)
api_router.include_router(progress.router)
api_router.include_router(plan_lifecycle.router)