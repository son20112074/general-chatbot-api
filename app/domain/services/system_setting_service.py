from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.system_setting import SystemSetting


class SystemSettingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_key(self, key: str) -> Optional[SystemSetting]:
        result = await self.db.execute(
            select(SystemSetting).where(SystemSetting.key == key)
        )
        return result.scalar_one_or_none()

    async def upsert_by_key(
        self, key: str, value: str | None, created_by: int | None
    ) -> SystemSetting:
        entity = await self.get_by_key(key)

        if entity:
            entity.value = value
        else:
            entity = SystemSetting(
                key=key,
                value=value,
                created_by=created_by,
            )
            self.db.add(entity)

        await self.db.commit()
        await self.db.refresh(entity)
        return entity
