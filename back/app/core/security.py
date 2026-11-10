#hash和jwt的工具函数
#hashcode
import hashlib
import hmac
import secrets
ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 600000
import uuid

# jwt
from datetime import datetime, timedelta, timezone

import jwt
from jwt.exceptions import InvalidTokenError

from app.config import settings
JWT_ALGORITHM = "HS256"

# 密码哈希函数
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, ITERATIONS
    ).hex()
    return f"{ALGORITHM}${ITERATIONS}${salt.hex()}${digest}"

# 密码验证函数
def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest = stored_hash.split("$")
        iterations_int = int(iterations)
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False

    if algorithm != ALGORITHM:
        return False
    if not 100000 <= iterations_int <= 2000000:
        return False

    computed = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations_int
    ).hex()
    return hmac.compare_digest(computed, digest)


# 创建JWT令牌


def _create_token(
    data: dict,
    expires_delta: timedelta,
    token_type: str,
) -> str:
    now = datetime.now(timezone.utc)

    payload = data.copy()

    payload.update({
        "iat": now,
        "exp": now + expires_delta,
        "type": token_type,
        # jti 保证即使同一秒内重复签发，token 也互不相同
        "jti": str(uuid.uuid4()),
    })

    return jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )


#access token
def create_access_token(data: dict) -> str:
    return _create_token(
        data=data,
        expires_delta=timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        ),
        token_type="access",
    )


#refresh token
def create_refresh_token(data: dict) -> str:
    return _create_token(
        data=data,
        expires_delta=timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        ),
        token_type="refresh",
    )



# 解码令牌

def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={
                "require": ["sub", "iat", "exp", "type"],
            },
        )
    except InvalidTokenError:
        return None


def decode_access_token(token: str) -> dict | None:
    payload = decode_token(token)

    if payload is None:
        return None

    if payload.get("type") != "access":
        return None

    return payload


def decode_refresh_token(token: str) -> dict | None:
    payload = decode_token(token)

    if payload is None:
        return None

    if payload.get("type") != "refresh":
        return None

    return payload


#refresh token 摘要
def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()

#登录会话id

def create_family_id() -> str:
    return str(uuid.uuid4())
