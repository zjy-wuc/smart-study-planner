from pydantic import BaseModel

# 待迁移：把 main.py 中的 UserCreate、UserUpdate 移到这里


class UserCreate(BaseModel):
    username: str
    password: str
    nickname: str


class UserUpdate(BaseModel):
    nickname: str
