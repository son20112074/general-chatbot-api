from datetime import datetime
from typing import List, Optional, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.domain.models.user import User
from app.domain.models.store import Store
from app.domain.models.shared_store import SharedStore


class SharedStoreService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_store_for_owner(self, store_id: int, current_user_id: int) -> Store:
        """Fetch active store and verify ownership. Raises on missing/forbidden."""
        result = await self.db.execute(
            select(Store).where(Store.id == store_id, Store.is_deleted == False)
        )
        store = result.scalar_one_or_none()
        if not store:
            raise LookupError("Store not found")
        if store.created_by != current_user_id:
            raise PermissionError("You can not modify shares of this store")
        return store

    async def sync_shares(
        self,
        store_id: int,
        user_ids: Optional[List[int]],
        current_user_id: int,
    ) -> dict:
        """Owner-only sync of shared_store rows for `store_id`.

        Semantics (per spec):
        - user_ids = None  → no-op. Returns current `total_active`.
        - user_ids = []    → revoke ALL active shares for the store.
        - user_ids = [...] → set the share-list to exactly these users:
            * pairs in payload but not in DB → insert (is_deleted=False)
            * pairs in payload and in DB     → update is_deleted=False
            * pairs in DB but not in payload → set is_deleted=True

        Atomic. Rolls back on any error.
        """
        await self._get_store_for_owner(store_id, current_user_id)

        # No-op path
        if user_ids is None:
            count_q = (
                select(func.count())
                .select_from(SharedStore)
                .where(
                    SharedStore.store_id == store_id,
                    SharedStore.is_deleted == False,
                )
            )
            total_active = (await self.db.execute(count_q)).scalar_one()
            return {"added": 0, "kept": 0, "revoked": 0, "total_active": total_active}

        # Normalise + dedupe
        target_ids: List[int] = list(dict.fromkeys(int(u) for u in user_ids))

        # Validate users exist when payload is non-empty
        if target_ids:
            users_q = select(User.id).where(User.id.in_(target_ids))
            existing_users = {row[0] for row in (await self.db.execute(users_q)).all()}
            missing = [uid for uid in target_ids if uid not in existing_users]
            if missing:
                raise ValueError(f"User ids not found: {missing}")

        try:
            # Load all rows for this store (active + soft-deleted) so we can flip them.
            existing_q = select(SharedStore).where(SharedStore.store_id == store_id)
            existing_rows = list((await self.db.execute(existing_q)).scalars())
            existing_by_uid = {row.user_id: row for row in existing_rows}

            target_set = set(target_ids)
            now = datetime.utcnow()

            added = 0
            kept = 0
            revoked = 0

            # Process target users (insert new, revive existing)
            for uid in target_ids:
                row = existing_by_uid.get(uid)
                if row is None:
                    self.db.add(SharedStore(
                        store_id=store_id,
                        user_id=uid,
                        is_deleted=False,
                        created_at=now,
                        updated_at=now,
                    ))
                    added += 1
                else:
                    if row.is_deleted:
                        row.is_deleted = False
                        row.updated_at = now
                        added += 1
                    else:
                        # Already active; touch updated_at to record the resync.
                        row.updated_at = now
                        kept += 1

            # Revoke active rows whose user_id is not in target_set.
            for row in existing_rows:
                if row.user_id in target_set:
                    continue
                if not row.is_deleted:
                    row.is_deleted = True
                    row.updated_at = now
                    revoked += 1

            await self.db.commit()

            total_active = added + kept  # active after sync = users in target list
            return {
                "added": added,
                "kept": kept,
                "revoked": revoked,
                "total_active": total_active,
            }
        except Exception:
            await self.db.rollback()
            raise
