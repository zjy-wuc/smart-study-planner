from datetime import datetime
from typing import Annotated

from email_validator import (
    validate_email,
    EmailNotValidError,
)
from pydantic import (
    BaseModel,
    AfterValidator,
    StringConstraints,
)


def normalize_email(value: str) -> str:
    """验证邮箱格式，并统一邮箱存储格式"""

    try:
        result = validate_email(
            value.strip().lower(),
            check_deliverability=False,
        )

    except EmailNotValidError:
        raise ValueError("邮箱格式不正确") from None

    email = result.normalized.lower()

    if len(email) > 254:
        raise ValueError("邮箱长度不能超过254字符")

    return email


# ==================== 公共字段类型 ====================

EmailAddress = Annotated[
    str,
    AfterValidator(normalize_email),
]

Username = Annotated[
    str,
    StringConstraints(
        min_length=4,
        max_length=32,
        pattern=r"^[a-zA-Z0-9_]+$",
    ),
]

Password = Annotated[
    str,
    StringConstraints(
        min_length=8,
        max_length=64,
    ),
]

Nickname = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=50,
    ),
]

EmailCode = Annotated[
    str,
    StringConstraints(
        min_length=6,
        max_length=6,
        pattern=r"^[0-9]{6}$",
    ),
]


# ==================== 请求模型 ====================

class UserCreate(BaseModel):
    username: Username
    password: Password
    email: EmailAddress
    code: EmailCode
    nickname: Nickname | None = None


class UserUpdate(BaseModel):
    nickname: Nickname


# ==================== 响应模型 ====================

class UserPublic(BaseModel):
    id: int
    username: str
    nickname: str | None
    email: EmailAddress
    avatar_url: str | None = None
    email_verified_at: datetime
    is_active: bool