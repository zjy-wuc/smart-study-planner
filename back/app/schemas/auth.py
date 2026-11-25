from enum import StrEnum

from pydantic import BaseModel

from app.schemas.user import (
    EmailAddress,
    EmailCode,
    Password,
    UserPublic,
)


# ==================== 验证码用途 ====================

class EmailCodePurpose(StrEnum):
    REGISTER = "REGISTER"
    LOGIN = "LOGIN"
    RESET_PASSWORD = "RESET_PASSWORD"
    CHANGE_EMAIL_OLD = "CHANGE_EMAIL_OLD"
    CHANGE_EMAIL_NEW = "CHANGE_EMAIL_NEW"


# ==================== 邮箱验证码 ====================

class EmailCodeRequest(BaseModel):
    email: EmailAddress
    purpose: EmailCodePurpose


# ==================== 登录 ====================

class EmailLoginRequest(BaseModel):
    email: EmailAddress
    code: EmailCode


# ==================== 密码管理 ====================

class PasswordResetRequest(BaseModel):
    email: EmailAddress
    code: EmailCode
    new_password: Password


class PasswordChangeRequest(BaseModel):
    old_password: Password
    new_password: Password


# ==================== 邮箱管理 ====================

class EmailChangeRequest(BaseModel):
    password: Password
    old_email_code: EmailCode
    new_email: EmailAddress
    new_email_code: EmailCode


# ==================== 会话管理 ====================

class SessionRevokeRequest(BaseModel):
    password: Password


# ==================== 内部 Token 模型 ====================

class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int


# ==================== 对外响应模型 ====================

class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int


class LoginResponse(AccessTokenResponse):
    user: UserPublic


# ==================== 临时兼容旧接口 ====================

class RefreshRequest(BaseModel):
    refresh_token: str