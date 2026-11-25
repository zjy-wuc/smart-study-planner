from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # ==================== 数据库 ====================

    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str

    # ==================== JWT ====================

    SECRET_KEY: str

    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=15, gt=0)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, gt=0)

    # ==================== 登录会话 ====================

    SESSION_IDLE_EXPIRE_DAYS: int = 7#连续 7 天不活跃，会话失效
    SESSION_ABSOLUTE_EXPIRE_DAYS: int = 30#登录满 30 天，必须重新登录

    # 最后活跃时间写入间隔
    SESSION_ACTIVITY_INTERVAL_SECONDS: int = 300#活跃时间最多约每 5 分钟更新

    # ==================== Refresh Cookie ====================

    REFRESH_COOKIE_NAME: str = "ssp_refresh"
    REFRESH_COOKIE_PATH: str = "/auth"
    REFRESH_COOKIE_SECURE: bool = True

    AUTH_ALLOWED_ORIGINS: list[str] = [
        "http://localhost:3000",
    ]

    # ==================== 邮箱验证码 ====================

    EMAIL_CODE_SECRET: str

    EMAIL_CODE_EXPIRE_MINUTES: int = 5
    EMAIL_CODE_COOLDOWN_SECONDS: int = 60
    EMAIL_CODE_MAX_ATTEMPTS: int = 5

    EMAIL_DAILY_LIMIT: int = 10
    EMAIL_IP_DAILY_LIMIT: int = 30


    # ==================== 邮件服务 ====================

    MAIL_ENABLED: bool = False

    BREVO_API_KEY: str | None = None
    MAIL_FROM_EMAIL: str | None = None
    MAIL_FROM_NAME: str = "Smart Study Planner"

    MAIL_TIMEOUT_SECONDS: int = Field(default=10, gt=0)#邮件延迟

    EMAIL_GLOBAL_DAILY_LIMIT: int = Field(
        default=80,
        gt=0,
    )

    # ==================== IP 认证限流 ====================

    AUTH_IP_WINDOW_MINUTES: int = Field(#设置 IP 认证限流的统计窗口为 15 分钟
        default=15,
        gt=0,
    )

    PASSWORD_IP_MAX_ATTEMPTS: int = Field(
        default=30,
        gt=0,
    )

    EMAIL_CODE_IP_MAX_ATTEMPTS: int = Field(
        default=30,
        gt=0,
    )

    AUTH_LOCK_TIMEOUT_SECONDS: int = Field(#控制获取认证相关锁时的等待时间，默认 3 秒
        default=3,
        gt=0,
    )



    # ==================== 认证安全 ====================

    PASSWORD_MAX_FAILED_ATTEMPTS: int = 5
    PASSWORD_LOCK_MINUTES: int = 15

    AUTH_EVENT_RETENTION_DAYS: int = 30#安全事件保留 30 天

    # ==================== 头像 ====================

    AVATAR_MAX_BYTES: int = 2 * 1024 * 1024
    AVATAR_MAX_SIZE: int = 512

    # ==================== AI 原有配置 ====================

    AI_ENABLED: bool = False
    DEEPSEEK_API_KEY: str | None = None
    DEEPSEEK_MODEL: str = "deepseek-flash"

    AI_MAX_NOTE_CHARS: int = 12000
    AI_MAX_OUTPUT_CHARS: int = 12000
    AI_STREAM_CHUNK_CHARS: int = 240
    AI_MAX_OUTPUT_TOKENS: int = 3500

    AI_USER_DAILY_LIMIT: int = 10
    AI_GLOBAL_DAILY_LIMIT: int = 80

    AI_USER_CONCURRENCY: int = 1
    AI_GLOBAL_CONCURRENCY: int = 2

    AI_MAX_STREAM_SECONDS: int = 120
    AI_LEASE_SECONDS: int = 180

    # ==================== 密钥校验 ====================

    @field_validator("SECRET_KEY", "EMAIL_CODE_SECRET")
    @classmethod
    def validate_secret(cls, value: str) -> str:
        if len(value.encode("utf-8")) < 32:
            raise ValueError("密钥长度不能小于32字节")

        return value

    @model_validator(mode="after")
    def validate_secrets(self):
        if self.SECRET_KEY == self.EMAIL_CODE_SECRET:
            raise ValueError("JWT和邮箱验证码不能使用相同密钥")

        return self

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )


settings = Settings()