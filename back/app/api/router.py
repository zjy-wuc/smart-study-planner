from fastapi import APIRouter

from app.api.routes import (
    auth, system, users, plans, steps, tasks, rollovers,
    active_tasks, active_steps, progress, plan_lifecycle,
    schedules, daily_tasks, statistics, knowledge, focus,
    knowledge_ai, ai_practice,
)


api_router = APIRouter()

# 系统与用户认证
api_router.include_router(system.router)
api_router.include_router(users.router)
api_router.include_router(auth.router)

# 计划
api_router.include_router(plans.router)
api_router.include_router(plan_lifecycle.router)

# 学习步骤与草稿安排
api_router.include_router(steps.router)
api_router.include_router(schedules.router)

# 每日任务与顺延
api_router.include_router(daily_tasks.router)
api_router.include_router(tasks.router)
api_router.include_router(rollovers.router)

# ACTIVE 阶段的修改
api_router.include_router(active_tasks.router)
api_router.include_router(active_steps.router)

# 进度与统计
api_router.include_router(progress.router)
api_router.include_router(statistics.router)

# 知识笔记
api_router.include_router(knowledge.router)
api_router.include_router(knowledge_ai.router)

# A5 AI 智能练习
api_router.include_router(ai_practice.router)

# 专注闹钟
api_router.include_router(focus.router)