from redis import Redis

from app.config import settings


redis_client = Redis.from_url(
    settings.REDIS_URL,
    decode_responses=True,
    socket_connect_timeout=1,
    socket_timeout=1,
    max_connections=10,
)