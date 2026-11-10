from pydantic import BaseModel


class UserCreate(BaseModel):
    username: str
    password: str
    nickname: str


class UserUpdate(BaseModel):
    nickname: str
    