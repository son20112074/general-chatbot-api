from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.linked_system import LinkedSystem
from app.presentation.api.v1.schemas.linked_system import (
    LinkedSystemCreate,
    LinkedSystemUpdate,
    normalize_icon,
)


class LinkedSystemService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_active(self) -> List[LinkedSystem]:
        result = await self.db.execute(
            select(LinkedSystem)
            .where(LinkedSystem.is_deleted == False)  # noqa: E712
            .order_by(LinkedSystem.sort_order.asc(), LinkedSystem.id.asc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, system_id: int) -> Optional[LinkedSystem]:
        result = await self.db.execute(
            select(LinkedSystem).where(LinkedSystem.id == system_id)
        )
        return result.scalar_one_or_none()

    async def _abbr_taken(self, abbr: str, exclude_id: Optional[int] = None) -> bool:
        query = select(LinkedSystem.id).where(
            LinkedSystem.abbr == abbr,
            LinkedSystem.is_deleted == False,  # noqa: E712
        )
        if exclude_id is not None:
            query = query.where(LinkedSystem.id != exclude_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none() is not None

    async def create(
        self, data: LinkedSystemCreate, created_by: int
    ) -> LinkedSystem:
        abbr = data.abbr.strip()
        name = data.name.strip()
        url = data.url.strip()
        if not abbr or not name or not url:
            raise ValueError("abbr, name and url are required")
        if await self._abbr_taken(abbr):
            raise ValueError(f"Abbreviation '{abbr}' already exists")

        entity = LinkedSystem(
            abbr=abbr,
            name=name,
            description=(data.description or "").strip() or None,
            icon=normalize_icon(data.icon),
            url=url,
            sort_order=data.sort_order if data.sort_order is not None else 0,
            created_by=created_by,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        self.db.add(entity)
        await self.db.commit()
        await self.db.refresh(entity)
        return entity

    async def update(
        self, system_id: int, data: LinkedSystemUpdate
    ) -> Optional[LinkedSystem]:
        entity = await self.get_by_id(system_id)
        if not entity or entity.is_deleted:
            return None

        update_data = data.model_dump(exclude_unset=True)

        if "abbr" in update_data and update_data["abbr"] is not None:
            abbr = update_data["abbr"].strip()
            if not abbr:
                raise ValueError("abbr cannot be empty")
            if await self._abbr_taken(abbr, exclude_id=system_id):
                raise ValueError(f"Abbreviation '{abbr}' already exists")
            entity.abbr = abbr

        if "name" in update_data and update_data["name"] is not None:
            name = update_data["name"].strip()
            if not name:
                raise ValueError("name cannot be empty")
            entity.name = name

        if "description" in update_data:
            desc = update_data["description"]
            entity.description = (desc or "").strip() or None

        if "icon" in update_data and update_data["icon"] is not None:
            entity.icon = normalize_icon(update_data["icon"])

        if "url" in update_data and update_data["url"] is not None:
            url = update_data["url"].strip()
            if not url:
                raise ValueError("url cannot be empty")
            entity.url = url

        if "sort_order" in update_data and update_data["sort_order"] is not None:
            entity.sort_order = update_data["sort_order"]

        entity.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(entity)
        return entity

    async def soft_delete(self, system_id: int) -> bool:
        entity = await self.get_by_id(system_id)
        if not entity or entity.is_deleted:
            return False
        entity.is_deleted = True
        entity.updated_at = datetime.utcnow()
        await self.db.commit()
        return True
