import logging
from uuid import uuid4

from fastapi import HTTPException
from redis.exceptions import RedisError

from app.config import settings
from app.core.redis_client import redis_client


logger = logging.getLogger(__name__)


SLIDING_WINDOW_SCRIPT = """
local key = KEYS[1]

local limit = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local request_id = ARGV[3]

-- 获取 Redis 服务端时间，转换为毫秒
local server_time = redis.call('TIME')

local now = tonumber(server_time[1]) * 1000
    + math.floor(tonumber(server_time[2]) / 1000)

-- 计算窗口左边界
local cutoff = now - window_ms

-- 清理已经离开窗口的请求
redis.call(
    'ZREMRANGEBYSCORE',
    key,
    '-inf',
    cutoff
)

-- 避免同一次 Redis 调用重试时重复计数
if redis.call('ZSCORE', key, request_id) then
    return {1, 0}
end

-- 统计当前窗口中的有效请求数量
local count = redis.call('ZCARD', key)

-- 达到限流阈值
if count >= limit then

    local index = count - limit
--拿到最早的请求
    local oldest = redis.call(
        'ZRANGE',
        key,
        index,
        index,
        'WITHSCORES'
    )

    local oldest_time = tonumber(oldest[2])

    local retry_ms = oldest_time + window_ms - now

    return {
        0,
        math.max(retry_ms, 1)
    }
end

-- 记录本次允许通过的请求
redis.call(
    'ZADD',
    key,
    now,
    request_id
)

-- 自动回收长期不活跃用户的 Key
redis.call(
    'PEXPIRE',
    key,
    window_ms
)

return {1, 0}
"""


sliding_window_script = redis_client.register_script(
    SLIDING_WINDOW_SCRIPT
)


def check_ai_rate_limit(
    user_id: int,
) -> None:
    """

    多 Worker 共享用户级限流状态。
    Redis 不可用时拒绝新 AI 请求。
    """

    key = (
        f"ssp:{settings.DB_NAME}:ai:rate:v2:{user_id}"
    )

    request_id = str(uuid4())

    try:
        result = sliding_window_script(
            keys=[key],
            args=[
                settings.AI_USER_RATE_LIMIT,
                settings.AI_RATE_WINDOW_SECONDS * 1000,
                request_id,
            ],
        )

    except RedisError:
        logger.warning(
            "ai_rate_limit_redis_unavailable"
        )

        raise HTTPException(
            status_code=503,
            detail={
                "code": "AI_RATE_LIMIT_UNAVAILABLE",
                "message": "AI 服务暂时不可用，请稍后重试",
            },
        ) from None

    allowed, retry_ms = map(int, result)

    if allowed == 0:
        retry_after = max(
            1,
            (retry_ms + 999) // 1000,
        )

        raise HTTPException(
            status_code=429,
            detail={
                "code": "AI_RATE_LIMIT",
                "message": "AI 请求过于频繁，请稍后重试",
                "retry_after": retry_after,
            },
            headers={
                "Retry-After": str(retry_after),
            },
        )