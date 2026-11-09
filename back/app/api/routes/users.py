from fastapi import APIRouter

router = APIRouter(prefix="/users", tags=["users"])

# 待迁移：POST /、GET /、GET /me、GET /{user_id}、PUT /{user_id}、DELETE /{user_id}
