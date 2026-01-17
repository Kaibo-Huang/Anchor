"""Redis client for caching and temporary data storage."""

from functools import lru_cache

import redis

from config import get_settings


@lru_cache
def get_redis() -> redis.Redis:
    """Get Redis client singleton.

    Used for:
    - Shopify OAuth nonce storage
    - Celery task broker
    - Caching TwelveLabs results
    """
    settings = get_settings()
    return redis.from_url(settings.redis_url, decode_responses=False)


def get_redis_async():
    """Get async Redis client for use in async contexts.

    Note: For most use cases, the sync client works fine with FastAPI.
    Only use this if you need true async Redis operations.
    """
    import redis.asyncio as aioredis
    settings = get_settings()
    return aioredis.from_url(settings.redis_url, decode_responses=False)
