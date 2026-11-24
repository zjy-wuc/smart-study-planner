
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str

    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    AI_ENABLED: bool = False
    DEEPSEEK_API_KEY: str | None = None
    DEEPSEEK_MODEL: str = "deepseek-flash"

    AI_MAX_NOTE_CHARS: int = 12000
    AI_MAX_OUTPUT_CHARS: int = 12000
    AI_STREAM_CHUNK_CHARS: int = 240
    AI_MAX_OUTPUT_TOKENS: int = 3500

    # 共享额度
    AI_USER_DAILY_LIMIT: int = 10
    AI_GLOBAL_DAILY_LIMIT: int = 80

    # 共享并发
    AI_USER_CONCURRENCY: int = 1
    AI_GLOBAL_CONCURRENCY: int = 2

    # 整条流的最大执行时间与租约有效期
    AI_MAX_STREAM_SECONDS: int = 120
    AI_LEASE_SECONDS: int = 180

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
