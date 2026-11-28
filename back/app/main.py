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

from fastapi.staticfiles import StaticFiles

app = FastAPI(
    title="学迹",
    description="学习计划与每日任务管理 API",
    version="0.1.0",
)

app.include_router(api_router)


# 仅公开经过处理的头像目录
settings.AVATAR_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

app.mount(
    "/media/avatars",
    StaticFiles(
        directory=str(settings.AVATAR_DIR),
        follow_symlink=False,
    ),
    name="avatars",
)



# 允许本地 Next.js 前端访问后端 API
app.add_middleware(
    CORSMiddleware,
   allow_origins=settings.AUTH_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


#中间件
@app.middleware("http")
async def session_activity_middleware(
    request: Request,
    call_next,#将请求传递给后续处理流程的可调用对象
):

    response = await call_next(request)#它表示将当前请求交给后续中间件、认证依赖和业务接口处理，然后等待获得响应对象

    identity = getattr(#用于动态读取对象的属性
        request.state,
        "auth_identity",
        None,
    )

    is_event_stream = response.headers.get(
        "content-type",
        "",
    ).startswith("text/event-stream")#可以匹配带有字符编码等附加参数的响应头

    if (
        identity is not None#	用户已经完成身份认证
        and 200 <= response.status_code < 300
        and not is_event_stream
        and request.headers.get(#前端将此次请求标记为用户活动
            "X-User-Activity"
        ) == "1"
        and activity_service.is_activity_path(
            request.url.path
        )
    ):

        user_id, family_id = identity

        await run_in_threadpool(#线程池
            activity_service.record_activity,
            user_id,
            family_id,
        )

    return response





# 统一处理 HTTP 异常


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
):

    detail = exc.detail

    if isinstance(detail, dict):
        message = detail.get("message") or "请求失败"
    else:
        message = str(detail)

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.status_code,
            "message": message,
            "detail": jsonable_encoder(detail),
            "data": None,
        },
        headers=exc.headers,
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
async def generic_exception_handler(
    request: Request,
    exc: Exception,
):

    return error(
        code=500,
        message="服务器内部错误",
    )
