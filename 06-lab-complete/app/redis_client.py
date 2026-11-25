"""
Kết nối Redis dùng chung cho rate limiter và cost guard.
"""
import redis

from app.config import settings


def get_redis_client() -> redis.Redis | None:
    """Tạo Redis client từ REDIS_URL mà không ping lúc import."""
    if not settings.redis_url:
        return None
    return redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )


r = get_redis_client()


def redis_healthy() -> bool:
    """Ping Redis; trả False nếu không kết nối được."""
    client = get_redis_client() if r is None else r
    if client is None:
        return False
    try:
        return bool(client.ping())
    except redis.RedisError:
        return False
