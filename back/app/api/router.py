
from fastapi import APIRouter

from app.api.routes import (
    auth,
    system,
    users,
    plans,
)


api_router = APIRouter()

api_router.include_router(system.router)
api_router.include_router(users.router)
api_router.include_router(auth.router)

# 学习计划接口
api_router.include_router(plans.router)
