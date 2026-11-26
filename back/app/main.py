from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.router import api_router
from app.response import error,success

from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder

from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.services.auth import activity_service


app = FastAPI(
    title="智能学习计划管理系统",
    description="学习计划与每日任务管理 API",
    version="0.1.0",
)

app.include_router(api_router)

# 允许本地 Next.js 前端访问后端 API
app.add_middleware(
    CORSMiddleware,
   allow_origins=settings.AUTH_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



@app.middleware("http")
async def session_activity_middleware(
    request: Request,
    call_next,
):

    response = await call_next(request)

    identity = getattr(
        request.state,
        "auth_identity",
        None,
    )

    is_event_stream = response.headers.get(
        "content-type",
        "",
    ).startswith("text/event-stream")

    if (
        identity is not None
        and 200 <= response.status_code < 300
        and not is_event_stream
        and request.headers.get(
            "X-User-Activity"
        ) == "1"
        and activity_service.is_activity_path(
            request.url.path
        )
    ):

        user_id, family_id = identity

        await run_in_threadpool(
            activity_service.record_activity,
            user_id,
            family_id,
        )

    return response





# 统一处理 HTTP 异常

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):

    errors = [
        {
            "loc": item["loc"],
            "type": item["type"],
            "msg": "Invalid input",
        }
        for item in exc.errors()
    ]

    return error(
        code=422,
        message="Request validation failed",
        data=errors,
    )
# 统一处理请求参数验证异常
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    errors = [
        {
            "loc": item["loc"],
            "type": item["type"],
            "msg": "Invalid input",
        }
        for item in exc.errors()
    ]

    return error(
        code=422,
        message="Request validation failed",
        data=errors,
    )

# 统一处理未捕获异常
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return error(code=500, message="服务器内部错误")
