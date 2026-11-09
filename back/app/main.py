import time
from collections import defaultdict#可以指定默认返回的类型

from app.api.router import api_router
from fastapi import Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from fastapi.security import OAuth2PasswordRequestForm

from app.response import success, error

from app.core.deps import get_current_user


from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException



from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
)

app = FastAPI(
    title="智能学习计划管理系统",
    description="学习计划与每日任务管理 API",
    version="0.1.0",
)

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


# ==================== 登录限流配置 ====================
MAX_FAILED_ATTEMPTS = 5          # 窗口期内最多失败次数
RATE_LIMIT_WINDOW = 60           # 窗口期（秒），即 1 分钟内
failed_login_attempts: dict[str, list[float]] = defaultdict(list)


def _is_rate_limited(client_ip: str) -> bool:
    """检查该 IP 是否在窗口期内失败次数超限"""
    now = time.time()
    # 只保留窗口期内的失败记录
    failed_login_attempts[client_ip] = [
        ts for ts in failed_login_attempts[client_ip]
        if now - ts < RATE_LIMIT_WINDOW
    ]
    return len(failed_login_attempts[client_ip]) >= MAX_FAILED_ATTEMPTS


def _record_failed_attempt(client_ip: str) -> None:
    """记录一次失败登录的时间戳"""
    failed_login_attempts[client_ip].append(time.time())


def _clear_failed_attempts(client_ip: str) -> None:
    """登录成功后清空该 IP 的失败记录"""
    failed_login_attempts.pop(client_ip, None)
# =====================================================


@app.get("/")
def read_root():
    return {
        "message": "智能学习计划管理系统后端运行成功！",
        "version": "0.1.0",
    }


@app.get("/health")
def health_check():
    return {"status": "ok"}

#CRUD*
# 用户注册
class UserCreate(BaseModel):
    username: str
    password: str
    nickname: str

class UserUpdate(BaseModel):
    nickname:str



#post 资源创建，201为资源创建成功
@app.post("/users", status_code=201)
def create_user(
    user: UserCreate,
    db: Session = Depends(get_db),
):
    stored_hash = hash_password(user.password)

    sql = text("""
        INSERT INTO users
            (username, password_hash, nickname, created_at, updated_at)
        VALUES
            (:username, :password_hash, :nickname, NOW(), NOW())
    """)

    try:
        result = db.execute(sql, {
            "username": user.username,
            "password_hash": stored_hash,
            "nickname": user.nickname,
        })
        db.commit()

        return success(
            data={
                "id": result.lastrowid,
                "username": user.username,
                "nickname": user.nickname,
            },
            message="用户创建成功",
            code=201,
        )
            
        
    except IntegrityError:
        # 用户名唯一索引 uk_users_username 冲突
        db.rollback()
        return error(409, "用户名已存在")
    except Exception:
        db.rollback()
        raise


#查询全部
@app.get("/users")
def get_all_users(db: Session = Depends(get_db)):
    sql = text("""
        SELECT id, username, nickname, created_at, updated_at
        FROM users
        ORDER BY id
    """)

    result = db.execute(sql)

    users = [
        dict(row)
        for row in result.mappings().all()
    ]

    return success(
        data=users,
        message="Users found"
    )

#当前用户接口
@app.get("/users/me")
def get_current_user_info(
    current_user: dict = Depends(get_current_user),
):
    return success(
        data=current_user,
        message="Current user info found",
        code=200,
    )



#查询单个id
@app.get("/users/{user_id}")
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if user_id != current_user["id"]:
        raise HTTPException(
            status_code=403,
            detail="You cannot access another user's data",
        )

    sql = text("""
        SELECT id, username, nickname, created_at, updated_at
        FROM users
        WHERE id = :user_id
    """)

    result = db.execute(sql, {"user_id": user_id})
    user = result.mappings().first()

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    return success(
        data=dict(user),
        message="User found"
    )

#修改用户昵称
@app.put("/users/{user_id}")
def update_user(
    user_id: int,
    user: UserUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # 检查当前用户是否有权修改这个账户
    if user_id != current_user["id"]:
        raise HTTPException(
            status_code=403,
            detail="You cannot modify another user's data",
        )

    sql = text("""
        UPDATE users
        SET nickname = :nickname,
            updated_at = NOW()
        WHERE id = :user_id
    """)

    result = db.execute(
        sql,
        {
            "nickname": user.nickname,
            "user_id": user_id,
        },
    )

    if result.rowcount == 0:
        db.rollback()
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    db.commit()

    return success(
        data={
            "id": user_id,
            "nickname": user.nickname,
        },
        message="用户修改成功",
    )  


#删除用户
@app.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # 检查当前用户是否有权删除目标账户
    if user_id != current_user["id"]:
        raise HTTPException(
            status_code=403,
            detail="You cannot delete another user's data",
        )

   
    sql = text("""
        DELETE FROM users
        WHERE id = :user_id
    """)

    result = db.execute(sql, {"user_id": user_id})

    #检查目标用户是否存在
    if result.rowcount == 0:
        db.rollback()
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

 
    db.commit()

    
    return success(
        data={"id": user_id},
        message="用户删除成功",
        code=200,
    )


# 统一处理请求参数验证异常
# 统一处理 HTTP 异常
@app.exception_handler(StarletteHTTPException)
#使用了异步函数
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

#处理其他异常
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return error(code=500, message="服务器内部错误")



#登录接口,返回令牌和token种类
@app.post("/auth/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),#从请求体中获取用户名和密码
    db: Session = Depends(get_db),
):
     # 查询用户
    sql = text("""
        SELECT id, username, password_hash, nickname
        FROM users
        WHERE username = :username
    """)

    result = db.execute(
        sql,
        {"username": form_data.username},
    )

    user = result.mappings().first()
#验证账号密码
    if user is None or not verify_password(
        form_data.password,
        user["password_hash"]
    ):
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
         )
#creat jwt
    access_token = create_access_token(
        {"sub":str(user["id"])},
    )
#返回统一的格式
    return success(
        data={
            "access_token":access_token,
            "token_type":"Bearer",
        },
        message="登录成功",
        code=200,
    )
   

