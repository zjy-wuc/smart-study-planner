#hash和jwt的工具函数
#hashcode
import hashlib
import hmac
import secrets
ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 600000

# jwt
from datetime import datetime, timedelta, timezone

import jwt
from jwt.exceptions import InvalidTokenError

from app.config import settings


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


# 创建令牌
def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    
    token = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm="HS256"
    )
    return token

# 解码令牌
def decode_access_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=["HS256"],
        )

        return payload

    except InvalidTokenError:
        return None
