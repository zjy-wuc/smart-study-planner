import base64
import hashlib
import json

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


PRACTICE_TICKET_TTL_SECONDS = 24 * 60 * 60


def _cipher() -> Fernet:
    material = (
        b"smart-study-planner:a5:ticket:v1:"
        + settings.SECRET_KEY.encode("utf-8")
    )
    digest = hashlib.sha256(material).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def create_practice_ticket(payload: dict) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")

    return _cipher().encrypt(raw).decode("ascii")


def read_practice_ticket(
    token: str,
    purpose: str = "A5_GENERATION",
) -> dict:
    try:
        raw = _cipher().decrypt(
            token.encode("ascii"),
            ttl=PRACTICE_TICKET_TTL_SECONDS,
        )
        payload = json.loads(raw)

    except (
        InvalidToken,
        UnicodeError,
        ValueError,
        TypeError,
    ) as exc:
        raise ValueError(
            "练习凭证无效或已过期"
        ) from exc

    if (
        not isinstance(payload, dict)
        or payload.get("purpose") != purpose
        or payload.get("version") != 1
    ):
        raise ValueError("练习凭证类型无效")

    return payload