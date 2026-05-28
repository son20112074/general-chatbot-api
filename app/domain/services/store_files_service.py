import logging
from datetime import datetime
from typing import List, Optional, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, select, func, or_, update
from app.domain.models.user import User
from app.core.config import settings
from app.domain.models.store import Store
from app.domain.models.file import File
from app.domain.models.store_file import StoreFile
from app.domain.models.shared_store import SharedStore
from app.utils.helpers import build_file_item
from app.infrastructure.services.milvus_cleanup_service import delete_chunks_by_path_async

ADMIN_ROLE_ID = settings.ADMIN_ROLE_ID
logger = logging.getLogger(__name__)


def _escape_like(value: str) -> str:
    """Escape SQL LIKE wildcards to prevent pattern injection."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class StoreFilesService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── access guards ────────────────────────────────────────

    async def _get_active_store(self, store_id: int) -> Store:
        """Fetch a non-deleted store. Raise LookupError if missing."""
        result = await self.db.execute(
            select(Store).where(Store.id == store_id, Store.is_deleted == False)
        )
        s = result.scalar_one_or_none()
        if not s:
            raise LookupError("Store not found")
        return s

    async def _get_store_for_owner(self, store_id: int, current_user_id: int) -> Store:
        """Fetch active store and verify ownership. Raises on missing/forbidden."""
        store = await self._get_active_store(store_id)
        if store.created_by != current_user_id:
            raise PermissionError("You can not modify this store")
        return store

    async def _assert_store_visible(self, store_id: int, current_user_id: int) -> Store:
        """Fetch active store and ensure current user can read it (owner or share)."""
        store = await self._get_active_store(store_id)
        if store.created_by == current_user_id:
            return store
        share_q = select(SharedStore.id).where(
            SharedStore.store_id == store_id,
            SharedStore.user_id == current_user_id,
            SharedStore.is_deleted == False,
        )
        share_row = (await self.db.execute(share_q)).scalar_one_or_none()
        if share_row is None:
            # Don't leak existence — treat as not-found.
            raise LookupError("Store not found")
        return store

    async def _get_active_file(self, file_id: int) -> File:
        """Fetch a non-deleted file. Raises if missing or soft-deleted."""
        result = await self.db.execute(
            select(File).where(File.id == file_id, File.is_deleted == False)
        )
        f = result.scalar_one_or_none()
        if not f:
            raise LookupError("File not found")
        return f

    # ── list ─────────────────────────────────────────────────

    async def get_store_files(
        self,
        skip: int = 0,
        limit: int = 100,
        store_id: Optional[int] = None,
        search: Optional[str] = None,
        current_role_id: Optional[int] = None,
        current_user_id: Optional[int] = None,
    ) -> Dict:
        """List active files in a store. Visible if user owns store or store is shared.

        No `File.type` filter (per spec): share recipient sees ALL files in the store.
        Search by file name / owner name / file summary / file content.
        """
        # Visibility check up-front. Raises LookupError if not visible / not found.
        await self._assert_store_visible(store_id, current_user_id)

        query = (
            select(File, User.id.label("u_id"), User.full_name.label("u_name"))
            .select_from(StoreFile)
            .join(File, StoreFile.file_id == File.id)
            .join(Store, StoreFile.store_id == Store.id)
            .outerjoin(User, File.created_by == User.id)
            .where(
                and_(
                    StoreFile.store_id == store_id,
                    StoreFile.is_deleted == False,
                    File.is_deleted == False,
                )
            )
        )

        count_query = (
            select(func.count())
            .select_from(StoreFile)
            .join(File, StoreFile.file_id == File.id)
            .join(Store, StoreFile.store_id == Store.id)
            .outerjoin(User, File.created_by == User.id)
            .where(
                and_(
                    StoreFile.store_id == store_id,
                    StoreFile.is_deleted == False,
                    File.is_deleted == False,
                )
            )
        )

        if search:
            escaped = _escape_like(search)
            search_filter = or_(
                File.name.ilike(f"%{escaped}%"),
                User.full_name.ilike(f"%{escaped}%"),
                File.summary.ilike(f"%{escaped}%"),
                File.content.ilike(f"%{escaped}%"),
            )
            query = query.where(search_filter)
            count_query = count_query.where(search_filter)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        query = query.order_by(File.created_at.desc()).offset(skip).limit(limit)

        result = await self.db.execute(query)
        files = []
        for f, u_id, u_name in result:
            files.append(build_file_item(f, u_id, u_name))

        return {"data": files, "total": total}

    # ── single add / remove ──────────────────────────────────

    async def add_file_to_store(
        self,
        store_id: int,
        file_id: int,
        current_user_id: int,
    ) -> dict:
        """Owner OR active share recipient: insert (store_id, file_id) or revive existing."""
        await self._assert_store_visible(store_id, current_user_id)
        await self._get_active_file(file_id)

        existing_q = select(StoreFile).where(
            StoreFile.store_id == store_id, StoreFile.file_id == file_id
        )
        existing = (await self.db.execute(existing_q)).scalar_one_or_none()

        if existing is None:
            now = datetime.utcnow()
            sf = StoreFile(
                file_id=file_id,
                store_id=store_id,
                is_deleted=False,
                created_at=now,
                updated_at=now,
            )
            self.db.add(sf)
            await self.db.commit()
            await self.db.refresh(sf)
            return {"id": sf.id, "store_id": store_id, "file_id": file_id, "is_deleted": False}

        existing.is_deleted = False
        existing.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(existing)
        return {"id": existing.id, "store_id": store_id, "file_id": file_id, "is_deleted": False}

    async def remove_file_from_store(
        self,
        store_id: int,
        file_id: int,
        current_user_id: int,
    ) -> dict:
        """Owner OR active share recipient: set is_deleted=True on the (store_id, file_id) record."""
        await self._assert_store_visible(store_id, current_user_id)

        existing_q = select(StoreFile).where(
            StoreFile.store_id == store_id, StoreFile.file_id == file_id
        )
        existing = (await self.db.execute(existing_q)).scalar_one_or_none()
        if existing is None:
            raise LookupError("File is not in this store")

        file_row = (
            await self.db.execute(select(File.path).where(File.id == file_id))
        ).scalar_one_or_none()

        existing.is_deleted = True
        existing.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(existing)

        if file_row:
            try:
                await delete_chunks_by_path_async(file_row)
            except Exception:
                logger.exception(
                    "Milvus cleanup failed after store file remove | store_id=%s file_id=%s path=%s",
                    store_id,
                    file_id,
                    file_row,
                )

        return {"id": existing.id, "store_id": store_id, "file_id": file_id, "is_deleted": True}

    # ── bulk add / remove ────────────────────────────────────

    async def bulk_add_files_to_store(
        self,
        store_id: int,
        file_ids: List[int],
        current_user_id: int,
    ) -> dict:
        """Owner OR active share recipient. Strict pre-check + atomic upsert.

        Steps:
        1. Validate store visibility (owner or active share row).
        2. Validate every file_id exists and is not soft-deleted. If any missing → 400.
        3. Diff existing rows (file_id IN (:ids), store=this) vs requested.
           - missing → INSERT is_deleted=False
           - existing → UPDATE is_deleted=False, updated_at=now
        4. Single transaction. Roll back on any error.
        """
        await self._assert_store_visible(store_id, current_user_id)
        ids = list(dict.fromkeys(int(x) for x in file_ids))  # de-dupe, keep order

        # Pre-check files exist
        files_q = select(File.id).where(File.id.in_(ids), File.is_deleted == False)
        existing_files = {row[0] for row in (await self.db.execute(files_q)).all()}
        missing = [fid for fid in ids if fid not in existing_files]
        if missing:
            raise ValueError(f"File ids not found or deleted: {missing}")

        try:
            existing_q = select(StoreFile).where(
                StoreFile.store_id == store_id,
                StoreFile.file_id.in_(ids),
            )
            existing_rows = list((await self.db.execute(existing_q)).scalars())
            existing_ids = {row.file_id for row in existing_rows}

            now = datetime.utcnow()
            inserted = 0
            updated = 0

            # Insert new pairs
            new_ids = [fid for fid in ids if fid not in existing_ids]
            for fid in new_ids:
                self.db.add(StoreFile(
                    file_id=fid, store_id=store_id, is_deleted=False,
                    created_at=now, updated_at=now,
                ))
                inserted += 1

            # Revive existing pairs
            for row in existing_rows:
                row.is_deleted = False
                row.updated_at = now
                updated += 1

            await self.db.commit()
            return {"inserted": inserted, "updated": updated, "total": inserted + updated}
        except Exception:
            await self.db.rollback()
            raise

    async def bulk_remove_files_from_store(
        self,
        store_id: int,
        file_ids: List[int],
        current_user_id: int,
    ) -> dict:
        """Owner OR active share recipient. Set is_deleted=True for matching rows.

        Atomic. Only flips currently-active rows; missing pairs are silently ignored.
        """
        await self._assert_store_visible(store_id, current_user_id)
        ids = list(dict.fromkeys(int(x) for x in file_ids))

        try:
            paths_q = select(File.id, File.path).where(File.id.in_(ids))
            path_by_file_id = {
                row[0]: row[1] for row in (await self.db.execute(paths_q)).all()
            }

            now = datetime.utcnow()
            stmt = (
                update(StoreFile)
                .where(
                    StoreFile.store_id == store_id,
                    StoreFile.file_id.in_(ids),
                    StoreFile.is_deleted == False,
                )
                .values(is_deleted=True, updated_at=now)
                .execution_options(synchronize_session=False)
            )
            result = await self.db.execute(stmt)
            await self.db.commit()
            updated = result.rowcount or 0

            seen_paths: set[str] = set()
            for fid in ids:
                path = path_by_file_id.get(fid)
                if not path or path in seen_paths:
                    continue
                seen_paths.add(path)
                try:
                    await delete_chunks_by_path_async(path)
                except Exception:
                    logger.exception(
                        "Milvus cleanup failed after bulk store file remove | store_id=%s file_id=%s path=%s",
                        store_id,
                        fid,
                        path,
                    )

            return {"updated": updated, "total": updated}
        except Exception:
            await self.db.rollback()
            raise

