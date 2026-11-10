from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.router import api_router
from app.response import error


app = FastAPI(
    title="智能学习计划管理系统",
    description="学习计划与每日任务管理 API",
    version="0.1.0",
)

app.include_router(api_router)

# 允许本地 Next.js 前端访问后端 API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 统一处理 HTTP 异常
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
):
    response = error(
        code=exc.status_code,
        message=str(exc.detail),
    )

    # 保留认证相关响应头
    if exc.headers:
        response.headers.update(exc.headers)

    return response


# 统一处理请求参数验证异常
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    return error(
        code=422,
        message="Request validation failed",
        data=exc.errors(),
    )


# 统一处理未捕获异常
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return error(code=500, message="服务器内部错误")
