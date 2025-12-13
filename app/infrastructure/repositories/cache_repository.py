from typing import Any, Dict
from app.domain.interfaces.repositories import CacheRepositoryInterface
# import aioredis


class RedisCacheRepository(CacheRepositoryInterface):
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.redis = None

    async def connect(self):
        self.redis = await aioredis.from_url(self.redis_url)

    async def disconnect(self):
        if self.redis:
            await self.redis.close()

    async def set(self, key: str, value: Any, expire: int = 3600) -> None:
        await self.redis.set(key, value, ex=expire)

    async def get(self, key: str) -> Any:
        value = await self.redis.get(key)
        return value

    async def delete(self, key: str) -> None:
        await self.redis.delete(key)

    async def exists(self, key: str) -> bool:
        return await self.redis.exists(key) > 0

    async def get_all(self, pattern: str) -> Dict[str, Any]:
        keys = await self.redis.keys(pattern)
        values = await self.redis.mget(*keys)
        return dict(zip(keys, values))