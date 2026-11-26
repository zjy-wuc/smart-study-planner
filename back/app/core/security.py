import hashlib
import hmac
import json
import secrets
import uuid

from datetime import datetime, timedelta

import jwt
from jwt.exceptions import InvalidTokenError, ExpiredSignatureError

from app.config import settings
from app.core.clock import utc_now


ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 600000

JWT_ALGORITHM = "HS256"


#  密码哈希


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        ITERATIONS,
    ).hex()

    return f"{ALGORITHM}${ITERATIONS}${salt.hex()}${digest}"





def verify_password(
    password: str,
    stored_hash: str,
) -> bool:

    if not isinstance(password, str):
        return False

    if not isinstance(stored_hash, str):
        return False

    try:
        algorithm, iterations, salt_hex, digest = (
            stored_hash.split("$")
        )

        iterations_int = int(iterations)
        salt = bytes.fromhex(salt_hex)
        expected_digest = bytes.fromhex(digest)

    except (ValueError, TypeError):
        return False

    if algorithm != ALGORITHM:
        return False

    if not 100000 <= iterations_int <= 2000000:
        return False

    if len(salt) != 16:
        return False

    if len(expected_digest) != 32:
        return False

    actual_digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations_int,
    )

    return hmac.compare_digest(
        actual_digest,
        expected_digest,
    )
#  会话 ID 


def create_family_id() -> str:
    return str(uuid.uuid4())

#检查
def _is_uuid4(value: object) -> bool:
    if not isinstance(value, str):
        return False

    try:
        parsed = uuid.UUID(value)#可以将符合 UUID 格式的字符串转换成 UUID 对象

        return (
            parsed.version == 4
            and str(parsed) == value
        )

    except ValueError:
        return False


# JWT Payload 校验


def _valid_identity(payload: dict) -> bool:
    user_id = payload.get("sub")
    family_id = payload.get("family_id")

    if not isinstance(user_id, str):
        return False

    if not (
        user_id.isascii()
        and user_id.isdigit()
        and 1 <= len(user_id) <= 20
    ):
        return False

    if not 1 <= int(user_id) <= 2**64 - 1:
        return False

    return _is_uuid4(family_id)


# ==================== JWT 签发 ====================


def _create_token(
    data: dict,
    expires_delta: timedelta,
    token_type: str,
    expires_at: datetime | None = None,
) -> str:

    if not _valid_identity(data):
        raise ValueError("JWT 缺少合法用户或会话标识")

    now = utc_now()
    expiration = now + expires_delta

    # Token 不能超过会话有效期限
    if expires_at is not None:

        if expires_at.utcoffset() is None:
            raise ValueError("过期时间必须包含时区")

        expiration = min(expiration, expires_at)

    if int(expiration.timestamp()) <= int(now.timestamp()):
        raise ValueError("Token 过期时间无效")

    payload = data.copy()

    payload.update({
        "iat": now,
        "exp": expiration,
        "type": token_type,
        "jti": str(uuid.uuid4()),#token唯一编号
    })

    return jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )


def create_access_token(
    data: dict,
    *,
    expires_at: datetime | None = None,
) -> str:

    return _create_token(
        data=data,
        expires_delta=timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        ),
        token_type="access",
        expires_at=expires_at,
    )


def create_refresh_token(
    data: dict,
    *,
    expires_at: datetime | None = None,
) -> str:

    return _create_token(
        data=data,
        expires_delta=timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS,
        ),
        token_type="refresh",
        expires_at=expires_at,
    )


# ==================== JWT 解码 ====================


def _decode_token_detailed(
    token: str,
) -> tuple[dict | None, str | None]:

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={
                "require": [
                    "sub",
                    "family_id",
                    "iat",
                    "exp",
                    "type",
                    "jti",
                ],
            },
        )

    except ExpiredSignatureError:
        return None, "TOKEN_EXPIRED"

    except InvalidTokenError:
        return None, "INVALID_TOKEN"

    if not _valid_identity(payload):
        return None, "INVALID_TOKEN_PAYLOAD"

    if not _is_uuid4(payload.get("jti")):
        return None, "INVALID_TOKEN_PAYLOAD"

    if payload.get("type") not in ("access", "refresh"):
        return None, "TOKEN_TYPE_INVALID"

    return payload, None


def decode_token(token: str) -> dict | None:
    payload, _ = _decode_token_detailed(token)

    return payload


def decode_access_token_detailed(
    token: str,
) -> tuple[dict | None, str | None]:

    payload, error_code = _decode_token_detailed(token)

    if payload is None:
        if error_code == "TOKEN_EXPIRED":
            return None, "ACCESS_EXPIRED"

        return None, error_code

    if payload["type"] != "access":
        return None, "TOKEN_TYPE_INVALID"

    return payload, None


def decode_access_token(token: str) -> dict | None:
    payload, _ = decode_access_token_detailed(token)

    return payload


def decode_refresh_token(token: str) -> dict | None:
    payload = decode_token(token)

    if payload is None:
        return None

    if payload["type"] != "refresh":
        return None

    return payload


# ==================== Refresh Token 摘要 ====================


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(
        token.encode("utf-8"),
    ).hexdigest()


# ==================== 邮箱验证码 ====================


def generate_email_code() -> str:
    """生成六位数字验证码，允许以 0 开头"""
    return f"{secrets.randbelow(1000000):06d}"


def hash_email_code(
    email: str,
    purpose: str,
    code: str,
) -> str:

    message = json.dumps(
        [email, purpose, code],
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
#验证码只有6位数，即使hash也安全性低，所以要添加密钥
    return hmac.new(
        settings.EMAIL_CODE_SECRET.encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()


def verify_email_code(
    email: str,
    purpose: str,
    code: str,
    stored_hash: str,
) -> bool:

    computed = hash_email_code(
        email=email,
        purpose=purpose,
        code=code,
    )

    return hmac.compare_digest(
        computed,
        stored_hash,
    )