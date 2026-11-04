from fastapi import Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
import hashlib
import secrets

from app.response import success, error




from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
    # 生成随机盐，并使用 PBKDF2 派生密码哈希
    salt = secrets.token_bytes(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        user.password.encode("utf-8"),
        salt,
        600000,
    ).hex()

    # 保存盐和哈希，便于后续验证密码
    stored_hash = f"pbkdf2_sha256${salt.hex()}${password_hash}"
#pbkdf2_sha256$600000$盐的十六进制值$密码哈希的十六进制值
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
            
        
    except Exception:
        db.rollback()
        raise


#查询全部
@app.get("/users")
def get_all_users(db: Session = Depends(get_db)):
    sql = text("""
        SELECT id, username, nickname, created_id, updated_a
        FROM users
        ORDER BY id
    """)

    result = db.execute(sql)

    users = [
        dict(row)
        for row in result.mappings().all()
    ]

    return users

#查询单个id
@app.get("/users/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db)):
    sql = text("""
        SELECT id, username, nickname, created_at, updated_at
        FROM users
        WHERE id = :user_id
    """)

    result = db.execute(sql, {"user_id": user_id})
    user = result.mappings().first()

    if user is None:
        return error(404, "User not found")

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
 ):
    sql = text("""
        UPDATE users
        SET nickname = :nickname,
            updated_at = NOW()
        WHERE id = :user_id
    """)
    result = db.execute(sql,{"nickname":user.nickname,"user_id":user_id,})

    if result.rowcount == 0:
        db.rollback()
        return error(404, "User not found")
    db.commit()
    
    return success(
        data={
            "id":user_id,
            "nickname":user.nickname,
        },
        message="用户修改成功",
        code=200,
    )
       


#删除用户
@app.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
):
    sql = text("""
        DELETE FROM users
        WHERE id = :user_id
    """)

    result = db.execute(sql, {"user_id": user_id})

    if result.rowcount == 0:
        db.rollback()
        return error(404, "User not found")

    db.commit()

    return success(
        data={
            "id":user_id,
        },
        message="用户删除成功",
        code=200,
    )