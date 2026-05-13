from datetime import datetime
from typing import List, Optional, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, select, func, or_
from app.domain.models.user import User
from app.core.config import settings
from app.presentation.api.v1.schemas.store import StoreCreate, StoreUpdate, StoreResponse
from app.domain.models.store import Store
from app.domain.models.store_file import StoreFile
from app.domain.models.shared_store import SharedStore  # noqa: F401  (also used in delete guard)

ADMIN_ROLE_ID = settings.ADMIN_ROLE_ID


def _escape_like(value: str) -> str:
    """Escape SQL LIKE wildcards to prevent pattern injection."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class StoreService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── CRUD ─────────────────────────────────────────────────

    async def create_store(self, store_data: StoreCreate, current_user_id: int) -> Store:
        store = Store(
            name=store_data.name,
            description=store_data.description,
            created_by=current_user_id,
            created_at=datetime.utcnow(),
        )
        self.db.add(store)
        await self.db.commit()
        await self.db.refresh(store)
        return store

    async def get_store(self, store_id: int) -> Optional[Store]:
        query = select(Store).where(
            and_(Store.id == store_id, Store.is_deleted == False)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_stores(
        self,
        skip: int = 0,
        limit: int = 100,
        search: Optional[str] = None,
        current_role_id: Optional[int] = None,
        current_user_id: Optional[int] = None,
    ) -> Dict:
        """List stores visible to current user (applies to ALL roles, no admin bypass).

        Visibility:
          - Every caller (including admin) sees only:
            * stores `created_by = current_user`, OR
            * stores actively shared with `current_user` via `shared_store`.
        Search by name or description.
        Each row contains `file_total` (count of `store_files.is_deleted=False`).
        """
        # LEFT JOIN shared_store ONLY for current user (so we can compute is_shared
        # and use it in the visibility WHERE clause).
        share_join_cond = and_(
            SharedStore.store_id == Store.id,
            SharedStore.user_id == current_user_id,
            SharedStore.is_deleted == False,
        )

        is_shared_expr = (SharedStore.id.isnot(None)).label("is_shared")

        # Owner OR shared — enforced for every role including admin.
        visibility = or_(
            Store.created_by == current_user_id,
            SharedStore.id.isnot(None),
        )

        base = (
            select(
                Store,
                User.id.label("u_id"),
                User.full_name.label("u_name"),
                is_shared_expr,
            )
            .outerjoin(User, Store.created_by == User.id)
            .outerjoin(SharedStore, share_join_cond)
            .where(Store.is_deleted == False, visibility)
        )

        count_query = (
            select(func.count())
            .select_from(Store)
            .outerjoin(SharedStore, share_join_cond)
            .where(Store.is_deleted == False, visibility)
        )

        if search:
            escaped = _escape_like(search)
            search_filter = or_(
                Store.name.ilike(f"%{escaped}%"),
                Store.description.ilike(f"%{escaped}%"),
            )
            base = base.where(search_filter)
            count_query = count_query.where(search_filter)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        base = base.order_by(Store.created_at.desc()).offset(skip).limit(limit)

        result = await self.db.execute(base)
        rows = list(result)

        paged_store_ids = [row[0].id for row in rows]
        totals_map: Dict[int, int] = {}
        if paged_store_ids:
            totals_q = (
                select(StoreFile.store_id, func.count(StoreFile.id).label("file_total"))
                .where(
                    StoreFile.store_id.in_(paged_store_ids),
                    StoreFile.is_deleted == False,
                )
                .group_by(StoreFile.store_id)
            )
            totals_result = await self.db.execute(totals_q)
            totals_map = {sid: cnt for sid, cnt in totals_result.all()}

        stores: List[dict] = []
        for store, u_id, u_name, is_shared in rows:
            item = self._build_store_response(store, u_id, u_name)
            item["file_total"] = totals_map.get(store.id, 0)
            item["is_shared"] = bool(is_shared)
            stores.append(item)

        return {"data": stores, "total": total}

    async def update_store(
        self,
        store_id: int,
        data: StoreUpdate,
        current_user_id: int,
    ) -> Optional[Store]:
        """Update store. Owner-only."""
        store = await self.get_store(store_id)
        if not store:
            return None

        if store.created_by != current_user_id:
            raise PermissionError("You can not update this store")

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(store, field, value)

        await self.db.commit()
        await self.db.refresh(store)
        return store

    async def delete_store(self, store_id: int, current_user_id: int) -> bool:
        """Soft-delete: set is_deleted=True. Owner-only.

        A store is only deletable when it is NOT in use elsewhere:
          - no active rows in `store_files`  (is_deleted=False)
          - no active rows in `shared_store` (is_deleted=False)
        Otherwise raises ValueError → router maps to 409.
        """
        store = await self.get_store(store_id)
        if not store:
            return None

        if store.created_by != current_user_id:
            raise PermissionError("You can not delete this store")

        files_used = (await self.db.execute(
            select(func.count())
            .select_from(StoreFile)
            .where(StoreFile.store_id == store_id, StoreFile.is_deleted == False)
        )).scalar_one()
        shares_active = (await self.db.execute(
            select(func.count())
            .select_from(SharedStore)
            .where(SharedStore.store_id == store_id, SharedStore.is_deleted == False)
        )).scalar_one()

        if files_used or shares_active:
            raise ValueError(
                f"Store is in use (files={files_used}, shares={shares_active}). "
                "Remove all files and revoke all shares before deleting."
            )

        store.is_deleted = True
        await self.db.commit()
        return True

    def _build_store_response(self, store, u_id: Optional[int], u_name: Optional[str]) -> dict:
        store_data = {
            column.name: getattr(store, column.name)
            for column in store.__table__.columns
        }
        store_data["owner"] = {"id": u_id, "full_name": u_name} if u_id else None
        return store_data
