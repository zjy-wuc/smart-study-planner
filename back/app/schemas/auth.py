#登录接口规定

from pydantic import BaseModel


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int

# 刷新 Token 请求体
class RefreshRequest(BaseModel):
    refresh_token: str