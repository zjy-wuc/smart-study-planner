import httpx

from app.config import settings
from app.schemas.auth import EmailCodePurpose


BREVO_API_URL = (
    "https://api.brevo.com/v3/smtp/email"
)


PURPOSE_NAMES = {
    EmailCodePurpose.REGISTER: "注册账号",
    EmailCodePurpose.LOGIN: "登录账号",
    EmailCodePurpose.RESET_PASSWORD: "重置密码",
    EmailCodePurpose.CHANGE_EMAIL_OLD: "验证原邮箱",
    EmailCodePurpose.CHANGE_EMAIL_NEW: "验证新邮箱",
}


def mail_ready() -> bool:
    """检查邮件服务是否已经配置"""

    return bool(
        settings.MAIL_ENABLED
        and settings.BREVO_API_KEY
        and settings.MAIL_FROM_EMAIL
    )


def send_verification_code(
    email: str,
    code: str,
    purpose: EmailCodePurpose,
) -> bool:
    """发送邮件，返回邮件服务商是否接受请求"""

    if not mail_ready():
        return False

    api_key = settings.BREVO_API_KEY
    sender_email = settings.MAIL_FROM_EMAIL

    if not api_key or not sender_email:
        return False

    purpose_name = PURPOSE_NAMES[purpose]

    subject = (
        f"Smart Study Planner - {purpose_name}验证码"
    )

    content = (
        f"您好！\n\n"
        f"您的{purpose_name}验证码为：{code}\n\n"
        f"验证码有效期为"
        f"{settings.EMAIL_CODE_EXPIRE_MINUTES}分钟。\n"
        f"请勿将验证码告知他人。\n\n"
        f"如果不是您本人操作，请忽略此邮件。\n\n"
        f"Smart Study Planner"
    )

    payload = {
        "sender": {
            "name": settings.MAIL_FROM_NAME,
            "email": sender_email,
        },
        "to": [
            {
                "email": email,
            }
        ],
        "subject": subject,
        "textContent": content,
    }

    try:
        response = httpx.post(
            BREVO_API_URL,
            headers={
                "api-key": api_key,
                "accept": "application/json",
            },
            json=payload,
            timeout=settings.MAIL_TIMEOUT_SECONDS,
            follow_redirects=False,
        )

    except httpx.HTTPError:
        return False

    return response.status_code == 201