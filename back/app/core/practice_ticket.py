import base64
import hashlib
import json

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


PRACTICE_TICKET_TTL_SECONDS = 24 * 60 * 60


def _cipher() -> Fernet:#Fernet 是 cryptography 提供的对称认证加密机制
    """从现有 SECRET_KEY 派生 A5 专用加密密钥。"""
#构造密钥材料
    material = (
        b"smart-study-planner:a5:ticket:v1:"
        + settings.SECRET_KEY.encode("utf-8")
    )

    digest = hashlib.sha256(material).digest()#bytes	32 字节

    key = base64.urlsafe_b64encode(digest)#而 Base64 将这些字节转换为便于作为文本表示的编码形式

    return Fernet(key)


def create_practice_ticket(payload: dict) -> str:
    """加密并认证完整练习信息。"""

    raw = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),#则用于去除 JSON 结构中的不必要空格，让结果更紧凑
    ).encode("utf-8")

    return _cipher().encrypt(raw).decode("ascii")


def read_practice_ticket(token: str) -> dict:
    """读取有效期内的练习信息。供后续批改接口使用。"""

    try:
        raw = _cipher().decrypt(
            token.encode("ascii"),
            ttl=PRACTICE_TICKET_TTL_SECONDS,
        )

        payload = json.loads(raw)

    except (InvalidToken, UnicodeError, ValueError) as exc:
        raise ValueError(
            "练习凭证无效或已过期"
        ) from exc

    if (
        not isinstance(payload, dict)
        or payload.get("purpose") != "A5_GENERATION"
        or payload.get("version") != 1
    ):
        raise ValueError("练习凭证类型无效")

    return payload