from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["auth"])

# 待迁移：POST /login
