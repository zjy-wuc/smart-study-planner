
from fastapi import APIRouter

from app.api.routes import (
    auth,
    system,
    users,
    plans,
    steps,
)


api_router = APIRouter()

api_router.include_router(system.router)
api_router.include_router(users.router)
api_router.include_router(auth.router)
api_router.include_router(plans.router)

# 新增树形学习步骤接口
api_router.include_router(steps.router)
